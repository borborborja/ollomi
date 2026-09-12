# Ollomi

Fork local de Omi: Android solo con el micrófono del teléfono, servidor configurable, autenticación local, importación MP3 y backend Docker con PostgreSQL/pgvector, Typesense, Redis, Whisper y Ollama o servidores compatibles.

- [Instalación, modelos, Android y copias de seguridad](docs/OLLomi_SELF_HOSTING.es.md)
- [Investigación y decisiones](docs/OLLomi_RESEARCH.es.md)
- [Pruebas y límites de esta versión](docs/OLLomi_VALIDATION.md)
- [Backend autoalojado](backend/selfhost/README.md)

El backend activo es `backend/selfhost`; el backend cloud upstream se conserva como referencia y no se despliega. No requiere Firebase ni cuentas comerciales. Los modelos e imágenes se instalan antes de ejecutar sin Internet. Consulte la matriz de validación antes de asumir paridad con todas las funciones de Omi.

## Publicación

El flujo `Publish Ollomi` publica imágenes multi-arquitectura `ollomi-backend` y `ollomi-speech` en GHCR y compila una APK `prod` firmada. Las imágenes publicadas se usan sin compilar con:

```bash
OLLOMI_IMAGE_OWNER=<cuenta-github> docker compose -f compose.yaml -f deploy/compose.ghcr.yaml up -d
```

La APK mantiene la misma identidad de firma entre ejecuciones, por lo que las actualizaciones posteriores se instalan sobre la anterior. El primer cambio desde una APK de desarrollo firmada con otra clave puede requerir desinstalar esa instalación una única vez. El repositorio debe tener cuatro secretos de Actions: `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` y `ANDROID_KEY_PASSWORD`.

Origen: BasedHardware/omi, commit `e02339f4c720eb726fb4b798991b306c817630c5`. Se conserva la licencia MIT y sus avisos. Piper y los pesos opcionales tienen sus propias licencias; véase `services/speech/THIRD_PARTY.md`.

La documentación original del proyecto está en [README_UPSTREAM.md](README_UPSTREAM.md).
