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
        self._columns_cache: dict[str, list[dict[str, Any]]] = {}

    def obtener_elementos(
        self,
        list_name: str,
        *,
        expand_fields: bool = True,
        select_fields: list[str] | None = None,
        top: int | None = None,
        odata_filter: str | None = None,
        rename_to_display_names: bool = False,
    ) -> list[dict[str, Any]]:

        list_id = self._obtener_id_lista(list_name)

        endpoint = f"/sites/{self.id_sitio}/lists/{list_id}/items"

        params: dict[str, Any] = {}
        expand_parts = ["fields"] if expand_fields else []

        if select_fields:
            expand_parts.append(f"fields($select={','.join(select_fields)})")

        if expand_parts:
            params["$expand"] = ",".join(expand_parts)

        if top:
            params["$top"] = min(top, 200)

        if odata_filter:
            params["$filter"] = odata_filter

        extra_headers = (
            {"Prefer": "HonorNonIndexedQueriesWarningMayFailRandomly"}
            if odata_filter
            else None
        )

        items = list(
            self._client.obtener_paginado(
                endpoint,
                params=params,
                max_items=top,
                extra_headers=extra_headers,
            )
        )
        result = [item.get("fields", item) for item in items]

        if rename_to_display_names:
            mapping = self.obtener_nombres_columnas(list_name)
            result = [
                {mapping.get(key, key): value for key, value in row.items()}
                for row in result
            ]

        return result

    def obtener_columnas(self, list_name: str) -> list[dict[str, Any]]:
        if list_name in self._columns_cache:
            return self._columns_cache[list_name]

        list_id = self._obtener_id_lista(list_name)
        try:
            columns = list(
                self._client.obtener_paginado(
                    f"/sites/{self.id_sitio}/lists/{list_id}/columns"
                )
            )
        except RequestError as exc:
            raise SharePointError(
                f"No se pudieron obtener las columnas de la lista '{list_name}': {exc}"
            ) from exc

        self._columns_cache[list_name] = columns
        return columns

    def obtener_nombres_columnas(
        self,
        list_name: str,
        *,
        include_hidden: bool = False,
        include_read_only: bool = True,
    ) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for column in self.get_list_columns(list_name):
            if not include_hidden and column.get("hidden"):
                continue
            if not include_read_only and column.get("readOnly"):
                continue

            internal_name = column.get("name")
            display_name = column.get("displayName")
            if internal_name and display_name:
                mapping[internal_name] = display_name

        return mapping

    def obtener_elementos_delta(
        self,
        list_name: str,
        *,
        delta_link: str | None = None,
        select_fields: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], str]:

        if delta_link:
            endpoint = delta_link
            params = None
        else:
            list_id = self._obtener_id_lista(list_name)
            endpoint = f"/sites/{self.id_sitio}/lists/{list_id}/items/delta"

            expand_parts = ["fields"]
            if select_fields:
                expand_parts = [f"fields($select={','.join(select_fields)})"]

            params = {"$expand": ",".join(expand_parts)}

        try:
            raw_items, new_delta_link = self._client.obtener_delta(endpoint, params=params)
        except RequestError as exc:
            raise SharePointError(
                f"Error al obtener el delta de la lista '{list_name}': {exc}"
            ) from exc

        items: list[dict[str, Any]] = []
        for item in raw_items:
            if "@removed" in item:
                items.append({"id": item.get("id"), "removed": True})
            else:
                items.append({"id": item.get("id"), **item.get("fields", item)})

        return items, new_delta_link

    def crear_elemento(
        self,
        list_name: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        list_id = self._obtener_id_lista(list_name)
        try:
            response = self._client.crear(
                f"/sites/{self.id_sitio}/lists/{list_id}/items",
                json={"fields": fields},
            )
        except RequestError as exc:
            raise SharePointError(
                f"Error al crear elemento en la lista '{list_name}': {exc}"
            ) from exc
        return response.get("fields", response)

    def actualizar_elemento(
        self,
        list_name: str,
        item_id: str,
        fields: dict[str, Any],
    ) -> None:
        list_id = self._obtener_id_lista(list_name)
        try:
            self._client.actualizar(
                f"/sites/{self.id_sitio}/lists/{list_id}/items/{item_id}/fields",
                json=fields,
            )
        except RequestError as exc:
            raise SharePointError(
                f"Error al actualizar el elemento {item_id} "
                f"de la lista '{list_name}': {exc}"
            ) from exc

    def eliminar_elemento(
        self,
        list_name: str,
        item_id: str,
    ) -> None:
        list_id = self._obtener_id_lista(list_name)
        try:
            self._client.eliminar(
                f"/sites/{self.id_sitio}/lists/{list_id}/items/{item_id}"
            )
        except RequestError as exc:
            raise SharePointError(
                f"Error al eliminar el elemento {item_id} "
                f"de la lista '{list_name}': {exc}"
            ) from exc

    @property
    def id_sitio(self) -> str:
        if self._site_id is None:
            self._site_id = self._resolver_id_sitio()
        return self._site_id

    def _resolver_id_sitio(self) -> str:
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
            response = self._client.obtener(
                f"/sites/{hostname}:{server_relative_path}"
            )
        except RequestError as exc:
            raise SharePointError(
                f"No se pudo resolver el sitio {self._site_url!r}: {exc}"
            ) from exc

        return response["id"]

    def _obtener_id_lista(self, list_name: str) -> str:
        if list_name in self._list_ids:
            return self._list_ids[list_name]

        escaped_name = list_name.replace("'", "''")
        try:
            response = self._client.obtener(
                f"/sites/{self.id_sitio}/lists",
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