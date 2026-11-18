from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any

from .client import GraphClient
from .constants import UPLOAD_CHUNK_SIZE
from .exceptions import MailError, RequestError

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_SIZE = 3 * 1024 * 1024
MAX_UPLOAD_SIZE = 150 * 1024 * 1024


class Mail:
    def __init__(
        self,
        client: GraphClient,
        sender: str,
    ) -> None:
        self._client = client
        self._sender = sender

    def crear(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        *,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        reply_to: str | list[str] | None = None,
        attachments: list[Any] | None = None,
        is_html: bool = True,
    ) -> str:

        adjuntos = self._leer_adjuntos(attachments)
        chicos = [a for a in adjuntos if len(a[1]) <= MAX_ATTACHMENT_SIZE]
        grandes = [a for a in adjuntos if len(a[1]) > MAX_ATTACHMENT_SIZE]

        message = self._armar_mensaje(
            to, subject, body,
            cc=cc, bcc=bcc, reply_to=reply_to, attachments=chicos, is_html=is_html
        )

        try:
            respuesta = self._client.crear(
                f"/users/{self._sender}/messages",
                json=message,
            )
        except RequestError as exc:
            raise MailError(
                f"Error al crear borrador desde {self._sender}: {exc}"
            ) from exc

        message_id = respuesta["id"]

        try:
            for nombre, contenido in grandes:
                self._subir_adjunto(message_id, nombre, contenido)
        except Exception as exc:
            self._descartar_borrador(message_id)
            if isinstance(exc, MailError):
                raise
            raise MailError(
                f"Error al subir adjunto grande desde {self._sender}: {exc}"
            ) from exc

        return message_id

    def enviar(
        self,
        to: str | list[str] | None = None,
        subject: str | None = None,
        body: str | None = None,
        *,
        message_id: str | None = None,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        reply_to: str | list[str] | None = None,
        attachments: list[Any] | None = None,
        is_html: bool = True,
        save_to_sent_items: bool = True,
    ) -> None:

        if message_id is not None:
            if to is not None or subject is not None or body is not None:
                raise MailError(
                    "enviar() recibe o 'message_id', o 'to'/'subject'/'body' — no ambos."
                )

            self._despachar_borrador(message_id)
            return

        if to is None or subject is None or body is None:
            raise MailError(
                "enviar() requiere 'to', 'subject' y 'body' cuando no se pasa 'message_id'."
            )

        adjuntos = self._leer_adjuntos(attachments)

        if any(len(contenido) > MAX_ATTACHMENT_SIZE for _, contenido in adjuntos):
            borrador = self.crear(
                to, subject, body,
                cc=cc, bcc=bcc, reply_to=reply_to, attachments=adjuntos, is_html=is_html
            )
            self._despachar_borrador(borrador)
            return

        message = self._armar_mensaje(
            to, subject, body,
            cc=cc, bcc=bcc, reply_to=reply_to, attachments=adjuntos, is_html=is_html
        )

        try:
            self._client.crear(
                f"/users/{self._sender}/sendMail",
                json={
                    "message": message,
                    "saveToSentItems": save_to_sent_items,
                },
            )
            logger.info("Correo enviado desde %s a %s", self._sender, to)
        except RequestError as exc:
            raise MailError(
                f"Error al enviar correo desde {self._sender}: {exc}"
            ) from exc

    def _despachar_borrador(self, message_id: str) -> None:
        try:
            self._client.crear(
                f"/users/{self._sender}/messages/{message_id}/send"
            )
            logger.info("Correo despachado desde %s (id=%s)", self._sender, message_id)
        except RequestError as exc:
            raise MailError(
                f"Error al enviar el borrador {message_id} desde {self._sender}: {exc}"
            ) from exc

    def _descartar_borrador(self, message_id: str) -> None:
        try:
            self._client.eliminar(f"/users/{self._sender}/messages/{message_id}")
        except Exception:
            logger.warning("No se pudo eliminar el borrador %s", message_id)

    def _subir_adjunto(self, message_id: str, nombre: str, contenido: bytes) -> None:
        total = len(contenido)

        if total > MAX_UPLOAD_SIZE:
            raise MailError(
                f"El adjunto '{nombre}' ({total} bytes) excede el límite "
                f"de {MAX_UPLOAD_SIZE} bytes de Graph."
            )

        content_type = mimetypes.guess_type(nombre)[0] or "application/octet-stream"

        try:
            sesion = self._client.crear(
                f"/users/{self._sender}/messages/{message_id}"
                f"/attachments/createUploadSession",
                json={
                    "AttachmentItem": {
                        "attachmentType": "file",
                        "name": nombre,
                        "size": total,
                        "contentType": content_type,
                    }
                },
            )

            url = sesion["uploadUrl"]

            for inicio in range(0, total, UPLOAD_CHUNK_SIZE):
                fin = min(inicio + UPLOAD_CHUNK_SIZE, total) - 1
                self._client.subir_fragmento(
                    url, contenido[inicio:fin + 1], inicio, fin, total
                )
        except RequestError as exc:
            raise MailError(
                f"Error al subir el adjunto '{nombre}' desde {self._sender}: {exc}"
            ) from exc

        logger.info("Adjunto grande subido: %s (%d bytes)", nombre, total)

    @staticmethod
    def _leer_adjuntos(attachments: list[Any] | None) -> list[tuple[str, bytes]]:
        resultado: list[tuple[str, bytes]] = []

        for item in attachments or []:
            if isinstance(item, tuple):
                name, content = item
                if not isinstance(content, (bytes, bytearray)):
                    raise MailError(
                        f"El adjunto en memoria '{name}' debe ser bytes."
                    )
            else:
                path = Path(item)
                if not path.is_file():
                    raise MailError(f"No se encontró el archivo: {path}")
                name = path.name
                content = path.read_bytes()

            resultado.append((name, bytes(content)))

        return resultado

    def _armar_mensaje(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        *,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        reply_to: str | list[str] | None = None,
        attachments: list[tuple[str, bytes]] | None = None,
        is_html: bool = True,
    ) -> dict[str, Any]:

        message: dict[str, Any] = {
            "subject": subject,
            "body": {
                "contentType": "HTML" if is_html else "Text",
                "content": body,
            },
            "toRecipients": self._a_destinatarios(to),
        }

        if cc:
            message["ccRecipients"] = self._a_destinatarios(cc)
        if bcc:
            message["bccRecipients"] = self._a_destinatarios(bcc)
        if reply_to:
            message["replyTo"] = self._a_destinatarios(reply_to)

        if attachments:
            message["attachments"] = [
                self._construir_adjunto(name, content) for name, content in attachments
            ]

        return message

    @staticmethod
    def _a_destinatarios(value: str | list[str]) -> list[dict[str, Any]]:
        if isinstance(value, str):
            value = [value]
        return [
            {"emailAddress": {"address": address}}
            for address in value
        ]

    @staticmethod
    def _construir_adjunto(name: str, content: bytes) -> dict[str, Any]:
        content_type = (
            mimetypes.guess_type(name)[0] or "application/octet-stream"
        )

        return {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": name,
            "contentType": content_type,
            "contentBytes": base64.b64encode(content).decode("ascii"),
        }