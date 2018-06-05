Changelog
=========

0.0.1.dev5 (2018-06-04)
-----------------------

Additions
~~~~~~~~~

- Added a long_description for PyPI.


0.0.1.dev4 (2018-06-04)
-----------------------

Changes
~~~~~~~

- Deprecated the repo (moved into `gordon-gcp`_).


0.0.1.dev3 (2018-05-25)
-----------------------

Changes
~~~~~~~

- Changed `dns_zone` configuration key format to one used by Gordon (core) plugins.
- Changed Authority EventMessages to use FQDNs.


0.0.1.dev2 (2018-05-01)
-----------------------

Changes
~~~~~~~

- Removed `http` and `auth` clients in favor of using those in `gordon-gcp`.
- Renamed configuration key from `zone` to `dns_zone`.
- Move instance parsing logic from client to authority plugin.


0.0.1.dev1 (2018-03-30)
-----------------------

Changes
~~~~~~~

Initial development release.



.. _`gordon-gcp`: https://github.com/spotify/gordon-gcp
