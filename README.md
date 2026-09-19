# Ollomi

Fork autoalojable de Omi: Android permite grabar con el teléfono o un dispositivo compatible conectado, importar MP3/M4A/WAV/OGG/FLAC y elegir el servidor. Todo el backend se ejecuta con Docker Compose sobre PostgreSQL/pgvector, Typesense, Redis, Whisper y Ollama o endpoints compatibles con OpenAI, sin Firebase.

[![Publish Ollomi](https://github.com/borborborja/ollomi/actions/workflows/ollomi-release.yml/badge.svg)](https://github.com/borborborja/ollomi/actions/workflows/ollomi-release.yml)

- [Instalación, modelos, Android y copias de seguridad](docs/OLLomi_SELF_HOSTING.es.md)
- [Investigación y decisiones](docs/OLLomi_RESEARCH.es.md)
- [Pruebas y límites de esta versión](docs/OLLomi_VALIDATION.md)
- [Backend autoalojado](backend/selfhost/README.md)

El backend activo es `backend/selfhost`; el backend cloud upstream se conserva como referencia y no se despliega. No requiere Firebase ni cuentas comerciales. Los modelos e imágenes se instalan antes de ejecutar sin Internet. Consulte la matriz de validación antes de asumir paridad con todas las funciones de Omi.

## Despliegue rápido

Requiere Docker Engine y Docker Compose v2 en una máquina `linux/amd64`:

```bash
git clone https://github.com/borborborja/ollomi.git
cd ollomi
python3 scripts/selfhost_init.py

# Para acceder desde otro dispositivo de la red local:
sed -i 's/OLLOMI_BIND=127.0.0.1/OLLOMI_BIND=0.0.0.0/' .env

OLLOMI_IMAGE_OWNER=borborborja docker compose \
  -f compose.yaml -f deploy/compose.ghcr.yaml pull
OLLOMI_IMAGE_OWNER=borborborja docker compose \
  -f compose.yaml -f deploy/compose.ghcr.yaml up -d
OLLOMI_IMAGE_OWNER=borborborja docker compose \
  -f compose.yaml -f deploy/compose.ghcr.yaml \
  exec api python -m selfhost.cli create-admin
```

Después abra `http://IP_DEL_SERVIDOR:8080/health`; debe devolver `{"status":"ok"}`. Instale la APK desde el artefacto **ollomi-android-…** de la [última ejecución de Publish Ollomi](https://github.com/borborborja/ollomi/actions/workflows/ollomi-release.yml) y use `http://IP_DEL_SERVIDOR:8080` como servidor en Android.

Antes de procesar audio hay que instalar los modelos locales o configurar proveedores externos en `.env`. La [guía completa](docs/OLLomi_SELF_HOSTING.es.md) incluye Whisper, Ollama, fallbacks, actualización, copias de seguridad y diagnóstico.

## Publicación automática

Cada cambio en `main` ejecuta [Publish Ollomi](https://github.com/borborborja/ollomi/actions/workflows/ollomi-release.yml): publica las imágenes `linux/amd64` [`ollomi-backend`](https://github.com/borborborja/ollomi/pkgs/container/ollomi-backend) y [`ollomi-speech`](https://github.com/borborborja/ollomi/pkgs/container/ollomi-speech) en GHCR, y compila una APK `prod` firmada como artefacto de Actions. Las etiquetas Git `v*` adjuntan también la APK y su SHA-256 a la Release.

Para actualizar una instalación que usa GHCR:

```bash
git pull --ff-only
OLLOMI_IMAGE_OWNER=borborborja docker compose -f compose.yaml -f deploy/compose.ghcr.yaml pull
OLLOMI_IMAGE_OWNER=borborborja docker compose -f compose.yaml -f deploy/compose.ghcr.yaml up -d
```

La APK mantiene la misma identidad de firma entre ejecuciones, por lo que las actualizaciones posteriores se instalan sobre la anterior. El primer cambio desde una APK de desarrollo firmada con otra clave puede requerir desinstalar esa instalación una única vez. El repositorio debe tener cuatro secretos de Actions: `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` y `ANDROID_KEY_PASSWORD`.

Origen: BasedHardware/omi, commit `e02339f4c720eb726fb4b798991b306c817630c5`. Se conserva la licencia MIT y sus avisos. Piper y los pesos opcionales tienen sus propias licencias; véase `services/speech/THIRD_PARTY.md`.

La documentación original del proyecto está en [README_UPSTREAM.md](README_UPSTREAM.md).
