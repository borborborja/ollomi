# Ollomi

Fork autoalojable de Omi: Android permite grabar con el teléfono o un dispositivo compatible conectado, importar MP3/M4A/WAV/OGG/FLAC y elegir el servidor. Todo el backend se ejecuta con Docker Compose sobre PostgreSQL/pgvector, Typesense, Redis, Whisper y Ollama o endpoints compatibles con OpenAI, sin Firebase.

- [Instalación, modelos, Android y copias de seguridad](docs/OLLomi_SELF_HOSTING.es.md)
- [Compose autónomo para usar solo APIs externas](deploy/examples/external-api/README.md)
- [Investigación y decisiones](docs/OLLomi_RESEARCH.es.md)
- [Pruebas y límites de esta versión](docs/OLLomi_VALIDATION.md)
- [Backend autoalojado](backend/selfhost/README.md)

El backend activo es `backend/selfhost`; el backend cloud upstream se conserva como referencia y no se despliega. No requiere Firebase ni cuentas comerciales. Los modelos e imágenes se instalan antes de ejecutar sin Internet. Consulte la matriz de validación antes de asumir paridad con todas las funciones de Omi.

## Despliegue rápido

Requiere Docker Engine y Docker Compose v2 en una máquina `linux/amd64`:

### Instalación desde una release

La forma recomendada para un servidor que usa IA externa o en la LAN es
descargar el paquete preparado de la última release. Ya contiene el Compose y
una plantilla `.env` fijada a la misma imagen revisada:

```bash
mkdir ollomi && cd ollomi
curl -L -o ollomi-backend.tar.gz https://github.com/borborborja/ollomi/releases/latest/download/ollomi-backend.tar.gz
tar -xzf ollomi-backend.tar.gz --strip-components=1
cp .env.example .env
chmod 600 .env
nano .env
docker compose config --quiet && docker compose pull && docker compose up -d
```

La APK de producción se descarga desde la misma release como
[`ollomi.apk`](https://github.com/borborborja/ollomi/releases/latest/download/ollomi.apk).
Todas las APK oficiales usan la misma firma, de modo que una versión nueva se
instala sobre la anterior sin desinstalarla. Compruebe el archivo `SHA256SUMS`
adjunto antes de una instalación manual.

### Servidor con modelos en LAN o proveedores externos

Para una instalación nueva sin modelos locales (la configuración apropiada
para un servidor CPU que delega la IA), copie la plantilla, sustituya **todos**
los valores `CHANGE_ME` y las direcciones `192.168.1.x`, y arranque el stack:

```bash
git clone https://github.com/YOUR_GITHUB_OWNER/ollomi.git
cd ollomi
cp .env.example .env
chmod 600 .env
${EDITOR:-vi} .env
docker compose config --quiet
docker compose build
docker compose up -d
```

La plantilla incluye PostgreSQL/pgvector, Redis, Typesense, API y workers, y
exige un perfil numerado para STT, chat y embeddings. No arranca Whisper ni
Ollama ni descarga pesos. El primer inicio crea `OLLOMI_ADMIN_EMAIL`; tras
iniciar sesión, borre `OLLOMI_ADMIN_PASSWORD` de `.env` y ejecute `docker
compose up -d --force-recreate migrate api worker scheduler`. Para MCP OAuth o
acceso público, active antes la modalidad TLS documentada; una URL HTTP de LAN
no es una identidad OAuth válida.

### Inicialización asistida y modelos locales opcionales

```bash
git clone https://github.com/YOUR_GITHUB_OWNER/ollomi.git
cd ollomi
read -rsp 'Contraseña inicial: ' INITIAL_ADMIN_PASSWORD; echo
export INITIAL_ADMIN_PASSWORD
python3 scripts/selfhost_init.py --source-build --bind 0.0.0.0 \
  --admin-email admin@example.com \
  --admin-password-env INITIAL_ADMIN_PASSWORD
unset INITIAL_ADMIN_PASSWORD

docker compose build
docker compose run --rm model-downloader --stt small
docker compose -f compose.yaml -f deploy/compose.connected.yaml \
  --profile local-ollama up -d ollama
docker compose exec ollama ollama pull qwen3:4b
docker compose exec ollama ollama pull embeddinggemma
docker compose up -d
```

El inicializador escribe `COMPOSE_FILE` en `.env`, construye esta revisión del código por defecto y busca un puerto libre empezando por 8080 y 8090. Consulte `OLLOMI_PORT` y abra `http://IP_DEL_SERVIDOR:PUERTO/health`; debe devolver `{"status":"ok"}`. Tras el primer acceso, elimine `OLLOMI_ADMIN_PASSWORD` de `.env` y ejecute `docker compose up -d --force-recreate migrate api worker scheduler`. El seed es idempotente y nunca cambia una cuenta existente.

Para usar únicamente IA en la LAN o en la nube, inicialice con `--external-ai`. Esto añade automáticamente `deploy/compose.connected.yaml`, no activa Whisper ni Ollama, no descarga pesos y deja ejemplos de OpenAI, OpenRouter, Ollama Cloud y endpoints OpenAI-compatible en `.env`. Configure STT, chat y embeddings antes de ejecutar `docker compose up -d`. También hay un [Compose autónomo con todas las variables de ejemplo](deploy/examples/external-api/README.md), utilizable después de publicar una imagen revisada desde el fork. Instale una APK creada por el workflow de su fork y use la URL del servidor en Android.

Antes de procesar audio hay que instalar los modelos locales o configurar proveedores externos en `.env`. La [guía completa](docs/OLLomi_SELF_HOSTING.es.md) incluye Whisper, Ollama, fallbacks, actualización, copias de seguridad y diagnóstico.

## Imágenes y compilación

Cada cambio en `main` de un fork con Actions habilitado ejecuta `Publish Ollomi`: publica las imágenes `linux/amd64` `ollomi-api`, `ollomi-stt` y `ollomi-voiceprint` en el GHCR de ese fork, y compila una APK de depuración para validación de dispositivo como artefacto. Solo las etiquetas Git `v*` compilan la APK `prod` firmada y publican una Release con `ollomi.apk`, sus comprobaciones SHA-256 y `ollomi-backend.tar.gz` listo para configurar.

Tras una release que haya pasado las puertas de validación, las imágenes se pueden descargar directamente. Sustituya ambos marcadores por el owner y tag de ese fork; no use una imagen de Omi upstream ni `latest` sin revisión:

```bash
docker pull ghcr.io/YOUR_GITHUB_OWNER/ollomi-api:REVIEWED_TAG
docker pull ghcr.io/YOUR_GITHUB_OWNER/ollomi-stt:REVIEWED_TAG
```

Para compilar las mismas imágenes desde el código:

```bash
docker build -f deploy/Dockerfile -t ollomi-backend:local .
docker build -f services/speech/Dockerfile -t ollomi-speech:local services/speech
```

También puede generar `.env` y construir todo el Compose localmente con `python3 scripts/selfhost_init.py --source-build`, `docker compose build` y `docker compose up -d`. El workflow usa `docker/build-push-action`, etiqueta cada imagen con la rama, la etiqueta Git y el SHA corto, y actualiza `latest` solo desde la rama predeterminada. En un fork, active Actions y conceda permiso de escritura a paquetes; la compilación de la APK requiere además los cuatro secretos de firma indicados más abajo.

Para actualizar una instalación que usa GHCR:

Las instalaciones creadas con una versión anterior deben añadir una vez `COMPOSE_FILE=compose.yaml:deploy/compose.ghcr.yaml` a `.env`. Añada al final `:deploy/compose.connected.yaml` si usa IA externa/LAN. Use `COMPOSE_PROFILES=local-whisper,local-ollama` para conservar ambos servicios locales, solo `local-whisper` para conservar Whisper o elimine la variable cuando todos los modelos sean externos.

```bash
git pull --ff-only
docker compose pull
docker compose up -d
```

La APK mantiene la misma identidad de firma entre ejecuciones, por lo que las actualizaciones posteriores se instalan sobre la anterior. El primer cambio desde una APK de desarrollo firmada con otra clave puede requerir desinstalar esa instalación una única vez. El repositorio debe tener cuatro secretos de Actions: `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` y `ANDROID_KEY_PASSWORD`.

Origen: BasedHardware/omi, commit `e02339f4c720eb726fb4b798991b306c817630c5`. Se conserva la licencia MIT y sus avisos. Piper y los pesos opcionales tienen sus propias licencias; véase `services/speech/THIRD_PARTY.md`.

La documentación original del proyecto está en [README_UPSTREAM.md](README_UPSTREAM.md).
