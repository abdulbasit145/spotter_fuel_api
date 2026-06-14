"""Load fuel station prices from the provided fuel-prices CSV.

The source CSV has no coordinates, only a city and state for each
truckstop. Coordinates are resolved entirely offline via
``api.services.city_geocoder`` (a GeoNames-based lookup with a
state-centroid fallback), so this command makes no network requests
and can be re-run at any time.
"""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.models import FuelStation
from api.services.city_geocoder import is_us_state, lookup_city

DEFAULT_DATA_FILE = settings.FUEL_DATA_FILE

BATCH_SIZE = 1000


class Command(BaseCommand):
    help = 'Load fuel station prices from the fuel-prices CSV file.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            default=str(DEFAULT_DATA_FILE),
            help='Path to the fuel prices CSV file.',
        )

    def handle(self, *args, **options):
        csv_path = Path(options['path'])
        if not csv_path.exists():
            raise CommandError(f'File not found: {csv_path}')

        FuelStation.objects.all().delete()

        stations = []
        skipped = 0

        with csv_path.open(newline='', encoding='utf-8') as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                station = self._build_station(row)
                if station is None:
                    skipped += 1
                    continue
                stations.append(station)

        FuelStation.objects.bulk_create(stations, batch_size=BATCH_SIZE)

        self.stdout.write(self.style.SUCCESS(
            f'Loaded {len(stations)} fuel stations from {csv_path} '
            f'({skipped} rows skipped).'
        ))

    @staticmethod
    def _build_station(row):
        city = row['City'].strip()
        state = row['State'].strip()

        if not is_us_state(state):
            return None

        coordinates = lookup_city(city, state)
        if coordinates is None:
            return None

        try:
            price = Decimal(row['Retail Price'].strip())
        except (InvalidOperation, AttributeError, KeyError):
            return None

        latitude, longitude = coordinates
        return FuelStation(
            name=row['Truckstop Name'].strip(),
            address=row.get('Address', '').strip(),
            city=city,
            state=state,
            latitude=latitude,
            longitude=longitude,
            price_per_gallon=price,
        )
