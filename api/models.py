import uuid

from django.db import models


class TimestampedModel(models.Model):
    """Abstract base that adds self-managed fields to model"""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class FuelStation(TimestampedModel):
    """A fuel retailer location with its current diesel price.

    Stations are geocoded once when the fixture/CSV is loaded via the
    ``load_fuel_stations`` management command, so the route-planning
    endpoint never has to call an external geocoder per fuel station.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=128)
    state = models.CharField(max_length=2)
    latitude = models.FloatField()
    longitude = models.FloatField()
    price_per_gallon = models.DecimalField(max_digits=5, decimal_places=3)

    class Meta:
        ordering = ['state', 'city', 'name']
        indexes = [
            models.Index(fields=['latitude', 'longitude']),
        ]

    def __str__(self):
        return f'{self.name} ({self.city}, {self.state}) - ${self.price_per_gallon}'
