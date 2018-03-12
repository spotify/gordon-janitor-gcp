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

import copy
import logging

import pytest
from aioresponses import aioresponses

from gordon_janitor_gcp.clients import gce


class TestGCEClient:
    @pytest.fixture
    def patch_compute_base_url(self, monkeypatch):
        fake_url = 'http://example.com/compute/'
        class_attribute = 'gordon_janitor_gcp.clients.gce.GCEClient.BASE_URL'
        monkeypatch.setattr(class_attribute, fake_url)
        return fake_url

    @pytest.fixture
    def compute_rsp(self):
        return {
            'kind': 'compute#instanceAggregatedList',
            'id': 'd34dbeef',
            # Simplified Instance resource
            'items': {
                'us-west1-z': {
                    'instances': [{
                        'id': '1',
                        'creationTimestamp': '2018-01-01 00:00:00.0000',
                        'name': 'instance-1',
                        'description': 'guc3-instance-1-54kj',
                        'tags': {
                            'items': ['some-tag'],
                            'fingerprint': ''
                        },
                        'machineType': 'n1-standard-1',
                        'status': 'RUNNING',
                        'statusMessage': 'RUNNING',
                        'zone': 'us-west9-z',
                        'canIpForward': False,
                        'networkInterfaces': [{
                            'network': 'network/url/string',
                            'subnetwork': 'subnetwork/url/string',
                            'networkIP': '192.168.0.1',
                            'name': 'test-network',
                            'accessConfigs': [{
                                'type': 'ONE_TO_ONE_NAT',
                                'name': 'EXTERNAL NAT',
                                'natIP': '1.1.1.1',
                                'kind': 'compute#accessConfig'
                            }],
                        }],
                        'metadata': {
                            'items': [
                                {'key': 'default', 'value': 'true'}
                            ],
                        },
                    }],
                    'warning': {
                        'warning': 'object'
                    }
                }
            },
        }

    @pytest.mark.parametrize('query_str,instance_meta,log_call_count', [
        # test one page of results + zone filter
        ('maxResults=10&filter=zone eq us-west9-z', None, 2),
        # test instance filtering when filtered by tags
        ('maxResults=10&filter=', ['bl-tag'], 3),
        # test instance filtering when filtered by metadata
        ('maxResults=10&filter=', {'key': 'type', 'value': 'c0ffee-b33f'}, 3),
    ])
    @pytest.mark.asyncio
    async def test_list_instances(
            self, compute_rsp, patch_compute_base_url, get_gce_client, caplog,
            query_str, instance_meta, log_call_count):
        """Client uses multiple filters to process results."""
        caplog.set_level(logging.DEBUG)
        gce_client = get_gce_client(gce.GCEClient)

        if instance_meta:
            instance_dict = compute_rsp['items']['us-west1-z']['instances'][0]
            blacklisted_instance = copy.deepcopy(instance_dict)
            blacklisted_instance['name'] = 'instance-2'
            compute_rsp['items']['us-west1-z']['instances'].append(
                blacklisted_instance)

        if isinstance(instance_meta, list):
            blacklisted_instance['tags']['items'] = instance_meta
            gce_client.blacklisted_tags.append(instance_meta[0])
        elif isinstance(instance_meta, dict):
            blacklisted_instance['metadata']['items'].append(instance_meta)
            blacklisted_metadata = {
                instance_meta['key']: instance_meta['value']
            }
            gce_client.blacklisted_metadata.append(blacklisted_metadata)

        with aioresponses() as m:
            filter_url = (f'{patch_compute_base_url}v1/projects/test-project/'
                          f'aggregated/instances?{query_str}')
            m.get(filter_url, payload=compute_rsp)

            kwargs = {}
            if instance_meta is None:
                kwargs = {'instance_filter': query_str[query_str.find('zone'):]}

            results = await gce_client.list_instances(
                'test-project',
                page_size=10,
                **kwargs)

        expected_results = [{
            'hostname': 'instance-1',
            'internal_ip': '192.168.0.1',
            'external_ip': '1.1.1.1'
        }]
        assert expected_results == results
        assert log_call_count == len(caplog.records)

    @pytest.mark.asyncio
    async def test_list_instances_bad_json(
            self, compute_rsp, patch_compute_base_url, get_gce_client, caplog):
        """Client ignores incomplete API replies."""
        gce_client = get_gce_client(gce.GCEClient)
        caplog.set_level(logging.DEBUG)
        del compute_rsp['items']['us-west1-z']['instances'][0]['name']
        with aioresponses() as m:
            filter_url = (f'{patch_compute_base_url}v1/projects/test-project/'
                          'aggregated/instances?maxResults=10')
            m.get(filter_url, payload=compute_rsp)

            results = await gce_client.list_instances(
                'test-project', page_size=10)

        assert [] == results
        assert 3 == len(caplog.records)

    @pytest.mark.asyncio
    async def test_list_instances_retrieves_multiple_pages(
            self, compute_rsp, patch_compute_base_url, get_gce_client, caplog):
        """Client successfully retrieves multiple pages of results from API."""
        gce_client = get_gce_client(gce.GCEClient)
        page2 = copy.deepcopy(compute_rsp)
        page2['items']['us-west1-z']['instances'][0]['name'] = 'instance-2'
        compute_rsp['nextPageToken'] = '123token123'
        with aioresponses() as m:
            filter_url = (f'{patch_compute_base_url}v1/projects/test-project/'
                          'aggregated/instances?maxResults=5')
            m.get(filter_url, payload=compute_rsp)
            url_with_token = (f'{filter_url}&pageToken=123token123')
            m.get(url_with_token, payload=page2)

            results = await gce_client.list_instances(
                'test-project', page_size=5)

        expected_results = [{
            'hostname': 'instance-1',
            'internal_ip': '192.168.0.1',
            'external_ip': '1.1.1.1'
        }]
        expected_results.append(expected_results[0].copy())
        expected_results[1]['hostname'] = 'instance-2'

        assert expected_results == results
        requests = list(m.requests.keys())
        assert 2 == len(requests)
        assert ('get', filter_url) == requests[0]
        assert ('get', url_with_token) == requests[1]
