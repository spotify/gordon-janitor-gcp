API Reference
=============


HTTP Sessions
-------------

By default, the HTTP session used for getting credentials is reused for
API calls (recommended if there are many). If this is not desired, you
can pass in your own ``aiohttp.ClientSession`` instance into
``AIOGoogleDNSClient`` or ``AIOGoogleHTTPClient``. The auth client
``GoogleAuthClient`` may also take an explicit session object, but is
not required to assert a different HTTP session is used for the API
calls.

.. code-block:: python

    import aiohttp

    from gordon_janitor_gcp import auth
    from gordon_janitor_gcp import gdns_client
    from gordon_janitor_gcp import http_client

    keyfile = '/path/to/service_account_keyfile.json'
    session = aiohttp.ClientSession()  # optional
    auth_client = auth.GoogleAuthClient(
        keyfile=keyfile, session=session
    )

    new_session = aiohttp.ClientSession()

    # basic HTTP client
    client = http_client.AIOGoogleHTTPClient(
        auth_client=auth_client, session=new_session
    )
    # or DNS client
    client = gdns_client.AIOGoogleDNSClient(
        project='my-dns-project', auth_client=auth_client,
        session=new_session
    )



Asynchronous GCP HTTP Client
----------------------------

.. automodule:: gordon_janitor_gcp.http_client


GCP Cloud DNS HTTP Client
-------------------------

.. automodule:: gordon_janitor_gcp.gdns_client


GCP Auth Client
---------------

.. automodule:: gordon_janitor_gcp.auth


Reconciler
----------

.. automodule:: gordon_janitor_gcp.gdns_reconciler


Publisher
----------

.. automodule:: gordon_janitor_gcp.gpubsub_publisher
