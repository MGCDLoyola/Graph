from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .auth import GraphAuth
from .constants import DEFAULT_TIMEOUT, GRAPH_URL
from .exceptions import RequestError

logger = logging.getLogger(__name__)


class GraphClient:
    def __init__(self, auth: GraphAuth) -> None:
        self._auth = auth
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PATCH", "PUT", "DELETE"],
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._auth.session.mount("https://", adapter)
        self._auth.session.mount("http://", adapter)

    def get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request("GET", endpoint, params=params)

    def post(
        self,
        endpoint: str,
        *,
        json: Any = None,
    ) -> dict[str, Any]:
        return self._request("POST", endpoint, json=json)

    def patch(
        self,
        endpoint: str,
        *,
        json: Any = None,
    ) -> dict[str, Any]:
        return self._request("PATCH", endpoint, json=json)

    def put(
        self,
        endpoint: str,
        *,
        json: Any = None,
    ) -> dict[str, Any]:
        return self._request("PUT", endpoint, json=json)

    def delete(self, endpoint: str) -> None:
        self._request("DELETE", endpoint)

    def get_paginated(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        url: str | None = self._build_url(endpoint)

        while url:
            logger.debug("Paginando: %s", url)
            response = self._auth.session.request(
                method="GET",
                url=url,
                headers=self._auth.headers,
                params=params if url == self._build_url(endpoint) else None,
                timeout=DEFAULT_TIMEOUT,
            )

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RequestError(
                    f"GET {url}\n{response.status_code}: {response.text}"
                ) from exc

            data: dict[str, Any] = response.json()
            yield from data.get("value", [])

            url = data.get("@odata.nextLink")
            # Params solo en la primera petición; nextLink ya los incluye

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = self._build_url(endpoint)
        logger.debug("%s %s", method, url)

        response = self._auth.session.request(
            method=method,
            url=url,
            headers=self._auth.headers,
            timeout=DEFAULT_TIMEOUT,
            **kwargs,
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RequestError(
                f"{method} {endpoint}\n{response.status_code}: {response.text}"
            ) from exc

        if response.status_code == 204:
            return {}

        if not response.content:
            return {}

        return response.json()

    @staticmethod
    def _build_url(endpoint: str) -> str:
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        return f"{GRAPH_URL}{endpoint}"