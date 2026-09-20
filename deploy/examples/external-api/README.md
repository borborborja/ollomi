# Ollomi con APIs de IA externas

Este ejemplo autónomo descarga el backend que GitHub Actions ya ha compilado en
`ghcr.io/borborborja/ollomi-backend`. Ejecuta PostgreSQL/pgvector, Redis,
Typesense, la API y los workers en Docker. No define servicios Whisper u Ollama,
no descarga pesos y no necesita `selfhost-data/models`.

```bash
mkdir ollomi && cd ollomi
curl -LO https://raw.githubusercontent.com/borborborja/ollomi/main/deploy/examples/external-api/compose.yaml
curl -Lo .env https://raw.githubusercontent.com/borborborja/ollomi/main/deploy/examples/external-api/env.example
chmod 600 .env
```

Edite `.env`, cambie todos los valores `CHANGE_ME`, indique en
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

`OLLOMI_IMAGE_TAG` está fijado a una release para que las actualizaciones sean
deliberadas. Cambie la etiqueta, ejecute `docker compose pull` y después
`docker compose up -d`. No use `docker compose down -v`, porque `-v` elimina la
base de datos y los audios.

Los proveedores deben exponer las rutas OpenAI compatibles que corresponden:
`/audio/transcriptions`, `/chat/completions` y `/embeddings`. Pueden ser tres
proveedores diferentes. Los sufijos `1`, `2`, `3` definen el orden de fallback;
cada entrada admite `PROVIDER`, `NAME`, `URL`, `MODEL`, `API_KEY`, `EXTERNAL`,
`OPTIONS` y, para embeddings, `DIMENSIONS`.
