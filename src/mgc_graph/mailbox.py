from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

from .client import GraphClient
from .exceptions import MailboxError, RequestError

CarpetaConocida = Literal[
    "Inbox",
    "Drafts",
    "SentItems",
    "DeletedItems",
    "Outbox",
    "JunkEmail",
    "Archive",
]


class Mailbox:

    def __init__(
        self,
        client: GraphClient,
        mailbox: str,
    ) -> None:
        self._client = client
        self._mailbox = mailbox

    def buscar(
        self,
        asunto: str,
        fecha: date,
        carpeta: CarpetaConocida | str,
    ) -> list[dict[str, Any]]:

        respuesta = self._client.obtener(
            f"/users/{self._mailbox}/mailFolders/{carpeta}/messages",
            params={
                "$filter": (
                    f"sentDateTime ge {fecha.isoformat()}T00:00:00Z "
                    f"and sentDateTime lt {fecha.isoformat()}T23:59:59Z "
                    f"and contains(subject,'{asunto}')"
                ),
            },
        )

        return respuesta.get("value", [])

    def obtener_id_carpeta(self, nombre_visible: str) -> str:

        respuesta = self._client.obtener(
            f"/users/{self._mailbox}/mailFolders",
            params={"$filter": f"displayName eq '{nombre_visible}'"},
        )

        resultados = respuesta.get("value", [])

        if not resultados:
            raise MailboxError(
                f"No se encontró la carpeta '{nombre_visible}' en {self._mailbox}."
            )

        return resultados[0]["id"]

    def descargar_correo(
        self,
        message_id: str,
        destino: Path,
    ) -> None:

        contenido = self._client.descargar(
            f"/users/{self._mailbox}/messages/{message_id}/$value"
        )

        destino.parent.mkdir(parents=True, exist_ok=True)

        destino.write_bytes(contenido)

    def eliminar(self, message_id: str) -> None:

        try:
            self._client.eliminar(
                f"/users/{self._mailbox}/messages/{message_id}"
            )
        except RequestError as exc:
            raise MailboxError(
                f"Error al eliminar el mensaje {message_id} de {self._mailbox}: {exc}"
            ) from exc