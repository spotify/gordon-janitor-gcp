Configuration
=============

Configuring Google Cloud Platform plugins for the `Gordon Janitor Service <https://github.com/spotify/gordon-janitor>`_.

Example Configuration
---------------------

An example of a ``gordon-janitor.toml`` file for GCP-specific plugins:

.. literalinclude:: ../gordon-janitor.toml.example
    :language: ini


Configuration
-------------

The following sections are supported:

gcp
~~~

Any configuration key/value listed here may also be used in the specific plugin configuration. Values set in a plugin-specific config section will overwrite what's set in this general ``[gcp]`` section.

.. option:: keyfile="/path/to/keyfile.json"

    `Required`: Path to the Service Account JSON keyfile to use while authenticating against Google APIs.

    While one global key for all plugins is supported, it's advised to create a key per plugin with only the permissions it requires. To setup a service account, follow `Google's docs on creating & managing service account keys <https://cloud.google.com/iam/docs/creating-managing-service-account-keys>`_.

.. option:: project="STR"

    `Required`: Google Project ID which hosts the relevant GCP services (e.g. Cloud DNS, PubSub, Compute Engine).

    To learn more about GCP projects, please see `Google's docs on creating & managing projects <https://cloud.google.com/resource-manager/docs/creating-managing-projects>`_.

.. option:: scopes=["STR", "STR"]

    `Optional`: A list of strings of the scope(s) needed when making calls to Google APIs. Defaults to ``["cloud-platform"]``.

.. option:: cleanup_timeout=INT

    `Optional`: Timeout in seconds for how long each plugin should wait for outstanding tasks (e.g. processing remaining message from a channel) before cancelling. This is only used when a plugin has received all messages from a channel, but may have work outstanding. Defaults to ``60``.


gcp.gdns
~~~~~~~~

All configuration options above may be used here. There are no specific DNS-related configuration options.
