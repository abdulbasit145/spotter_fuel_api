# Spotter Fuel Route API

A Django REST Framework service that, given a start and finish location in the USA,
returns the driving route, the cheapest set of fuel stops for a 500-mile-range /
10-MPG vehicle, and the total fuel cost — plus an interactive map UI.

## Quick start

```bash
# Docker (recommended)
docker compose -f docker/development/docker-compose.yml up --build

# or locally
pip install -r requirements.txt
python manage.py migrate
python manage.py load_fuel_stations
python manage.py runserver
```

UI at `http://localhost:8000/`, API at `http://localhost:8000/api/v1/route-plan/`.

## API

```http
POST /api/v1/route-plan/
Content-Type: application/json

{ "start_location": "Chicago, IL", "finish_location": "Denver, CO" }
```

Returns the total distance, total fuel cost, route geometry, and the recommended
fuel stops (gallons and cost per stop). Unresolvable locations return `400`; a trip
that can't be completed within range returns `422`.

Interactive API docs (live "Try it out"):

- Swagger UI — `http://localhost:8000/api/docs/`
- ReDoc — `http://localhost:8000/api/redoc/`
- OpenAPI schema — `http://localhost:8000/api/schema/`

## Tests

```bash
python manage.py test
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_SETTINGS_MODULE` | `config.settings.development` | `development` or `production`. |
| `DJANGO_SECRET_KEY` | — | Required in production. |
| `DJANGO_ALLOWED_HOSTS` | — | Comma-separated hosts (production). |
| `DATABASE_URL` | — | PostgreSQL URL (production). |
| `REDIS_URL` | — | Optional Redis cache (production). Falls back to local-memory cache when unset. |
| `VEHICLE_RANGE_MILES` | `500` | Vehicle range on a full tank. |
| `VEHICLE_MILES_PER_GALLON` | `10` | Fuel economy. |

## Production

```bash
cp .env.example .env   # set DJANGO_SECRET_KEY and a strong DB password
docker compose -f docker/production/docker-compose.yml up --build
```

Runs Gunicorn behind WhiteNoise with PostgreSQL and Redis via the hardened
`config.settings.production` module. Route and geocode results are cached, so an
identical trip is served from cache with no external calls.
