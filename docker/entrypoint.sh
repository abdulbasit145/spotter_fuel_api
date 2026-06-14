#!/bin/sh
set -e

case "$DATABASE_URL" in
  postgres*|postgresql*)
    echo "Waiting for PostgreSQL to accept connections..."
    until python -c "import dj_database_url, psycopg2; c = dj_database_url.config(env='DATABASE_URL'); psycopg2.connect(dbname=c['NAME'], user=c['USER'], password=c['PASSWORD'], host=c['HOST'], port=c['PORT'] or 5432).close()" 2>/dev/null; do
      sleep 1
    done
    echo "PostgreSQL is ready."
    ;;
esac

python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ "$(python -c "import django; django.setup(); from api.models import FuelStation; print('empty' if not FuelStation.objects.exists() else 'loaded')")" = "empty" ]; then
  echo "Loading fuel station data..."
  python manage.py load_fuel_stations
fi

exec "$@"
