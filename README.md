Wrapper interno de Microsoft Graph API para los proyectos de MGC México.

Incluye:

- **`GraphAuth`** — autenticación OAuth2 (client credentials) contra Azure AD, con caché y renovación automática del token.
- **`GraphClient`** — cliente HTTP genérico (`get`/`post`/`patch`/`put`/`delete`) contra Microsoft Graph.
- **`Mail`** — envío de correos (con adjuntos) vía Outlook.
- **`SharePoint`** — lectura y escritura de listas de SharePoint.

## Instalación

Dentro de tus proyectos, agrégalo como dependencia desde git:

```bash
pip install git+https://github.com/MGC-Mexico/mgc-graph.git
```

O en modo editable si lo estás desarrollando localmente:

```bash
pip install -e /ruta/a/mgc-graph
```

## Autenticación

Todo parte de `GraphAuth` + `GraphClient`, que se reutilizan para `Mail` y `SharePoint`:

```python
from mgc_graph import GraphAuth, GraphClient

auth = GraphAuth(
    tenant_id="...",
    client_id="...",
    client_secret="...",
)
client = GraphClient(auth)
```

Se recomienda tomar `tenant_id`, `client_id` y `client_secret` de variables de entorno, no dejarlos escritos en el código.

## Enviar correos (`Mail`)

```python
from mgc_graph import Mail

mail = Mail(client, sender="notificaciones@mgcmexico.com")

mail.enviar(
    to="destinatario@ejemplo.com",
    subject="Reporte mensual",
    body="<p>Adjunto el reporte.</p>",
    cc=["copia@ejemplo.com"],
    attachments=[
        "C:/reportes/estado.pdf",              # ruta en disco
        ("resumen.txt", b"contenido en memoria"),  # bytes en memoria
    ],
)
```

- `sender` es la cuenta remitente. Se deja fija por proyecto pero como parámetro, no hardcodeada dentro de la librería.
- `attachments` acepta rutas de archivo (`str`/`Path`) y/o tuplas `(nombre_archivo, bytes)` para contenido generado en memoria, mezclados en la misma lista.
- Si algo falla, se lanza `MailError`.

## Leer y escribir listas de SharePoint (`SharePoint`)

```python
from mgc_graph import SharePoint

sp = SharePoint(client, site_url="https://mgcmexico.sharepoint.com/sites/Cobranza")

# Leer
items = sp.obtener_elementos("Expedientes")

# Crear
sp.crear_elemento("Expedientes", {"Title": "Cliente Nuevo", "Estatus": "Pendiente"})

# Actualizar
sp.actualizar_elemento("Expedientes", item_id="123", fields={"Estatus": "Cerrado"})

# Eliminar
sp.eliminar_elemento("Expedientes", item_id="123")
```

- `site_url` es la URL completa del sitio; la librería resuelve internamente el `site_id` y lo cachea (igual que el `list_id` de cada lista que uses), así que no hay que buscarlos a mano.
- Si algo falla (sitio no encontrado, lista no encontrada, etc.), se lanza `SharePointError`.

## Estructura del paquete

```
src/mgc_graph/
├── auth.py         # GraphAuth
├── client.py       # GraphClient
├── constants.py
├── exceptions.py    # GraphError y subclases
├── mail.py          # Mail
└── sharepoint.py     # SharePoint
```

## Excepciones

Todas heredan de `GraphError`:

- `AuthenticationError` — falla al autenticarse contra Azure AD.
- `RequestError` — falla genérica al llamar Microsoft Graph.
- `MailError` — falla específica de `Mail`.
- `SharePointError` — falla específica de `SharePoint`.