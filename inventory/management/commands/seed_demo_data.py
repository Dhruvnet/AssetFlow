from datetime import date, timedelta

from django.core.management.base import BaseCommand

from inventory.models import Asset


class Command(BaseCommand):
    help = "Seed demo assets for testing."

    ASSETS = [
        ("Dell XPS 15", Asset.Category.LAPTOP),
        ("MacBook Pro 14", Asset.Category.LAPTOP),
        ("Sony A7 III", Asset.Category.CAMERA),
        ("Canon EOS R6", Asset.Category.CAMERA),
        ("Temperature Sensor Rig", Asset.Category.SENSOR),
        ("Humidity Sensor Rig", Asset.Category.SENSOR),
        ("Delivery Van 1", Asset.Category.VEHICLE),
        ("Delivery Van 2", Asset.Category.VEHICLE),
    ]

    def handle(self, *args, **options):
        existing_count = Asset.objects.count()

        for index, (name, category) in enumerate(self.ASSETS, start=1):
            asset_number = existing_count + index

            Asset.objects.create(
                asset_tag=f"ASSET-{asset_number:03d}",
                name=name,
                category=category,
                purchase_date=date.today() - timedelta(days=180),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete. {len(self.ASSETS)} new assets created."
            )
        )