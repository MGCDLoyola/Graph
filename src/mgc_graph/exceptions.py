class GraphError(Exception):
    """Excepción base de la librería."""


class AuthenticationError(GraphError):
    """Error durante la autenticación."""


class RequestError(GraphError):
    """Error al consumir Microsoft Graph."""


class SharePointError(GraphError):
    """Error relacionado con SharePoint."""


class MailError(GraphError):
    """Error relacionado con el envío en Outlook."""


class MailboxError(GraphError):
    """Error relacionado con las carpetas de Outlook."""