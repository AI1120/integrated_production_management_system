# IPMS — Integrated Production Management System

A working production management system for a small discrete-assembly factory,
built as the foundation for a multi-plant rollout.

The sample plant makes LED floodlights: raw castings and LED chips come in, get
built into module sub-assemblies, assembled into finished lights, tested,
packed, and shipped. Every module — production, inventory, quality, equipment —
runs off the same data, so a scrap booked at a test bench moves the OEE number,
the yield KPI and the stock ledger in one transaction.

---

## Quick start

**Easiest — Windows:** double-click `start-backend.cmd`, then `start-frontend.cmd`.
Each creates its venv / installs dependencies on first run, seeds the sample
factory, and starts its server. If anything fails the window stays open with the
reason.

**Manually**, two terminals from the repository root.

Backend (Python 3.10+) — PowerShell:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m app.seed --reset      # build the sample factory
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8010 --reload
```

macOS / Linux:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m app.seed --reset
.venv/bin/python -m uvicorn app.main:app --port 8010 --reload
```

Frontend (Node 18+), either platform:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The Vite dev server proxies `/api` to the
backend, so there is no CORS setup or base URL to configure.

Interactive API docs: **http://localhost:8010/docs**

> The dev server listens on all interfaces (`host: '::'`) so shop-floor tablets
> on the LAN can reach the operator terminal. Run `IPMS_HOST=127.0.0.1 npm run dev`
> to keep it on this machine only.

### Sign in

| Username    | Password     | Role      | Can do                                        |
|-------------|--------------|-----------|-----------------------------------------------|
| `admin`     | `admin123`   | Admin     | Everything, plus user management               |
| `planner`   | `planner123` | Planner   | Master data, create/release/close work orders  |
| `operator1` | `oper123`    | Operator  | Shop-floor terminal, confirmations, downtime   |
| `qc1`       | `qc123`      | Quality   | Inspections, dispositions, NCRs                |
| `wh1`       | `wh123`      | Warehouse | Goods receipt, issue, transfer, adjustment     |

Operator badges (`B-1001`, `B-2001`, …) are scannable at the terminal.

### Verify the install

```bash
cd backend
.venv/Scripts/python.exe smoke_test.py
```

Drives a real order through the whole plant against the running API — create,
release, issue, confirm every operation, inspect, release from quarantine — and
asserts stock, OEE and traceability all moved correctly. 50+ checks, exits
non-zero on failure.

---

## What the sample factory contains

Seeded by `python -m app.seed --reset`, deterministic (fixed random seed):

- **14 parts** — 2 finished goods, 1 sub-assembly, 9 raw materials, 2 consumables
- **3 BOMs** and **3 routings** across 4 work centres and 5 machines
- **1 shift** — day shift 08:00–17:00, Monday to Friday
- **10 days of history** — 18 work orders, 44 confirmations, 91 downtime events,
  14 inspections, 4 NCRs, ~48 stock lots
- Live state: one machine down with an open downtime event, two orders in flight,
  two queued for tomorrow

---

## Modules

### Production
Work orders take a **frozen copy** of the BOM and routing at creation, so later
master-data edits never rewrite what the floor was told to build. Operations must
run in sequence; you cannot book step 30 before step 20 has released units, and
you cannot over-report against what cleared the previous step. The final routing
step books finished output into stock — into quarantine when the routing requires
inspection.

### Inventory
Every quantity change goes through one function (`post_movement`) that updates
the affected lots and appends an immutable ledger row. Nothing else writes `qty`.
Issues pick FIFO by receipt date. Lot genealogy walks backwards from a finished
lot to every component lot consumed by the order that produced it — the trace an
audit or recall starts from.

### Quality
Inspection plans carry measurable characteristics with limits. Recording an
inspection judges each value automatically, then acts on the verdict: a pass
releases the lot from quarantine into finished stock, a failure blocks the lot
and raises an NCR. Setting an NCR disposition to Scrap writes the quantity off
stock immediately.

### Equipment & OEE
Machine state changes open and close downtime events, so availability data cannot
drift from what the machine board shows.

```
Scheduled time = shift calendar ∩ reporting window
Loading time   = scheduled − planned stops
Run time       = loading − unplanned stops
Availability   = run / loading
Performance    = (ideal cycle × units) / run
Quality        = good / total
OEE            = A × P × Q
```

The shift calendar matters: measured against wall-clock time the same plant
reports **2.8%** OEE, because it counts nights and weekends as lost production.
Against scheduled time it reports **60%**, which is the real number. Time with no
order queued is logged against an excluded reason — an idle machine with no
demand has not lost anything.

### Optimisation — process, time and cost
A finite-capacity forward scheduler loads the open order book onto real machines
under three constraints: routing sequence, one job per machine, and the shift
calendar. It then builds the same book under five dispatch rules and reports what
each one costs, so the choice of sequence is evidenced rather than habitual.

```
Scheduled   -> Loading   -> Run        finite capacity, calendar-aware
PRIORITY | EDD | SPT | LPT | CR        judged on lateness, makespan or worst case
```

Costing rolls each order up twice — standard from master data, actual from the
issues and confirmations the floor recorded — and reports the variance, plus
scrap ranked by **money** rather than count. The page ends in a ranked list of
evidenced actions across all three dimensions.

The customer due date is stored separately from the planned dates, and applying a
schedule rewrites only the plan. Overwriting the commitment would make every
schedule look perfectly on time.

### Calendar
A month view of the plant with three distinct kinds of event: what the floor
actually booked (history, not editable), what is planned for open orders, and
what was promised to the customer. A planner drags a planned order to re-plan it.

Moving a due date is a separate act from moving the plan: it needs an explicit
flag and a written reason, which is recorded on the order. A calendar that treats
the plan and the promise as the same object is how a plant talks itself into
believing it is on time.

### Accounts
Administrators create people, set roles, reset passwords and disable accounts.
Accounts are disabled rather than deleted so the production history stays intact.
Anyone can change their own password with their current one.

Two lockouts are refused outright: an administrator cannot remove their own
admin access, and the last active administrator cannot be demoted or disabled.

### Process map
`/workflow` draws the whole system as a diagram: the end-to-end material
pipeline, and every state machine — order, operation, lot, inspection, NCR,
disposition, machine — with a live count on each state. States are zero-filled
from the enums rather than from whatever rows exist, so an empty state still
appears (dashed) instead of silently vanishing from the picture.

### Shop floor
A scanner is a keyboard that types a code and presses Enter, so the terminal is
driven from one always-focused input. `POST /api/production/scan` resolves a
scanned string to whichever of order / part / lot / operator badge it matches.

---

## Layout

```
backend/
  app/
    models/          SQLAlchemy tables, one module per domain
    schemas/         Pydantic request & response models
    services/        Business logic — the only place that mutates state
      inventory_service.py    stock engine + immutable ledger
      production_service.py   order lifecycle, confirmations, roll-up
      oee_service.py          shift calendar, OEE, downtime Pareto
    api/routers/     HTTP layer: validation, roles, error mapping
    seed.py          the sample factory
  smoke_test.py      end-to-end API test
frontend/
  src/
    api/             typed client + TanStack Query hooks
    components/      layout, UI primitives, charts
    pages/           one per module
```

Business rules live in `services/`, never in routers. Routers validate input,
enforce roles, and translate `StockError` / `ProductionError` into HTTP codes.

---

## Scaling to the full plant

Deliberate choices that make the sample a foundation rather than a throwaway:

| Concern | Sample today | Production change |
|---|---|---|
| Database | SQLite file | Set `IPMS_DATABASE_URL=postgresql+psycopg://…` — no model changes; enum columns are plain VARCHAR precisely so adding a status is a code change, not a table migration |
| Schema changes | `create_all` at startup | Add Alembic before the first real deployment |
| Multi-plant | `IPMS_PLANT_CODE` / `IPMS_PLANT_NAME` | One deployment per site, or add `plant_id` to the transactional tables |
| Auth | JWT + PBKDF2 | Point at the corporate IdP; swap `hash_password`/`verify_password` for argon2 |
| Scheduling | Heuristic forward loading, five dispatch rules | Add sequence-dependent setup and a real optimiser (CP-SAT) if the plant outgrows a rule comparison |
| Machine data | Manual entry + barcode | Add an ingestion endpoint writing `Confirmation` and `DowntimeEvent` from PLC counters — the OEE math needs no change |
| Secret key | Dev default | **Set `IPMS_SECRET_KEY`.** The default is not safe outside a demo |
| Frontend API URL | `/api` via the dev proxy | The proxy is dev-only. For a production build, either serve the app and API from one origin, or build with `VITE_API_BASE=https://api.example.com/api npm run build` |

Configuration is environment-driven (`IPMS_` prefix, or a `backend/.env` file).
See `backend/app/config.py`.

---

## Known limitations

Scoped out of the sample, in rough priority order for the next iteration:

- **No purchasing or MRP.** Low stock is flagged; nothing raises a purchase order.
- **No rework routing.** An NCR can be dispositioned to Rework, but that does not
  yet generate a rework order.
- **No shift-level or operator-level labour reporting** beyond the duration on
  each confirmation.
- **`create_all` instead of migrations** — fine for a demo, not for a plant with
  live data.
- **Single shift pattern.** The `Shift` table supports several, including
  overnight, but there is no UI to manage them.
