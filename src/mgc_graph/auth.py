from __future__ import annotations

import logging
import threading
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
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret

        self._token: str | None = None
        self._expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self._lock = threading.Lock()

        self._session = requests.Session()

    @property
    def session(self) -> requests.Session:
        return self._session

    @property
    def token(self) -> str:
        with self._lock:
            if self._token is None or datetime.now(timezone.utc) >= self._expires_at:
                self._authenticate()
            return self._token

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _authenticate(self) -> None:
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
        except requests.RequestException as exc:
            raise AuthenticationError(
                f"Error al autenticarse con Microsoft Graph: {exc}"
            ) from exc

        data = response.json()
        self._token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
        logger.debug("Token refrescado correctamente.")