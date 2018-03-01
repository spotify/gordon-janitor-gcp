# -*- coding: utf-8 -*-
#
# Copyright 2018 Spotify AB
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import concurrent.futures
import datetime
import json
import logging

import pytest
from google.api_core import exceptions as google_exceptions
from google.cloud import pubsub

from gordon_janitor_gcp import exceptions
from gordon_janitor_gcp.plugins import publisher
from tests.unit import conftest


@pytest.fixture
def publisher_client(mocker, monkeypatch):
    mock = mocker.Mock(pubsub.PublisherClient, autospec=True)
    patch = 'gordon_janitor_gcp.plugins.publisher.pubsub.PublisherClient'
    monkeypatch.setattr(patch, mock)
    return mock


@pytest.fixture
def kwargs(config, publisher_client):
    return {
        'config': config,
        'publisher': publisher_client,
        'changes_channel': asyncio.Queue()
    }


@pytest.mark.parametrize('exp_log_records,timeout,side_effect', [
    # tasks did not complete before timeout
    [2, 0, (False, False)],
    # tasks completed
    [1, 1, (False, True)],
    # tasks completed before timeout
    [1, 1, (False, False, True)],
])
@pytest.mark.asyncio
async def test_done(exp_log_records, timeout, side_effect, kwargs,
                    publisher_client, auth_client, caplog, mocker,
                    monkeypatch):
    """Proper cleanup with or without pending tasks."""
    caplog.set_level(logging.DEBUG)

    mock_msg1 = mocker.Mock(concurrent.futures.Future, autospec=True)
    mock_msg2 = mocker.Mock(concurrent.futures.Future, autospec=True)

    if side_effect:
        mock_msg1.done.side_effect = side_effect
        mock_msg2.done.side_effect = side_effect

    kwargs['config']['cleanup_timeout'] = timeout
    client = publisher.GPubsubPublisher(**kwargs)
    client._messages.add(mock_msg1)
    client._messages.add(mock_msg2)

    await client.done()

    assert exp_log_records == len(caplog.records)
    if exp_log_records == 2:
        mock_msg1.cancel.assert_called_once()
        mock_msg2.cancel.assert_called_once()

    assert 0 == client.changes_channel.qsize()


@pytest.mark.asyncio
async def test_publish(kwargs, publisher_client, auth_client, mocker,
                       monkeypatch):
    """Publish received messages."""
    datetime.datetime = conftest.MockDatetime

    topic = kwargs['config']['topic']
    project = kwargs['config']['project']
    exp_topic = f'projects/{project}/topics/{topic}'
    kwargs['config']['topic'] = exp_topic

    client = publisher.GPubsubPublisher(**kwargs)

    msg1 = {'message': 'one'}

    await client.publish(msg1)

    msg1['timestamp'] = datetime.datetime.utcnow().isoformat()
    bytes_msg1 = bytes(json.dumps(msg1), encoding='utf-8')

    publisher_client.publish.assert_called_once_with(exp_topic, bytes_msg1)
    assert 1 == len(client._messages)


@pytest.mark.parametrize('raises,exp_log_records', [
    [False, 1],
    [Exception('foo'), 2],
])
@pytest.mark.asyncio
async def test_start(raises, exp_log_records, kwargs, publisher_client,
                     auth_client, mocker, monkeypatch, caplog):
    """Start consuming the changes channel queue."""
    caplog.set_level(logging.DEBUG)

    if raises:
        publisher_client.publish.side_effect = [Exception('foo')]

    msg1 = {'message': 'one'}
    await kwargs['changes_channel'].put(msg1)
    await kwargs['changes_channel'].put(None)

    client = publisher.GPubsubPublisher(**kwargs)
    await client.start()

    publisher_client.publish.assert_called_once()
    assert exp_log_records == len(caplog.records)


@pytest.fixture
def emulator(monkeypatch):
    monkeypatch.delenv('PUBSUB_EMULATOR_HOST', raising=False)


@pytest.mark.parametrize('local,timeout,exp_timeout,topic', [
    (True, None, 60, 'a-topic'),
    (False, 30, 30, 'projects/test-example/topics/a-topic'),
])
def test_get_publisher(local, timeout, exp_timeout, topic, config,
                       auth_client, publisher_client, emulator, monkeypatch):
    """Happy path to initialize a Publisher client."""
    changes_chnl = asyncio.Queue()

    if local:
        monkeypatch.setenv('PUBSUB_EMULATOR_HOST', True)

    if timeout:
        config['cleanup_timeout'] = timeout

    config['topic'] = topic
    client = publisher.get_publisher(config, changes_chnl)

    topic = topic.split('/')[-1]
    exp_topic = f'projects/{config["project"]}/topics/{topic}'
    assert exp_timeout == client.cleanup_timeout
    assert client.publisher is not None
    assert not client._messages

    client.publisher.create_topic.assert_called_once_with(exp_topic)


@pytest.mark.parametrize('config_key,exp_msg',  [
    ('keyfile', 'The path to a Service Account JSON keyfile is required '),
    ('project', 'The GCP project where Cloud Pub/Sub is located is required.'),
    ('topic', ('A topic for the client to publish to in Cloud Pub/Sub is '
               'required.')),
])
def test_get_publisher_config_raises(config_key, exp_msg, config, auth_client,
                                     publisher_client, caplog, emulator):
    """Raise with improper configuration."""
    changes_chnl = asyncio.Queue()
    config.pop(config_key)

    with pytest.raises(exceptions.GCPConfigError) as e:
        client = publisher.get_publisher(config, changes_chnl)
        client.publisher.create_topic.assert_not_called()

    e.match(exp_msg)
    assert 1 == len(caplog.records)


def test_get_publisher_raises(config, auth_client, publisher_client, caplog,
                              emulator):
    """Raise when there's an issue creating a Google Pub/Sub topic."""
    changes_chnl = asyncio.Queue()
    publisher_client.return_value.create_topic.side_effect = [Exception('fooo')]

    with pytest.raises(exceptions.GCPGordonJanitorError) as e:
        client = publisher.get_publisher(config, changes_chnl)

        client.publisher.create_topic.assert_called_once_with(client.topic)
        e.match(f'Error trying to create topic "{client.topic}"')

    assert 1 == len(caplog.records)


def test_get_publisher_topic_exists(config, auth_client, publisher_client,
                                    emulator):
    """Do not raise if topic already exists."""
    changes_chnl = asyncio.Queue()
    exp = google_exceptions.AlreadyExists('foo')
    publisher_client.return_value.create_topic.side_effect = [exp]

    short_topic = config['topic']
    client = publisher.get_publisher(config, changes_chnl)

    exp_topic = f'projects/{config["project"]}/topics/{short_topic}'
    assert 60 == client.cleanup_timeout
    assert client.publisher is not None
    assert not client._messages
    assert exp_topic == client.topic

    client.publisher.create_topic.assert_called_once_with(exp_topic)
