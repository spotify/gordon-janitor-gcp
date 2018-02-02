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

Only service account (JSON Web Tokens/JWT) authentication is currently
supported. To setup a service account, follow `Google's docs <https://
cloud.google.com/iam/docs/creating-managing-service-account-keys>`_.

To use:

.. code-block:: python

    keyfile = '/path/to/service_account_keyfile.json'
    client = AIOGoogleHTTPClient(keyfile)
    resp = await client.request('get', 'http://api.example.com/foo')

"""

import asyncio
import datetime
import http.client
import json
import logging
import urllib.parse

import aiohttp
from google.oauth2 import _client
from google.oauth2 import service_account

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

    Attributes:
        JWT_GRANT_TYPE (str): grant type header value when
            requesting/refreshing an access token.
        SCOPE_TMPL_URL (str): template URL for Google auth scopes

    Args:
        keyfile (str): path to service account (SA) keyfile.
        scopes (list): scopes with which to authorize the SA. Default is
            ``['cloud-platform']``.
        loop: asyncio event loop to use for HTTP requests.
    """
    JWT_GRANT_TYPE = 'urn:ietf:params:oauth:grant-type:jwt-bearer'
    SCOPE_TMPL_URL = 'https://www.googleapis.com/auth/{scope}'

    def __init__(self, keyfile=None, scopes=None, loop=None):
        self._keydata = self._load_keyfile(keyfile)
        self.scopes = self._set_scopes(scopes)
        # NOTE: Anything <3.6, the loop returned isn't actually the
        #       current running loop but the loop that was configured
        #       for the current thread. This supports earlier Python3
        #       versions if we ever want to.
        self._loop = loop or asyncio.get_event_loop()
        self._session = aiohttp.ClientSession(loop=self._loop)
        self._creds = self._load_credentials()
        self.token = None
        self.expiry = None  # UTC time

    def _load_keyfile(self, keyfile):
        try:
            with open(keyfile, 'r') as f:
                return json.load(f)
        except FileNotFoundError as e:
            msg = f'Keyfile {keyfile} was not found.'
            logging.error(msg, exc_info=e)
            raise exceptions.GCPGordonJanitorError(msg)
        except json.JSONDecodeError as e:
            msg = f'Keyfile {keyfile} is not valid JSON.'
            logging.error(msg, exc_info=e)
            raise exceptions.GCPGordonJanitorError(msg)

    def _set_scopes(self, scopes):
        if not scopes:
            scopes = ['cloud-platform']
        return [self.SCOPE_TMPL_URL.format(scope=s) for s in scopes]

    def _load_credentials(self):
        # TODO (lynn): FEATURE - load other credentials like app default
        return service_account.Credentials.from_service_account_info(
            self._keydata, scopes=self.scopes)

    def _setup_token_request(self):
        url = self._keydata.get('token_uri')
        headers = {
            'Content-type': 'application/x-www-form-urlencoded',
        }
        body = {
            'assertion': self._creds._make_authorization_grant_assertion(),
            'grant_type': self.JWT_GRANT_TYPE,
        }
        body = urllib.parse.urlencode(body)
        return url, headers, bytes(body.encode('utf-8'))

    async def refresh_token(self):
        """Refresh oauth access token attached to this HTTP session.

        Raises:
            exceptions.GCPAuthError: if no token was found in the
                response.
            exceptions.GCPHTTPError: if any exception occurred.
        """
        url, headers, body = self._setup_token_request()

        logging.debug(REQ_LOG_FMT.format(method='POST', url=url))
        async with self._session.post(url, headers=headers, data=body) as resp:
            log_kw = {
                'method': 'POST',
                'url': url,
                'status': resp.status,
                'reason': resp.reason,
            }
            logging.debug(RESP_LOG_FMT.format(**log_kw))

            # avoid leaky abstractions and wrap http errors with our own
            try:
                resp.raise_for_status()
            except aiohttp.ClientResponseError as e:
                msg = f'Issue connecting to {resp.url.host}: {e}'
                logging.error(msg, exc_info=e)
                raise exceptions.GCPHTTPError(msg)

            response = await resp.json()
            try:
                self.token = response['access_token']
            except KeyError:
                msg = 'No access token in response.'
                logging.error(msg)
                raise exceptions.GCPAuthError(msg)

        self.expiry = _client._parse_expiry(response)

    async def set_valid_token(self):
        """Check for validity of token, and refresh if none or expired."""
        is_valid = False

        if self.token:
            # Account for a token near expiration
            now = datetime.datetime.utcnow()
            skew = datetime.timedelta(seconds=60)
            if self.expiry > (now + skew):
                is_valid = True

        if not is_valid:
            await self.refresh_token()

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
        req_headers.update({'Authorization': f'Bearer {self.token}'})

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
