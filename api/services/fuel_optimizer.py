"""Optimal fuel-stop planning.

Given a driving route and a set of geocoded fuel stations, compute the
minimum-cost set of fuel purchases that lets the vehicle complete the
trip without ever exceeding its range.
"""
from dataclasses import dataclass
from decimal import Decimal

from api.services.geometry import downsample_route, project_point_onto_route

DEFAULT_VEHICLE_RANGE_MILES = 500
DEFAULT_MILES_PER_GALLON = 10
ROUTE_CORRIDOR_MILES = 30
BOUNDING_BOX_MARGIN_DEGREES = 1.0
MAX_ROUTE_VERTICES_FOR_PROJECTION = 300


@dataclass(frozen=True)
class FuelStop:
    """A single planned fuel purchase."""

    station: object
    distance_from_start: float
    gallons_purchased: float
    cost: Decimal


class RouteRangeError(Exception):
    """Raised when the trip cannot be completed within the vehicle's
    range using the available fuel stations."""


def stations_near_route(queryset, route_points):
    """Restrict ``queryset`` to a bounding box around the route.

    This is a cheap database-level pre-filter; the precise corridor
    check happens later in ``_candidate_stations``.
    """
    latitudes = [point[0] for point in route_points]
    longitudes = [point[1] for point in route_points]

    return queryset.filter(
        latitude__gte=min(latitudes) - BOUNDING_BOX_MARGIN_DEGREES,
        latitude__lte=max(latitudes) + BOUNDING_BOX_MARGIN_DEGREES,
        longitude__gte=min(longitudes) - BOUNDING_BOX_MARGIN_DEGREES,
        longitude__lte=max(longitudes) + BOUNDING_BOX_MARGIN_DEGREES,
    )


def _cheapest_per_location(stations):
    """Collapse stations that share the same coordinates down to the
    cheapest one.

    Many rows in the source data resolve to the same city-level
    coordinates. Since the optimizer only cares about price at each
    distinct point along the route, keeping just the cheapest station
    per location shrinks both the projection and DP steps without
    affecting the result.
    """
    cheapest = {}

    for station in stations:
        key = (round(float(station.latitude), 4), round(float(station.longitude), 4))
        current_best = cheapest.get(key)
        if current_best is None or station.price_per_gallon < current_best.price_per_gallon:
            cheapest[key] = station

    return cheapest.values()


def _candidate_stations(stations, route_points, cumulative_distances):
    """Project the cheapest station at each unique location onto the
    route and keep only those within ``ROUTE_CORRIDOR_MILES`` of it.

    Returns a list of ``(distance_from_start, station)`` tuples sorted
    by distance along the route.
    """
    projection_points, projection_distances = downsample_route(
        route_points, cumulative_distances, MAX_ROUTE_VERTICES_FOR_PROJECTION,
    )

    candidates = []
    for station in _cheapest_per_location(stations):
        station_point = (float(station.latitude), float(station.longitude))
        distance_along_route, lateral_distance = project_point_onto_route(
            station_point, projection_points, projection_distances,
        )
        if lateral_distance <= ROUTE_CORRIDOR_MILES:
            candidates.append((distance_along_route, station))

    candidates.sort(key=lambda candidate: candidate[0])
    return candidates


def plan_fuel_stops(
    stations,
    route_points,
    cumulative_distances,
    total_distance,
    vehicle_range=DEFAULT_VEHICLE_RANGE_MILES,
    miles_per_gallon=DEFAULT_MILES_PER_GALLON,
):
    """Return ``(stops, total_cost)`` for the cheapest feasible plan.

    The vehicle starts with a full tank, so the first leg of up to
    ``vehicle_range`` miles is free; every later leg is paid for at the
    price of the station where the fuel was bought.

    Each candidate stop (plus the start and destination) is a node, with
    a forward edge between any two nodes at most ``vehicle_range`` apart.
    Because the nodes are sorted by position along the route, this forms
    a weighted DAG, and the cheapest plan is its shortest path -- found
    with an O(n^2) dynamic program over n candidate stations.

    Raises ``RouteRangeError`` if no feasible plan exists.
    """
    candidates = _candidate_stations(stations, route_points, cumulative_distances)

    nodes = [(0.0, None)] + candidates + [(total_distance, None)]
    node_count = len(nodes)

    minimum_cost = [None] * node_count
    previous_node = [None] * node_count
    minimum_cost[0] = Decimal('0')

    for origin in range(node_count):
        if minimum_cost[origin] is None:
            continue

        origin_distance, origin_station = nodes[origin]
        price_per_gallon = (
            Decimal(str(origin_station.price_per_gallon))
            if origin_station is not None
            else None
        )

        for destination in range(origin + 1, node_count):
            leg_distance = nodes[destination][0] - origin_distance
            if leg_distance > vehicle_range:
                continue

            leg_cost = Decimal('0')
            if price_per_gallon is not None:
                gallons_needed = Decimal(str(leg_distance)) / Decimal(str(miles_per_gallon))
                leg_cost = gallons_needed * price_per_gallon

            total_cost_via_origin = minimum_cost[origin] + leg_cost
            if minimum_cost[destination] is None or total_cost_via_origin < minimum_cost[destination]:
                minimum_cost[destination] = total_cost_via_origin
                previous_node[destination] = origin

    destination_node = node_count - 1
    if minimum_cost[destination_node] is None:
        raise RouteRangeError(
            'No combination of fuel stations along this route keeps the '
            f'vehicle within its {vehicle_range}-mile range.'
        )

    path = []
    node = destination_node
    while node is not None:
        path.append(node)
        node = previous_node[node]
    path.reverse()

    stops = []
    for current_node, next_node in zip(path[1:-1], path[2:]):
        distance_along_route, station = nodes[current_node]
        leg_distance = nodes[next_node][0] - distance_along_route
        gallons_purchased = leg_distance / miles_per_gallon
        cost = Decimal(str(gallons_purchased)) * Decimal(str(station.price_per_gallon))

        stops.append(FuelStop(
            station=station,
            distance_from_start=distance_along_route,
            gallons_purchased=round(gallons_purchased, 3),
            cost=round(cost, 2),
        ))

    return stops, round(minimum_cost[destination_node], 2)
