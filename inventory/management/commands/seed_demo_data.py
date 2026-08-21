from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory.models import Asset, CheckOut, Employee


class Command(BaseCommand):
    help = "Seed a fresh database with demo assets, employees, and checkouts."

    ASSETS = [
        ("ASSET-001", "Dell XPS 15", Asset.Category.LAPTOP),
        ("ASSET-002", "MacBook Pro 14", Asset.Category.LAPTOP),
        ("ASSET-003", "Sony A7 III", Asset.Category.CAMERA),
        ("ASSET-004", "Canon EOS R6", Asset.Category.CAMERA),
        ("ASSET-005", "Temperature Sensor Rig", Asset.Category.SENSOR),
        ("ASSET-006", "Humidity Sensor Rig", Asset.Category.SENSOR),
        ("ASSET-007", "Delivery Van 1", Asset.Category.VEHICLE),
        ("ASSET-008", "Delivery Van 2", Asset.Category.VEHICLE),
    ]

    EMPLOYEES = [
        ("EMP001", "Alice Johnson", "alice@example.com", True),
        ("EMP002", "Bob Smith", "bob@example.com", True),
        ("EMP003", "Carol Williams", "carol@example.com", True),
        ("EMP004", "David Brown", "david@example.com", False),  # inactive
    ]

    # Each demo checkout is pinned to one specific asset/employee pair.
    # Re-running the command checks "does a CheckOut already exist for
    # this asset?" before creating one — that's what makes this safe
    # to run repeatedly without duplicating checkout history.
    CHECKOUT_PLAN = [
        # (asset_tag, employee_code, type)
        ("ASSET-001", "EMP001", "OVERDUE"),
        ("ASSET-002", "EMP002", "OVERDUE"),
        ("ASSET-003", "EMP001", "RETURNED_ON_TIME"),
        ("ASSET-004", "EMP002", "RETURNED_ON_TIME"),
        ("ASSET-005", "EMP003", "RETURNED_LATE"),
    ]

    def handle(self, *args, **options):
        now = timezone.now()

        self.stdout.write("Seeding assets...")
        asset_map = {}
        for tag, name, category in self.ASSETS:
            asset, created = Asset.objects.get_or_create(
                asset_tag=tag,
                defaults={
                    "name": name,
                    "category": category,
                    "purchase_date": date.today() - timedelta(days=180),
                },
            )
            asset_map[tag] = asset
            self.stdout.write(
                self.style.SUCCESS(f"  {'created' if created else 'exists'}: {tag}")
            )

        self.stdout.write("Seeding employees...")
        employee_map = {}
        for code, full_name, email, is_active in self.EMPLOYEES:
            employee, created = Employee.objects.get_or_create(
                employee_code=code,
                defaults={
                    "full_name": full_name,
                    "email": email,
                    "is_active": is_active,
                },
            )
            employee_map[code] = employee
            self.stdout.write(
                self.style.SUCCESS(f"  {'created' if created else 'exists'}: {code}")
            )

        self.stdout.write("Seeding checkouts...")
        for asset_tag, employee_code, checkout_type in self.CHECKOUT_PLAN:
            asset = asset_map[asset_tag]
            employee = employee_map[employee_code]

            if CheckOut.objects.filter(asset=asset).exists():
                self.stdout.write(f"  skipped (already seeded): {asset_tag}")
                continue

            self._create_checkout(asset, employee, checkout_type, now)
            self.stdout.write(
                self.style.SUCCESS(f"  created {checkout_type}: {asset_tag} -> {employee_code}")
            )

        self._seed_demo_user()

        self.stdout.write(self.style.SUCCESS("\nSeed complete."))

    def _create_checkout(self, asset, employee, checkout_type, now):
        if checkout_type == "OVERDUE":
            checkout = CheckOut.objects.create(
                asset=asset,
                employee=employee,
                due_at=now - timedelta(days=3),
                condition_note="Demo overdue checkout.",
            )
            CheckOut.objects.filter(pk=checkout.pk).update(
                checked_out_at=now - timedelta(days=10)
            )
            asset.status = Asset.Status.CHECKED_OUT

        elif checkout_type == "RETURNED_ON_TIME":
            checkout = CheckOut.objects.create(
                asset=asset,
                employee=employee,
                due_at=now + timedelta(days=1),
                returned_at=now,
                condition_note="Demo asset returned on time, good condition.",
            )
            CheckOut.objects.filter(pk=checkout.pk).update(
                checked_out_at=now - timedelta(days=5)
            )
            asset.status = Asset.Status.AVAILABLE

        elif checkout_type == "RETURNED_LATE":
            checkout = CheckOut.objects.create(
                asset=asset,
                employee=employee,
                due_at=now - timedelta(days=3),
                returned_at=now - timedelta(days=1),
                condition_note="Demo asset returned late.",
            )
            CheckOut.objects.filter(pk=checkout.pk).update(
                checked_out_at=now - timedelta(days=10)
            )
            asset.status = Asset.Status.AVAILABLE

        asset.save(update_fields=["status", "updated_at"])

    def _seed_demo_user(self):
        username = "dhruv"
        password = "demo12345"

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nDemo API user created — username: {username}  password: {password}"
                )
            )
        else:
            self.stdout.write(f"\nDemo API user already exists — username: {username}")