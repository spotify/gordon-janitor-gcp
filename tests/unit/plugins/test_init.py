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

import pytest
from google.api_core import exceptions as google_exceptions

from gordon_janitor_gcp import exceptions
from gordon_janitor_gcp import plugins


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
    client = plugins.get_publisher(config, changes_chnl)

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
        client = plugins.get_publisher(config, changes_chnl)
        client.publisher.create_topic.assert_not_called()

    e.match(exp_msg)
    assert 1 == len(caplog.records)


def test_get_publisher_raises(config, auth_client, publisher_client, caplog,
                              emulator):
    """Raise when there's an issue creating a Google Pub/Sub topic."""
    changes_chnl = asyncio.Queue()
    publisher_client.return_value.create_topic.side_effect = [Exception('fooo')]

    with pytest.raises(exceptions.GCPGordonJanitorError) as e:
        client = plugins.get_publisher(config, changes_chnl)

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
    client = plugins.get_publisher(config, changes_chnl)

    exp_topic = f'projects/{config["project"]}/topics/{short_topic}'
    assert 60 == client.cleanup_timeout
    assert client.publisher is not None
    assert not client._messages
    assert exp_topic == client.topic

    client.publisher.create_topic.assert_called_once_with(exp_topic)
