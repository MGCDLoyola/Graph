from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .client import GraphClient


class Mailbox:

    def __init__(
        self,
        client: GraphClient,
        mailbox: str,
    ) -> None:
        self._client = client
        self._mailbox = mailbox

    def buscar_enviados(
        self,
        asunto: str,
        fecha: date,
    ) -> list[dict[str, Any]]:

        respuesta = self._client.obtener(
            f"/users/{self._mailbox}/mailFolders/SentItems/messages",
            params={
                "$filter": (
                    f"sentDateTime ge {fecha.isoformat()}T00:00:00Z "
                    f"and sentDateTime lt {fecha.isoformat()}T23:59:59Z "
                    f"and contains(subject,'{asunto}')"
                ),
            },
        )

        return respuesta.get("value", [])

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