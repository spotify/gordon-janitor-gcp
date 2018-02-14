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

import logging

import pytest  # NOQA


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
