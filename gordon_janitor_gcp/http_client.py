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
Module to interact with Google APIs via asynchronous HTTP calls.

To use:

.. code-block:: python

    from gordon_janitor_gcp import auth

    keyfile = '/path/to/service_account_keyfile.json'
    auth_client = auth.GoogleAuthClient(keyfile=keyfile)

    client = AIOGoogleHTTPClient(auth_client=auth_client)
    resp = await client.request('get', 'http://api.example.com/foo')

"""

import asyncio
import datetime
import http.client
import json
import logging

import aiohttp

from gordon_janitor_gcp import exceptions


DEFAULT_REQUEST_HEADERS = {
    'X-Goog-API-Client': 'custom-aiohttp-gcloud-python/3.6.2 gccl',
    'Accept-Encoding': 'gzip',
    'User-Agent': 'custom-aiohttp-gcloud-python',
    'Authorization': '',
}
MAX_REFRESH_ATTEMPTS = 2
REFRESH_STATUS_CODES = (http.client.UNAUTHORIZED,)

# aiohttp does not log client request/responses; mimicking
# `requests` log format
REQ_LOG_FMT = 'Request: "{method} {url}"'
RESP_LOG_FMT = 'Response: "{method} {url}" {status} {reason}'


class AIOGoogleHTTPClient:
    """Async HTTP client to Google APIs with service-account-based auth.

    Args:
        auth_client (gordon_janitor_gcp.auth.GoogleAuthClient): client
            to manage authentication for HTTP API requests.
        session (aiohttp.ClientSession): (optional) ``aiohttp`` HTTP
            session to use for sending requests. Defaults to the
            session object attached to ``auth_client`` if not provided.
    """

    def __init__(self, auth_client=None, session=None):
        self._auth_client = auth_client
        self._session = session or auth_client._session

    async def set_valid_token(self):
        """Check for validity of token, and refresh if none or expired."""
        is_valid = False

        if self._auth_client.creds.token:
            # Account for a token near expiration
            now = datetime.datetime.utcnow()
            skew = datetime.timedelta(seconds=60)
            if self._auth_client.creds.expiry > (now + skew):
                is_valid = True

        if not is_valid:
            await self._auth_client.refresh_token()

    async def request(self, method, url, params=None, body=None,
                      headers=None, **kwargs):
        """Make an asynchronous HTTP request.

        Args:
            method (str): HTTP method to use for the request.
            url (str): URL to be requested.
            params (dict): (optional) Query parameters for the request.
                Defaults to ``None``.
            body (obj): (optional) A dictionary, bytes, or file-like
                object to send in the body of the request.
            headers (dict): (optional) HTTP headers to send with the
                request. Headers pass through to the request will
                include :py:attr:`DEFAULT_REQUEST_HEADERS`.
        Returns:
            (str) HTTP response body.
        Raises:
            exceptions.GCPHTTPError: if any exception occurred.
        """
        refresh_attempt = kwargs.pop('cred_refresh_attempt', 0)

        req_headers = headers or {}
        req_headers.update(DEFAULT_REQUEST_HEADERS)

        await self.set_valid_token()
        req_headers.update(
            {'Authorization': f'Bearer {self._auth_client.creds.token}'}
        )

        req_kwargs = {
            'params': params,
            'data': body,
            'headers': req_headers,
        }
        logging.debug(REQ_LOG_FMT.format(method=method.upper(), url=url))
        async with self._session.request(method, url, **req_kwargs) as resp:
            log_kw = {
                'method': method.upper(),
                'url': url,
                'status': resp.status,
                'reason': resp.reason
            }
            logging.debug(RESP_LOG_FMT.format(**log_kw))

            # Try to refresh token once if received a 401
            if resp.status in REFRESH_STATUS_CODES:
                if refresh_attempt < MAX_REFRESH_ATTEMPTS:
                    log_msg = ('Unauthorized. Attempting to refresh token and '
                               'try again.')
                    logging.info(log_msg)

                    new_req_kwargs = {
                        'params': params,
                        'body': body,
                        'headers': headers,  # use original req headers
                        'cred_refresh_attempt': refresh_attempt + 1
                    }
                    return await self.request(method, url, **new_req_kwargs)

            # avoid leaky abstractions and wrap http errors with our own
            try:
                resp.raise_for_status()
            except aiohttp.ClientResponseError as e:
                msg = f'Issue connecting to {resp.url.host}: {e}'
                logging.error(msg, exc_info=e)
                raise exceptions.GCPHTTPError(msg)

            return await resp.text()

    async def get_json(self, url, json_callback=None, **kwargs):
        """Get a URL and return its JSON response.

        Args:
            url (str): URL to be requested.
            json_callback (func): Custom JSON loader function. Defaults
                to json.loads
            kwargs (dict): Additional arguments to pass through to the
                request.
        Returns:
            response body returned by ``json_callback`` function.
        """
        if not json_callback:
            json_callback = json.loads
        response = await self.request(method='get', url=url, **kwargs)
        return json_callback(response)


class PagingGoogleClientMixin:
    """HTTP client base class that extracts data from paginated Google APIs.
    """

    def parse_response_into_items(self, response, items):
        """Parse an API response and append the results to ``items``

        Must be implemented by inheriting class.

        Args:
            response (dict): API json response.
            items (list): list for collecting parsed results.
        """
        raise NotImplementedError(
            f'{self.__class__.__name__} implement "parse_response_into_items" '
            'method!')

    async def list_all_items(self, url, params, retries, retry_wait):
        """Aggregate data from all pages of an API query.

        Args:
            url (str): Google API endpoint URL.
            params (dict): URL query parameters.
            retries (int): Number of times to retry an API call.
            retry_wait (int): Number of seconds to wait between each retry.
        Returns:
            list: parsed query response results.
        """
        items = []
        next_page_token = None

        while True:
            if next_page_token:
                params['pageToken'] = next_page_token
            try:
                response = await self.get_json(url, params=params)
            except exceptions.GCPHTTPError as e:
                base_msg = f'Fetching items from "{url}" failed: {e}, '
                if retries > 0:
                    retries -= 1
                    msg = base_msg + f'RETRYING. {retries} retries left.'
                    logging.warning(msg)
                    await asyncio.sleep(retry_wait)
                    continue
                else:
                    msg = base_msg + f'NO RETRIES left, return partial reply'
                    logging.warning(msg)
                    return items

            self.parse_response_into_items(response, items)
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
        return items
