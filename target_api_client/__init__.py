from datetime import datetime, timedelta
from hashlib import md5
from json import dumps
from random import random
from typing import Callable, List, Tuple, Optional

import requests
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import (
    BackendApplicationClient, InvalidGrantError, TokenExpiredError
)


class TargetApiError(Exception):
    def __init__(self, message, http_status=500):
        self.message = message
        self.http_status = http_status

    def __str__(self):
        return "{} (http status {})".format(self.message, self.http_status)


class TargetValidationError(TargetApiError):
    def __init__(self, fields):
        self.http_status = 400
        self.fields = fields

    def __str__(self):
        return "Validation failed on:\n {}".format(
            "\n  ".join(
                "#{}: {}".format(f, e) for f, e in self.fields.items()
            )
        )


class TargetAuthError(TargetApiError):
    def __init__(self, message, oauth_message):
        self.message = message
        self.oauth_message = oauth_message
        self.http_status = 401

    def __str__(self):
        return "{} (http status {}) {}".format(
            self.message,
            self.http_status,
            self.oauth_message,
        )


class TargetApiClient(object):
    PRODUCTION_HOST = 'target.my.com'
    SANDBOX_HOST = 'target-sandbox.my.com'

    OAUTH_TOKEN_URL = 'v2/oauth2/token.json'
    OAUTH_USER_URL = '/oauth2/authorize'
    # GRANT_CLIENT = 'client_credentials'
    # GRANT_AGENCY_CLIENT = 'agency_client_credentials'
    # GRANT_RERFESH = 'refresh_token'
    # GRANT_AUTH_CODE = 'authorization_code'
    # OAUTH_ADS_SCOPES = ('read_ads', 'read_payments', 'create_ads')
    # OAUTH_AGENCY_SCOPES = (
    #     'create_clients', 'read_clients', 'create_agency_payments'
    # )
    # OAUTH_MANAGER_SCOPES = (
    #     'read_manager_clients', 'edit_manager_clients', 'read_payments'
    # )

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token: dict = None,
        is_sandbox: bool = True,
        token_updater: Callable[[dict], None] = None,
    ):
        """
        Args:
            token - access_token and token_type
                    Example: {"access_token": "", "token_type": "Bearer"}
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._token = token
        self._token_updater_clb = token_updater
        self._timeout = 20  # second

        self.host = self.SANDBOX_HOST if is_sandbox else self.PRODUCTION_HOST
        self.url = 'https://{}/api/'.format(self.host)

        # Setup
        self._session = OAuth2Session(
            client=BackendApplicationClient(client_id=self._client_id),
            auto_refresh_url=self.url_token,
            auto_refresh_kwargs={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            token_updater=self._token_updater,
            token=self._token
        )

    @property
    def url_token(self) -> str:
        return "{}{}".format(self.url, self.OAUTH_TOKEN_URL)

    def _token_updater(self, token: dict):
        self._token = token
        if self._token_updater_clb is not None:
            self._token_updater_clb(token)

    def _request(
        self,
        resource: str,
        method: str,
        **kwargs
    ) -> requests.Response:
        """
        Performs HTTP request to Target API.
        """
        response = self._session.request(
            method,
            self._get_url_resource(resource),
            timeout=self._timeout,
            **kwargs
        )

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 204:
            return True
        self._process_error(response)
    
    def _get_url_resource(self, resource: str) -> str:
        """Create URL for resource"""
        resource = resource.lstrip('/')
        if not resource.startswith('v'):
            resource = 'v1/' + resource
        return "{}{}".format(self.url, resource) 

    def get_token(self):
        """Get token"""
        try:
            token = self._session.fetch_token(
                token_url=self.url_token,
                # client_id=self._client_id,
                include_client_id=True,
                client_secret=self._client_secret,
            )
        except InvalidGrantError:
            raise
        self._token_updater(token)

    def get_ok_lead(self, form_id: str, **kwargs):
        """
        Args:
            limit - Количество возвращаемых в ответе лидов. Значение по умолчанию: 20. Максимальное значение: 50.
            offset - Смещение точки отсчета относительно начала списка лидов. Значение по умолчанию: 0.
            _created_time__lt - Лиды, созданные до указанной даты. Дата задается в формате «YYYY-MM-DD hh:mm:ss».
            _created_time__gt - Лиды, созданные после указанной даты. Дата задается в формате «YYYY-MM-DD hh:mm:ss».
            _created_time__lte - Лиды, созданные в указанную дату или до нее. Дата задается в формате «YYYY-MM-DD hh:mm:ss».
            _created_time__gte - Лиды, созданные в указанную дату или после нее. Дата задается в формате «YYYY-MM-DD hh:mm:ss».
            _campaign_id__in - Список идентификаторов кампаний, для которых нужно получить лиды. Идентификаторы задаются в формате «id_1,id_2,…,id_N».
            _campaign_id - Идентификатор кампании, для которой нужно получить лиды. Идентификатор задается в формате «id_1».
            _banner_id__in - Список идентификаторов баннеров, для которых нужно получить лиды. Идентификаторы задаются в формате «id_1,id_2,…,id_N».
            _banner_id - Идентификатор баннера, для которого нужно получить лиды. Идентификатор задается в формате «id_1».
        """
        resp = self._request(
            method="get",
            resource="v2/ok/lead_ads/{}.json".format(form_id),
            params=kwargs,
        )
        return resp

    def _process_error(self, resp: requests.Response):
        body = resp.json()
        if resp.status_code == 400:
            raise TargetValidationError(body)
        if resp.status_code == 401:
            raise TargetAuthError(body, resp.headers.get('WWW-Authenticate'))
        raise TargetApiError(body, resp.status_code)

    # def _request_oauth_token(self, scheme=GRANT_CLIENT, **extra):
    #     params = {
    #         'grant_type': scheme,
    #         'client_id': self.client_id,
    #         'client_secret': self.client_secret,
    #     }
    #     if extra:
    #         params.update(extra)

    #     resp = requests.post(self.url + self.OAUTH_TOKEN_URL, data=params)

    #     if resp.status_code == 200:
    #         return resp.json()
    #     self._process_error(resp)

    # def refresh_access_token(self, refresh_token):
    #     return self._request_oauth_token(
    #         self.GRANT_RERFESH,
    #         refresh_token=refresh_token,
    #     )

    # def request_client_token(self):
    #     return self._request_oauth_token()

    # def token_delete(self, username: str = None):
    #     params = {
    #         'client_id': self.client_id,
    #         'client_secret': self.client_secret,
    #     }
    #     if username is not None:
    #         params["username"] = username

    #     resp = requests.post(
    #         self.url + "v2/oauth2/token/delete.json",
    #         data=params
    #     )

    #     if resp.status_code == 204:
    #         return True
    #     self._process_error(resp)

    # def request_app_user_token(self, code):
    #     return self._request_oauth_token(self.GRANT_AUTH_CODE, code=code)

    # def get_oauth_authorize_url(self, scopes=OAUTH_ADS_SCOPES, state=None):
    #     if not state:
    #         state = md5(str(random())).hexdigest()
    #     url = '%s?response_type=code&client_id=%s&state=%s&scope=%s' % (
    #         self.OAUTH_USER_URL,
    #         self.client_id,
    #         state,
    #         scopes,
    #     )
    #     return {'state': state, 'url': url}
