# Ollomi con APIs de IA externas

Este ejemplo autónomo descarga una imagen del backend publicada por **el mismo
fork de Ollomi** que se va a instalar. Ejecuta PostgreSQL/pgvector, Redis,
Typesense, la API y los workers en Docker. No define servicios Whisper u Ollama,
no descarga pesos y no necesita `selfhost-data/models`. Antes de usarlo, el
fork debe haber publicado y validado una release; mientras tanto use la
instalación compilada desde código.

En las releases oficiales de `borborborja/ollomi`, descargue mejor
`ollomi-backend.tar.gz`: incluye este Compose, los scripts de copia y una
`.env.example` que ya fija el propietario y la etiqueta de esa release.

```bash
mkdir ollomi && cd ollomi
curl -LO https://raw.githubusercontent.com/YOUR_GITHUB_OWNER/ollomi/main/deploy/examples/external-api/compose.yaml
curl -Lo .env https://raw.githubusercontent.com/YOUR_GITHUB_OWNER/ollomi/main/deploy/examples/external-api/env.example
mkdir -p scripts
curl -Lo scripts/selfhost_backup.sh https://raw.githubusercontent.com/YOUR_GITHUB_OWNER/ollomi/main/scripts/selfhost_backup.sh
curl -Lo scripts/selfhost_restore.sh https://raw.githubusercontent.com/YOUR_GITHUB_OWNER/ollomi/main/scripts/selfhost_restore.sh
chmod 700 scripts/selfhost_backup.sh scripts/selfhost_restore.sh
chmod 600 .env
```

Edite `.env`, cambie todos los valores `CHANGE_ME`, incluidos
`OLLOMI_IMAGE_OWNER` y `OLLOMI_IMAGE_TAG`, indique en
`OLLOMI_PUBLIC_URL` la IP o el dominio que utilizará el teléfono y configure al
menos un perfil STT, chat y embeddings. Después valide e inicie:

```bash
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
curl "http://127.0.0.1:$(sed -n 's/^OLLOMI_PORT=//p' .env)/health"
```

La respuesta debe ser `{"status":"ok"}`. Inicie sesión desde Android con
`OLLOMI_PUBLIC_URL`, `OLLOMI_ADMIN_EMAIL` y la contraseña inicial. Una vez
comprobado el acceso, elimine `OLLOMI_ADMIN_PASSWORD` y retírela de los
contenedores:

```bash
sed -i '/^OLLOMI_ADMIN_PASSWORD=/d' .env
docker compose up -d --force-recreate migrate ollomi-api worker scheduler
```

Para acceso público, configure primero un DNS que resuelva al servidor y abra
los puertos TCP 80 y 443. Active el perfil incluido en el mismo `.env`, mantenga
el puerto de la API ligado a loopback y cambie la URL usada por Android a HTTPS:

```dotenv
COMPOSE_PROFILES=public-tls
OLLOMI_BIND=127.0.0.1
OLLOMI_TLS_DOMAIN=ollomi.example.com
OLLOMI_TLS_BIND=0.0.0.0
OLLOMI_HTTP_PORT=80
OLLOMI_HTTPS_PORT=443
OLLOMI_PUBLIC_URL=https://ollomi.example.com
OLLOMI_MCP_ENABLED=true
OLLOMI_MCP_PUBLIC_URL=https://ollomi.example.com
```

Caddy forma parte del Compose, obtiene y renueva el certificado y reenvía el
WebSocket de captura. No active el perfil hasta que DNS y los puertos estén
operativos; si se activa sin `OLLOMI_TLS_DOMAIN`, Caddy se detendrá con un
error en lugar de exponer un certificado o dominio implícito. No use una IP
pública ni HTTP para MCP OAuth.

`OLLOMI_IMAGE_TAG` debe estar fijado a una release revisada para que las
actualizaciones sean deliberadas. Cambie la etiqueta, ejecute `docker compose
pull` y después `docker compose up -d`. No use `docker compose down -v`, porque
`-v` elimina la base de datos y los audios.

Guarde copias fuera del servidor y compruebe periódicamente que restauran. El
restaurador pide una confirmación explícita, verifica `SHA256SUMS` y exige el
mismo `OLLOMI_SECRET_KEY` que el respaldo para poder descifrar las credenciales:

```bash
scripts/selfhost_backup.sh /ruta/privada/backup-ollomi
scripts/selfhost_restore.sh /ruta/privada/backup-ollomi --confirm-restore
```

La restauración sustituye la base de datos y los originales de audio de la
instalación actual. Al finalizar reinicia los escritores y reconstruye los
índices derivados; no ejecute la segunda orden sobre la instancia fuente salvo
que quiera volver deliberadamente al estado de la copia.

OpenAI/Whisper y Ollama pueden exponer las rutas compatibles
`/audio/transcriptions`, `/chat/completions` y `/embeddings`. Gemini,
AssemblyAI y Deepgram para STT, y Voyage y Cohere para embeddings, usan sus
APIs nativas cuando se elige su `PROVIDER`. Pueden ser tres proveedores
diferentes. Los sufijos `1`, `2`, `3` definen el orden de fallback; cada entrada
admite `PROVIDER`, `NAME`, `URL`, `MODEL`, `API_KEY`, `EXTERNAL`, `OPTIONS` y,
para embeddings, `DIMENSIONS`. Si `OLLOMI_MCP_ENABLED=true`, configure además
`OLLOMI_MCP_PUBLIC_URL` con una URL HTTPS pública: el backend ofrece `/mcp` y
OAuth/PKCE local, sin proveedor de identidad externo.

Por defecto el primer perfil de cada tarea es el primario y el resto son
fallbacks. Para permitir que cada usuario escoja como primario uno de los
perfiles configurados, añada `OLLOMI_ALLOW_USER_MODEL_SELECTION=true` a
`.env`; el servidor impone este permiso también si se intenta llamar a la API
directamente.

Para identificar de forma persistente la voz de la cuenta, despliegue el
servicio CPU separado de [`../voiceprint`](../voiceprint/), conserve su puerto
privado y añada `OLLOMI_VOICEPRINT_URL`, `OLLOMI_VOICEPRINT_API_KEY` y el
umbral a `.env`. La diarización de STT por sí sola distingue interlocutores
dentro de un audio, pero no sabe cuál es el propietario en otra grabación.
