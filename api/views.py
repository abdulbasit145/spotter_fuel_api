import hashlib
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

from django.conf import settings
from django.core.cache import cache
from django.views.generic import TemplateView
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import FuelStation
from api.serializers import RouteRequestSerializer, RouteResponseSerializer
from api.services.directions import DirectionsError, geocode, get_route
from api.services.fuel_optimizer import RouteRangeError, plan_fuel_stops, stations_near_route


def _plan_cache_key(start_location, finish_location):
    digest = hashlib.sha256(
        f'{start_location.strip().lower()}|{finish_location.strip().lower()}'.encode()
    ).hexdigest()
    return f'route-plan:{digest}'


def _geocode_pair(start_location, finish_location):
    with ThreadPoolExecutor(max_workers=2) as executor:
        start_future = executor.submit(geocode, start_location)
        finish_future = executor.submit(geocode, finish_location)
        return start_future.result(), finish_future.result()


def _server_timing(durations):
    return ', '.join(f'{name};dur={milliseconds:.1f}' for name, milliseconds in durations.items())


@extend_schema(
    summary='Plan the cheapest fuel stops for a US road trip',
    request=RouteRequestSerializer,
    responses={
        status.HTTP_200_OK: RouteResponseSerializer,
        status.HTTP_400_BAD_REQUEST: OpenApiResponse(
            description='Invalid input, or a location that could not be geocoded or routed.',
        ),
        status.HTTP_422_UNPROCESSABLE_ENTITY: OpenApiResponse(
            description='The trip cannot be completed within the vehicle range using the available stations.',
        ),
    },
    examples=[
        OpenApiExample(
            'Seattle to Miami',
            value={'start_location': 'Seattle, WA', 'finish_location': 'Miami, FL'},
            request_only=True,
        ),
    ],
)
class RouteFuelPlanView(APIView):
    """Plan an optimal fuel-up strategy for a road trip within the US.

    ``POST`` body::

        {"start_location": "Seattle, WA", "finish_location": "Miami, FL"}

    The response contains the driving route geometry, the total trip
    distance, the recommended fuel stops (with how much fuel to buy at
    each one) and the total amount that will be spent on fuel,
    assuming a 500-mile range and 10 miles per gallon.
    """

    # Public, anonymous, throttled endpoint — no auth. This also avoids
    # SessionAuthentication's CSRF enforcement, which otherwise breaks the
    # browser fetch whenever a Django admin session cookie is present.
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        request_serializer = RouteRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data
        start_location = validated_data['start_location']
        finish_location = validated_data['finish_location']

        cache_key = _plan_cache_key(start_location, finish_location)
        cached_plan = cache.get(cache_key)
        if cached_plan is not None:
            response = Response(cached_plan)
            response['Server-Timing'] = 'cache;desc="hit"'
            return response

        durations = {}
        started = perf_counter()
        try:
            start_coordinates, finish_coordinates = _geocode_pair(start_location, finish_location)
            durations['geocode'] = (perf_counter() - started) * 1000
            started = perf_counter()
            route = get_route(start_coordinates, finish_coordinates)
            durations['route'] = (perf_counter() - started) * 1000
        except DirectionsError as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)

        started = perf_counter()
        try:
            stops, total_fuel_cost = plan_fuel_stops(
                stations=stations_near_route(FuelStation.objects.all(), route['points']),
                route_points=route['points'],
                cumulative_distances=route['cumulative_distances'],
                total_distance=route['total_distance'],
                vehicle_range=settings.VEHICLE_RANGE_MILES,
                miles_per_gallon=settings.VEHICLE_MILES_PER_GALLON,
            )
        except RouteRangeError as error:
            return Response({'detail': str(error)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        durations['plan'] = (perf_counter() - started) * 1000

        response_data = {
            'start_location': start_location,
            'finish_location': finish_location,
            'total_distance_miles': round(route['total_distance'], 2),
            'total_fuel_cost': total_fuel_cost,
            'vehicle_range_miles': settings.VEHICLE_RANGE_MILES,
            'miles_per_gallon': settings.VEHICLE_MILES_PER_GALLON,
            'route_geometry': [[lat, lon] for lat, lon in route['points']],
            'fuel_stops': [
                {
                    'name': stop.station.name,
                    'address': stop.station.address,
                    'city': stop.station.city,
                    'state': stop.station.state,
                    'latitude': stop.station.latitude,
                    'longitude': stop.station.longitude,
                    'distance_from_start_miles': round(stop.distance_from_start, 2),
                    'price_per_gallon': stop.station.price_per_gallon,
                    'gallons_purchased': stop.gallons_purchased,
                    'cost': stop.cost,
                }
                for stop in stops
            ],
        }

        serialized = RouteResponseSerializer(response_data).data
        cache.set(cache_key, serialized, timeout=settings.ROUTE_PLAN_CACHE_TIMEOUT)

        response = Response(serialized)
        response['Server-Timing'] = _server_timing(durations) + ', cache;desc="miss"'
        return response


class MapView(TemplateView):
    """Render the browsable map UI used to demo the API."""

    template_name = 'api/map.html'


class DeveloperHubView(TemplateView):
    """Landing page linking to the app, the live API, and the docs."""

    template_name = 'api/hub.html'
