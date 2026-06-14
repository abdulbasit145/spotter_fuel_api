from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    """Input payload for the route fuel plan endpoint."""

    start_location = serializers.CharField(max_length=255, trim_whitespace=True)
    finish_location = serializers.CharField(max_length=255, trim_whitespace=True)


class FuelStopSerializer(serializers.Serializer):
    """A single recommended fuel purchase."""

    name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    distance_from_start_miles = serializers.FloatField()
    price_per_gallon = serializers.DecimalField(max_digits=5, decimal_places=3)
    gallons_purchased = serializers.FloatField()
    cost = serializers.DecimalField(max_digits=8, decimal_places=2)


class RouteResponseSerializer(serializers.Serializer):
    """Full response payload for the route fuel plan endpoint."""

    start_location = serializers.CharField()
    finish_location = serializers.CharField()
    total_distance_miles = serializers.FloatField()
    total_fuel_cost = serializers.DecimalField(max_digits=10, decimal_places=2)
    vehicle_range_miles = serializers.IntegerField()
    miles_per_gallon = serializers.IntegerField()
    route_geometry = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField()),
        help_text='Ordered list of [latitude, longitude] pairs tracing the driving route.',
    )
    fuel_stops = FuelStopSerializer(many=True)
