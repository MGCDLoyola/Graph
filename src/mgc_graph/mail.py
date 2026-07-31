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

    def send(
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
        save_to_sent_items: bool = True,
    ) -> None:
        message: dict[str, Any] = {
            "subject": subject,
            "body": {
                "contentType": "HTML" if is_html else "Text",
                "content": body,
            },
            "toRecipients": self._as_recipients(to),
        }

        if cc:
            message["ccRecipients"] = self._as_recipients(cc)
        if bcc:
            message["bccRecipients"] = self._as_recipients(bcc)
        if reply_to:
            message["replyTo"] = self._as_recipients(reply_to)

        if attachments:
            message["attachments"] = [
                self._build_attachment(item) for item in attachments
            ]

        try:
            self._client.post(
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

    @staticmethod
    def _as_recipients(value: str | list[str]) -> list[dict[str, Any]]:
        if isinstance(value, str):
            value = [value]
        return [
            {"emailAddress": {"address": address}}
            for address in value
        ]

    @staticmethod
    def _build_attachment(item: Any) -> dict[str, Any]:
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