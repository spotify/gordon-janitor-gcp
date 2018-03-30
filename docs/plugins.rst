Plugins
=======

Currently available Google Cloud Platform plugins for the `gordon-janitor`_ service.

.. attention::

    These plugins are internal modules for the core `gordon-janitor`_ logic. No other use cases are expected.

.. todo::

    Add prose documentation for how to implement a plugin.


Reconciler
----------

.. automodule:: gordon_janitor_gcp.plugins.reconciler
.. autoclass:: gordon_janitor_gcp.GDNSReconciler
    :members:

Publisher
----------

.. automodule:: gordon_janitor_gcp.plugins.publisher
.. autoclass:: gordon_janitor_gcp.GPubsubPublisher
    :members:

Authority
---------

.. automodule:: gordon_janitor_gcp.plugins.authority
.. autoclass:: gordon_janitor_gcp.GCEAuthority
    :members:

.. _`gordon-janitor`: https://github.com/spotify/gordon-janitor
