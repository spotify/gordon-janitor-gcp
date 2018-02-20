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
A GCEInstanceAuthority object retrieves a list of all instances in all
projects that the ``keyfile`` gives it access to. It is meant to work
in an asynchronous context and to be executed through the ``start()`` method.

It is also meant to be easy to extend and customize so all methods except
``start`` can be overridden as long as they follow the interfaces over the
base methods. For example, if a different project filtering scheme is to be
used, it's possible to inherit from GCEInstanceAuthority and override
the ``get_all_projects`` method and ensure it returns a set of project IDs.

To use:

.. code-block:: pycon

    >>> import asyncio
    >>> rrset_channel = asyncio.Queue()
    >>> authority = GCEInstanceAuthority(config, rrset_channel)
    >>> await authority.start()
    >>> msg = await.channel.get()
    >>> print(msg)
    {'zone': 'us-central1-b', 'resourceRecords': [...]}
"""

import aiohttp

from gordon_janitor_gcp import auth
from gordon_janitor_gcp import gce_clients
from gordon_janitor_gcp import msg_generators


class GCEInstanceAuthority:
    """Gordon-Janitor plugin that gathers "state of truth" GCE instance data.

    Args:
        config (dict): Plugin-specific configuration.
        rrset_channel (asyncio.Queue): channel to receive instance data
            messages.
    """
    def __init__(self, config, rrset_channel=None, **kwargs):
        self.config = config
        self.keyfile = self.config['keyfile']
        self.rrset_channel = rrset_channel

    async def get_all_projects(self):
        """Get all active GCE projects.

        Returns:
            set: active GCE project IDs.
        """
        auth_client = auth.GoogleAuthClient(
            self.keyfile,
            scopes=['cloud-platform.read-only'],
            session=self.session)
        crm_client = gce_clients.CRMClient(auth_client, self.session)

        active_projects = await crm_client.list_all_active_projects()
        return set(p.get('projectId') for p in active_projects)

    async def get_processed_projects(self):
        """Get list of GCE project IDs with blacklisted ones filtered out.

        Returns:
            list: project IDs.
        """
        projects = await self.get_all_projects()
        project_blacklist = set(self.config['project_blacklist'])
        return sorted(projects - project_blacklist)

    async def get_instance_filter(self):
        """Get filter string used by instances.aggregatedList endpoint.

        For filter string details, see api endpoint documentation:
        https://cloud.google.com/compute/docs/reference/latest/instances/aggregatedList

        Returns:
            str: filter suitable for the 'filter' endpoint parameter.
        """
        return ''

    async def get_instances_for_projects(self, projects):
        """Get list of instance data for each project.

        Args:
            projects (list): list of project names.
        Yields:
            list: list of dicts that contain instance information.
        """
        tag_blacklist = self.config.get('tag_blacklist', [])
        metadata_blacklist = self.config.get('metadata_blacklist', {})

        auth_client = auth.GoogleAuthClient(
            self.keyfile, scopes=['cloud-platform'], session=self.session)

        gcp_client = gce_clients.GCPClient(
            auth_client,
            self.session,
            tag_blacklist=tag_blacklist,
            metadata_blacklist=metadata_blacklist)

        instance_filter = await self.get_instance_filter()

        for project in projects:
            yield await gcp_client.list_instances(
                project, instance_filter=instance_filter)

    async def get_msg_generator(self):
        """Get message generator to translate instance data into channel msgs.

        Returns:
            obj: obj that creates messages for the channel.
        """
        return msg_generators.ARecordMsgGenerator(self.config['zone'])

    async def start(self):
        """Gather instance data batches and send them to the
        :py:obj:`self.rrset_channel`.
        """
        async with aiohttp.ClientSession() as session:
            self.session = session
            msg_generator = await self.get_msg_generator()

            projects = await self.get_processed_projects()

            async for project_instances in self.get_instances_for_projects(
                    projects):
                rrsets = await msg_generator.generate_batch(project_instances)
                await self.rrset_channel.put(rrsets)
            await self.rrset_channel.put(None)
        self.session = None
