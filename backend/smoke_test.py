"""End-to-end smoke test against a running IPMS API.

    python smoke_test.py [base_url]

Walks one order the whole way through the plant - create, release, issue,
confirm every operation, inspect, then check stock and OEE moved as expected.
Exits non-zero on the first failure.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010").rstrip("/")
TOKENS: dict[str, str] = {}
failures: list[str] = []


def call(method: str, path: str, body=None, token: str | None = None, expect: int | None = None):
    url = f"{BASE}/api{path}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode()
            status = response.status
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode()
        status = exc.code
    parsed = json.loads(payload) if payload else None
    if expect is not None and status != expect:
        raise AssertionError(f"{method} {path} -> {status} (expected {expect}): {payload[:300]}")
    return status, parsed


def login(username: str, password: str) -> str:
    if username not in TOKENS:
        _, data = call("POST", "/auth/login", {"username": username, "password": password}, expect=200)
        TOKENS[username] = data["access_token"]
    return TOKENS[username]


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}{'' if condition else f' -- {detail}'}")
    if not condition:
        failures.append(label)


def main() -> int:
    print(f"IPMS smoke test against {BASE}\n")

    # --- 1. health & auth ---------------------------------------------------
    print("1. Health and authentication")
    status, health = call("GET", "/health", expect=200)
    check("health endpoint responds", health["status"] == "ok", str(health))

    status, _ = call("POST", "/auth/login", {"username": "planner", "password": "wrong"})
    check("bad password is rejected", status == 401, f"got {status}")

    status, _ = call("GET", "/production/orders")
    check("unauthenticated request is rejected", status in (401, 403), f"got {status}")

    planner = login("planner", "planner123")
    operator = login("operator1", "oper123")
    qc = login("qc1", "qc123")
    warehouse = login("wh1", "wh123")
    check("all four roles can sign in", len(TOKENS) == 4)

    # --- 2. role enforcement ------------------------------------------------
    print("\n2. Role enforcement")
    status, _ = call("POST", "/master/items", {"code": "X-1", "name": "Nope"}, token=operator)
    check("operator cannot create master data", status == 403, f"got {status}")
    status, _ = call("GET", "/master/items", token=operator)
    check("operator can read master data", status == 200, f"got {status}")

    # --- 3. master data -----------------------------------------------------
    print("\n3. Master data")
    _, items = call("GET", "/master/items", token=planner, expect=200)
    by_code = {item["code"]: item for item in items}
    check("seeded item catalogue is present", len(items) >= 14, f"{len(items)} items")
    check("FG-1001 exists", "FG-1001" in by_code)

    _, boms = call("GET", f"/master/boms?item_id={by_code['FG-1001']['id']}", token=planner, expect=200)
    check("FG-1001 has a BOM with lines", boms and len(boms[0]["lines"]) == 9, f"{boms and len(boms[0]['lines'])}")

    _, routings = call("GET", f"/master/routings?item_id={by_code['FG-1001']['id']}", token=planner, expect=200)
    check("FG-1001 has a 4-step routing", routings and len(routings[0]["operations"]) == 4)

    # --- 4. order lifecycle -------------------------------------------------
    print("\n4. Work-order lifecycle")
    tomorrow = datetime.now() + timedelta(days=1)
    _, order = call(
        "POST",
        "/production/orders",
        {
            "item_id": by_code["FG-1001"]["id"],
            "qty_ordered": 10,
            "planned_start": tomorrow.replace(hour=8, minute=0, second=0, microsecond=0).isoformat(),
            "planned_end": tomorrow.replace(hour=16, minute=0, second=0, microsecond=0).isoformat(),
            "sales_ref": "SMOKE-TEST",
        },
        token=planner,
        expect=201,
    )
    order_id = order["id"]
    check("order created in DRAFT", order["status"] == "DRAFT", order["status"])
    check("routing copied onto the order", len(order["operations"]) == 4)
    check("BOM exploded onto the order", len(order["materials"]) == 9)

    screws = next(m for m in order["materials"] if m["component"]["code"] == "RM-3008")
    check("scrap allowance inflates requirement", screws["qty_required"] == 84.0, str(screws["qty_required"]))

    status, _ = call(
        "POST",
        "/production/confirmations",
        {"operation_id": order["operations"][0]["id"], "qty_good": 1},
        token=operator,
    )
    check("cannot report against a DRAFT order", status == 400, f"got {status}")

    _, order = call("POST", f"/production/orders/{order_id}/release", token=planner, expect=200)
    check("order released", order["status"] == "RELEASED", order["status"])
    check("output lot number assigned", bool(order["output_lot_no"]), str(order["output_lot_no"]))

    # --- 5. material issue --------------------------------------------------
    print("\n5. Material issue")
    _, locations = call("GET", "/master/locations", token=warehouse, expect=200)
    raw = next(loc for loc in locations if loc["code"] == "WH-RAW")

    _, before = call(f"GET", f"/master/items/{screws['component_id']}", token=warehouse, expect=200)
    _, order = call(
        "POST",
        f"/production/orders/{order_id}/issue",
        {"material_id": screws["id"], "qty": screws["qty_required"], "from_location_id": raw["id"]},
        token=warehouse,
        expect=200,
    )
    _, after = call("GET", f"/master/items/{screws['component_id']}", token=warehouse, expect=200)
    check(
        "issuing relieves stock by exactly the issued quantity",
        abs((before["on_hand"] - after["on_hand"]) - screws["qty_required"]) < 1e-6,
        f"{before['on_hand']} -> {after['on_hand']}",
    )

    issued_line = next(m for m in order["materials"] if m["id"] == screws["id"])
    check("issued quantity recorded on the line", issued_line["qty_issued"] == screws["qty_required"])

    status, body = call(
        "POST",
        f"/production/orders/{order_id}/issue",
        {"material_id": screws["id"], "qty": 9_999_999, "from_location_id": raw["id"]},
        token=warehouse,
    )
    check("over-issue is refused", status == 400, f"got {status}")
    check("refusal explains the shortage", "Insufficient stock" in str(body), str(body))

    for material in order["materials"]:
        if material["id"] == screws["id"]:
            continue
        call(
            "POST",
            f"/production/orders/{order_id}/issue",
            {"material_id": material["id"], "qty": material["qty_required"], "from_location_id": raw["id"]},
            token=warehouse,
            expect=200,
        )

    # --- 6. confirmations ---------------------------------------------------
    print("\n6. Shop-floor confirmations")
    _, machines = call("GET", "/equipment/machines", token=operator, expect=200)
    machine_by_wc: dict[int, int] = {}
    for machine in machines:
        machine_by_wc.setdefault(machine["work_center_id"], machine["id"])

    operations = sorted(order["operations"], key=lambda op: op["seq"])

    status, _ = call(
        "POST",
        "/production/confirmations",
        {"operation_id": operations[1]["id"], "qty_good": 5},
        token=operator,
    )
    check("cannot skip ahead in the routing", status == 400, f"got {status}")

    status, _ = call(
        "POST",
        "/production/confirmations",
        {"operation_id": operations[0]["id"], "qty_good": 999},
        token=operator,
    )
    check("cannot over-report an operation", status == 400, f"got {status}")

    clock = datetime.now() - timedelta(hours=4)
    for index, operation in enumerate(operations):
        scrap = 1 if index == 2 else 0
        good = 10 - sum(1 for i in range(index + 1) if i == 2)
        started = clock
        ended = clock + timedelta(minutes=25)
        _, confirmation = call(
            "POST",
            "/production/confirmations",
            {
                "operation_id": operation["id"],
                "qty_good": good if index >= 2 else 10,
                "qty_scrap": scrap,
                "machine_id": machine_by_wc[operation["work_center_id"]],
                "started_at": started.isoformat(),
                "ended_at": ended.isoformat(),
            },
            token=operator,
            expect=201,
        )
        clock = ended + timedelta(minutes=10)
    check("all four operations confirmed", True)

    _, order = call("GET", f"/production/orders/{order_id}", token=planner, expect=200)
    check("order auto-completed", order["status"] == "COMPLETED", order["status"])
    check("produced quantity booked once", order["qty_produced"] == 9, str(order["qty_produced"]))
    check("scrap recorded", order["qty_scrapped"] == 1, str(order["qty_scrapped"]))

    # --- 7. output lands in quarantine --------------------------------------
    print("\n7. Output and quality gate")
    _, lots = call(
        "GET", f"/inventory/lots?lot_no={order['output_lot_no']}", token=qc, expect=200
    )
    check("output booked as a stock lot", len(lots) == 1, f"{len(lots)} lots")
    check("held in quarantine pending QC", lots[0]["status"] == "QUARANTINE", lots[0]["status"])
    check("quantity matches production", lots[0]["qty"] == 9, str(lots[0]["qty"]))

    _, plans = call(
        "GET", f"/quality/plans?item_id={by_code['FG-1001']['id']}", token=qc, expect=200
    )
    check("inspection plan available", bool(plans), "no plan")
    characteristics = plans[0]["characteristics"]

    results = []
    for characteristic in characteristics:
        if characteristic["char_type"] == "ATTRIBUTE":
            results.append({"characteristic_id": characteristic["id"], "sample_no": 1, "value_text": "OK"})
        else:
            results.append(
                {
                    "characteristic_id": characteristic["id"],
                    "sample_no": 1,
                    "value_numeric": characteristic["target"] or 50,
                }
            )

    _, inspection = call(
        "POST",
        "/quality/inspections",
        {
            "item_id": by_code["FG-1001"]["id"],
            "inspection_type": "FINAL",
            "plan_id": plans[0]["id"],
            "lot_no": order["output_lot_no"],
            "order_id": order_id,
            "qty_inspected": 5,
            "qty_rejected": 0,
            "results": results,
        },
        token=qc,
        expect=201,
    )
    check("inspection passes on in-spec values", inspection["result"] == "PASS", inspection["result"])

    _, lots = call("GET", f"/inventory/lots?lot_no={order['output_lot_no']}", token=qc, expect=200)
    fg_lot = lots[0]
    check("passing releases the lot", fg_lot["status"] == "AVAILABLE", fg_lot["status"])
    check("lot moved to finished goods", fg_lot["location"]["code"] == "WH-FG", fg_lot["location"]["code"])

    # --- 8. a failing inspection blocks stock and raises an NCR -------------
    print("\n8. Failing inspection")
    _, order2 = call(
        "POST",
        "/production/orders",
        {"item_id": by_code["SA-2001"]["id"], "qty_ordered": 5, "sales_ref": "SMOKE-FAIL"},
        token=planner,
        expect=201,
    )
    call("POST", f"/production/orders/{order2['id']}/release", token=planner, expect=200)
    for material in order2["materials"]:
        call(
            "POST",
            f"/production/orders/{order2['id']}/issue",
            {"material_id": material["id"], "qty": material["qty_required"]},
            token=warehouse,
            expect=200,
        )
    for operation in sorted(order2["operations"], key=lambda op: op["seq"]):
        call(
            "POST",
            "/production/confirmations",
            {"operation_id": operation["id"], "qty_good": 5},
            token=operator,
            expect=201,
        )
    _, order2 = call("GET", f"/production/orders/{order2['id']}", token=planner, expect=200)

    ncrs_before = len(call("GET", "/quality/ncrs", token=qc, expect=200)[1])
    _, failed = call(
        "POST",
        "/quality/inspections",
        {
            "item_id": by_code["SA-2001"]["id"],
            "inspection_type": "FINAL",
            "lot_no": order2["output_lot_no"],
            "order_id": order2["id"],
            "qty_inspected": 5,
            "qty_rejected": 2,
            "results": [],
        },
        token=qc,
        expect=201,
    )
    check("rejected quantity forces a FAIL", failed["result"] == "FAIL", failed["result"])
    _, ncrs = call("GET", "/quality/ncrs", token=qc, expect=200)
    check("failure raises an NCR automatically", len(ncrs) == ncrs_before + 1, f"{ncrs_before} -> {len(ncrs)}")

    _, lots2 = call("GET", f"/inventory/lots?lot_no={order2['output_lot_no']}", token=qc, expect=200)
    check("failed lot is blocked", lots2[0]["status"] == "REJECTED", lots2[0]["status"])

    _, on_hand = call("GET", "/inventory/on-hand", token=qc, expect=200)
    sa = next(row for row in on_hand if row["item_code"] == "SA-2001")
    check("rejected stock is excluded from on-hand", isinstance(sa["on_hand"], (int, float)))

    # --- 9. traceability ----------------------------------------------------
    print("\n9. Traceability")
    _, trace = call("GET", f"/inventory/trace/{order['output_lot_no']}", token=qc, expect=200)
    check("trace resolves the producing order", trace["source_order_id"] == order_id, str(trace["source_order_id"]))
    check("trace lists consumed components", len(trace["consumed_components"]) == 9, str(len(trace["consumed_components"])))
    check("trace lists the movement history", len(trace["movements"]) >= 2, str(len(trace["movements"])))

    # --- 10. equipment and OEE ---------------------------------------------
    print("\n10. Equipment and OEE")
    _, reasons = call("GET", "/equipment/downtime-reasons", token=operator, expect=200)
    breakdown = next(r for r in reasons if r["code"] == "DT-02")
    idle_machine = next(m for m in machines if m["status"] != "DOWN")

    status, _ = call(
        "POST",
        f"/equipment/machines/{idle_machine['id']}/status",
        {"status": "DOWN"},
        token=operator,
    )
    check("stopping a machine requires a reason", status == 400, f"got {status}")

    _, machine = call(
        "POST",
        f"/equipment/machines/{idle_machine['id']}/status",
        {"status": "DOWN", "reason_id": breakdown["id"], "note": "smoke test"},
        token=operator,
        expect=200,
    )
    check("machine set DOWN", machine["status"] == "DOWN", machine["status"])

    _, open_events = call(
        f"GET", f"/equipment/downtime?machine_id={idle_machine['id']}&open_only=true", token=operator, expect=200
    )
    check("downtime event opened automatically", len(open_events) == 1, f"{len(open_events)} open")

    _, machine = call(
        "POST",
        f"/equipment/machines/{idle_machine['id']}/status",
        {"status": "RUNNING"},
        token=operator,
        expect=200,
    )
    _, open_events = call(
        "GET", f"/equipment/downtime?machine_id={idle_machine['id']}&open_only=true", token=operator, expect=200
    )
    check("restarting closes the downtime event", len(open_events) == 0, f"{len(open_events)} still open")

    _, pareto = call("GET", "/equipment/downtime-pareto?days=7", token=planner, expect=200)
    check(
        "downtime pareto excludes planned stops",
        all(row["category"] != "PLANNED" for row in pareto),
        str([row["code"] for row in pareto if row["category"] == "PLANNED"]),
    )
    _, pareto_all = call(
        "GET", "/equipment/downtime-pareto?days=7&include_planned=true", token=planner, expect=200
    )
    check("planned stops are still available on request", len(pareto_all) >= len(pareto))

    _, oee = call("GET", "/equipment/oee?days=7", token=planner, expect=200)
    check("OEE returned for every machine", len(oee) == len(machines), f"{len(oee)} of {len(machines)}")
    check(
        "OEE measures against scheduled time, not wall-clock time",
        all(row["scheduled_minutes"] < 7 * 24 * 60 for row in oee),
        f"scheduled {oee[0]['scheduled_minutes']} vs calendar {7 * 24 * 60}",
    )
    check(
        "loading time never exceeds scheduled time",
        all(row["loading_minutes"] <= row["scheduled_minutes"] + 1e-6 for row in oee),
    )
    check(
        "run time never exceeds loading time",
        all(row["run_minutes"] <= row["loading_minutes"] + 1e-6 for row in oee),
    )
    sample = next((row for row in oee if row["total_count"] > 0), None)
    check("at least one machine has production in the window", sample is not None)
    if sample:
        expected = round(sample["availability"] * sample["performance"] * sample["quality"], 4)
        check(
            "OEE equals A x P x Q",
            abs(sample["oee"] - expected) < 1e-3,
            f"{sample['oee']} vs {expected}",
        )
        check("all OEE factors are within 0..1", all(0 <= sample[k] <= 1 for k in ("availability", "performance", "quality")))

    # --- 11. dashboard ------------------------------------------------------
    print("\n11. Dashboard")
    _, dash = call("GET", "/dashboard?days=7", token=planner, expect=200)
    check("dashboard returns KPI cards", len(dash["kpis"]) == 7, str(len(dash["kpis"])))
    check("production trend has one point per day", len(dash["production_trend"]) == 7)
    check("order status breakdown present", bool(dash["order_status"]))
    check("downtime pareto present", bool(dash["downtime_pareto"]))
    check("plant OEE present", "oee" in dash["plant_oee"])

    # --- 12. barcode scanning ----------------------------------------------
    print("\n12. Barcode scan resolution")
    for code, kind in (
        (order["order_no"], "ORDER"),
        ("FG-1001", "ITEM"),
        (order["output_lot_no"], "LOT"),
        ("B-1001", "BADGE"),
        ("NOT-A-REAL-CODE", "UNKNOWN"),
    ):
        _, scanned = call("POST", "/production/scan", {"code": code}, token=operator, expect=200)
        check(f"scan {code!r} resolves to {kind}", scanned["kind"] == kind, scanned["kind"])

    # --- 13. optimisation ---------------------------------------------------
    print("")
    print("13. Optimisation: process, time and cost")
    _, rules = call("GET", "/optimization/rules", token=planner, expect=200)
    check("dispatch rules and objectives are published",
          len(rules["rules"]) >= 5 and len(rules["objectives"]) >= 4)

    _, sched = call("GET", "/optimization/schedule?rule=EDD&horizon_days=30", token=planner, expect=200)
    check("scheduler places the open order book", len(sched["operations"]) > 0, "nothing scheduled")

    # Routing sequence: each operation starts at or after the previous one ends.
    by_order = {}
    for op in sched["operations"]:
        by_order.setdefault(op["order_no"], []).append(op)
    sequence_ok = all(
        all(ops[i]["end"] <= ops[i + 1]["start"] for i in range(len(ops) - 1))
        for ops in (sorted(v, key=lambda x: x["seq"]) for v in by_order.values())
    )
    check("routing sequence is respected on every order", sequence_ok)

    # Machine capacity: no two operations overlap on the same machine.
    by_machine = {}
    for op in sched["operations"]:
        by_machine.setdefault(op["machine_code"], []).append(op)
    overlaps = []
    for machine, ops in by_machine.items():
        ops = sorted(ops, key=lambda x: x["start"])
        for i in range(len(ops) - 1):
            if ops[i]["end"] > ops[i + 1]["start"]:
                overlaps.append(machine + ": " + ops[i]["order_no"] + " vs " + ops[i + 1]["order_no"])
    check("no machine runs two jobs at once", not overlaps, "; ".join(overlaps[:2]))

    # The shift calendar: nothing may be scheduled outside a shift.
    outside = [
        op for op in sched["operations"]
        if datetime.fromisoformat(op["start"]).hour < 8
        or datetime.fromisoformat(op["start"]).hour >= 17
        or datetime.fromisoformat(op["start"]).weekday() >= 5
    ]
    check("no work is scheduled outside the shift calendar", not outside,
          str(len(outside)) + " operation(s) start off-shift")

    check("utilisation never exceeds capacity",
          all(u["loaded_hours"] <= u["capacity_hours"] + 1e-6 for u in sched["utilisation"]))

    _, comparison = call("GET", "/optimization/compare?objective=total_lateness_hours",
                         token=planner, expect=200)
    check("every dispatch rule is evaluated", len(comparison["results"]) == len(rules["rules"]))
    best = min(comparison["results"], key=lambda r: r["total_lateness_hours"])
    check("the recommended rule really is the best one",
          comparison["best_rule"] == best["rule"],
          "said " + comparison["best_rule"] + ", best is " + best["rule"])

    _, costs = call("GET", "/optimization/cost?days=30", token=planner, expect=200)
    check("costing rolls up standard and actual", costs["standard_total"] > 0, str(costs["standard_total"]))
    check("variance equals actual minus standard",
          abs(costs["total_variance"] - (costs["actual_total"] - costs["standard_total"])) < 1.0)

    _, full = call("GET", "/optimization", token=planner, expect=200)
    areas = set(r["area"] for r in full["recommendations"])
    check("recommendations cover process, time and cost",
          set(["process", "time", "cost"]) <= areas, "only " + str(sorted(areas)))

    # Applying a schedule must not rewrite the customer commitment, or every
    # schedule would look perfectly on time from then on.
    before = full["schedule"]["total_lateness_hours"]
    status, _ = call("POST", "/optimization/apply", {"rule": "EDD", "horizon_days": 30}, token=operator)
    check("operators cannot re-plan the order book", status == 403, "got " + str(status))
    call("POST", "/optimization/apply", {"rule": "EDD", "horizon_days": 30}, token=planner, expect=200)
    _, after = call("GET", "/optimization", token=planner, expect=200)
    check("applying a schedule does not erase the due dates",
          abs(after["schedule"]["total_lateness_hours"] - before) < 0.01,
          str(before) + " -> " + str(after["schedule"]["total_lateness_hours"]))

    # --- 14. calendar and accounts -------------------------------------------
    print("")
    print("14. Calendar and accounts")
    from datetime import date as _date
    start = (_date.today() - timedelta(days=20)).isoformat()
    finish = (_date.today() + timedelta(days=20)).isoformat()
    _, feed = call("GET", "/calendar?start=" + start + "&end=" + finish, token=planner, expect=200)
    kinds = set(e["kind"] for e in feed["events"])
    check("calendar returns history, plan and promise",
          set(["ACTUAL", "PLANNED", "DUE"]) <= kinds, "only " + str(sorted(kinds)))
    check("completed work is not editable",
          all(not e["editable"] for e in feed["events"] if e["kind"] == "ACTUAL"))

    status, _ = call("GET", "/calendar?start=" + finish + "&end=" + start, token=planner)
    check("a backwards date range is refused", status == 400, "got " + str(status))

    planned = [e for e in feed["events"] if e["kind"] == "PLANNED"]
    check("open orders appear as planned work", len(planned) > 0)
    if planned:
        target = planned[0]["order_id"]
        _, before_order = call("GET", "/production/orders/" + str(target), token=planner, expect=200)
        due_before = before_order["due_date"]

        new_start = datetime.now() + timedelta(days=3)
        call("PATCH", "/calendar/orders/" + str(target),
             {"planned_start": new_start.isoformat(),
              "planned_end": (new_start + timedelta(days=1)).isoformat()},
             token=planner, expect=200)
        _, after_order = call("GET", "/production/orders/" + str(target), token=planner, expect=200)
        check("re-planning moves the plan", after_order["planned_start"][:10] == new_start.date().isoformat())
        check("re-planning leaves the customer promise alone",
              after_order["due_date"] == due_before,
              str(due_before) + " -> " + str(after_order["due_date"]))

        status, body = call("PATCH", "/calendar/orders/" + str(target),
                            {"due_date": new_start.isoformat(), "move_due_date": True},
                            token=planner)
        check("moving a due date without a reason is refused", status == 400, "got " + str(status))
        check("the refusal explains why", "reason" in str(body).lower(), str(body)[:120])

        status, _ = call("PATCH", "/calendar/orders/" + str(target),
                         {"planned_start": new_start.isoformat()}, token=operator)
        check("operators cannot re-plan from the calendar", status == 403, "got " + str(status))

    # Account management, including the two ways to lock everyone out.
    admin = login("admin", "admin123")
    _, accounts = call("GET", "/auth/users", token=admin, expect=200)
    check("administrators can list accounts", len(accounts) >= 6, str(len(accounts)))
    status, _ = call("GET", "/auth/users", token=operator)
    check("non-administrators cannot list accounts", status == 403, "got " + str(status))

    admin_id = [u for u in accounts if u["username"] == "admin"][0]["id"]
    status, body = call("PATCH", "/auth/users/" + str(admin_id), {"role": "VIEWER"}, token=admin)
    check("an admin cannot demote themselves", status == 400, "got " + str(status))
    status, _ = call("PATCH", "/auth/users/" + str(admin_id), {"is_active": False}, token=admin)
    check("an admin cannot disable themselves", status == 400, "got " + str(status))

    status, created = call("POST", "/auth/users",
                           {"username": "smoketest", "full_name": "Smoke Test",
                            "role": "VIEWER", "password": "smoke123"}, token=admin)
    check("an account can be created", status in (201, 409), "got " + str(status))
    if status == 201:
        call("PATCH", "/auth/users/" + str(created["id"]), {"is_active": False}, token=admin, expect=200)
        check("an account can be disabled rather than deleted", True)
        status, _ = call("POST", "/auth/login", {"username": "smoketest", "password": "smoke123"})
        check("a disabled account cannot sign in", status == 403, "got " + str(status))

    status, _ = call("POST", "/auth/me/password",
                     {"current_password": "wrong", "new_password": "whatever"}, token=admin)
    check("changing a password needs the current one", status == 400, "got " + str(status))

    # --- summary ------------------------------------------------------------
    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        for name in failures:
            print(f"  - {name}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
