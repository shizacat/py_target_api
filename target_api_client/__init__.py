from datetime import datetime, timedelta
from hashlib import md5
from json import dumps
from random import random

import requests


class TargetApiError(Exception):
    def __init__(self, message, http_status=500):
        self.message = message
        self.http_status = http_status

    def __str__(self):
        return '%s (http status %s)' % (self.message, self.http_status)


class TargetValidationError(TargetApiError):
    def __init__(self, fields):
        self.http_status = 400
        self.fields = fields

    def __str__(self):
        return 'Validation failed on:\n  %s' % (
            '\n  '.join(
                '#%s: %s' % (f, e) for f, e in self.fields.items()
            )
        )


class TargetAuthError(TargetApiError):
    def __init__(self, message, oauth_message):
        self.message = message
        self.oauth_message = oauth_message
        self.http_status = 401

    def __str__(self):
        return '%s (http status %s) %s' % (
            self.message,
            self.http_status,
            self.oauth_message,
        )


class TargetApiClient(object):
    PRODUCTION_HOST = 'target.my.com'
    SANDBOX_HOST = 'target-sandbox.my.com'

    OAUTH_TOKEN_URL = 'v2/oauth2/token.json'
    OAUTH_USER_URL = '/oauth2/authorize'
    GRANT_CLIENT = 'client_credentials'
    GRANT_AGENCY_CLIENT = 'agency_client_credentials'
    GRANT_RERFESH = 'refresh_token'
    GRANT_AUTH_CODE = 'authorization_code'
    OAUTH_ADS_SCOPES = ('read_ads', 'read_payments', 'create_ads')
    OAUTH_AGENCY_SCOPES = (
        'create_clients', 'read_clients', 'create_agency_payments'
    )
    OAUTH_MANAGER_SCOPES = (
        'read_manager_clients', 'edit_manager_clients', 'read_payments'
    )

    client_id = None
    client_secret = None
    url = None

    def __init__(self, client_id, client_secret, is_sandbox=True):
        self.client_id = client_id
        self.client_secret = client_secret
        self.host = self.SANDBOX_HOST if is_sandbox else self.PRODUCTION_HOST
        self.url = 'https://%s/api/' % self.host

    def request(self, resource, access_token, data=None, params=None,
                files=None, http_method=None):
        """
        Performs HTTP request to Target API.
        """
        resource = resource.lstrip('/')
        if not resource.startswith('v'):
            resource = 'v1/' + resource
        url = self.url + resource

        req = {
            'headers': {'Authorization': 'Bearer ' + access_token},
            'params': params,
        }
        if data is not None:
            if http_method is None:
                http_method = 'post'
            req['data'] = dumps(data)
            req['headers']['Content-Type'] = 'application/json'
        if files:
            if http_method is None:
                http_method = 'post'
            req['files'] = files

        resp = getattr(requests, http_method or 'get')(url, **req)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 204:
            return True
        self._process_error(resp)

    def get_ok_lead(self, form_id: str, access_token, **kwargs):
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
        resp = self.request(
            resource="v2/ok/lead_ads/{}.json".format(form_id),
            access_token=access_token,
            params=kwargs,
            http_method="get"
        )
        return resp

    def _process_error(self, resp):
        body = resp.json()
        if resp.status_code == 400:
            raise TargetValidationError(body)
        if resp.status_code == 401:
            raise TargetAuthError(body, resp.headers.get('WWW-Authenticate'))
        raise TargetApiError(body, resp.status_code)

    def _request_oauth_token(self, scheme=GRANT_CLIENT, **extra):
        params = {
            'grant_type': scheme,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }
        if extra:
            params.update(extra)

        resp = requests.post(self.url + self.OAUTH_TOKEN_URL, data=params)

        if resp.status_code == 200:
            return resp.json()
        self._process_error(resp)

    def refresh_access_token(self, refresh_token):
        return self._request_oauth_token(
            self.GRANT_RERFESH,
            refresh_token=refresh_token,
        )

    def request_client_token(self):
        return self._request_oauth_token()

    def token_delete(self, username: str = None):
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }
        if username is not None:
            params["username"] = username

        resp = requests.post(
            self.url + "v2/oauth2/token/delete.json",
            data=params
        )

        if resp.status_code == 204:
            return True
        self._process_error(resp)

    def request_app_user_token(self, code):
        return self._request_oauth_token(self.GRANT_AUTH_CODE, code=code)

    def get_oauth_authorize_url(self, scopes=OAUTH_ADS_SCOPES, state=None):
        if not state:
            state = md5(str(random())).hexdigest()
        url =  '%s?response_type=code&client_id=%s&state=%s&scope=%s' % (
            self.OAUTH_USER_URL,
            self.client_id,
            state,
            scopes,
        )
        return {'state': state, 'url': url}
