# auuction

Self-hosted church fundraising auction app (Django + DRF). Includes Docker Compose for Postgres, Redis, Caddy.

## Quick start (dev/prod parity)
1. Copy env: `cp .env.example .env` and edit values.
2. Build images: `docker compose build`
3. Start stack: `docker compose up -d`
4. Run migrations: `docker compose exec web python manage.py migrate`
5. Create admin: `docker compose exec web python manage.py createsuperuser`
6. Collect static: `docker compose exec web python manage.py collectstatic --noinput`
7. Visit health check: `http://localhost:8080/health` (or `https://auuction.org/health` in prod)

## Services
- proxy: Caddy (TLS, static)
- web: Django + Gunicorn
- worker: Celery workers
- beat: Celery Beat scheduler
- db: Postgres
- cache: Redis

## Volumes
- static_assets (served by Caddy)
- media (uploads)
- pg_data (database)
- redis_data
- caddy_data / caddy_config
- backups

## Notes
- App code is in `backend/`.
- Update the Caddyfile hosts for your domain.
- Ensure DNS and ports 80/443 point to the VM for auto TLS.
