from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .auth import GraphAuth
from .constants import DEFAULT_TIMEOUT, GRAPH_URL, UPLOAD_TIMEOUT
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
        self._auth.sesion.mount("https://", adapter)
        self._auth.sesion.mount("http://", adapter)

    def obtener(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._request("GET", endpoint, params=params, extra_headers=extra_headers)

    def descargar(
        self,
        endpoint: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> bytes:
        url = self._build_url(endpoint)

        logger.debug("DESCARGA %s", url)

        headers = {
            **self._auth.encabezados,
            **(extra_headers or {})
        }

        response = self._auth.sesion.request(
            method="GET",
            url=url,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            verify=self._auth.sesion.verify,
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RequestError(
                f"GET {endpoint}\n{response.status_code}: {response.text}"
            ) from exc

        return response.content

    def crear(
        self,
        endpoint: str,
        *,
        json: Any = None,
    ) -> dict[str, Any]:
        return self._request("POST", endpoint, json=json)

    def actualizar(
        self,
        endpoint: str,
        *,
        json: Any = None,
    ) -> dict[str, Any]:
        return self._request("PATCH", endpoint, json=json)

    def reemplazar(
        self,
        endpoint: str,
        *,
        json: Any = None,
    ) -> dict[str, Any]:
        return self._request("PUT", endpoint, json=json)

    def subir_fragmento(
        self,
        url: str,
        datos: bytes,
        inicio: int,
        fin: int,
        total: int,
    ) -> dict[str, Any]:
        logger.debug("SUBIDA %s bytes %d-%d/%d", url, inicio, fin, total)

        response = self._auth.sesion.request(
            method="PUT",
            url=url,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Range": f"bytes {inicio}-{fin}/{total}",
            },
            data=datos,
            timeout=UPLOAD_TIMEOUT,
            verify=self._auth.sesion.verify,
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RequestError(
                f"PUT fragmento {inicio}-{fin}/{total}\n"
                f"{response.status_code}: {response.text}"
            ) from exc

        if not response.content:
            return {}

        return response.json()

    def eliminar(self, endpoint: str) -> None:
        self._request("DELETE", endpoint)

    def obtener_paginado(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        max_items: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        url: str | None = self._build_url(endpoint)
        count = 0
        headers = {**self._auth.encabezados, **(extra_headers or {})}

        while url:
            logger.debug("Paginando: %s", url)
            response = self._auth.sesion.request(
                method="GET",
                url=url,
                headers=headers,
                params=params if url == self._build_url(endpoint) else None,
                timeout=DEFAULT_TIMEOUT,
                verify=self._auth.sesion.verify,
            )

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RequestError(
                    f"GET {url}\n{response.status_code}: {response.text}"
                ) from exc

            data: dict[str, Any] = response.json()

            for item in data.get("value", []):
                yield item
                count += 1
                if max_items is not None and count >= max_items:
                    return

            url = data.get("@odata.nextLink")

    def obtener_delta(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        url: str | None = self._build_url(endpoint)
        items: list[dict[str, Any]] = []
        delta_link: str | None = None
        first = True

        while url:
            logger.debug("Paginando delta: %s", url)
            response = self._auth.sesion.request(
                method="GET",
                url=url,
                headers=self._auth.encabezados,
                params=params if first else None,
                timeout=DEFAULT_TIMEOUT,
                verify=self._auth.sesion.verify,
            )
            first = False

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RequestError(
                    f"GET {url}\n{response.status_code}: {response.text}"
                ) from exc

            data: dict[str, Any] = response.json()
            items.extend(data.get("value", []))

            delta_link = data.get("@odata.deltaLink", delta_link)
            url = data.get("@odata.nextLink")

        if delta_link is None:
            raise RequestError(
                "La respuesta de delta no incluyó '@odata.deltaLink'; "
                "no se pudo capturar el token para la siguiente sincronización."
            )

        return items, delta_link

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        extra_headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = self._build_url(endpoint)
        logger.debug("%s %s", method, url)

        headers = {**self._auth.encabezados, **(extra_headers or {})}

        response = self._auth.sesion.request(
            method=method,
            url=url,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            verify=self._auth.sesion.verify,
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