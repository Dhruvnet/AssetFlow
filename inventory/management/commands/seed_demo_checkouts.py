from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory.models import Asset, CheckOut, Employee


class Command(BaseCommand):
    help = (
        "Seed demo checkouts including held, overdue, "
        "returned, and maintenance records."
    )

    CHECKOUTS_PER_RUN = 8

    def handle(self, *args, **options):
        now = timezone.now()

        active_employees = list(
            Employee.objects.filter(
                is_active=True
            ).order_by(
                "employee_code"
            )
        )

        if not active_employees:
            self.stdout.write(
                self.style.ERROR(
                    "No active employees found. "
                    "Run seed_employees first."
                )
            )
            return

        available_assets = list(
            Asset.objects.filter(
                status=Asset.Status.AVAILABLE
            ).order_by("id")[
                :self.CHECKOUTS_PER_RUN
            ]
        )

        if not available_assets:
            self.stdout.write(
                self.style.ERROR(
                    "No available assets found. "
                    "Run seed_assets first."
                )
            )
            return

        created_count = 0

        # ==================================================
        # CHECKOUT TYPES
        # ==================================================

        checkout_types = [
            "HELD",
            "HELD",
            "OVERDUE",
            "OVERDUE",
            "RETURNED",
            "RETURNED",
            "RETURNED",
            "MAINTENANCE",
        ]

        for index, asset in enumerate(available_assets):

            checkout_type = checkout_types[
                index % len(checkout_types)
            ]

            employee = self.get_employee(
                active_employees,
                index,
            )

            if employee is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping {asset.asset_tag}: "
                        "all employees reached the "
                        "maximum open checkout limit."
                    )
                )
                continue

            checkout = self.create_checkout(
                asset=asset,
                employee=employee,
                checkout_type=checkout_type,
                now=now,
            )

            created_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"{checkout_type}: "
                    f"{asset.asset_tag} → "
                    f"{employee.employee_code}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDemo checkout seed complete. "
                f"{created_count} new checkouts created."
            )
        )

    def get_employee(
        self,
        employees,
        start_index,
    ):
        """
        Find an employee who has fewer than
        3 currently open checkouts.
        """

        for offset in range(len(employees)):
            index = (
                start_index + offset
            ) % len(employees)

            employee = employees[index]

            open_checkout_count = (
                CheckOut.objects.filter(
                    employee=employee,
                    returned_at__isnull=True,
                ).count()
            )

            if open_checkout_count < 3:
                return employee

        return None

    def create_checkout(
        self,
        *,
        asset,
        employee,
        checkout_type,
        now,
    ):

        # ==============================================
        # HELD
        # ==============================================

        if checkout_type == "HELD":

            checked_out_at = (
                now - timedelta(days=2)
            )

            due_at = (
                now + timedelta(days=7)
            )

            checkout = CheckOut.objects.create(
                asset=asset,
                employee=employee,
                due_at=due_at,
                condition_note=(
                    "Demo asset currently held."
                ),
            )

            CheckOut.objects.filter(
                pk=checkout.pk
            ).update(
                checked_out_at=checked_out_at
            )

            asset.status = (
                Asset.Status.CHECKED_OUT
            )

        # ==============================================
        # OVERDUE
        # ==============================================

        elif checkout_type == "OVERDUE":

            checked_out_at = (
                now - timedelta(days=10)
            )

            due_at = (
                now - timedelta(days=3)
            )

            checkout = CheckOut.objects.create(
                asset=asset,
                employee=employee,
                due_at=due_at,
                condition_note=(
                    "Demo overdue checkout."
                ),
            )

            CheckOut.objects.filter(
                pk=checkout.pk
            ).update(
                checked_out_at=checked_out_at
            )

            asset.status = (
                Asset.Status.CHECKED_OUT
            )

        # ==============================================
        # RETURNED
        # ==============================================

        elif checkout_type == "RETURNED":

            checked_out_at = (
                now - timedelta(days=10)
            )

            returned_at = (
                now - timedelta(days=5)
            )

            due_at = (
                now - timedelta(days=3)
            )

            checkout = CheckOut.objects.create(
                asset=asset,
                employee=employee,
                due_at=due_at,
                returned_at=returned_at,
                condition_note=(
                    "Demo asset returned in "
                    "good condition."
                ),
            )

            CheckOut.objects.filter(
                pk=checkout.pk
            ).update(
                checked_out_at=checked_out_at
            )

            asset.status = (
                Asset.Status.AVAILABLE
            )

        # ==============================================
        # MAINTENANCE
        # ==============================================

        else:

            checked_out_at = (
                now - timedelta(days=7)
            )

            returned_at = (
                now - timedelta(days=1)
            )

            due_at = (
                now - timedelta(days=2)
            )

            checkout = CheckOut.objects.create(
                asset=asset,
                employee=employee,
                due_at=due_at,
                returned_at=returned_at,
                condition_note=(
                    "Demo asset returned and "
                    "requires maintenance."
                ),
            )

            CheckOut.objects.filter(
                pk=checkout.pk
            ).update(
                checked_out_at=checked_out_at
            )

            asset.status = (
                Asset.Status.MAINTENANCE
            )

        asset.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        checkout.refresh_from_db()

        return checkout