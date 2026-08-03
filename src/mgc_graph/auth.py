from __future__ import annotations

import logging
import threading
import urllib3
from datetime import datetime, timedelta, timezone

import requests

from .constants import TOKEN_SCOPE
from .exceptions import AuthenticationError

logger = logging.getLogger(__name__)


class GraphAuth:
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        *,
        verify_ssl: bool = True,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret

        self._token: str | None = None
        self._expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self._lock = threading.Lock()

        self._session = requests.Session()
        self._session.verify = verify_ssl

        if not verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    @property
    def sesion(self) -> requests.Session:
        return self._session

    @property
    def token(self) -> str:
        with self._lock:
            if self._token is None or datetime.now(timezone.utc) >= self._expires_at:
                self._autenticar()
            return self._token

    @property
    def encabezados(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _autenticar(self) -> None:
        logger.debug("Refrescando token de Microsoft Graph...")
        try:
            response = self._session.post(
                f"https://login.microsoftonline.com/"
                f"{self._tenant_id}/oauth2/v2.0/token",
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": TOKEN_SCOPE,
                    "grant_type": "client_credentials",
                },
                timeout=30,
            )
            response.raise_for_status()

        except requests.HTTPError as exc:
            error_detail = ""
            try:
                error_body = exc.response.json()
                error_code = error_body.get("error", "unknown")
                error_desc = error_body.get("error_description", "Sin descripción")
                error_detail = f"\nCódigo: {error_code}\nDescripción: {error_desc}"
            except Exception:
                error_detail = f"\nRespuesta: {exc.response.text}"

            raise AuthenticationError(
                f"Error al autenticarse con Microsoft Graph (HTTP {exc.response.status_code})."
                f"{error_detail}"
            ) from exc

        except requests.RequestException as exc:
            raise AuthenticationError(
                f"Error de red al autenticarse con Microsoft Graph: {exc}"
            ) from exc

        data = response.json()
        self._token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
        logger.debug("Token refrescado correctamente.")