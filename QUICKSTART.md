# Quickstart

## Voraussetzung

[Docker Desktop](https://www.docker.com/products/docker-desktop/) installieren und starten.

## Starten

```bash
docker compose up --build
```

Beim ersten Start werden die Images gebaut (~5–10 Min, je nach Internetverbindung).

Danach: **http://localhost:3000** im Browser öffnen.

## Stoppen

```bash
docker compose down
```

Trace-Logs bleiben im `traces/`-Ordner erhalten.
