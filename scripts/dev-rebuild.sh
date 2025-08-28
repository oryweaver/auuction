#!/usr/bin/env bash
set -euo pipefail

# Utility script to speed up local rebuilds and DB maintenance for this project.
# Usage examples:
#   scripts/dev-rebuild.sh rebuild           # Build images for web/worker/beat and restart them
#   scripts/dev-rebuild.sh up                # Start services (no rebuild)
#   scripts/dev-rebuild.sh migrate           # Run Django migrations in web container
#   scripts/dev-rebuild.sh migrate-host      # Run migrations with host bind-mount (no rebuild)
#   scripts/dev-rebuild.sh makemigrations    # Make migrations for changed apps (inside container; not persisted if no mount)
#   scripts/dev-rebuild.sh makemigrations-host # Make migrations with host bind-mount so files persist with correct ownership
#   scripts/dev-rebuild.sh collectstatic     # Collect static files
#   scripts/dev-rebuild.sh shell             # Open Django shell
#   scripts/dev-rebuild.sh logs web          # Tail logs for a service
#   scripts/dev-rebuild.sh resetdb           # DANGEROUS: stop and remove volumes, fresh start
#   scripts/dev-rebuild.sh status            # docker compose ps
#   scripts/dev-rebuild.sh end-live          # End live phase (inside container; requires rebuilt image)
#   scripts/dev-rebuild.sh end-live-host     # End live phase using host bind-mount (no rebuild needed)
#
# Compose services (see docker-compose.yml): proxy, web, worker, beat, db, cache

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$ROOT_DIR"

COMPOSE="docker compose"
SERVICES_CORE=(web worker beat)

cmd=${1:-help}
shift || true

function ensure_env() {
  if [[ ! -f .env ]]; then
    echo ".env not found. You may copy .env.example to .env and adjust settings."
  fi
}

function compose_build_core() {
  $COMPOSE build "${SERVICES_CORE[@]}"
}

function compose_up_core() {
  $COMPOSE up -d "${SERVICES_CORE[@]}" proxy
}

function run_in_web() {
  $COMPOSE run --rm web "$@"
}

function run_in_web_hostbind() {
  # Bind-mount the backend source so generated files (migrations) are written to the host.
  # Also run as the host user to avoid root-owned files.
  $COMPOSE run --rm --no-deps \
    --entrypoint "" \
    --user "$(id -u):$(id -g)" \
    -v "$ROOT_DIR/backend:/app" \
    web "$@"
}

case "$cmd" in
  rebuild)
    ensure_env
    echo "==> Building images for: ${SERVICES_CORE[*]}"
    compose_build_core
    echo "==> Restarting core services and proxy"
    compose_up_core
    echo "==> Running migrations"
    run_in_web python manage.py migrate --noinput
    echo "==> Collecting static files"
    run_in_web python manage.py collectstatic --noinput
    echo "Done."
    ;;

  up)
    ensure_env
    echo "==> Starting services"
    compose_up_core
    ;;

  migrate)
    ensure_env
    run_in_web python manage.py migrate --noinput
    ;;

  makemigrations)
    ensure_env
    run_in_web python manage.py makemigrations
    ;;

  makemigrations-host)
    ensure_env
    echo "==> Running makemigrations with host bind-mount (writes files to ./backend)"
    run_in_web_hostbind python manage.py makemigrations
    ;;

  end-live)
    ensure_env
    # Pass all remaining args to the management command
    run_in_web python manage.py end_live_phase "$@"
    ;;

  end-live-host)
    ensure_env
    echo "==> Ending live phase with host bind-mount"
    run_in_web_hostbind python manage.py end_live_phase "$@"
    ;;

  migrate-host)
    ensure_env
    run_in_web_hostbind python manage.py migrate --noinput
    ;;

  collectstatic)
    ensure_env
    run_in_web python manage.py collectstatic --noinput
    ;;

  shell)
    ensure_env
    run_in_web python manage.py shell
    ;;

  logs)
    svc=${1:-web}
    shift || true
    $COMPOSE logs -f "$svc"
    ;;

  status)
    $COMPOSE ps
    ;;

  resetdb)
    echo "WARNING: This will remove containers and volumes, wiping the database."
    read -r -p "Type 'YES' to proceed: " CONFIRM
    if [[ "$CONFIRM" == "YES" ]]; then
      $COMPOSE down -v
      ensure_env
      compose_up_core
      echo "==> Running migrations"
      run_in_web python manage.py migrate --noinput
      echo "==> Collecting static files"
      run_in_web python manage.py collectstatic --noinput
      echo "Fresh environment ready."
    else
      echo "Aborted."
    fi
    ;;

  help|*)
    sed -n '1,80p' "$0" | sed -n '1,40p'
    echo "\nCommands: rebuild | up | migrate | migrate-host | makemigrations | makemigrations-host | end-live | end-live-host | collectstatic | shell | logs [svc] | status | resetdb"
    ;;

esac
