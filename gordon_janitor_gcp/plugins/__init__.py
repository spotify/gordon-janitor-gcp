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
from gordon_janitor_gcp.plugins import publisher
from gordon_janitor_gcp.plugins.publisher import GPubsubPublisher  # noqa: F401
from gordon_janitor_gcp.plugins.reconciler import *  # noqa: F403


__all__ = (
    reconciler.__all__ +  # noqa: F405
    ('get_publisher', 'GPubsubPublisher')
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
    publisher._validate_pubsub_config(config)
    auth_client = publisher._init_pubsub_auth(config)
    pubsub_client = publisher._init_pubsub_client(auth_client, config)
    return publisher.GPubsubPublisher(
        config, pubsub_client, changes_channel, **kw)
