# Ollomi backend — install from a release

This package runs the self-hosted API, PostgreSQL/pgvector, Redis and
Typesense. It is for a Linux `amd64` server with Docker Engine and Docker
Compose v2. It contains no local AI model: point STT, chat and embeddings to
the external or LAN services configured in `.env`.

The supplied `.env.example` pins `OLLOMI_IMAGE_OWNER` and `OLLOMI_IMAGE_TAG`
to this release. Dockge users can opt into one-click, validated releases by
changing the tag to `stable` once. Do not use `latest`, which follows `main`.

## First installation

```bash
cp .env.example .env
chmod 600 .env
nano .env
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
curl "http://127.0.0.1:$(sed -n 's/^OLLOMI_PORT=//p' .env)/health"
```

Before starting, replace every `CHANGE_ME` value. Set `OLLOMI_PUBLIC_URL` to
the LAN URL or HTTPS domain the Android phone will use, and configure at least
one profile for STT, chat and embeddings. The first login uses
`OLLOMI_ADMIN_EMAIL` and `OLLOMI_ADMIN_PASSWORD`.

After verifying that login, remove the administrator password from `.env` and
recreate the backend writers so it is no longer passed to containers:

```bash
sed -i '/^OLLOMI_ADMIN_PASSWORD=/d' .env
docker compose up -d --force-recreate ollomi-api worker scheduler
```

For public HTTPS and MCP OAuth, configure DNS and inbound TCP 80/443, then
follow the commented `public-tls` section in `.env`. Keep `OLLOMI_BIND` on
`127.0.0.1` in that mode and use the same HTTPS domain for
`OLLOMI_PUBLIC_URL` and `OLLOMI_MCP_PUBLIC_URL`.

## Update safely

Back up first with `scripts/selfhost_backup.sh`. For a pinned installation,
download the next release bundle, replace `compose.yaml` and `scripts/`, but
retain your existing `.env`, volumes and `OLLOMI_SECRET_KEY`. Update
`OLLOMI_IMAGE_TAG` to the new release tag, then run:

```bash
docker compose pull
docker compose up -d
```

For Dockge, make a one-time change to the new `compose.yaml` (which has no
one-shot `migrate` service) and set `OLLOMI_IMAGE_TAG=stable` in the existing
`.env`. Click **Deploy** once to remove the old migration container. Thereafter
click **Update** to pull and restart on the newest validated release. The API
applies migrations before serving requests, and workers wait for its health.
Keep the existing volumes and secret key. An external/LAN model provider needs
no STT or voiceprint container in this stack.

Never use `docker compose down -v` for an update: it deletes the local
database and audio volumes.
