API Clients
===========

.. currentmodule:: gordon_janitor_gcp

HTTP Sessions
-------------

By default, the HTTP session used for getting credentials is reused for
API calls (recommended if there are many). If this is not desired, you
can pass in your own :class:`aiohttp.ClientSession` instance into
:class:`AIOGoogleDNSClient` or :class:`AIOGoogleHTTPClient`. The
auth client :class:`GoogleAuthClient` may also take an explicit
session object, but is not required to assert a different HTTP session
is used for the API calls.

.. code-block:: python

    import aiohttp
    import gordon_janitor_gcp

    keyfile = '/path/to/service_account_keyfile.json'
    session = aiohttp.ClientSession()  # optional
    auth_client = gordon_janitor_gcp.GoogleAuthClient(
        keyfile=keyfile, session=session
    )

    new_session = aiohttp.ClientSession()

    # basic HTTP client
    client = gordon_janitor_gcp.AIOGoogleHTTPClient(
        auth_client=auth_client, session=new_session
    )
    # or DNS client
    client = gordon_janitor_gcp.AIOGoogleDNSClient(
        project='my-dns-project', auth_client=auth_client,
        session=new_session
    )


.. NOTE: we separate out `automodule` and `autoclass` (rather than list members with automodule) to make use of the namespace flattening.


Asynchronous GCP HTTP Client
----------------------------

.. automodule:: gordon_janitor_gcp.clients.http
.. autoclass:: gordon_janitor_gcp.AIOGoogleHTTPClient
    :members:


GCP Auth Client
---------------

.. automodule:: gordon_janitor_gcp.clients.auth
.. autoclass:: gordon_janitor_gcp.GoogleAuthClient
    :members:


GCP Cloud DNS HTTP Client
-------------------------

.. automodule:: gordon_janitor_gcp.clients.gdns
.. autoclass:: gordon_janitor_gcp.AIOGoogleDNSClient
    :members:
.. autoclass:: gordon_janitor_gcp.GCPResourceRecordSet
    :members:


GCE Clients
-----------

.. automodule:: gordon_janitor_gcp.clients.gcp
.. autoclass:: gordon_janitor_gcp.GCRMClient
    :members:
.. autoclass:: gordon_janitor_gcp.GCEClient
    :members:
