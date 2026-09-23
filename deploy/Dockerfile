FROM python:3.11.16-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libopus0 liblc3-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY backend/selfhost/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && useradd --uid 10001 --create-home ollomi && mkdir /data && chown ollomi /data
COPY backend/selfhost /srv/selfhost
USER ollomi
# The API is the sole migration owner. Its process only starts serving after
# Alembic succeeds; workers wait for the API healthcheck in Compose.
CMD ["sh", "-ec", "python -m selfhost.cli migrate && exec uvicorn selfhost.main:app --host 0.0.0.0 --port 8080 --no-access-log"]
