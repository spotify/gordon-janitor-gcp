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
Client classes to retrieve project and instance data from GCE.

These clients use the asynchronous HTTP client defined in
:py:mod:`gordon_janitor_gcp.http_client` and require service account or
JWT-token credentials for authentication.

To use:

.. code-block:: python

    import asyncio

    import aiohttp

    from gordon_janitor_gcp import auth

    loop = asyncio.get_event_loop()

    async def main():
        session = aiohttp.ClientSession()
        loop = asyncio.get_event_loop()
        auth_client = auth.GoogleAuthClient(k
            eyfile='/path/to/keyfile', session=session)
        client = GCPClient(auth_client, session)
        instances = await client.list_instances('project-id')
        print(instances)

    loop.run_until_complete(main())
    # example output
    # [{'hostname': 'instance-1', 'internal_ip': '10.10.10.10',
    #   'external_ip': '192.168.1.10'}]
"""

import logging

from gordon_janitor_gcp import http_client


class CRMClient(http_client.AIOGoogleHTTPClient,
                http_client.PagingGoogleClientMixin):
    """Async client to interact with Google Cloud Resource Manager API.

    API endpoint documentation:
    https://cloud.google.com/resource-manager/reference/rest/#rest-resource-v1projects

    Attributes:
        BASE_URL (str): Base endpoint URL.

    Args:
        auth_client (gordon_janitor_gcp.auth.GoogleAuthClient): client
            to manage authentication for HTTP API requests.
        session (aiohttp.ClientSession): (optional) ``aiohttp`` HTTP
            session to use for sending requests. Defaults to the
            session object attached to ``auth_client`` if not provided.
    """
    BASE_URL = 'https://cloudresourcemanager.googleapis.com'

    def __init__(self, auth_client=None, session=None):
        super().__init__(auth_client=auth_client, session=session)

    def parse_response_into_items(self, response, items):
        """Parse API response for all active projects into a list.

        Args:
            response (dict): CRM API endpoint response data.
            items (list): list for collecting parsed results.
        """
        projects = response.get('projects', [])
        for project in projects:
            if project.get('lifecycleState', '').lower() == 'active':
                items.append(project)

    async def list_all_active_projects(self,
                                       page_size=1000,
                                       retries=3,
                                       retry_wait=5):
        """Get all active projects.

        Endpoint documentation:
        https://cloud.google.com/resource-manager/reference/rest/v1/projects/list

        Args:
            page_size (int): hint for the client to only retrieve up to this
                number of results per API call.
            retries (int): number of times to retry request on 4xx/5xx errors.
            retry_wait (int): seconds to wait between retries.
        Returns:
            list: list of dicts of all active projects.
        """
        url = f'{self.BASE_URL}/v1/projects'
        params = {'pageSize': page_size}

        return await self.list_all_items(url, params, retries, retry_wait)


class GCPClient(http_client.AIOGoogleHTTPClient,
                http_client.PagingGoogleClientMixin):
    """Async client to interact with Google Cloud Compute API.

    Attributes:
        BASE_URL (str): base compute endpoint URL.

    Args:
        auth_client (gordon_janitor_gcp.auth.GoogleAuthClient): client
            to manage authentication for HTTP API requests.
        session (aiohttp.ClientSession): (optional) ``aiohttp`` HTTP
            session to use for sending requests. Defaults to the
            session object attached to ``auth_client`` if not provided.
        blacklisted_tags (list): Do not collect an instance if it has been
            tagged with any of these.
        blacklisted_metadata (list): Do not collect an instance if its metadata
            key:val matches a {key:val} dict in this list.
    """
    BASE_URL = 'https://www.googleapis.com/compute/v1/projects'

    def __init__(self,
                 auth_client=None,
                 session=None,
                 blacklisted_tags=None,
                 blacklisted_metadata=None):
        super().__init__(auth_client=auth_client, session=session)
        self.blacklisted_tags = blacklisted_tags or []
        self.blacklisted_metadata = blacklisted_metadata or []

    async def list_instances(self,
                             project,
                             page_size=500,
                             instance_filter=None,
                             retries=3,
                             retry_wait=5):
        """Fetch all instances in a GCE project.

        Endpoint documentation:
        https://cloud.google.com/compute/docs/reference/latest/instances/aggregatedList

        Args:
            project (str): unique, user-provided project ID.
            page_size (int): hint for the client to only retrieve up to this
                number of results per API call.
            instance_filter (str): endpoint-specific filter string used to
                retrieve a subset of instances. This is passed directly to the
                endpoint's "filter" URL query parameter.
        Returns:
            list: dicts containing instance data.
        """
        url = f'{self.BASE_URL}/{project}/aggregated/instances'
        params = {'maxResults': page_size}
        if instance_filter:
            params['filter'] = instance_filter

        return await self.list_all_items(url, params, retries, retry_wait)

    def parse_response_into_items(self, response, items):
        """Parse API response for all instances in a project into a list.

        Args:
            response (dict): endpoint response data.
            items (list): list for collecting parsed results.
        """
        zones = response.get('items', {})
        for zone in zones.values():
            for instance in zone.get('instances', []):
                if not any([
                        self._blacklisted_by_tag(instance),
                        self._blacklisted_by_metadata(instance)
                ]):
                    try:
                        items.append(self._extract_instance_data(instance))
                    except KeyError as e:
                        logging.info(
                            'Could not extract instance information for '
                            f'{instance} because of missing key {e}, skipping.')

    def _extract_instance_data(self, instance):
        iface_data = instance['networkInterfaces'][0]
        return {
            'hostname': instance['name'],
            'internal_ip': iface_data['networkIP'],
            'external_ip': iface_data['accessConfigs'][0]['natIP'],
        }

    def _blacklisted_by_tag(self, instance):
        """Check if instance has any blacklisted tags.

        Args:
            instance (dict): instance data as returned by API.
        Return:
            bool: if instance has any blacklisted tag.
        """
        instance_tags = instance.get('tags', {}).get('items', [])
        for tag in instance_tags:
            if tag in self.blacklisted_tags:
                msg = (f'Instance "{instance["name"]}" filtered out for '
                       f'blacklisted tag: "{tag}"')
                logging.info(msg)
                return True
        return False

    def _blacklisted_by_metadata(self, instance):
        """Check if instance has any blacklisted metadata.

        NOTE: Both key and value are used when comparing the instance and
        blacklist metadata.

        Args:
            instance (dict): instance data as returned by API.
        Return:
            bool: if instance has blacklisted metadata.
        """
        instance_metadata = instance.get('metadata', {}).get('items', [])
        for metadata in instance_metadata:
            for bl_meta in self.blacklisted_metadata:
                if bl_meta.get(metadata['key']) == metadata['value']:
                    msg = (f'Instance "{instance["name"]}" filtered out for '
                           f'blacklisted metadata: "{bl_meta}"')
                    logging.info(msg)
                    return True
        return False
