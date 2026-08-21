from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from inventory.exceptions import Conflict
from inventory.models import Asset, CheckOut


def return_checkout(
    *,
    checkout_id,
    condition_note="",
    needs_maintenance=False,
):
    with transaction.atomic():

        try:
            checkout = (
                CheckOut.objects
                .select_for_update()
                .select_related("asset")
                .get(pk=checkout_id)
            )
        except CheckOut.DoesNotExist:
            raise NotFound(
                {
                    "detail": "Checkout does not exist."
                }
            )

        if checkout.returned_at is not None:
            raise Conflict(
                {
                    "detail": (
                        "This checkout has already been returned."
                    )
                }
            )

        checkout.returned_at = timezone.now()

        checkout.condition_note = condition_note

        checkout.save(
            update_fields=[
                "returned_at",
                "condition_note",
            ]
        )

        asset = checkout.asset

        if needs_maintenance:
            asset.status = Asset.Status.MAINTENANCE
        else:
            asset.status = Asset.Status.AVAILABLE

        asset.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return checkout