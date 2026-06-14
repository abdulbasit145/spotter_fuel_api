"""Geometric helpers for working with route polylines."""
import math

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1, lon1, lat2, lon2):
    """Return the great-circle distance between two points, in miles.

    Uses the haversine formula, which is accurate enough for the
    distances involved in snapping stations to a route segment.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def project_point_onto_route(point, route_points, cumulative_distances):
    """Snap ``point`` to the nearest vertex of ``route_points``.

    ``cumulative_distances`` holds the running distance (in miles) up to
    each vertex of the polyline. Returns a
    ``(distance_along_route, lateral_distance)`` tuple, both in miles.
    """
    nearest_index = 0
    nearest_lateral = math.inf

    for index, vertex in enumerate(route_points):
        lateral = haversine_miles(point[0], point[1], vertex[0], vertex[1])
        if lateral < nearest_lateral:
            nearest_lateral = lateral
            nearest_index = index

    return cumulative_distances[nearest_index], nearest_lateral


def downsample_route(route_points, cumulative_distances, max_points=300):
    """Return a coarser copy of the route polyline with at most
    ``max_points`` vertices.

    Station snapping only needs mile-level accuracy, so every ``step``-th
    vertex is kept (plus the final one) to bound the cost of
    ``project_point_onto_route`` while preserving the route's shape.
    """
    if len(route_points) <= max_points:
        return route_points, cumulative_distances

    step = math.ceil(len(route_points) / max_points)
    sampled_points = route_points[::step]
    sampled_distances = cumulative_distances[::step]

    if sampled_points[-1] != route_points[-1]:
        sampled_points = sampled_points + [route_points[-1]]
        sampled_distances = sampled_distances + [cumulative_distances[-1]]

    return sampled_points, sampled_distances
