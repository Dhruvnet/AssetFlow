# Part B — Diagnosing Broken Snippets

### Snippet 1 — Overdue Report View

#### 1. What is wrong

- **N+1 queries.** `c.asset.name`, `c.asset.asset_tag`, `c.employee.full_name` each trigger a fresh query per checkout, no `select_related()`. Design doc explicitly requires "must not issue a query per row" — this violates it directly. At 10 overdue rows that's 21 queries; at 10,000 rows, 20,001.
- **No pagination.** Loads and returns every overdue checkout in one response. Fine at 10 rows, a multi-second/multi-MB response at scale.
- **Sorting in Python, not SQL.** `rows.sort(...)` after pulling every row into memory. The database can do this with `ORDER BY` for free; doing it in application memory doesn't scale and defeats any DB-side index on `due_at`.
- **No authentication.** This is a bare Django view (`JsonResponse`), not wired through DRF's permission classes at all. If this replaced the real endpoint, `/reports/overdue/` — which the spec requires to be authenticated — would be silently open to anyone.
- **Two separate `timezone.now()` calls** — once in the filter condition, once in the `days_overdue` calculation. Under normal load this is a rounding non-issue, but it's non-deterministic: the "now" used to decide *if* something is overdue isn't the same "now" used to compute *how* overdue. Should be captured once.
- **`days_overdue` truncates toward zero, not toward "at least 1 day."** `(timezone.now() - c.due_at).days` on a `timedelta` floors the result. A checkout that's 23 hours and 59 minutes overdue reports `days_overdue: 0`, which reads as "not overdue" on a report whose entire purpose is showing overdue items, and is exactly the boundary case A5 requires a test for ("an item due exactly now"). Not a crash, but a reporting-accuracy bug that would mislead whoever reads this screen.

#### 2. Why it looks correct locally

With seed data of ~5–10 checkouts, 21 queries execute in milliseconds — nobody notices. Auth is invisible in casual testing because the developer is testing from an already-authenticated browser session or simply never tries an anonymous request. The two-`now()` issue produces identical values in practice because the two lines execute microseconds apart — the bug only matters under GC pauses, slow queries between the two calls, or exact-boundary test cases. The truncation bug is invisible unless a test is deliberately constructed around a checkout that's overdue by less than 24 hours — seed data built around "a few days overdue" for readability will never trigger it.

#### 3. Fix

```python
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

class OverdueReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        checkouts = (
            CheckOut.objects
            .filter(returned_at__isnull=True, due_at__lt=now)
            .select_related("asset", "employee")
            .order_by("due_at")  # most overdue (earliest due_at) first
        )
        rows = [
            {
                "asset": c.asset.name,
                "asset_tag": c.asset.asset_tag,
                "employee": c.employee.full_name,
                # ceil, not floor: any overdue checkout reports at least 1 day
                "days_overdue": max(1, -(-(now - c.due_at).total_seconds() // 86400).__int__()),
            }
            for c in checkouts
        ]
        return Response({"count": len(rows), "rows": rows})
```

A cleaner way to express the ceiling than the inline arithmetic above is `math.ceil((now - c.due_at).total_seconds() / 86400)` — either works; the point is not to use `.days` directly on the raw timedelta.

Pagination should be layered on via DRF's standard `PageNumberPagination` if this endpoint is expected to scale beyond a screenful of results — omitted above only because the design doc doesn't explicitly mandate pagination for this specific report.

#### 4. What would have caught it

- `django-debug-toolbar` or the `nplusone` package flags the N+1 immediately in dev.
- `assertNumQueries(2)` (or similar fixed bound) in a pytest test — fails the moment someone adds an unrelated field access that triggers a new query.
- A test hitting the endpoint with no `Authorization` header, asserting `401` — would fail instantly against this snippet.
- A boundary test: a checkout with `due_at` a few hours in the past, asserting `days_overdue == 1`, not `0` — would fail instantly against the original `.days` truncation.
- Load-testing the seed command's output scaled to thousands of rows before shipping.

---

## Snippet 2 — Check-out Endpoint

#### 1. What is wrong

- **No 404 handling.** `Asset.objects.get(...)` and `Employee.objects.get(...)` raise `DoesNotExist` on a bad `asset_tag`/`employee_code`, which DRF turns into an unhandled `500`, not the required `404` (rule 8).
- **No `KeyError` handling.** `request.data["asset_tag"]` (and others) raise `KeyError` → `500` if any field is missing, instead of `400`.
- **No transaction.** `CheckOut.objects.create()` and `asset.save()` are two independent statements. If the process dies (or an exception fires) between them, a `CheckOut` row exists while the asset is still `AVAILABLE` — exactly the inconsistency rule 5 forbids.
- **No row locking — the core concurrency bug.** Nothing prevents two simultaneous requests both reading `status == "AVAILABLE"` before either writes. Both would pass the check, both would create a `CheckOut`, both would set `CHECKED_OUT` — two checkouts on one asset. Rule 7 requires this be solved at the database level; this snippet doesn't attempt it.
- **No inactive-employee check.** Rule 2 (`is_active=False` → `400`) is entirely missing.
- **No `due_at` validation.** Rule 4 (must be future, ≤30 days ahead) is missing. `due_at` is also passed straight from `request.data` with no parsing/type validation — a malformed string could error unpredictably deep inside the ORM instead of failing cleanly at the boundary.
- **No explicit permission class.** Relies on whatever the global DRF default happens to be. Fragile — a settings change elsewhere in the project could silently open this endpoint.

#### 2. Why it looks correct locally

A developer testing manually sends one request at a time with a real `asset_tag`, real `employee_code`, an active employee, and a sane `due_at` — every unhappy path is simply never exercised. The race condition is the most dangerous because it *cannot* be caught by sequential manual testing at all, no matter how thorough — it only manifests under genuine concurrent load, which local click-testing structurally cannot produce.

#### 3. Fix

```python
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from datetime import timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def check_out_asset(request):
    asset_tag = request.data.get("asset_tag")
    employee_code = request.data.get("employee_code")
    due_at_raw = request.data.get("due_at")

    if not all([asset_tag, employee_code, due_at_raw]):
        return Response({"detail": "asset_tag, employee_code, due_at required"}, status=400)

    asset = get_object_or_404(Asset, asset_tag=asset_tag)
    employee = get_object_or_404(Employee, employee_code=employee_code)

    if not employee.is_active:
        return Response({"detail": "employee is not active"}, status=400)

    due_at = parse_datetime(due_at_raw)  # returns None on bad input
    now = timezone.now()
    if not due_at or due_at <= now or due_at > now + timedelta(days=30):
        return Response({"detail": "due_at must be in the future and within 30 days"}, status=400)

    with transaction.atomic():
        # Lock the asset row — closes the single-asset race (rule 7).
        asset = Asset.objects.select_for_update().get(pk=asset.pk)

        if asset.status != "AVAILABLE":
            return Response({"detail": "not available"}, status=409)

        # Lock the employee row too — see note below on why this matters
        # for rule 3, not just rule 7.
        employee = Employee.objects.select_for_update().get(pk=employee.pk)

        open_count = CheckOut.objects.filter(
            employee=employee, returned_at__isnull=True
        ).count()
        if open_count >= 3:
            return Response({"detail": "limit reached"}, status=409)

        checkout = CheckOut.objects.create(asset=asset, employee=employee, due_at=due_at)
        asset.status = "CHECKED_OUT"
        asset.save(update_fields=["status", "updated_at"])

    return Response({"id": checkout.id}, status=201)
```

(`get_object_or_404` note: since `Asset`/`Employee` lookups happen outside the transaction, re-fetching each with `select_for_update()` inside the atomic block is what actually establishes the lock — the first lookup is just for the 404 check.)

**Note on a second, related race condition (rule 3):** the asset lock above closes the single-asset race described in rule 7, which is the one the spec and A5's test explicitly name. But the *employee's* three-open-checkout limit has an analogous race: without locking the employee row, two concurrent requests for the *same employee* against *two different assets* could both read `open_count < 3` before either commits, producing four open checkouts for one employee. The fix above closes this too, by also taking `select_for_update()` on the employee row inside the same atomic block — but it's worth flagging explicitly in review, because it's easy to fix the asset race (the one everyone is looking for) and miss that the count-then-write pattern on rule 3 has the identical structural flaw.

#### 4. What would have caught it

- **A concurrency test** — two threads/connections firing simultaneous checkout requests for the same asset, asserting exactly one `201` and one `409`. Required by A5 explicitly; this snippet would fail it outright.
- **A second concurrency test** for rule 3 specifically — one employee, two different available assets, two simultaneous checkout requests when the employee already has two open checkouts; assert exactly one `201` and one `409`. Not explicitly named in A5 but the same technique, and worth including to prove the employee-lock fix actually works.
- Unit tests for each unhappy path: unknown tag → `404`, inactive employee → `400`, past `due_at` → `400`, fourth checkout → `409`, missing field → `400`.
- Code review against the rule checklist in the design doc — every rule maps to a missing branch here.
- `select_for_update()` usage is easy to grep for in review; its absence on a write-then-check pattern is a known red flag — and its presence on *only one* of two structurally identical check-then-write patterns (asset status vs. employee open-count) is worth a second look in review too.

---

## Snippet 3 — Nightly Notice Task

#### 1. What is wrong

- **Not idempotent — the core defect.** `OverdueNotice.objects.create(...)` runs unconditionally every time. Re-running the task (retry after partial failure, or an operator manually re-triggering it) creates duplicate notices for checkouts already processed, unless a DB uniqueness constraint blocks it — and if that constraint exists, the duplicate `INSERT` raises `IntegrityError`, which **kills the entire task on the first repeat**, meaning none of the *remaining*, genuinely-new overdue checkouts get processed either. Either way, partial-failure retry is broken.
- **Passing model instances into `.delay()`.** `deliver_email.delay(c.employee, c)` hands Celery live Django model instances as task arguments. Celery's default (JSON) serializer cannot serialize model instances — this either raises a serialization error at call time, or "works" only because the project happens to be using the insecure `pickle` serializer, or because tests run with `CELERY_TASK_ALWAYS_EAGER=True` (synchronous execution, no real serialization ever occurs).
- **N+1 queries.** `c.employee` inside the loop, with no `select_related("employee")` on the queryset — one query per row on top of the main query.
- **`overdue.count()` at the end re-executes the query** rather than reusing the already-fetched results (e.g. `len(processed_list)`), doubling the query cost at exactly the scale (tens of thousands of rows) where it matters most.
- **`timezone.now().date()` called once but implicitly assumed stable for the whole loop** — for a long-running task processing tens of thousands of rows, "today" should be captured once at the top, not implicitly relied upon; here it's actually only called once (fine), but nothing prevents duplicate-notice risk if the task legitimately spans a midnight boundary in a slow run.
- **No batching/streaming at scale.** Iterating the full queryset without `.iterator()` loads all matching rows into memory at once; creating notices one `INSERT` at a time instead of `bulk_create()`; firing tens of thousands of individual `.delay()` calls floods the broker in one burst instead of being throttled or chunked.
- **No per-row error isolation.** One bad row (e.g. a broken FK, an email delivery task failure) can abort the whole loop, losing notices for every subsequent row that would otherwise have succeeded.

#### 2. Why it looks correct locally

Local/test runs almost never retry a task after partial failure — that's specifically a production failure-mode, not something casual testing exercises. Serialization issues vanish under `CELERY_TASK_ALWAYS_EAGER=True` (common in test settings) since tasks execute synchronously in-process, never touching the actual message broker or serializer. Small seed data (a handful of overdue rows) makes the N+1 and `count()`-recount costs imperceptible. Nothing in a first pass surfaces until either (a) the task is genuinely retried mid-batch, or (b) the overdue set grows large enough for query volume and memory to matter.

#### 3. Fix

```python
from celery import shared_task
from celery.utils.log import get_task_logger
from django.db import DatabaseError
from django.utils import timezone

logger = get_task_logger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_overdue_notices(self):
    today = timezone.now().date()
    now = timezone.now()

    overdue = (
        CheckOut.objects
        .filter(returned_at__isnull=True, due_at__lt=now)
        .select_related("employee", "asset")
    )

    sent_count = 0
    try:
        for c in overdue.iterator(chunk_size=500):
            notice, created = OverdueNotice.objects.get_or_create(
                checkout=c, notice_date=today
            )
            if created:
                # pass primitive IDs, not model instances — Celery-serializable
                deliver_email.delay(c.employee_id, c.id)
                sent_count += 1
    except DatabaseError as exc:
        # get_or_create + the unique constraint means a genuine retry after
        # this point is safe: already-created notices are skipped, not
        # duplicated, so retrying the whole task is the correct response
        # to a transient DB error rather than losing the remaining rows.
        logger.warning("send_overdue_notices failed, retrying: %s", exc)
        raise self.retry(exc=exc)

    return f"sent {sent_count} notices"
```

`bind=True` / `max_retries` / `self.retry(...)` are now load-bearing rather than decorative: because `get_or_create` makes each row's write idempotent, a retry of the *entire* task after a transient failure (e.g. the DB connection drops mid-loop) is safe — it will skip every row already notified and only create the remaining ones. That safety property is exactly what was missing in the original, and is why the retry config is meaningful here rather than just boilerplate.

`deliver_email` itself should accept `employee_id`/`checkout_id` and re-fetch inside its own body — never accept live model instances as task arguments, since the task may run on a different process/machine than the one that enqueued it.

For genuinely tens-of-thousands-scale batches, `bulk_create(..., ignore_conflicts=True)` combined with the existing `(checkout, notice_date)` unique constraint is a faster idempotent alternative to per-row `get_or_create()`, at the cost of not knowing exactly which rows were newly created (so email dispatch would need a separate follow-up query for "notices created today with no email sent yet" rather than inline dispatch in the same loop).

#### 4. What would have caught it

- **The exact idempotency test A5 already requires** — "run the task twice, assert one notice" — this snippet fails that test outright with `create()` instead of `get_or_create()`.
- Running the test suite with `CELERY_TASK_ALWAYS_EAGER=False` and a real (JSON) serializer at least once in CI, rather than only ever testing in eager mode — would surface the model-instance-argument bug immediately.
- A retry-simulation test: manually process half the queryset, simulate a crash, re-run the task, assert no duplicate notices and that the remaining rows still get processed.
- `assertNumQueries` bound in a test, to catch the N+1 the moment `select_related` is removed or a new field access is added.
- Load-testing with the seed command scaled to thousands of overdue rows before shipping, per the pattern used to catch Snippet 1's scaling issue too.