"""Thin clients for the free geocoding and routing services used to
build a driving route between two US locations.

At most three external HTTP calls are made per request -- two geocodes
(Nominatim) and one route fetch (OSRM) -- and fewer when results are
served from the cache. Calls share a connection-pooled session with
automatic retries on transient upstream failures.
"""
import requests
from django.conf import settings
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from api.services.geometry import haversine_miles

NOMINATIM_SEARCH_URL = 'https://nominatim.openstreetmap.org/search'
OSRM_ROUTE_URL = 'https://router.project-osrm.org/route/v1/driving'

METERS_PER_MILE = 1609.34
REQUEST_TIMEOUT = (3.05, 10)

_retry = Retry(
    total=2,
    backoff_factor=0.3,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=('GET',),
)
_adapter = HTTPAdapter(max_retries=_retry, pool_connections=10, pool_maxsize=10)
_session = requests.Session()
_session.mount('https://', _adapter)
_session.mount('http://', _adapter)


class DirectionsError(Exception):
    """Raised when a location cannot be geocoded or routed."""


def _geocode_cache_key(location):
    return f'geocode:{location.strip().lower()}'


def geocode(location):
    """Resolve a free-text US location string to ``(latitude, longitude)``.

    Results are cached, so repeated lookups of the same location make no
    network call. Raises ``DirectionsError`` if no match is found.
    """
    cache_key = _geocode_cache_key(location)
    cached = cache.get(cache_key)
    if cached is not None:
        return tuple(cached)

    params = {
        'q': location,
        'format': 'json',
        'limit': 1,
        'countrycodes': 'us',
    }
    headers = {'User-Agent': settings.GEOCODER_USER_AGENT}

    response = _session.get(
        NOMINATIM_SEARCH_URL,
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    results = response.json()

    if not results:
        raise DirectionsError(f'Could not find a location matching {location!r}.')

    coordinates = (float(results[0]['lat']), float(results[0]['lon']))
    cache.set(cache_key, coordinates, timeout=settings.GEOCODE_CACHE_TIMEOUT)
    return coordinates


def get_route(start_coords, finish_coords):
    """Fetch the driving route between two ``(lat, lon)`` coordinates.

    Returns a dict with:

    * ``points`` -- a list of ``(lat, lon)`` tuples describing the
      route geometry.
    * ``cumulative_distances`` -- the running distance, in miles,
      travelled up to each point in ``points``.
    * ``total_distance`` -- the total route distance, in miles.
    """
    coordinates = (
        f'{start_coords[1]},{start_coords[0]};'
        f'{finish_coords[1]},{finish_coords[0]}'
    )
    url = f'{OSRM_ROUTE_URL}/{coordinates}'
    params = {'overview': 'simplified', 'geometries': 'geojson'}

    response = _session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()

    if payload.get('code') != 'Ok' or not payload.get('routes'):
        raise DirectionsError('No driving route could be found between the given locations.')

    route = payload['routes'][0]
    raw_points = route['geometry']['coordinates']
    points = [(lat, lon) for lon, lat in raw_points]

    cumulative_distances = [0.0]
    for previous_point, current_point in zip(points, points[1:]):
        segment_distance = haversine_miles(
            previous_point[0], previous_point[1],
            current_point[0], current_point[1],
        )
        cumulative_distances.append(cumulative_distances[-1] + segment_distance)

    return {
        'points': points,
        'cumulative_distances': cumulative_distances,
        'total_distance': route['distance'] / METERS_PER_MILE,
    }
