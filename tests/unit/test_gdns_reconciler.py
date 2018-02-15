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

from gordon_janitor_gcp import auth
from gordon_janitor_gcp import exceptions
from gordon_janitor_gcp import gdns_client
from gordon_janitor_gcp import gdns_reconciler as reconciler


@pytest.fixture
def minimal_config(fake_keyfile):
    return {
        'keyfile': fake_keyfile,
        'scopes': ['my-awesome-scope'],
        'project': 'a-project',
    }


@pytest.fixture
def full_config(minimal_config):
    minimal_config['api_version'] = 'zeta'
    return minimal_config


@pytest.fixture
def dns_client(mocker, monkeypatch):
    mock = mocker.Mock(gdns_client.AIOGoogleDNSClient, autospec=True)
    mock._session = mocker.Mock()
    mock._session.close.return_value = True
    monkeypatch.setattr(
        'gordon_janitor_gcp.gdns_client.AIOGoogleDNSClient', mock)
    return mock


@pytest.fixture
def config(fake_keyfile):
    return {
        'keyfile': fake_keyfile,
        'project': 'test-example',
        'scopes': ['a-scope'],
    }


@pytest.fixture
def auth_client(mocker, monkeypatch):
    mock = mocker.Mock(auth.GoogleAuthClient, autospec=True)
    monkeypatch.setattr(
        'gordon_janitor_gcp.gdns_reconciler.auth.GoogleAuthClient', mock)
    return mock


args = 'timeout,exp_timeout'
params = [
    (None, 60),
    (30, 30),
]


@pytest.mark.parametrize(args, params)
def test_reconciler_default(timeout, exp_timeout, config, auth_client):
    rrset_chnl, changes_chnl = asyncio.Queue(), asyncio.Queue()

    if timeout:
        config['cleanup_timeout'] = timeout

    recon_client = reconciler.GoogleDNSReconciler(
        config, rrset_chnl, changes_chnl)
    assert exp_timeout == recon_client.cleanup_timeout
    assert recon_client.dns_client is not None
    assert config is recon_client.config


args = 'config_key,exp_msg'
params = [
    ('keyfile', 'The path to a Service Account JSON keyfile is required '),
    ('project', 'The GCP project where Cloud DNS is located is required.')
]


@pytest.mark.parametrize(args, params)
def test_reconciler_default_raises(config_key, exp_msg, auth_client, config,
                                   caplog):
    config.pop(config_key)
    rrset_chnl, changes_chnl = asyncio.Queue(), asyncio.Queue()

    with pytest.raises(exceptions.GCPConfigError) as e:
        reconciler.GoogleDNSReconciler(config, rrset_chnl, changes_chnl)

    e.match(exp_msg)
    assert 1 == len(caplog.records)


@pytest.fixture
async def recon_client(config, auth_client):
    rch, chch = asyncio.Queue(), asyncio.Queue()
    recon_client = reconciler.GoogleDNSReconciler(config, rch, chch)
    yield recon_client
    while not chch.empty():
        await chch.get()


args = 'exp_log_records,timeout'
params = [
    # tasks did not complete before timeout
    [2, 0],
    # tasks completed before timeout
    [1, 1],
]


@pytest.mark.parametrize(args, params)
@pytest.mark.asyncio
async def test_done(exp_log_records, timeout, recon_client, caplog, mocker,
                    monkeypatch):
    """Proper cleanup with or without pending tasks."""
    recon_client.cleanup_timeout = timeout

    # mocked methods names must match those in reconciler._ASYNC_METHODS
    async def publish_change_messages():
        await asyncio.sleep(0)

    async def validate_rrsets_by_zone():
        await asyncio.sleep(0)

    coro1 = asyncio.ensure_future(publish_change_messages())
    coro2 = asyncio.ensure_future(validate_rrsets_by_zone())

    mock_task = mocker.MagicMock(asyncio.Task, autospec=True)
    mock_task.all_tasks.side_effect = [
        # in the `while iterations` loop twice
        # timeout of `0` will never hit this loop
        [coro1, coro2],
        [coro1.done(), coro2.done()]
    ]
    monkeypatch.setattr(
        'gordon_janitor_gcp.gdns_reconciler.asyncio.Task', mock_task)

    await recon_client.done()

    assert exp_log_records == len(caplog.records)
    if exp_log_records == 2:
        # it's in a cancelling state which can't be directly tested
        assert not coro1.done()
        assert not coro2.done()
    else:
        assert coro1.done()
        assert coro2.done()

    assert 1 == recon_client.changes_channel.qsize()


@pytest.mark.asyncio
async def test_publish_change_messages(recon_client, fake_response_data,
                                       caplog):
    """Publish message to changes queue."""
    rrsets = fake_response_data['rrsets']
    desired_rrsets = [gdns_client.GCPResourceRecordSet(**kw) for kw in rrsets]

    await recon_client.publish_change_messages(desired_rrsets)

    assert 3 == recon_client.changes_channel.qsize()
    assert 4 == len(caplog.records)


@pytest.mark.asyncio
async def test_validate_rrsets_by_zone(recon_client, fake_response_data, caplog,
                                       monkeypatch):
    """A difference is detected and a change message is published."""
    rrsets = fake_response_data['rrsets']

    mock_get_records_for_zone_called = 0

    async def mock_get_records_for_zone(*args, **kwargs):
        nonlocal mock_get_records_for_zone_called
        mock_get_records_for_zone_called += 1
        rrsets = fake_response_data['rrsets']
        rrsets[0]['rrdatas'] = ['10.4.5.6']
        return [
            gdns_client.GCPResourceRecordSet(**kw) for kw in rrsets
        ]

    monkeypatch.setattr(
        recon_client.dns_client, 'get_records_for_zone',
        mock_get_records_for_zone
    )

    await recon_client.validate_rrsets_by_zone('example.net.', rrsets)

    assert 1 == recon_client.changes_channel.qsize()
    assert 3 == len(caplog.records)
    assert 1 == mock_get_records_for_zone_called


args = 'msg,exp_log_records,exp_mock_calls'
params = [
    # happy path
    [{'zone': 'example.net.', 'rrsets': []}, 1, 1],
    # no rrsets key
    [{'zone': 'example.net.'}, 3, 0],
    # no zone key
    [{'rrsets': []}, 3, 0],
]


@pytest.mark.asyncio
@pytest.mark.parametrize(args, params)
async def test_start(msg, exp_log_records, exp_mock_calls, caplog, recon_client,
                     monkeypatch):
    """Start reconciler & continue if certain errors are raised."""
    mock_validate_rrsets_by_zone_called = 0

    async def mock_validate_rrsets_by_zone(*args, **kwargs):
        nonlocal mock_validate_rrsets_by_zone_called
        mock_validate_rrsets_by_zone_called += 1
        await asyncio.sleep(0)

    monkeypatch.setattr(
        recon_client, 'validate_rrsets_by_zone', mock_validate_rrsets_by_zone)

    await recon_client.rrset_channel.put(msg)
    await recon_client.rrset_channel.put(None)

    await recon_client.start()

    assert exp_log_records == len(caplog.records)
    assert exp_mock_calls == mock_validate_rrsets_by_zone_called
