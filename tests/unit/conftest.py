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
import json

import pytest
from google.oauth2 import service_account


API_BASE_URL = 'https://example.com'
API_URL = f'{API_BASE_URL}/v1/foo_endpoint'


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
