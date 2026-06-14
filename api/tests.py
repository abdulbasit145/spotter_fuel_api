from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from api.models import FuelStation
from api.services.fuel_optimizer import RouteRangeError, plan_fuel_stops
from api.services.geometry import haversine_miles, project_point_onto_route


class HaversineMilesTests(TestCase):
    def test_same_point_is_zero_distance(self):
        self.assertAlmostEqual(haversine_miles(40.0, -100.0, 40.0, -100.0), 0.0)

    def test_known_distance_between_cities(self):
        """New York City to Los Angeles is roughly 2,450 great-circle miles."""
        distance = haversine_miles(40.7128, -74.0060, 34.0522, -118.2437)
        self.assertAlmostEqual(distance, 2450, delta=50)


class ProjectPointOntoRouteTests(TestCase):
    def test_snaps_to_nearest_vertex(self):
        route_points = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
        cumulative_distances = [0.0, 69.0, 138.0]

        distance, lateral = project_point_onto_route(
            (0.01, 0.95), route_points, cumulative_distances,
        )

        self.assertEqual(distance, 69.0)
        self.assertGreater(lateral, 0)


class PlanFuelStopsTests(TestCase):
    """Exercise the optimizer against routes with hand-computed answers.

    The base route runs due east along the equator for 1,200 miles
    (roughly 17.36 degrees of longitude), with fuel stations placed at
    known mile-markers so the optimal plan can be verified by hand.
    """

    def setUp(self):
        self.route_points = [(0.0, lon) for lon in (0.0, 5.0, 10.0, 15.0, 17.36)]
        self.cumulative_distances = [0.0, 345.5, 691.0, 1036.5, 1200.0]
        self.total_distance = 1200.0

    def _make_station(self, lon, price):
        return FuelStation(
            name=f'Station @ {lon}',
            city='Testville',
            state='TX',
            latitude=0.0,
            longitude=lon,
            price_per_gallon=Decimal(str(price)),
        )

    def test_destination_within_range_needs_no_stops(self):
        stations = [self._make_station(10.0, 3.00)]
        stops, total_cost = plan_fuel_stops(
            stations=stations,
            route_points=self.route_points,
            cumulative_distances=self.cumulative_distances,
            total_distance=400.0,
            vehicle_range=500,
            miles_per_gallon=10,
        )
        self.assertEqual(stops, [])
        self.assertEqual(total_cost, Decimal('0'))

    def test_chooses_cheapest_feasible_station(self):
        """A cheap stop at mile 100 beats a pricier one at mile 200.

        With a 500-mile range over a 600-mile route, the cheap station
        lets the vehicle finish in a single stop; the pricier station is
        also reachable but costs more once the longer remaining leg is
        priced in.
        """
        route_points = [(0.0, 0.0), (0.0, 100 / 69), (0.0, 200 / 69), (0.0, 600 / 69)]
        cumulative_distances = [0.0, 100.0, 200.0, 600.0]

        cheap_station = self._make_station(100 / 69, 2.00)
        expensive_station = self._make_station(200 / 69, 5.00)

        stops, total_cost = plan_fuel_stops(
            stations=[cheap_station, expensive_station],
            route_points=route_points,
            cumulative_distances=cumulative_distances,
            total_distance=600.0,
            vehicle_range=500,
            miles_per_gallon=10,
        )

        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0].station.price_per_gallon, Decimal('2.00'))
        self.assertAlmostEqual(stops[0].gallons_purchased, 50.0, places=1)
        self.assertEqual(stops[0].cost, Decimal('100.00'))
        self.assertEqual(total_cost, Decimal('100.00'))

    def test_raises_when_no_path_within_range(self):
        """A lone station near the start cannot bridge a long route."""
        far_station = self._make_station(2.0, 3.00)

        with self.assertRaises(RouteRangeError):
            plan_fuel_stops(
                stations=[far_station],
                route_points=self.route_points,
                cumulative_distances=self.cumulative_distances,
                total_distance=2000.0,
                vehicle_range=200,
                miles_per_gallon=10,
            )


class RouteFuelPlanEndpointTests(TestCase):
    """End-to-end tests for the versioned route-plan endpoint.

    The external geocoding and routing calls are mocked so the view can
    be exercised without any network access.
    """

    def setUp(self):
        cache.clear()
        self.url = reverse('api:route-plan')
        FuelStation.objects.create(
            name='Cheap Stop',
            address='I-80',
            city='Lincoln',
            state='NE',
            latitude=0.0,
            longitude=1.45,
            price_per_gallon=Decimal('2.000'),
        )

    def test_endpoint_returns_plan(self):
        fake_route = {
            'points': [(0.0, 0.0), (0.0, 1.45), (0.0, 8.7)],
            'cumulative_distances': [0.0, 100.0, 600.0],
            'total_distance': 600.0,
        }

        with mock.patch('api.views.geocode', return_value=(0.0, 0.0)), \
                mock.patch('api.views.get_route', return_value=fake_route):
            response = self.client.post(
                self.url,
                data={'start_location': 'A, NE', 'finish_location': 'B, NE'},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body['total_distance_miles'], 600.0)
        self.assertEqual(len(body['fuel_stops']), 1)
        self.assertEqual(body['fuel_stops'][0]['name'], 'Cheap Stop')

    def test_plan_uses_a_single_station_query(self):
        """Planning a route must touch the DB exactly once.

        Stations are filtered by an indexed bounding-box query and then
        processed entirely in memory, so there is no per-station (N+1)
        access. This guards that property against regressions.
        """
        fake_route = {
            'points': [(0.0, 0.0), (0.0, 1.45), (0.0, 8.7)],
            'cumulative_distances': [0.0, 100.0, 600.0],
            'total_distance': 600.0,
        }

        with mock.patch('api.views.geocode', return_value=(0.0, 0.0)), \
                mock.patch('api.views.get_route', return_value=fake_route):
            with self.assertNumQueries(1):
                self.client.post(
                    self.url,
                    data={'start_location': 'A, NE', 'finish_location': 'B, NE'},
                    content_type='application/json',
                )

    def test_repeat_request_is_served_from_cache(self):
        """An identical trip is returned from cache with no DB query."""
        fake_route = {
            'points': [(0.0, 0.0), (0.0, 1.45), (0.0, 8.7)],
            'cumulative_distances': [0.0, 100.0, 600.0],
            'total_distance': 600.0,
        }
        payload = {'start_location': 'A, NE', 'finish_location': 'B, NE'}

        with mock.patch('api.views.geocode', return_value=(0.0, 0.0)), \
                mock.patch('api.views.get_route', return_value=fake_route):
            first = self.client.post(self.url, data=payload, content_type='application/json')
            with self.assertNumQueries(0):
                second = self.client.post(self.url, data=payload, content_type='application/json')

        self.assertIn('cache;desc="miss"', first['Server-Timing'])
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second['Server-Timing'], 'cache;desc="hit"')
        self.assertEqual(first.json(), second.json())

    def test_missing_fields_return_400(self):
        response = self.client.post(
            self.url, data={}, content_type='application/json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
