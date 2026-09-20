# Ollomi

Fork autoalojable de Omi: Android permite grabar con el teléfono o un dispositivo compatible conectado, importar MP3/M4A/WAV/OGG/FLAC y elegir el servidor. Todo el backend se ejecuta con Docker Compose sobre PostgreSQL/pgvector, Typesense, Redis, Whisper y Ollama o endpoints compatibles con OpenAI, sin Firebase.

[![Publish Ollomi](https://github.com/borborborja/ollomi/actions/workflows/ollomi-release.yml/badge.svg)](https://github.com/borborborja/ollomi/actions/workflows/ollomi-release.yml)

- [Instalación, modelos, Android y copias de seguridad](docs/OLLomi_SELF_HOSTING.es.md)
- [Compose autónomo para usar solo APIs externas](deploy/examples/external-api/README.md)
- [Investigación y decisiones](docs/OLLomi_RESEARCH.es.md)
- [Pruebas y límites de esta versión](docs/OLLomi_VALIDATION.md)
- [Backend autoalojado](backend/selfhost/README.md)

El backend activo es `backend/selfhost`; el backend cloud upstream se conserva como referencia y no se despliega. No requiere Firebase ni cuentas comerciales. Los modelos e imágenes se instalan antes de ejecutar sin Internet. Consulte la matriz de validación antes de asumir paridad con todas las funciones de Omi.

## Despliegue rápido

Requiere Docker Engine y Docker Compose v2 en una máquina `linux/amd64`:

```bash
git clone https://github.com/borborborja/ollomi.git
cd ollomi
read -rsp 'Contraseña inicial: ' INITIAL_ADMIN_PASSWORD; echo
export INITIAL_ADMIN_PASSWORD
python3 scripts/selfhost_init.py --bind 0.0.0.0 \
  --admin-email admin@example.com \
  --admin-password-env INITIAL_ADMIN_PASSWORD
unset INITIAL_ADMIN_PASSWORD

docker compose pull
docker compose run --rm model-downloader --stt small
docker compose -f compose.yaml -f deploy/compose.ghcr.yaml \
  -f deploy/compose.connected.yaml --profile local-ollama up -d ollama
docker compose exec ollama ollama pull qwen3:4b
docker compose exec ollama ollama pull embeddinggemma
docker compose up -d
```

El inicializador escribe `COMPOSE_FILE` en `.env`, usa las imágenes públicas de `borborborja` y busca un puerto libre empezando por 8080 y 8090. Consulte `OLLOMI_PORT` y abra `http://IP_DEL_SERVIDOR:PUERTO/health`; debe devolver `{"status":"ok"}`. Tras el primer acceso, elimine `OLLOMI_ADMIN_PASSWORD` de `.env` y ejecute `docker compose up -d --force-recreate migrate api worker scheduler`. El seed es idempotente y nunca cambia una cuenta existente.

Para usar únicamente IA en la LAN o en la nube, inicialice con `--external-ai`. Esto añade automáticamente `deploy/compose.connected.yaml`, no activa Whisper ni Ollama, no descarga pesos y deja ejemplos de OpenAI, OpenRouter, Ollama Cloud y endpoints OpenAI-compatible en `.env`. Configure STT, chat y embeddings antes de ejecutar `docker compose up -d`. También hay un [Compose autónomo con todas las variables de ejemplo](deploy/examples/external-api/README.md) que solo descarga la imagen del backend. Instale la APK desde la [última Release](https://github.com/borborborja/ollomi/releases/latest) y use la URL del servidor en Android.

Antes de procesar audio hay que instalar los modelos locales o configurar proveedores externos en `.env`. La [guía completa](docs/OLLomi_SELF_HOSTING.es.md) incluye Whisper, Ollama, fallbacks, actualización, copias de seguridad y diagnóstico.

## Imágenes y compilación

Cada cambio en `main` ejecuta [Publish Ollomi](https://github.com/borborborja/ollomi/actions/workflows/ollomi-release.yml): publica las imágenes `linux/amd64` [`ollomi-backend`](https://github.com/borborborja/ollomi/pkgs/container/ollomi-backend) y [`ollomi-speech`](https://github.com/borborborja/ollomi/pkgs/container/ollomi-speech) en GHCR, y compila una APK `prod` firmada como artefacto de Actions. Las etiquetas Git `v*` adjuntan también la APK y su SHA-256 a la Release.

Las imágenes publicadas se pueden descargar directamente. Sustituya `v0.3.0` por una release concreta o use `latest` para seguir `main`:

```bash
docker pull ghcr.io/borborborja/ollomi-backend:v0.3.0
docker pull ghcr.io/borborborja/ollomi-speech:v0.3.0
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
