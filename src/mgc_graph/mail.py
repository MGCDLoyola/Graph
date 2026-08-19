from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any

from .client import GraphClient
from .exceptions import MailError, RequestError

logger = logging.getLogger(__name__)

# Límite de Graph para fileAttachment en sendMail (por archivo)
MAX_ATTACHMENT_SIZE = 3 * 1024 * 1024


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

        message = self._armar_mensaje(
            to, subject, body,
            cc=cc, bcc=bcc, reply_to=reply_to, attachments=attachments, is_html=is_html
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

        return respuesta["id"]

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

            try:
                self._client.crear(
                    f"/users/{self._sender}/messages/{message_id}/send"
                )
                logger.info("Correo despachado desde %s (id=%s)", self._sender, message_id)
            except RequestError as exc:
                raise MailError(
                    f"Error al enviar el borrador {message_id} desde {self._sender}: {exc}"
                ) from exc

            return

        if to is None or subject is None or body is None:
            raise MailError(
                "enviar() requiere 'to', 'subject' y 'body' cuando no se pasa 'message_id'."
            )

        message = self._armar_mensaje(
            to, subject, body,
            cc=cc, bcc=bcc, reply_to=reply_to, attachments=attachments, is_html=is_html
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

    def _armar_mensaje(
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
                self._construir_adjunto(item) for item in attachments
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
    def _construir_adjunto(item: Any) -> dict[str, Any]:
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

        if len(content) > MAX_ATTACHMENT_SIZE:
            raise MailError(
                f"El adjunto '{name}' ({len(content)} bytes) excede el límite "
                f"de {MAX_ATTACHMENT_SIZE} bytes. Para archivos grandes usa "
                f"uploadSession en lugar de sendMail."
            )

        content_type = (
            mimetypes.guess_type(name)[0] or "application/octet-stream"
        )

        return {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": name,
            "contentType": content_type,
            "contentBytes": base64.b64encode(content).decode("ascii"),
        }