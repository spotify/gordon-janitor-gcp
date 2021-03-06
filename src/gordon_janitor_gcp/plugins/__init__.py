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

# Mainly for easier documentation reading
from gordon_janitor_gcp.plugins import authority
from gordon_janitor_gcp.plugins import publisher
from gordon_janitor_gcp.plugins import reconciler
from gordon_janitor_gcp.plugins.authority import GCEAuthority  # noqa: F401
from gordon_janitor_gcp.plugins.publisher import GPubsubPublisher  # noqa: F401
from gordon_janitor_gcp.plugins.reconciler import GDNSReconciler  # noqa: F401


__all__ = (
    reconciler.__all__ +  # noqa: F405
    ('get_publisher', 'GPubsubPublisher') +
    ('get_reconciler', 'GDNSReconciler') +
    ('get_authority', 'GCEAuthority')
)


def get_publisher(config, changes_channel, **kw):
    """Get a GPubsubPublisher client.

    A factory function that validates configuration, creates an auth
    and pubsub API client, and returns a Google Pub/Sub Publisher
    provider.

    Args:
        config (dict): Google Cloud Pub/Sub-related configuration.
        changes_channel (asyncio.Queue): queue to publish message to
            make corrections to Cloud DNS.
        kw (dict): Additional keyword arguments to pass to the
            Publisher.
    Returns:
        A :class:`GPubsubPublisher` instance.
    """
    builder = publisher.GPubsubPublisherBuilder(config, changes_channel, **kw)
    return builder.build_publisher()


def get_reconciler(config, rrset_channel, changes_channel, **kw):
    """Get a GDNSReconciler client.

    A factory function that validates configuration, creates an auth
    and :class:`GDNSClient` instance, and returns a GDNSReconciler
    provider.

    Args:
        config (dict): Google Cloud Pub/Sub-related configuration.
        rrset_channel (asyncio.Queue): queue from which to consume
            record set messages to validate.
        changes_channel (asyncio.Queue): queue to publish message to
            make corrections to Cloud DNS.
        kw (dict): Additional keyword arguments to pass to the
            Publisher.
    Returns:
        A :class:`GDNSReconciler` instance.
    """
    builder = reconciler.GDNSReconcilerBuilder(
        config, rrset_channel, changes_channel, **kw)
    return builder.build_reconciler()


def get_authority(config, rrset_channel, **kwargs):
    """Get a GCEAuthority client.

    A factory function that validates configuration and creates a
    proper GCEAuthority.

    Args:
        config (dict): GCEAuthority related configuration.
        rrset_channel (asyncio.Queue): queue used for sending messages
            to the reconciler plugin.
        kw (dict): Additional keyword arguments to pass to the
            Authority.
    Returns:
        A :class:`GCEAuthority` instance.
    """
    builder = authority.GCEAuthorityBuilder(config, rrset_channel, **kwargs)
    return builder.build_authority()
