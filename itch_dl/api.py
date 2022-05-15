from typing import Optional

from requests import Session
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from .consts import ITCH_API


class ItchApiClient:
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.base_url = base_url or ITCH_API
        self.api_key = api_key

        self.requests = Session()

        retry_strategy = Retry(
            total=5,
            backoff_factor=10,
            allowed_methods=["HEAD", "GET"],
            status_forcelist=[429, 500, 502, 503, 504]
        )

        # No timeouts - set them explicitly on API calls below!
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.requests.mount("https://", adapter)
        self.requests.mount("http://", adapter)

    def get(self, endpoint: str, append_api_key: bool = True, **kwargs):
        if append_api_key:
            params = kwargs.get('data') or {}

            if 'api_key' not in params:
                params['api_key'] = self.api_key

            kwargs['data'] = params

        if endpoint.startswith("https://"):
            url = endpoint
        else:
            url = self.base_url + endpoint

        return self.requests.get(url, **kwargs)
