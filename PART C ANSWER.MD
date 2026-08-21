# Part C — Optimise a Slow PostgreSQL Query

## 1. Rewrite the query

```sql
SELECT
    c.id,
    c.asset_id,
    c.employee_id,
    c.checked_out_at,
    c.due_at,
    c.returned_at,
    c.condition_note
FROM checkouts c
JOIN employees e
    ON e.id = c.employee_id
   AND e.is_active = true
WHERE c.checked_out_at >= '2026-01-01T00:00:00+00'
  AND c.checked_out_at <  '2026-07-01T00:00:00+00'
  AND c.returned_at IS NULL
ORDER BY c.due_at ASC;
```

**What changed and why:**

- **`DATE(c.checked_out_at) BETWEEN ...` → a plain range predicate.** Wrapping a column in `DATE()` makes it non-sargable — Postgres can't use a btree index on `checked_out_at` because the index stores raw timestamp values, not their date-truncated form, so every row must be evaluated by the function before comparison. Rewriting as `>= start AND < end` lets the planner use a direct index range scan instead of a full scan.
- **Switched to a half-open interval** (`< '2026-07-01'` instead of `<= '2026-06-30'`). The original `BETWEEN` with a bare date literal on a `timestamptz` column implicitly means `'2026-06-30 00:00:00'`, silently excluding any checkout that happened later that same day. This is a correctness bug hiding inside what looks like a pure performance query — worth flagging even though the assignment framed this as an optimisation task, not a bug hunt.
- **`SELECT *` → explicit columns.** `condition_note` is a `text` field that's expensive to pull for every row and unnecessary for a reporting screen; selecting only what's needed reduces I/O and heap access, and makes an index-only scan possible for the filter/sort columns if the query is narrowed further in future.
- **`IN (SELECT id FROM employees WHERE is_active = true)` → explicit `JOIN`.** Functionally the planner on PG15 already rewrites this subquery into a semi-join, so the raw performance gain here is minimal — but it's clearer to read, easier to reason about in `EXPLAIN` output, and removes any risk of the planner choosing a worse strategy (e.g. a correlated re-execution per row) if the subquery becomes non-trivial in a future edit.
- **`ORDER BY c.due_at` kept as-is** — it's required by the report and is addressed via indexing below, not by removing it.

## 2. Indexes

```sql
-- Primary index: partial on open checkouts, indexed by the range-filter column.
-- returned_at IS NULL is almost certainly the most selective predicate here —
-- most historical checkouts over 4.2M rows have long since been returned, so
-- "open" checkouts are a small, roughly-bounded subset (proportional to the
-- number of assets currently checked out, not to total history).
CREATE INDEX CONCURRENTLY idx_checkouts_open_checked_out_at
    ON checkouts (checked_out_at)
    WHERE returned_at IS NULL;

-- Safety net on the employees side. employees is only ~12k rows, so a seq
-- scan there is cheap regardless — this index mostly matters if is_active
-- filtering is reused elsewhere at higher frequency; low priority here.
CREATE INDEX CONCURRENTLY idx_employees_active
    ON employees (id)
    WHERE is_active = true;
```

**Why a partial index, not a full composite one:** a non-partial composite index like `(returned_at, checked_out_at)` would still have to be maintained across all 4.2 million rows (and growing), including the ~4M+ rows that will never again match `returned_at IS NULL`. That's wasted index size and wasted write-amplification on every checkout return — an `UPDATE` that flips `returned_at` from `NULL` to a timestamp has to update every index touching that row. A **partial index restricted to `WHERE returned_at IS NULL`** only ever indexes currently-open checkouts — it stays small and cheap to maintain regardless of how large the historical table grows, and it directly matches the query's actual access pattern.

**Why I did *not* add an index on `due_at` for the `ORDER BY`:** after the partial index narrows the scan to open checkouts within the date range, the remaining row count is very likely small enough (tens of thousands, not millions) that an in-memory quicksort on `due_at` is fast and not worth a second index and its maintenance cost. If `EXPLAIN ANALYZE` shows this sort spilling to disk in practice (see part 3 below), the fix is a second partial index — `CREATE INDEX CONCURRENTLY idx_checkouts_open_due_at ON checkouts (due_at) WHERE returned_at IS NULL;` — but I'd only add it after confirming the sort is actually the bottleneck, not preemptively.

**On `CONCURRENTLY`:** both indexes are created with `CONCURRENTLY` so they don't hold a blocking lock on a table this large in production — it takes longer to build but never blocks reads or writes during creation. In Django, this requires a migration with `atomic = False` and `AddIndexConcurrently`, since `CONCURRENTLY` cannot run inside a transaction block.

## 3. Expected `EXPLAIN (ANALYZE, BUFFERS)` — before vs. after

**Before:** I'd expect a `Seq Scan on checkouts` node scanning close to the full 4.2M rows, with `DATE(checked_out_at) BETWEEN ...` and `returned_at IS NULL` both applied as `Filter` conditions (not `Index Cond`) since neither is index-supported as written, joined via `Hash Semi Join` against `employees`, and then a `Sort` node on `due_at` over whatever survives the filter. The line I'd look for specifically: **`Sort Method: external merge  Disk: NNNN kB`** — if the pre-filter result set is large enough that Postgres can't sort it in `work_mem`, it spills to disk, which is often the single biggest cost in a query like this. `Buffers: shared hit=... read=...` would show a very high block count, roughly proportional to the whole table's physical size.

**After:** I'd expect an `Index Scan using idx_checkouts_open_checked_out_at`, with the `checked_out_at` range as `Index Cond` and no `Filter` needed for `returned_at` (the partial index already guarantees it). The employee join becomes a cheap `Hash Join` against a tiny, already-filtered `employees` set. The critical line to check: the `Sort` node should now show **`Sort Method: quicksort  Memory: NN kB`** — confirming the filtered set is small enough to sort in memory, no disk spill. `Buffers` should drop by roughly two orders of magnitude, since the scan now touches only the open-checkout subset of the table rather than all 4.2M rows.

**The one line that proves the fix worked:** the `Sort Method` line changing from `external merge  Disk: ...` to `quicksort  Memory: ...`, combined with the top-level `Execution Time` dropping from ~8000ms toward something in the tens-to-low-hundreds of milliseconds.

## 4. What breaks first as the table keeps growing (8,000 rows/day)

The partial index stays healthy indefinitely, since it only tracks currently-open checkouts, not total history — that part of the design doesn't degrade with table growth. What **does** break first:

- **Autovacuum falling behind.** Every checkout return is an `UPDATE` (flipping `returned_at` from `NULL` to a timestamp), which creates a dead tuple, and every new checkout is an `INSERT`. At 8,000 new checkouts/day plus a comparable volume of returns, dead-tuple accumulation grows in lockstep with the table. If autovacuum's default cost-based throttling can't keep pace with that write volume, table and index bloat creep in — the partial index specifically will start silently indexing dead rows that autovacuum hasn't reclaimed yet, degrading its selectivity advantage over time. This tends to be invisible until it's suddenly not: query plans stay fine for months, then degrade over a week or two as bloat crosses a threshold.
- **The employees FK index and general write amplification.** At 4.2M+ rows and climbing, every new checkout's `INSERT` has to update the standard btree indexes Django creates on `asset_id` and `employee_id`, plus the two new partial indexes. This is a fixed, small per-row cost, but it compounds — write latency creeps upward gradually rather than falling off a cliff.
- **Table bloat inflating physical size disproportionate to live data**, which slowly increases the cost of any operation that still needs a broader scan (e.g. an admin report with a wider date range than "open checkouts," or ad hoc analytics queries that can't use this partial index).

**What I'd do before it happens:** monitor `pg_stat_user_tables` for `n_dead_tup` relative to `n_live_tup` on `checkouts`, and check `last_autovacuum` timestamps to confirm vacuum is actually keeping up rather than being pushed further behind. If it starts falling behind, tune `autovacuum_vacuum_cost_limit` / `autovacuum_vacuum_scale_factor` specifically for this table (via `ALTER TABLE checkouts SET (autovacuum_vacuum_scale_factor = ...)`) rather than globally, since a table this size and write volume needs more aggressive vacuuming than Postgres's defaults assume. I'd also consider whether `checkouts` eventually needs partitioning by `checked_out_at` (e.g. monthly range partitions) once it's an order of magnitude larger than today — not needed now, but worth flagging as the next lever if row count keeps compounding at this rate for years.

## 5. One thing I'd want to measure on the real database first

**The actual selectivity of `returned_at IS NULL`** — i.e., what fraction of the 4.2M rows are currently open vs. returned. My entire indexing strategy assumes open checkouts are a small minority of the table (which is true for any healthy equipment-tracking system, since most historical checkouts get returned eventually). But if, for some operational reason, a large fraction of checkouts are never marked returned — abandoned records, a broken return flow elsewhere in the system, bulk-imported historical data with `returned_at` left null — the partial index balloons toward the size of a full index and loses most of its advantage. I can't know this from the schema alone; it requires running `SELECT count(*) FILTER (WHERE returned_at IS NULL), count(*) FROM checkouts;` against production, or at minimum a realistic staging copy, before committing to this indexing strategy over alternatives like a full composite index.