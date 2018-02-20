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
Module to collect classes that transform different inputs into messages that
can be passed from one plugin to another through a channel.

Example A record message generator usage:

.. code-block:: pycon

    >>> import asyncio
    >>> loop = asyncio.get_event_loop()
    >>> instance1_data = {'hostname': 'a-host', 'internal_ip': '192.168.11.5'}
    >>> instance2_data = {'hostname': 'b-host', 'internal_ip': '192.168.11.6'}
    >>> generator = ARecordMsgGenerator('dnszone.com')
    >>> batch = loop.run_until_complete(
            generator.generate_batch([instance1_data, instance2_data]))
    >>> print(batch)
    {'zone': 'dnszone.com', 'rrsets':
        [{'name': 'a-host', 'type': 'A', 'rrdatas': ['192.168.11.5']},
         {'name': 'b-host', 'type': 'A', 'rrdatas': ['192.168.11.6']}]}
"""


class MsgGeneratorBase:
    """Base class that establishes a common interface."""
    async def generate_msg(self, data_item):
        """Create a message based off a data item.

        Must be implemented by the inheriting class.

        Args:
            data_item (any): source data.
        """
        raise NotImplementedError(
            f'{self.__class__.__name__} must implement "generate_msg" method')

    async def generate_batch(self, data):
        """Create a batch of messages based on data.

        Args:
            data (list): a collection of data to transform.
        Returns:
            list: a collection fo messages.
        """
        raise NotImplementedError(
            f'{self.__class__.__name__} must implement "generate_batch" method')


class ARecordMsgGenerator(MsgGeneratorBase):
    """Generates messages used to verify A records.

    Args:
        zone (str): DNS zone that the instance's record should belong to.
    """
    def __init__(self, zone):
        self.zone = zone

    async def generate_msg(self, instance):
        """Transform instance data into a dictionary.

        Args:
            instance (dict): GCP instance data.
        Returns:
            dict: instance data formatted for submitting to a channel.
        """
        return {
            'name': instance.get('hostname'),
            'type': 'A',
            'rrdatas': [instance.get('internal_ip')]
        }

    async def generate_batch(self, instances):
        return {
            'zone': self.zone,
            'rrsets': [
                await self.generate_msg(instance_data)
                for instance_data in instances
            ]
        }
