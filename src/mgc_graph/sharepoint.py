from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .client import GraphClient
from .exceptions import RequestError, SharePointError


class SharePoint:
    def __init__(
        self,
        client: GraphClient,
        site_url: str,
    ) -> None:
        self._client = client
        self._site_url = site_url

        self._site_id: str | None = None
        self._list_ids: dict[str, str] = {}

    def get_list_items(
        self,
        list_name: str,
        *,
        expand_fields: bool = True,
        select_fields: list[str] | None = None,
        top: int | None = None,
    ) -> list[dict[str, Any]]:
        list_id = self._get_list_id(list_name)
        endpoint = f"/sites/{self.site_id}/lists/{list_id}/items"

        params: dict[str, Any] = {}
        expand_parts = ["fields"] if expand_fields else []

        if select_fields:
            expand_parts.append(f"fields($select={','.join(select_fields)})")

        if expand_parts:
            params["$expand"] = ",".join(expand_parts)

        if top:
            params["$top"] = top

        items = list(self._client.get_paginated(endpoint, params=params))
        return [item.get("fields", item) for item in items]

    def create_item(
        self,
        list_name: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        list_id = self._get_list_id(list_name)
        try:
            response = self._client.post(
                f"/sites/{self.site_id}/lists/{list_id}/items",
                json={"fields": fields},
            )
        except RequestError as exc:
            raise SharePointError(
                f"Error al crear elemento en la lista '{list_name}': {exc}"
            ) from exc
        return response.get("fields", response)

    def update_item(
        self,
        list_name: str,
        item_id: str,
        fields: dict[str, Any],
    ) -> None:
        list_id = self._get_list_id(list_name)
        try:
            self._client.patch(
                f"/sites/{self.site_id}/lists/{list_id}/items/{item_id}/fields",
                json=fields,
            )
        except RequestError as exc:
            raise SharePointError(
                f"Error al actualizar el elemento {item_id} "
                f"de la lista '{list_name}': {exc}"
            ) from exc

    def delete_item(
        self,
        list_name: str,
        item_id: str,
    ) -> None:
        list_id = self._get_list_id(list_name)
        try:
            self._client.delete(
                f"/sites/{self.site_id}/lists/{list_id}/items/{item_id}"
            )
        except RequestError as exc:
            raise SharePointError(
                f"Error al eliminar el elemento {item_id} "
                f"de la lista '{list_name}': {exc}"
            ) from exc

    @property
    def site_id(self) -> str:
        if self._site_id is None:
            self._site_id = self._resolve_site_id()
        return self._site_id

    def _resolve_site_id(self) -> str:
        parsed = urlparse(self._site_url)
        hostname = parsed.netloc
        server_relative_path = parsed.path.rstrip("/")

        if not hostname or not server_relative_path:
            raise SharePointError(
                f"URL de sitio inválida: {self._site_url!r}. "
                f"Se espera algo como "
                f"'https://empresa.sharepoint.com/sites/Nombre'."
            )

        try:
            response = self._client.get(
                f"/sites/{hostname}:{server_relative_path}"
            )
        except RequestError as exc:
            raise SharePointError(
                f"No se pudo resolver el sitio {self._site_url!r}: {exc}"
            ) from exc

        return response["id"]

    def _get_list_id(self, list_name: str) -> str:
        if list_name in self._list_ids:
            return self._list_ids[list_name]

        escaped_name = list_name.replace("'", "''")
        try:
            response = self._client.get(
                f"/sites/{self.site_id}/lists",
                params={"$filter": f"displayName eq '{escaped_name}'"},
            )
        except RequestError as exc:
            raise SharePointError(
                f"No se pudo buscar la lista '{list_name}': {exc}"
            ) from exc

        results = response.get("value", [])

        if not results:
            raise SharePointError(
                f"No se encontró la lista '{list_name}' en el sitio "
                f"{self._site_url!r}."
            )

        if len(results) > 1:
            raise SharePointError(
                f"Se encontraron múltiples listas con el nombre '{list_name}'. "
                f"Los nombres deben ser únicos."
            )

        list_id = results[0]["id"]
        self._list_ids[list_name] = list_id
        return list_id