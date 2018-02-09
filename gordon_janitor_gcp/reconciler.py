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
Module to compare desired record sets produced from a Resource Authority
(i.e. ``GCEInstanceAuthority`` for Google Compute Engine) and actual
record sets from Google Cloud DNS, then publish corrective messages to
the internal ``changes_channel`` if there are differences.

This client makes use of the asynchronous DNS client as defined in
:py:mod:`gordon_janitor_gcp.cloud_dns`, and therefore must use
service account/JWT authentication (for now).

.. attention::

    This reconciler client is an internal module for the core janitor
    logic. No other user cases are expected.

To use:

.. code-block:: python

    import asyncio

    from gordon_janitor_gcp import auth
    from gordon_janitor_gcp import cloud_dns

    # setup auth + dns client
    keyfile = '/path/to/service_account_keyfile.json'
    auth_client = auth.GoogleAuthClient(keyfile=keyfile)
    dns_client = AIOGoogleDNSClient(
        project='my-dns-project', auth_client=auth_client)

    # reconciler client setup
    rrset_chnl = asyncio.Queue()
    changes_chnl = asyncio.Queue()

    reconciler = GoogleDNSReconciler(
        dns_client, rrset_chnl, changes_chnl)

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(reconciler.start())
    finally:
        loop.close()
"""

import asyncio
import logging

import attr

from gordon_janitor_gcp import cloud_dns
from gordon_janitor_gcp import exceptions


class GoogleDNSReconciler:
    """Validate current records in DNS against desired source of truth.

    ``GoogleDNSReconciler`` will create a change message for the
    configured publisher client plugin to consume if there is a
    discrepancy between records in Google Cloud DNS and the desired
    state.

    Once validation is done, the Reconciler will emit a ``None`` message
    to the ``changes_channel`` queue signalling to the ``Publisher``
    (TODO: update name of publisher class once decided) that there are
    no more change messages to expect.

    Args:
        dns_client (gordon_janitor_gcp.cloud_dns.AIOGoogleDNSClient):
            instantiated DNS client
        rrset_channel (asyncio.Queue): queue from which to consume
            record set messages to validate.
        changes_channel (asyncio.Queue): queue to publish message to
            make corrections to Cloud DNS.
        timeout (int): (optional) seconds to wait for the plugin's tasks
            to finish before emitting a ``None`` message to the
            ``changes_channel``. Outstanding tasks will be cancelled
            and logged. Defaults to 60.
        loop: (optional) asyncio event loop to use for HTTP requests.
    """
    # TODO (lynn): update object type of ``dns_client`` arg when proper
    #              interfaces are implemented

    _ASYNC_METHODS = ['publish_change_messages', 'validate_rrsets_by_zone']

    def __init__(self, dns_client, rrset_channel, changes_channel, timeout=60):
        self.dns_client = dns_client
        self.rrset_channel = rrset_channel
        self.changes_channel = changes_channel
        self.timeout = timeout

    async def done(self):
        """Clean up and notify ``changes_channel`` of no more messages.

        This method collects all tasks that this particular class
        initiated, and will cancel them if they don't complete within
        the configured timeout period.

        Once all tasks are done, `None` is added to the
        :py:obj:`self.changes_channel` to signify that it has no
        more work to process. Then the HTTP session attached to the
        :py:obj:`self.dns_client` is properly closed.
        """
        all_tasks = asyncio.Task.all_tasks()
        tasks_to_clear = [
            t for t in all_tasks if t._coro.__name__ in self._ASYNC_METHODS
        ]
        sleep_for = 0.5  # half a second
        iterations = self.timeout / sleep_for

        while iterations:
            tasks_to_clear = [t for t in tasks_to_clear if not t.done()]
            if not tasks_to_clear:
                break

            await asyncio.sleep(sleep_for)
            iterations -= 1

        # give up on waiting for tasks to complete
        if tasks_to_clear:
            msg = (f'The following tasks did not complete in time and are '
                   f'being cancelled: {tasks_to_clear}')
            logging.warning(msg)
            for task in tasks_to_clear:
                task.cancel()

        await self.changes_channel.put(None)
        # TODO (lynn): add metrics.flush call here once aioshumway is released
        self.dns_client._session.close()

        msg = ('Reconciliation of desired records against actual records in '
               'Google DNS is complete.')
        logging.info(msg)

    async def publish_change_messages(self, desired_rrsets, action='additions'):
        """Publish change messages to the ``changes_channel``.

        NOTE: Only `'additions'` are currently supported. `'deletions'`
        may be supported in the future.

        Args:
            desired_rrsets (list(GCPResourceRecordSet)): Desired record
                sets that are not in Google Cloud DNS.
            action (str): (optional) action for these corrective
                messages. Defaults to ``'additions'``.
        """
        for rrset in desired_rrsets:
            msg = {
                'resourceRecords': attr.asdict(rrset),
                'action': action
            }
            # TODO (lynn): add metrics.incr call here once aioshumway is
            #              released
            logging.debug('Creating the following change message: {msg}')
            await self.changes_channel.put(msg)

        logging.info(f'Created {len(desired_rrsets)} change messages.')

    def _parse_rrset_message(self, message):
        # assert that keys 'zone' and 'rrsets' are present, and return
        # values for each
        try:
            zone = message['zone']
        except KeyError:
            msg = (f'No zone was defined in the given message: {message}.')
            logging.error(msg)
            raise exceptions.GCPGordonJanitorError(msg)
        try:
            rrsets = message['rrsets']
        except KeyError:
            msg = (f'No resource record sets were defined in given message: '
                   f'{message}.')
            logging.error(msg)
            raise exceptions.GCPGordonJanitorError(msg)

        return zone, rrsets

    async def validate_rrsets_by_zone(self, zone, rrsets):
        """Given a zone, validate current versus desired rrsets.

        If there are any missing records, a corrective message for each
        record will be published.

        Args:
            zone (str): zone to query Google Cloud DNS API.
            rrsets (list): desired record sets to which to compare the
                Cloud DNS API's response.
        """
        desired_rrsets = [
            cloud_dns.GCPResourceRecordSet(**record) for record in rrsets
        ]

        actual_rrsets = await self.dns_client.get_records_for_zone(zone)

        # NOTE: only working on "additions" (which includes changes to
        #       current records) right now.
        # TODO: (FEATURE) add support for cleaning up records that
        #       should have been deleted.
        missing_rrsets = [
            rs for rs in desired_rrsets if rs not in actual_rrsets
        ]
        msg = (f'[{zone}] Processed {len(actual_rrsets)} rrset messages '
               f'and found {len(missing_rrsets)} missing rrsets.')
        logging.info(msg)
        # TODO (lynn): emit or incr metric of missing_rrsets by zone once
        #              aioshumway is released
        # TODO: (FEATURE): have separate metrics for additions and deletions
        await self.publish_change_messages(missing_rrsets, action='additions')

    async def start(self):
        """Start consuming from :py:obj:`self.rrset_channel`.

        Once ``None`` is received from the channel, finish processing
        records and emit a ``None`` message to the
        :py:obj:`self.changes_channel`.
        """
        while True:
            desired_rrset = await self.rrset_channel.get()
            if desired_rrset is None:
                break
            # TODO: emit metric of message received once aioshumway is released
            try:
                zone, raw_rrsets = self._parse_rrset_message(desired_rrset)
                await self.validate_rrsets_by_zone(zone, raw_rrsets)
            except exceptions.GCPGordonJanitorError as e:
                msg = f'Dropping message {desired_rrset}: {e}'
                logging.error(msg, exc_info=e)

        await self.done()
