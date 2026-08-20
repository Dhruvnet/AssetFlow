from django.db import models


class Asset(models.Model):
    """A physical piece of company equipment that can be checked out."""

    class Category(models.TextChoices):
        CAMERA = "CAMERA", "Camera"
        LAPTOP = "LAPTOP", "Laptop"
        SENSOR = "SENSOR", "Sensor"
        VEHICLE = "VEHICLE", "Vehicle"

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        CHECKED_OUT = "CHECKED_OUT", "Checked out"
        MAINTENANCE = "MAINTENANCE", "Maintenance"

    asset_tag = models.CharField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=16, choices=Category.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    purchase_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["asset_tag"]

    def __str__(self):
        return f"{self.asset_tag} ({self.name})"


class Employee(models.Model):
    """The person who physically holds a checked-out asset.

    Deliberately not linked to Django's auth ``User`` model — employees
    are a business record, not API principals. See design doc §2.
    """

    employee_code = models.CharField(max_length=16, unique=True, db_index=True)
    full_name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["employee_code"]

    def __str__(self):
        return f"{self.employee_code} — {self.full_name}"


class CheckOut(models.Model):
    """A single loan of an Asset to an Employee.

    An open checkout is one where ``returned_at`` is null. PROTECT is
    used on both foreign keys so an asset or employee with checkout
    history can never be silently deleted out from under it.
    """

    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name="checkouts",
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="checkouts",
    )
    checked_out_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField()
    returned_at = models.DateTimeField(null=True, blank=True)
    condition_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-checked_out_at"]
        indexes = [
            # Speeds up "open checkouts for this employee/asset" lookups,
            # which the checkout-limit rule and current_holder both do.
            models.Index(fields=["employee", "returned_at"]),
            models.Index(fields=["asset", "returned_at"]),
        ]

    def __str__(self):
        return f"{self.asset.asset_tag} -> {self.employee.employee_code}"

    @property
    def is_open(self):
        return self.returned_at is None


class OverdueNotice(models.Model):
    """Idempotency record: at most one notice per checkout per day.

    The uniqueness constraint below is what makes
    ``flag_overdue_checkouts`` safe to run more than once on the same
    day — it is the last line of defense, not just an optimization.
    """

    checkout = models.ForeignKey(
        CheckOut,
        on_delete=models.CASCADE,
        related_name="notices",
    )
    notice_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-notice_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["checkout", "notice_date"],
                name="unique_notice_per_checkout_per_day",
            )
        ]

    def __str__(self):
        return f"Notice for checkout {self.checkout_id} on {self.notice_date}"
