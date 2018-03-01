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
"""
Module for reusable pytest fixtures.
"""

import datetime
import json
import logging

import aiohttp
import pytest
from google.cloud import pubsub

from gordon_janitor_gcp.clients import auth

API_BASE_URL = 'https://example.com'
API_URL = f'{API_BASE_URL}/v1/foo_endpoint'


@pytest.fixture
def fake_response_data():
    return {
        'rrsets': [
            {
                'name': 'a-test.example.net.',
                'type': 'A',
                'ttl': 300,
                'rrdatas': [
                    '10.1.2.3',
                ]
            }, {
                'name': 'b-test.example.net.',
                'type': 'CNAME',
                'ttl': 600,
                'rrdatas': [
                    'a-test.example.net.',
                ]
            }, {
                'name': 'c-test.example.net.',
                'type': 'TXT',
                'ttl': 300,
                'rrdatas': [
                    '"OHAI"',
                    '"OYE"',
                ]
            }
        ]
    }


@pytest.fixture
def caplog(caplog):
    """Set global test logging levels."""
    caplog.set_level(logging.DEBUG)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    return caplog


@pytest.fixture
def fake_keyfile_data():
    return {
        'type': 'service_account',
        'project_id': 'a-test-project',
        'private_key_id': 'yeahright',
        'private_key': 'nope',
        'client_email': 'test-key@a-test-project.iam.gserviceaccount.com',
        'client_id': '12345678910',
        'auth_uri': f'{API_BASE_URL}/auth',
        'token_uri': f'{API_BASE_URL}/token',
        'auth_provider_x509_cert_url': f'{API_BASE_URL}/certs',
        'client_x509_cert_url': f'{API_BASE_URL}/x509/a-test-project'
    }


@pytest.fixture
def fake_keyfile(fake_keyfile_data, tmpdir):
    tmp_keyfile = tmpdir.mkdir('keys').join('fake_keyfile.json')
    tmp_keyfile.write(json.dumps(fake_keyfile_data))
    return tmp_keyfile


# pytest prevents monkeypatching datetime directly
class MockDatetime(datetime.datetime):
    @classmethod
    def utcnow(cls):
        return datetime.datetime(2018, 1, 1, 11, 30, 0)


@pytest.fixture
def config(fake_keyfile):
    return {
        'keyfile': fake_keyfile,
        'project': 'test-example',
        'topic': 'a-topic'
    }


@pytest.fixture
def auth_client(mocker, monkeypatch):
    mock = mocker.Mock(auth.GAuthClient, autospec=True)
    mock.token = '0ldc0ffe3'
    mock._session = aiohttp.ClientSession()
    creds = mocker.Mock()
    mock.creds = creds
    monkeypatch.setattr(
        'gordon_janitor_gcp.plugins.publisher.auth.GAuthClient', mock)
    yield mock
    mock._session.close()


@pytest.fixture
def mock_coro(mocker):
    mock = mocker.Mock()

    async def _coro(*args, **kwargs):
        return mock(*args, **kwargs)

    return mock, _coro


async def _noop():
    pass


@pytest.fixture
def get_gce_client(mocker, auth_client):
    client = None

    def _create_client(klass, *args, **kwargs):
        nonlocal client
        client = klass(auth_client, *args, **kwargs)
        mocker.patch.object(client, 'set_valid_token', _noop)
        return client
    return _create_client


@pytest.fixture
def publisher_client(mocker, monkeypatch):
    mock = mocker.Mock(pubsub.PublisherClient, autospec=True)
    patch = 'gordon_janitor_gcp.plugins.publisher.pubsub.PublisherClient'
    monkeypatch.setattr(patch, mock)
    return mock
