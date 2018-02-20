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

from gordon_janitor_gcp import gce_clients
from gordon_janitor_gcp import gce_instance_authority
from gordon_janitor_gcp import msg_generators


def echoing_helper_coro(data):
    async def _coro():
        return data
    return _coro()


@pytest.fixture
def authority_config():
    return {
        'keyfile': 'b33fc0ffee',
        'metadata_blacklist': [],
        'project_blacklist': [],
        'tag_blacklist': [],
        'zone': 'zone1',
    }


@pytest.fixture
def authority(mocker, monkeypatch, authority_config, fake_auth_client):
    monkeypatch.setattr(
        'gordon_janitor_gcp.gce_instance_authority.auth.GoogleAuthClient',
        mocker.Mock(return_value=fake_auth_client))
    rrset_channel = asyncio.Queue()
    authority = gce_instance_authority.GCEInstanceAuthority(
        authority_config, rrset_channel)
    authority.session = fake_auth_client._session
    return authority


@pytest.fixture
def get_mock_client(mocker, get_gce_client):
    def _create_fake(klass, *args, **kwargs):
        client = get_gce_client(klass, *args, **kwargs)
        fake_client = mocker.Mock(client)
        return fake_client
    return _create_fake


@pytest.mark.asyncio
async def test_start_publishes_msg_to_channel(mocker, authority_config):
    instance_data = [{
        'hostname': f'host-{i}',
        'internal_ip': f'192.168.1.{i}',
        'external_ip': f'1.1.1.{i}'
    } for i in range(1, 4)]

    class SimpleAuthority(gce_instance_authority.GCEInstanceAuthority):
        async def get_all_projects(self):
            return {'project-1', 'project-2'}

        async def get_instances_for_projects(self, projects):
            for project in projects:
                yield instance_data.copy()

        async def get_msg_generator(self):
            async def _batch(self):
                return instance_data.copy()

            generator = mocker.Mock()
            generator.generate_batch.side_effect = _batch
            return generator

    rrset_channel = asyncio.Queue()
    authority = SimpleAuthority(authority_config, rrset_channel)

    await authority.start()

    # one message per each project
    assert (await rrset_channel.get()) == instance_data.copy()
    assert (await rrset_channel.get()) == instance_data.copy()
    assert (await rrset_channel.get()) is None


@pytest.mark.asyncio
async def test_get_all_projects_gets_set_of_ids(mocker, authority,
                                                get_mock_client):
    crm_client = get_mock_client(gce_clients.CRMClient)
    project_data = [{'projectId': f'project-{i}'} for i in range(3)]
    coro = echoing_helper_coro(project_data)

    crm_client.list_all_active_projects.return_value = coro
    mocker.patch(
        ('gordon_janitor_gcp.gce_instance_authority'
         '.gce_clients.CRMClient'),
        mocker.Mock(return_value=crm_client))

    projects = await authority.get_all_projects()

    assert projects == {p['projectId'] for p in project_data}


@pytest.mark.asyncio
async def test_get_processes_projects(mocker, authority,
                                      get_mock_client):
    crm_client = get_mock_client(gce_clients.CRMClient)

    authority.config['project_blacklist'].append('project-0')
    project_data = [{'projectId': f'project-{i}'} for i in range(3)]
    coro = echoing_helper_coro(project_data)

    crm_client.list_all_active_projects.return_value = coro
    mocker.patch(
        ('gordon_janitor_gcp.gce_instance_authority'
         '.gce_clients.CRMClient'),
        mocker.Mock(return_value=crm_client))

    projects = await authority.get_processed_projects()

    assert projects == [p['projectId'] for p in project_data[1:]]


@pytest.mark.asyncio()
async def test_get_default_filter_is_empty(authority):
    instance_filter = await authority.get_instance_filter()
    assert instance_filter == ''


@pytest.mark.asyncio
async def test_get_instances_for_projects_yields_instances(
        mocker, authority, get_mock_client):
    gcp_client = get_mock_client(gce_clients.GCPClient)
    instance_data = [{
        'hostname': f'host-{i}',
        'internal_ip': f'192.168.1.{i}',
        'external_ip': f'1.1.1.{i}'
    } for i in range(1, 4)]

    gcp_client.list_instances.side_effect = [
        echoing_helper_coro(instance_data),
        echoing_helper_coro(instance_data)
    ]
    mocker.patch(
        ('gordon_janitor_gcp.gce_instance_authority'
         '.gce_clients.GCPClient'),
        mocker.Mock(return_value=gcp_client))

    async for instances in authority.get_instances_for_projects(
            ['project-1', 'project-2']):
        assert instances == instance_data
    gcp_client.list_instances.assert_has_calls([
        mocker.call('project-1', instance_filter=''),
        mocker.call('project-2', instance_filter='')])


@pytest.mark.asyncio
async def test_get_msg_generator_returns_a_record_gen(authority):
    generator = await authority.get_msg_generator()
    assert isinstance(generator, msg_generators.ARecordMsgGenerator)
