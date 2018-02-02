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
import datetime
import json
import logging
import os

import aiohttp
import pytest
from aioresponses import aioresponses
from google.oauth2 import _client as oauth_client
from google.oauth2 import service_account

from gordon_janitor_gcp import exceptions
from gordon_janitor_gcp import http_client


API_BASE_URL = 'https://example.com'
API_URL = f'{API_BASE_URL}/v1/foo_endpoint'


@pytest.fixture
def mock_credentials(mocker, monkeypatch):
    mock_creds = mocker.MagicMock(service_account.Credentials, autospec=True)
    sa_creds = mocker.MagicMock(service_account.Credentials, autospec=True)
    sa_creds._make_authorization_grant_assertion.return_value = 'deadb33f=='
    mock_creds.from_service_account_info.return_value = sa_creds

    patch = 'gordon_janitor_gcp.http_client.service_account.Credentials'
    monkeypatch.setattr(patch, mock_creds)
    return mock_creds


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


#####
# Tests for simple client instantiation
#####
args = 'scopes,provide_loop'
params = [
    [['not-a-real-scope'], True],
    [['not-a-real-scope'], False],
    [None, True],
    [None, False],
]


@pytest.mark.parametrize(args, params)
def test_http_client_default(scopes, provide_loop, event_loop, fake_keyfile,
                             fake_keyfile_data, mock_credentials):
    """AIOGoogleHTTPClient is created with expected attributes."""
    loop = None
    if provide_loop:
        loop = event_loop

    client = http_client.AIOGoogleHTTPClient(
        keyfile=fake_keyfile, scopes=scopes, loop=loop
    )
    assert fake_keyfile_data == client._keydata

    if not scopes:
        scopes = ['cloud-platform']
    exp_scopes = [f'https://www.googleapis.com/auth/{s}' for s in scopes]

    assert exp_scopes == client.scopes

    if not provide_loop:
        loop = asyncio.get_event_loop()
    assert loop == client._loop

    assert isinstance(client._session, aiohttp.client.ClientSession)
    assert not client.token
    assert not client.expiry

    client._session.close()


def test_http_client_raises_json(tmpdir, caplog):
    """Client initialization raises when keyfile not valid json."""
    caplog.set_level(logging.DEBUG)

    tmp_keyfile = tmpdir.mkdir('keys').join('broken_keyfile.json')
    tmp_keyfile.write('broken json')

    with pytest.raises(exceptions.GCPGordonJanitorError) as e:
        http_client.AIOGoogleHTTPClient(keyfile=tmp_keyfile)

    e.match(f'Keyfile {tmp_keyfile} is not valid JSON.')
    assert 1 == len(caplog.records)


def test_http_client_raises_not_found(tmpdir, caplog):
    """Client initialization raises when keyfile not found."""
    caplog.set_level(logging.DEBUG)

    tmp_keydir = tmpdir.mkdir('keys')
    no_keyfile = os.path.join(tmp_keydir, 'not-existent.json')

    with pytest.raises(exceptions.GCPGordonJanitorError) as e:
        http_client.AIOGoogleHTTPClient(keyfile=no_keyfile)

    e.match(f'Keyfile {no_keyfile} was not found.')
    assert 1 == len(caplog.records)


#####
# Tests & fixtures for access token handling
#####
@pytest.fixture
def mock_parse_expiry(mocker, monkeypatch):
    mock = mocker.MagicMock(oauth_client, autospec=True)
    mock._parse_expiry.return_value = datetime.datetime(2018, 1, 1, 12, 0, 0)
    monkeypatch.setattr('gordon_janitor_gcp.http_client._client', mock)
    return mock


@pytest.fixture
def client(fake_keyfile, mock_credentials):
    client = http_client.AIOGoogleHTTPClient(keyfile=fake_keyfile)
    yield client
    # test teardown
    client._session.close()


@pytest.mark.asyncio
async def test_refresh_token(client, fake_keyfile_data, mock_parse_expiry,
                             caplog):
    """Successfully refresh access token."""
    caplog.set_level(logging.DEBUG)

    url = fake_keyfile_data['token_uri']
    token = 'c0ffe3'
    payload = {
        'access_token': token,
        'expires_in': 3600,  # seconds = 1hr
    }
    with aioresponses() as mocked:
        mocked.post(url, status=200, payload=payload)
        await client.refresh_token()
    assert token == client.token
    assert 2 == len(caplog.records)


args = 'status,payload,exc,err_msg'
params = [
    [504, None, exceptions.GCPHTTPError, 'Issue connecting to example.com'],
    [200, {}, exceptions.GCPAuthError, 'No access token in response.'],
]


@pytest.mark.parametrize(args, params)
@pytest.mark.asyncio
async def test_refresh_token_raises(status, payload, exc, err_msg, client,
                                    fake_keyfile_data, caplog):
    """Response errors from attempting to refresh token."""
    caplog.set_level(logging.DEBUG)

    url = fake_keyfile_data['token_uri']

    with aioresponses() as mocked:
        mocked.post(url, status=status, payload=payload)
        with pytest.raises(exc) as e:
            await client.refresh_token()

        e.match(err_msg)

    assert 3 == len(caplog.records)


# pytest prevents monkeypatching datetime directly
class MockDatetime(datetime.datetime):
    @classmethod
    def utcnow(cls):
        return datetime.datetime(2018, 1, 1, 11, 30, 0)


args = 'token,expiry,exp_mocked_refresh'
params = [
    # no token - expiry doesn't matter
    [None, datetime.datetime(2018, 1, 1, 9, 30, 0), 1],
    # expired token
    ['0ldc0ffe3', datetime.datetime(2018, 1, 1, 9, 30, 0), 1],
    # token expires within 60 seconds
    ['0ldc0ffe3', datetime.datetime(2018, 1, 1, 11, 29, 30), 1],
    # valid token
    ['0ldc0ffe3', datetime.datetime(2018, 1, 1, 12, 30, 00), 0]
]


@pytest.mark.parametrize(args, params)
@pytest.mark.asyncio
async def test_set_valid_token(client, token, expiry, exp_mocked_refresh,
                               monkeypatch):
    """Refresh tokens if invalid or not set."""
    datetime.datetime = MockDatetime

    mock_refresh_token_called = 0

    async def mock_refresh_token():
        nonlocal mock_refresh_token_called
        mock_refresh_token_called += 1

    client.token = token
    client.expiry = expiry

    monkeypatch.setattr(client, 'refresh_token', mock_refresh_token)

    await client.set_valid_token()
    assert exp_mocked_refresh == mock_refresh_token_called


#####
# Tests & fixtures for HTTP request handling
#####
@pytest.mark.asyncio
async def test_request(client, monkeypatch, caplog):
    """HTTP GET request is successful."""
    caplog.set_level(logging.DEBUG)

    mock_set_valid_token_called = 0

    async def mock_set_valid_token():
        nonlocal mock_set_valid_token_called
        mock_set_valid_token_called += 1

    monkeypatch.setattr(client, 'set_valid_token', mock_set_valid_token)

    resp_text = 'ohai'

    with aioresponses() as mocked:
        mocked.get(API_URL, status=200, body=resp_text)
        resp = await client.request('get', API_URL)

    assert resp == resp_text
    assert 1 == mock_set_valid_token_called
    assert 2 == len(caplog.records)


@pytest.mark.asyncio
async def test_request_refresh(client, monkeypatch, caplog):
    """HTTP GET request is successful while refreshing token."""
    caplog.set_level(logging.DEBUG)

    mock_set_valid_token_called = 0

    async def mock_set_valid_token():
        nonlocal mock_set_valid_token_called
        mock_set_valid_token_called += 1

    monkeypatch.setattr(client, 'set_valid_token', mock_set_valid_token)

    resp_text = 'ohai'

    with aioresponses() as mocked:
        mocked.get(API_URL, status=401)
        mocked.get(API_URL, status=200, body=resp_text)
        resp = await client.request('get', API_URL)

    assert resp == resp_text
    assert 2 == mock_set_valid_token_called
    assert 5 == len(caplog.records)


@pytest.mark.asyncio
async def test_request_max_refresh_reached(client, monkeypatch, caplog):
    """HTTP GET request is not successful from max refresh requests met."""
    caplog.set_level(logging.DEBUG)
    mock_set_valid_token_called = 0

    async def mock_set_valid_token():
        nonlocal mock_set_valid_token_called
        mock_set_valid_token_called += 1

    monkeypatch.setattr(client, 'set_valid_token', mock_set_valid_token)

    with aioresponses() as mocked:
        mocked.get(API_URL, status=401)
        mocked.get(API_URL, status=401)
        mocked.get(API_URL, status=401)
        with pytest.raises(exceptions.GCPHTTPError) as e:
            await client.request('get', API_URL)

        e.match('Issue connecting to example.com:')

    assert 3 == mock_set_valid_token_called
    assert 9 == len(caplog.records)


def simple_json_callback(resp):
    raw_data = json.loads(resp)
    data = {}
    for key, value in raw_data.items():
        data["key"] = key
        data["value"] = value
    return data


args = 'json_func,exp_resp'
params = [
    [None, {'hello': 'world'}],
    [simple_json_callback, {'key': 'hello', 'value': 'world'}],
]


@pytest.mark.parametrize(args, params)
@pytest.mark.asyncio
async def test_get_json(json_func, exp_resp, client, monkeypatch, caplog):
    """HTTP GET request with JSON parsing."""
    caplog.set_level(logging.DEBUG)

    mock_set_valid_token_called = 0

    async def mock_set_valid_token():
        nonlocal mock_set_valid_token_called
        mock_set_valid_token_called += 1

    monkeypatch.setattr(client, 'set_valid_token', mock_set_valid_token)

    resp_json = '{"hello": "world"}'

    with aioresponses() as mocked:
        mocked.get(API_URL, status=200, body=resp_json)
        resp = await client.get_json(API_URL, json_func)

    assert exp_resp == resp
    assert 1 == mock_set_valid_token_called
    assert 2 == len(caplog.records)
