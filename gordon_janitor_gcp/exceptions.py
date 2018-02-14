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


# TODO: Inherit from a general gordon janitor exception once added to
#       the core janitor package
class GCPGordonJanitorError(Exception):
    """Tmp base exception until gordon_janitor has exceptions"""


class GCPAuthError(GCPGordonJanitorError):
    """Authentication error with Google Cloud."""


class GCPHTTPError(GCPGordonJanitorError):
    """An HTTP error occured."""


class GCPConfigError(GCPGordonJanitorError):
    """Improper or incomplete configuration for plugin."""
