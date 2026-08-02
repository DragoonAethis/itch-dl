from typing import Any

import requests
import logging
from requests import Session
from urllib.parse import urlsplit
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from .config import Settings
from .consts import ITCH_API


class ItchApiClient:
    def __init__(self, settings: Settings, base_url: str | None = None) -> None:
        self.base_url = base_url or ITCH_API
        self.api_key = settings.api_key

        self.requests = Session()
        self.requests.headers["User-Agent"] = settings.user_agent

        if settings.cookie:
            self.requests.cookies.set("itchio", settings.cookie)
        if settings.cf_clearance:
            self.requests.cookies.set("cf-clearance", settings.cf_clearance)

        retry_strategy = Retry(
            total=5,
            backoff_factor=10,
            allowed_methods=["HEAD", "GET"],
            status_forcelist=[429, 500, 502, 503, 504],
        )

        # No timeouts - set them explicitly on API calls below!
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.requests.mount("https://", adapter)
        self.requests.mount("http://", adapter)

    def get(
        self,
        endpoint: str,
        append_api_key: bool = True,
        guess_encoding: bool = False,
        **kwargs: Any,  # noqa: ANN401
    ) -> requests.Response:
        """Wrapper around `requests.get`.

        :param endpoint: Path to fetch on the specified base URL.
        :param append_api_key: Send an authenticated API request.
        :param guess_encoding: Let requests guess the response encoding.
        """
        if append_api_key:
            params = kwargs.get("data") or {}

            if "api_key" not in params:
                params["api_key"] = self.api_key

            kwargs["data"] = params

        # Use the API endpoint if not requested otherwise:
        url = endpoint if endpoint.startswith("https://") else self.base_url + endpoint

        # HACK: Send requests to itch.io but pass Host: full.itch.io if the subdomain
        # contains underscores (workaround for HTTPS issues on dj_link.itch.io/...)
        parsed_url = urlsplit(url)
        if parsed_url.netloc.endswith(".itch.io") and "_" in parsed_url.netloc:
            self.requests.headers["Host"] = parsed_url.netloc
            url = parsed_url._replace(netloc="itch.io").geturl()

        r = self.requests.get(url, **kwargs)

        if "Host" in self.requests.headers:
            self.requests.headers.pop("Host")

        # Itch always returns UTF-8 pages and API responses. Force
        # UTF-8 everywhere, except for binary file downloads.
        if not guess_encoding:
            r.encoding = "utf-8"

        if not r.ok and "challenges.cloudflare.com" in r.text:
            logging.warning(
                "WARNING: Request failed - you are likely getting hit with a Cloudflare challenge.\n"
                "See https://github.com/DragoonAethis/itch-dl/wiki/Cloudflare-Challenge for more info."
            )

        return r
