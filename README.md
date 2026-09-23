# Server Schedule

Drag-and-drop weekly server scheduling. Servers on rows, days across, morning and night shift tiles you place by hand or auto-fill from availability and staffing targets.

Runs as one small container: FastAPI serves the page and stores everything in a single SQLite file at `/data/schedule.db`. No external calls; fonts are bundled.

## Run with Docker Compose

```bash
docker compose up -d --build
```

Open `http://<server-ip>:8085`.

Data lives in `./data` next to the compose file. Back it up like any other volume, or use **Shifts and rules > Backup** in the app to download a JSON file.

## Run in Portainer

1. Copy this folder to the host (for example `/mnt/user/appdata/server-schedule` on Unraid).
2. Build once on the host: `docker build -t server-schedule:latest .`
3. In Portainer, create a stack with:

```yaml
services:
  server-schedule:
    image: server-schedule:latest
    pull_policy: never
    container_name: server-schedule
    restart: unless-stopped
    ports:
      - "8085:8080"
    volumes:
      - /mnt/user/appdata/server-schedule/data:/data
    environment:
      - TZ=America/Chicago
      - PUID=99
      - PGID=100
```

The image only exists on your host (it's not on Docker Hub), so `pull_policy: never` stops Docker from trying to download it. For the same reason, leave **Re-pull image** switched off when you update the stack or recreate the container in Portainer; otherwise it fails with `pull access denied for server-schedule`.

On start the container fixes ownership of `/data` to `PUID:PGID`, then runs the app as that user. Use `99`/`100` on Unraid (nobody:users) or `1000`/`1000` elsewhere. Don't also set `user:` on the service; that skips the ownership fix.

## Security

There is no login. Keep it on your LAN, or put it behind your reverse proxy with authentication (Authelia, Authentik, basic auth, Tailscale, etc.) before exposing it.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET/PUT | `/api/doc/{collection}/{id}` | Read or replace one document (`config/main`, `weeks/2026-09-28`) |
| GET | `/api/export` | Download all data as JSON |
| POST | `/api/import` | Restore from an export |

## Updating

Replace `static/index.html` or `app/main.py`, then `docker compose up -d --build`. Data in `/data` is untouched.
