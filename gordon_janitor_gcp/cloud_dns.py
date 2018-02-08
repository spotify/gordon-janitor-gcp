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
Client module to interact with the Google Cloud DNS API.

This client makes use of the asynchronus HTTP client as defined in
:py:mod:`gordon_janitor_gcp.http_client`, and therefore must use
service account/JWT authentication (for now).

To use:

.. code-block:: pycon

    >>> keyfile = '/path/to/service_account_keyfile.json'
    >>> client = AIOGoogleDNSClient(
    ...   project='my-dns-project', keyfile=keyfile)
    >>> records = client.get_records_for_zone('testzone')
    >>> print(records[0])
    GCPResourceRecordSet(name='foo.testzone.com', type='A',
                         rrdatas=['10.1.2.3'], ttl=300)

"""

import logging

import attr

from gordon_janitor_gcp import http_client


@attr.s
class GCPResourceRecordSet:
    """DNS Resource Record Set.

    Args:
        name (str): Name/label.
        type (str): Record type (see `Google's supported records
            <https://cloud.google.com/dns/overview#supported_dns_r
            ecord_types>`_ for valid types).
        rrdatas (list): Record data according to RFC 1034§3.6.1 and
            RFC 1035§5.
        ttl (int): (optional) Number of seconds that the record set can
            be cached by resolvers. Defaults to 300.
    """
    # TODO (lynn): This will be moved to a common package to be shared
    #   between all of gordon* packages. It will also make use of attrs
    #   ability to optionally validate upon creation.
    name = attr.ib(type=str)
    type = attr.ib(type=str)
    rrdatas = attr.ib(type=list)
    ttl = attr.ib(type=int, default=300)


class AIOGoogleDNSClient(http_client.AIOGoogleHTTPClient):
    """Async HTTP client to interact with Google Cloud DNS API.

    Attributes:
        BASE_URL (str): base call url for the DNS API

    Args:
        project (str): Google project ID that hosts the managed DNS.
        keyfile (str): path to service account (SA) keyfile.
        scopes (list): scopes with which to authorize the SA. Default is
            ``['cloud-platform']``.
        api_version (str): DNS API endpoint version. Defaults to ``v1``.
        loop: asyncio event loop to use for HTTP requests.
    """
    BASE_URL = 'https://www.googleapis.com/dns'

    def __init__(self, project=None, keyfile=None, scopes=None,
                 api_version='v1', loop=None):
        super().__init__(keyfile=keyfile, scopes=scopes, loop=loop)
        self.project = project
        self._base_url = f'{self.BASE_URL}/{api_version}/projects/{project}'

    def _parse_resp_to_records(self, response, records):
        unparsed_records = response.get('rrsets', [])
        for record in unparsed_records:
            rrset = GCPResourceRecordSet(**record)
            records.append(rrset)

    async def get_records_for_zone(self, zone):
        """Get all resource record sets for a particular managed zone.

        Args:
            zone (str): Desired managed zone to query.
        Returns:
            list of :py:class:`GCPResourceRecordSet` instances.
        """
        url = f'{self._base_url}/managedZones/{zone}/rrsets'

        # to limit the amount of data across the wire; also makes it
        # easier to create GCPResourceRecordSet instances
        fields = 'rrsets/name,rrsets/rrdatas,rrsets/type,rrsets/ttl'
        params = {
            'fields': fields,
        }
        next_page_token = None

        records = []
        while True:
            if next_page_token:
                params['pageToken'] = next_page_token
            response = await self.get_json(url, params=params)
            self._parse_resp_to_records(response, records)
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

        logging.info(f'Found {len(records)} for zone "{zone}".')
        return records
