# Domain model & business rules

Reference for anyone extending IPMS toward the full plant. Describes what each
table means, the invariants the code enforces, and why the boundaries sit where
they do.

---

## 1. Master data

| Table | Meaning |
|---|---|
| `items` | Part master. Everything stockable, buyable or makeable. `item_type` decides behaviour: only `FINISHED_GOOD` and `SUB_ASSEMBLY` can be produced. |
| `boms` / `bom_lines` | What a part is made of. `qty_per` is per one unit of parent; `scrap_pct` inflates the requirement; `operation_seq` says which routing step consumes it. |
| `routings` / `routing_operations` | How a part is made. Ordered steps, each on a work centre, with setup and per-unit run time. `requires_inspection` gates the output through quarantine. |
| `work_centers` | Capacity groups — a cell, a line, a bench. |
| `machines` | Physical equipment inside a work centre. `ideal_cycle_seconds` is the P in OEE. |
| `locations` | Stock locations, typed `RAW` / `WIP` / `FINISHED` / `QUARANTINE` / `SCRAP`. The type drives automatic routing of stock, so the code never hardcodes a location code. |
| `shifts` | When the plant is scheduled to produce. Minutes-from-midnight, so an overnight shift is arithmetic rather than a special case. |
| `partners` | Customers and suppliers. Minimal — the hook for an ERP link. |

**Only one BOM and one routing per item may be active.** Creating an active one
deactivates the others (`api/routers/master.py`).

---

## 2. Production

```
ProductionOrder ──< OrderOperation ──< Confirmation
       └────────< OrderMaterial
```

`OrderOperation` and `OrderMaterial` are **copies** taken from the routing and
BOM at order creation. This is the single most important structural decision in
the system: master data is mutable, production history is not. Change a routing
tomorrow and yesterday's orders still show what the floor was actually told to
build.

### Order lifecycle

```
DRAFT ──release──> RELEASED ──first confirmation──> IN_PROGRESS
                                                         │
                        all operations complete ─────────┴──> COMPLETED ──> CLOSED
DRAFT ──cancel──> CANCELLED        (only while qty_produced = 0)
```

Releasing assigns the output lot number (`WO-2609-0007` → `LOT-2609-0007`).

### Invariants enforced in `services/production_service.py`

1. **Material cannot be issued before release.**
2. **Operations run in sequence.** An operation's capacity is the order quantity
   for the first step, and *whatever cleared the previous step* for every later
   one. This is why upstream scrap does not make downstream steps impossible to
   finish — the naive rule (`>= qty_ordered`) leaves the last operation stuck
   forever the moment a single unit is scrapped.
3. **No over-reporting.** `qty_completed + qty_scrapped` may never exceed that
   capacity.
4. **Only the final routing step adds to `qty_produced`** and books stock.
   Intermediate steps move units along; they do not create finished goods.
5. **Statuses are re-derived, never incremented.** Every confirmation recomputes
   all operation statuses from quantities, so a booking anywhere on the order
   leaves the whole order consistent.

---

## 3. Inventory

```
StockLot     — on-hand qty of (item, lot, location). Mutable.
StockMovement — immutable ledger. Append-only.
```

**Every quantity change goes through `inventory_service.post_movement`.** It is
the only code permitted to write `StockLot.qty`. Each movement type declares
whether it adds to a location, removes from one, or both:

| Type | Removes from | Adds to |
|---|---|---|
| `RECEIPT` | — | destination |
| `ISSUE` | source | — (consumed by the order) |
| `PRODUCTION_RECEIPT` | — | destination |
| `TRANSFER` | source | destination |
| `SCRAP` | source | — |
| `ADJUSTMENT` | — | destination (signed) |

`ISSUE` and `SCRAP` deliberately have no inbound leg. The destination is recorded
on the ledger row for reporting, but no lot is created — issued material is
consumed by the order, not parked in a WIP lot that would never be relieved.

Other rules:

- Lot-controlled items reject a movement with no lot number.
- Outbound movements refuse to drive a lot negative unless `allow_negative`.
- Inbound movements maintain a weighted-average `unit_cost`.
- A lot that reaches zero is marked `CONSUMED`.
- `allocate_fifo` picks oldest-first and **raises rather than partially
  allocating**, so a caller never silently issues a short kit.

### Traceability

`GET /api/inventory/trace/{lot_no}` returns where the lot is now, every movement
that touched it, and — via `StockLot.source_order_id` — every component lot
issued to the order that produced it. That backward walk is what an audit or a
recall starts from.

---

## 4. Quality

```
InspectionPlan ──< InspectionCharacteristic
Inspection ──< InspectionResult
NonConformance
```

Recording an inspection (`api/routers/quality.py`) does four things in one
transaction:

1. Judges each measured value against its characteristic's limits.
   Numeric: inside `[lower_limit, upper_limit]`. Attribute: text in
   `{OK, PASS, GOOD, Y, YES}`.
2. Sets the overall result — `FAIL` if any value failed **or** any quantity was
   rejected.
3. Acts on the lot: a pass transfers it out of quarantine into its proper store
   and marks it `AVAILABLE`; a failure marks it `REJECTED`, which excludes it
   from on-hand and from FIFO allocation.
4. Raises an NCR automatically on failure.

Setting an NCR's disposition to `SCRAP` posts a scrap movement immediately —
the write-off is a consequence of the decision, not a separate task someone has
to remember.

---

## 5. Equipment & OEE

```
Machine ──< DowntimeEvent >── DowntimeReason
Machine ──< MaintenanceRequest
```

`DowntimeReason.affects_availability` is the pivotal flag. `False` means the
minutes are **excluded** from loading time rather than counted as a loss:
breaks, planned maintenance, and "no work scheduled".

```
scheduled = shift calendar ∩ window          # oee_service.scheduled_minutes
loading   = scheduled − planned stops
run       = loading − unplanned stops
A = run / loading
P = min(ideal_cycle × total_units / run, 1)
Q = good / total
```

Three things to know before trusting the number:

- **Without a shift calendar the result is meaningless.** With no shifts
  configured the service falls back to wall-clock time, and a plant running one
  day shift reports single-digit OEE because nights and weekends count as loss.
- **`ideal_cycle_seconds` is per machine, not per product.** On a machine running
  a mix, it must be the volume-weighted best cycle across that mix. It is the
  first thing to re-derive when the mix changes, and the usual cause of a
  performance figure that looks wrong.
- **P is capped at 1.0.** Performance above 100% means the ideal cycle is wrong,
  not that the machine beat physics.

Machine status changes and downtime events are two views of one fact:
`POST /equipment/machines/{id}/status` opens an event when a machine stops and
closes it when it restarts, so availability cannot drift from the board.

---

## 6. Cross-cutting

**Document numbers** — `services/numbering.py` issues `WO-YYMM-0001`,
`INS-…`, `NCR-…`, `MNT-…`, `RCV-…` from a counter table, inside the caller's
transaction so concurrent callers cannot collide.

**Enums** are stored as plain `VARCHAR` through the `EnumString` type decorator
(`database.py`), which converts back to the Python enum on load. A bare `String`
column returns `str`, which silently breaks every `is` comparison against the
enum — and a native DB enum would make adding a status a migration on a live
table instead of a code change.

**Roles** — `require_roles(...)` in `api/deps.py`; `ADMIN` passes every gate. The
frontend mirrors this in `useAuth().can()` to hide controls, but the server is
the enforcement point.

**Errors** — services raise `StockError` / `ProductionError` with a message
written for the person on the floor ("Insufficient stock: RM-3008 lot L2608-3008-1
has 40 EA, needs 84 EA"). Routers map them to HTTP 400 and the UI shows them
verbatim.
