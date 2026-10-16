# Build de Bazarr (fork Lumen2-0/bazarr) pour Coolify : frontend (vite) puis runtime Python.
FROM node:24-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Europe/Paris
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg mediainfo p7zip-full libxml2 libxslt1.1 curl tini \
    && rm -rf /var/lib/apt/lists/*
# Meme uid/gid que la stack media (PUID/PGID 2000) pour garder les droits sur /config et les medias
RUN groupadd -g 2000 media && useradd -u 2000 -g 2000 -d /config -s /usr/sbin/nologin -M media \
    && mkdir -p /app /config && chown 2000:2000 /app /config
WORKDIR /app
COPY requirements.txt postgres-requirements.txt ./
RUN pip install -r requirements.txt -r postgres-requirements.txt
COPY --chown=2000:2000 . /app
COPY --from=frontend --chown=2000:2000 /src/frontend/build /app/frontend/build
USER 2000:2000
VOLUME /config
EXPOSE 6767
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD curl -fs http://127.0.0.1:6767/ >/dev/null || exit 1
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "/app/bazarr.py", "--no-update", "--config", "/config"]
