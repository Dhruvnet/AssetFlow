# AssetFlow

Internal REST API for tracking physical company equipment checked out to and
returned by employees. Built with Django, Django REST Framework, PostgreSQL,
Redis and Celery.

---

## Prerequisites

**Recommended path — Docker:**
- Docker and Docker Compose
- Git

No local Python/PostgreSQL/Redis install is required for this path —
everything runs inside containers.

**Alternative path — running without Docker** (see [Appendix: local
setup](#appendix-running-without-docker) at the end of this README):
- Python 3.12+
- PostgreSQL 16 running locally
- Redis running locally (only needed for Celery)
- Git

---

## 1. Clone and configure environment

```bash
git clone https://github.com/Dhruvnet/AssetFlow.git
cd AssetFlow
cp .env.example .env
```

`.env.example` ships with working local defaults, so the copy above is
enough to run the stack as-is. Adjust values only if you need to change
ports or credentials.

| Variable | Purpose |
|---|---|
| `DEBUG` | Django debug mode |
| `SECRET_KEY` | Django secret key — change for anything beyond local/demo use |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Database credentials |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Overridden to `db` / `5432` inside Docker via `docker-compose.yml`; these `.env` values matter for running outside Docker |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Redis connection for Celery — overridden to the `redis` service inside Docker |

---

## 2. Start the stack

```bash
docker compose up --build
```

This brings up four services:

| Service | Role |
|---|---|
| `web` | Django app via Gunicorn, port `8000` |
| `db` | PostgreSQL 16, exposed on host port `5433` (container port `5432`) |
| `redis` | Redis 7, exposed on host port `6380` (container port `6379`) |
| `worker` | Celery worker |
| `beat` | Celery Beat, runs `flag_overdue_checkouts` hourly |

Leave this running in its own terminal, or add `-d` to run detached.

> **Troubleshooting — `password authentication failed for user "postgres"`**
> when running `migrate` or on `web`/`worker` startup: this happens if
> `POSTGRES_PASSWORD` (or `POSTGRES_USER`/`POSTGRES_DB`) in `.env` was
> changed *after* the `db` container had already initialized once.
> Postgres's Docker image only runs its create-user/create-database
> initialization the **first** time it starts against an empty data
> volume — after that, the password is baked into the volume itself, so a
> later `.env` change doesn't update it and the two stop matching. Fix by
> wiping the volume so Postgres re-initializes with the current `.env`
> values:
> ```bash
> docker compose down -v
> docker compose up --build
> ```
> `-v` deletes the `postgres_data` volume — meaning all data in it,
> including anything seeded — so re-run `migrate` and `seed_demo_data`
> afterward. Any time you change Postgres credentials in `.env` after the
> first `docker compose up`, `down -v` is required again — a plain
> `docker compose restart` will not pick up the change.

---

## 3. Run migrations

In a second terminal:

```bash
docker compose exec web python manage.py migrate
```

---

## 4. Seed demo data

```bash
docker compose exec web python manage.py seed_demo_data
```

Creates, on a fresh database:

- 8 assets across all 4 categories (`CAMERA`, `LAPTOP`, `SENSOR`, `VEHICLE`)
- 4 employees, one of whom (`EMP004`) is inactive
- 2 currently overdue check-outs
- 2 check-outs returned on time
- 1 check-out returned late
- a demo API user for authentication: **username `dhruv`, password `demo12345`**

The command is idempotent — safe to run again on an already-seeded
database. It re-checks existing rows by natural key (`asset_tag`,
`employee_code`) and by existing check-out history before creating
anything, and prints `exists` / `skipped` instead of duplicating data.
Re-running the seed command does not replace the API — you can still
create additional assets through `POST /assets/`.

> **Note:** the `inventory/management/commands/` folder also contains
> `seed_demo_assets.py`, `seed_demo_employees.py`, and
> `seed_demo_checkouts.py`. These are **not used by, and not required by,
> the setup above** — they were early standalone drafts kept around for
> manual ad-hoc testing during development (e.g. quickly adding a batch of
> extra assets/employees to poke at the API by hand). They are **not
> idempotent** — running them more than once duplicates rows — so do not
> run them as part of normal setup or evaluation. `seed_demo_data.py` is
> the only seed command intended for use.

---

## 5. Authenticate

```bash
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "dhruv", "password": "demo12345"}'
```

Returns:

```json
{"refresh": "<refresh_token>", "access": "<access_token>"}
```

Use the access token on every subsequent request:

```bash
curl http://localhost:8000/api/v1/assets/ \
  -H "Authorization: Bearer <access_token>"
```

Access tokens last 60 minutes; refresh tokens last 1 day. Refresh via:

```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<refresh_token>"}'
```

Only `GET /api/v1/health/` is unauthenticated. Every other endpoint
requires a valid Bearer token and returns `401` without one.

Authentication uses Django's built-in `User` model with JWT
(`djangorestframework-simplejwt`) — see **Assumptions** below for why this
is separate from `Employee`.

---

## 6. API reference

Base path: `/api/v1/`

| Method & path | Auth | Notes |
|---|---|---|
| `POST /auth/login/` | No | Returns access + refresh tokens |
| `POST /auth/refresh/` | No | Exchanges refresh token for a new access token |
| `GET /health/` | No | `200` + `{"status": "healthy", "database": "connected"}`, or `503` if the DB is unreachable |
| `POST /assets/` | Yes | Create an asset |
| `GET /assets/` | Yes | Paginated (20/page); filter by `status`, `category`; search by `name` or `asset_tag` via `?search=` |
| `GET /assets/{id}/` | Yes | Includes `current_holder`: `null` if available, else `{employee_code, full_name}` |
| `POST /checkouts/` | Yes | Body: `{asset_tag, employee_code, due_at}` |
| `POST /checkouts/{id}/return/` | Yes | Body: `{condition_note, needs_maintenance}` |
| `GET /employees/{employee_code}/summary/` | Yes | Lifetime count, currently held, currently overdue, mean hold duration in days — single aggregated ORM query |
| `GET /employees/{employee_code}/checkouts/` | Yes | **Extra endpoint, not required by the assignment.** Returns the employee's full check-out history (asset, dates, returned/open status). Added because `/summary/` only returns aggregate numbers — during manual testing there was no way to see *which* check-outs made up those numbers without querying the database directly. This gives that visibility through the API instead. |
| `GET /reports/overdue/` | Yes | Open, overdue check-outs, most overdue first, with asset/employee detail |

### Business rules and status codes

| Rule | Status |
|---|---|
| Asset not `AVAILABLE` | `409` |
| Employee `is_active=False` | `400` |
| Employee already has 3 open check-outs | `409` |
| `due_at` not in the future, or more than 30 days out | `400` |
| Unknown `asset_tag` or `employee_code` | `404` |
| Returning an already-returned check-out | `409` |

A successful check-out creates the `CheckOut` row and flips the asset to
`CHECKED_OUT` atomically (`transaction.atomic()`); a failure anywhere in
that block leaves the asset `AVAILABLE`, never orphaned mid-state.

Concurrency: two simultaneous check-out requests for the same asset are
resolved at the database level with `select_for_update()` locking the
asset row before the availability check — exactly one succeeds, the other
gets `409`. This is verified by a real multi-threaded test
(`test_concurrent_checkout_only_allows_one`), not a sequential one.

---

## 7. Background task

`flag_overdue_checkouts` (Celery task) finds every open, overdue
check-out and creates an `OverdueNotice` dated today. It is idempotent —
`get_or_create` on `(checkout, notice_date)` plus a database-level unique
constraint means running it any number of times in a day produces at most
one notice per check-out. It's scheduled hourly via Celery Beat inside the
`beat` service.

Run it manually if needed:

```bash
docker compose exec web python manage.py shell -c "from inventory.tasks import flag_overdue_checkouts; flag_overdue_checkouts.delay()"
```

Watch the worker logs to confirm it ran:

```bash
docker compose logs -f worker
```

---

## 8. Running tests

```bash
docker compose exec web pytest -v
```

or, without Docker (see [Appendix](#appendix-running-without-docker) for
the full local setup — venv, pip install, local `.env`):

```bash
pytest
```

Current state: **39 passed, 0 failed.**

Coverage includes: check-out business rules (all rejection paths and
status codes), the concurrency guarantee (real threads, not a mocked
sequential call), the return flow including duplicate-return rejection,
employee summary aggregation values against controlled test data, the
overdue report (including an item due exactly now), and the background
task's idempotency (run twice, assert exactly one notice).

---

## 9. Assumptions

- **Authentication is Django `User` + JWT, kept fully separate from
  `Employee`.** `Employee` is a business record (who physically holds an
  asset) with no login of its own, per the assignment's explicit
  instruction not to build employee accounts or role management. The API
  user authenticating requests and the employee holding an asset are
  unrelated concepts.
- **`select_for_update()` is the sole concurrency mechanism** for
  check-out — no application-level locks, flags, or sleep-based
  workarounds, as required.
- **Pagination is DRF's standard `PageNumberPagination` at 20/page**, no
  cursor pagination, since the assignment didn't call for it and the
  data volumes here don't need it.
- **The demo API user (`dhruv` / `demo12345`) is created by
  `seed_demo_data`** purely so the API is immediately usable after
  seeding, without a separate manual `createsuperuser` step. It is a
  superuser/staff account for convenience in this take-home context, not
  a production credential.
- **`GET /employees/{employee_code}/checkouts/` was added beyond the
  spec.** The required `/summary/` endpoint only returns four aggregate
  numbers (lifetime count, held, overdue, mean duration). There was no
  way to inspect which actual check-out records produced those numbers
  without going into the database directly, which made both manual
  testing and debugging harder than necessary. This endpoint exposes the
  underlying list so that verification doesn't require DB access. It adds
  no new business rule and doesn't replace or change anything the
  assignment specifies.

---

## 10. Known gaps

- **JWT signing key length**: `SECRET_KEY` in `.env.example` is a short
  placeholder (`change-me`). `djangorestframework-simplejwt` emits an
  `InsecureKeyLengthWarning` in tests because of this. Fine for local/demo
  use; a real deployment needs a properly generated, ≥32-byte secret.
- **No rate limiting / throttling** on the login endpoint or elsewhere —
  out of scope for the assignment, but would matter in production.
- **No token blacklist/rotation** configured for JWT — refresh tokens
  remain valid for their full lifetime even after use. `simplejwt`
  supports this out of the box if it becomes a requirement.
- **Three unused seed-script drafts remain in the repo** (see the note in
  step 4 above) — kept intentionally for reference/manual testing rather
  than deleted, but not part of the supported setup path.

---

## Project structure

```text
assetflow/
├── config/                  # Django project settings, urls, celery app
├── inventory/
│   ├── models.py             # Asset, Employee, CheckOut, OverdueNotice
│   ├── serializers/
│   ├── views/
│   ├── services/              # checkout/return business logic
│   ├── tasks.py               # flag_overdue_checkouts
│   ├── management/commands/   # seed_demo_data (+ unused drafts, see step 4)
│   ├── migrations/
│   └── tests/                 # conftest.py + test_*.py, 39 tests
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
└── manage.py
```

---
