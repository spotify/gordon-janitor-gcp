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

import pytest

from gordon_janitor_gcp import msg_generators


#####
# Tests and fixture for MsgGeneratorBase
#####

@pytest.mark.parametrize('method', ['generate_msg', 'generate_batch'])
@pytest.mark.asyncio
async def test_method_not_implemented(method):
    generator = msg_generators.MsgGeneratorBase()
    with pytest.raises(NotImplementedError):
        await getattr(generator, method)('data')


#####
# Tests and fixture for ARecordMsgGenerator
#####
@pytest.mark.asyncio
async def test_generate_msg():
    """Object creates a well-formed message for a single host."""
    generator = msg_generators.ARecordMsgGenerator('zone-1')

    instance_data = {'hostname': 'instance-1', 'internal_ip': '192.168.1.1'}

    result = await generator.generate_msg(instance_data)
    expected = {
        'name': instance_data['hostname'],
        'rrdatas': [instance_data['internal_ip']],
        'type': 'A'
    }
    assert result == expected


@pytest.mark.asyncio
async def test_generate_batch():
    """Creates a well-formed dict with multiple message."""
    generator = msg_generators.ARecordMsgGenerator('zone-1')
    instance_data = {'hostname': 'instance-1', 'internal_ip': '192.168.1.1'}
    results = await generator.generate_batch(
        [instance_data, instance_data.copy()])

    expected = {
        'zone':
        'zone-1',
        'rrsets': [{
            'name': instance_data['hostname'],
            'rrdatas': [instance_data['internal_ip']],
            'type': 'A'
        }, {
            'name': instance_data['hostname'],
            'rrdatas': [instance_data['internal_ip']],
            'type': 'A'
        }]
    }

    assert results == expected
