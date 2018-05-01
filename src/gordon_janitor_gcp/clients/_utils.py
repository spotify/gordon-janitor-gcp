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
"""Common utils shared among clients."""


class GPaginatorMixin:
    """HTTP client mixin that aggregates data from paginated responses."""
    async def list_all(self, url, params):
        """Aggregate data from all pages of an API query.

        Args:
            url (str): Google API endpoint URL.
            params (dict): URL query parameters.
        Returns:
            list: parsed query response results.
        """
        items = []
        next_page_token = None

        while True:
            if next_page_token:
                params['pageToken'] = next_page_token
            response = await self.get_json(url, params=params)

            items.append(response)
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
        return items
