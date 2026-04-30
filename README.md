# Docker Service Dashboard

Tiny dashboard for a local network that lists published Docker container ports as clickable links.

## Run

```sh
python3 app.py
```

Open `http://m920q.local:8080` from another device on your LAN, or use [http://localhost:8080](http://localhost:8080) on the server itself.

By default the app uses `<hostname>.local` as the service host. That fits an mDNS-style setup such as `m920q.local`.

Optional override:

```sh
DASHBOARD_HOST=m920q.local PORT=8080 python3 app.py
```

## Docker

```sh
docker build -t service-dashboard .
docker run -d \
  --name service-dashboard \
  -p 8080:8080 \
  -e DASHBOARD_HOST=m920q.local \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  service-dashboard
```

With automatic Caddy hostname discovery:

```sh
docker run -d \
  --name service-dashboard \
  -p 8080:8080 \
  -e DASHBOARD_HOST=m920q.local \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /path/to/Caddyfile:/etc/caddy/Caddyfile:ro \
  service-dashboard
```

## Labels

Optional container labels:

- `dashboard.name`
- `dashboard.description`
- `dashboard.host`
- `dashboard.protocol`
- `dashboard.path`
- `dashboard.hide`
