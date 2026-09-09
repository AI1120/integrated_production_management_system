"""Seed the sample factory: master data, users and ~10 days of shop-floor history.

Run with::

    python -m app.seed          # create if empty
    python -m app.seed --reset  # drop everything and rebuild

The generated history is deterministic (fixed random seed) so screenshots,
demos and tests all show the same numbers.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .enums import (
    CharacteristicType,
    Disposition,
    DowntimeCategory,
    InspectionType,
    ItemType,
    Judgment,
    LocationType,
    LotStatus,
    MachineStatus,
    OrderStatus,
    MovementType,
    NcrStatus,
    Role,
)
from .models import (
    Bom,
    BomLine,
    DefectCode,
    DowntimeEvent,
    DowntimeReason,
    InspectionCharacteristic,
    InspectionPlan,
    Item,
    Location,
    Machine,
    MaintenancePlan,
    NonConformance,
    Partner,
    Routing,
    RoutingOperation,
    Shift,
    User,
    WorkCenter,
)
from .models.inventory import StockLot
from .models.production import ProductionOrder
from .security import hash_password
from .services import inventory_service as inv
from .services import production_service as prod
from .services.numbering import next_number

RNG = random.Random(20260907)
HISTORY_DAYS = 10
SHIFT_START_HOUR = 8


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------
USERS = [
    ("admin", "Alex Admin", None, Role.ADMIN, "admin123"),
    ("planner", "Priya Planner", "B-1000", Role.PLANNER, "planner123"),
    ("operator1", "Omar Operator", "B-1001", Role.OPERATOR, "oper123"),
    ("operator2", "Olga Operator", "B-1002", Role.OPERATOR, "oper123"),
    ("qc1", "Quinn Inspector", "B-2001", Role.QC, "qc123"),
    ("wh1", "Wes Warehouse", "B-3001", Role.WAREHOUSE, "wh123"),
]

LOCATIONS = [
    ("WH-RAW", "Raw material store", LocationType.RAW),
    ("WH-WIP", "Work in progress", LocationType.WIP),
    ("WH-FG", "Finished goods store", LocationType.FINISHED),
    ("QC-HOLD", "Quality hold area", LocationType.QUARANTINE),
    ("WH-SCRAP", "Scrap bin", LocationType.SCRAP),
]

WORK_CENTERS = [
    ("WC-PREP", "Preparation & kitting", 60.0, 28.0),
    ("WC-ASSY", "Main assembly line", 20.0, 42.0),
    ("WC-TEST", "Electrical test bench", 40.0, 38.0),
    ("WC-PACK", "Packing & despatch", 75.0, 24.0),
]

# Ideal cycle time is per machine, not per product, so each figure is the
# volume-weighted best cycle across the mix that machine actually runs. Get this
# wrong and OEE performance is wrong - it is the one number worth re-deriving
# whenever the product mix shifts.
MACHINES = [
    ("PRESS-01", "Housing press 30T", "WC-PREP", 50.0),
    ("ASSY-01", "Assembly station 1", "WC-ASSY", 195.0),
    ("ASSY-02", "Assembly station 2", "WC-ASSY", 195.0),
    ("TEST-01", "Photometric test rig", "WC-TEST", 60.0),
    ("PACK-01", "Carton sealer", "WC-PACK", 48.0),
]

#      machine,     what,                          every,  takes,  last done
MAINTENANCE_PLANS = [
    ("PRESS-01", "Ram and die inspection", 30, 180.0, 24),
    ("PRESS-01", "Hydraulic oil change", 90, 240.0, 80),
    ("ASSY-01", "Torque driver calibration", 60, 90.0, 52),
    ("TEST-01", "Photometric reference calibration", 30, 120.0, 33),  # already overdue
    ("PACK-01", "Sealer belt and blade service", 45, 60.0, 20),
]

#      code,      name,                       type,               uom,  cost, safety, lead
ITEMS = [
    ("FG-1001", "LED Floodlight 100W", ItemType.FINISHED_GOOD, "EA", 148.0, 120, 0),
    ("FG-1002", "LED Floodlight 200W", ItemType.FINISHED_GOOD, "EA", 236.0, 60, 0),
    ("SA-2001", "LED module assembly 100W", ItemType.SUB_ASSEMBLY, "EA", 52.0, 220, 0),
    ("RM-3001", "Aluminium housing, cast", ItemType.RAW_MATERIAL, "EA", 34.5, 800, 21),
    ("RM-3002", "LED chip 50W COB", ItemType.RAW_MATERIAL, "EA", 18.9, 2600, 35),
    ("RM-3003", "LED driver 100W IP67", ItemType.RAW_MATERIAL, "EA", 27.4, 900, 28),
    ("RM-3004", "Tempered glass lens", ItemType.RAW_MATERIAL, "EA", 9.8, 900, 14),
    ("RM-3005", "Silicone gasket ring", ItemType.RAW_MATERIAL, "EA", 1.6, 1400, 10),
    ("RM-3006", "Mounting bracket, steel", ItemType.RAW_MATERIAL, "EA", 6.2, 900, 14),
    ("RM-3007", "Wiring harness 300mm", ItemType.RAW_MATERIAL, "EA", 4.4, 1300, 12),
    ("RM-3008", "Screw M4x10 stainless", ItemType.RAW_MATERIAL, "EA", 0.06, 14000, 7),
    ("RM-3009", "Thermal paste", ItemType.RAW_MATERIAL, "KG", 62.0, 20, 20),
    ("CN-4001", "Shipping carton", ItemType.CONSUMABLE, "EA", 1.35, 1100, 7),
    ("CN-4002", "Label set", ItemType.CONSUMABLE, "EA", 0.28, 1500, 5),
]

BOMS = {
    "FG-1001": [
        # component, qty_per, scrap_pct, consumed at operation
        ("SA-2001", 1, 1.0, 20),
        ("RM-3001", 1, 2.0, 20),
        ("RM-3003", 1, 1.0, 20),
        ("RM-3004", 1, 3.0, 20),
        ("RM-3005", 1, 2.0, 20),
        ("RM-3006", 1, 1.0, 20),
        ("RM-3008", 8, 5.0, 20),
        ("CN-4001", 1, 1.0, 40),
        ("CN-4002", 1, 2.0, 40),
    ],
    "FG-1002": [
        ("SA-2001", 2, 1.0, 20),
        ("RM-3001", 1, 2.0, 20),
        ("RM-3003", 2, 1.0, 20),
        ("RM-3004", 1, 3.0, 20),
        ("RM-3005", 1, 2.0, 20),
        ("RM-3006", 1, 1.0, 20),
        ("RM-3008", 10, 5.0, 20),
        ("CN-4001", 1, 1.0, 40),
        ("CN-4002", 1, 2.0, 40),
    ],
    "SA-2001": [
        ("RM-3002", 2, 2.0, 10),
        ("RM-3007", 1, 1.0, 10),
        ("RM-3009", 0.015, 5.0, 10),
    ],
}

ROUTINGS = {
    "FG-1001": [
        (10, "Kitting & housing prep", "WC-PREP", 10, 0.5, False, "Pick the kit against the order and de-burr the housing."),
        (20, "Main assembly", "WC-ASSY", 15, 3.0, False, "Fit module, driver, gasket and lens. Torque screws to 1.2 Nm."),
        (30, "Function & photometric test", "WC-TEST", 5, 1.5, True, "Run the 60 s burn-in, then record flux, power and insulation."),
        (40, "Pack & label", "WC-PACK", 5, 0.8, False, "Carton, label, palletise."),
    ],
    "FG-1002": [
        (10, "Kitting & housing prep", "WC-PREP", 12, 0.6, False, None),
        (20, "Main assembly", "WC-ASSY", 20, 4.5, False, "Twin-module build. Torque screws to 1.2 Nm."),
        (30, "Function & photometric test", "WC-TEST", 5, 2.0, True, None),
        (40, "Pack & label", "WC-PACK", 5, 1.0, False, None),
    ],
    "SA-2001": [
        (10, "Module build", "WC-PREP", 20, 1.2, False, "Apply thermal paste, seat both COB chips, solder the harness."),
        (20, "Module test", "WC-TEST", 5, 0.6, True, "Light-up test at rated current."),
    ],
}

DEFECT_CODES = [
    ("DEF-01", "Cold solder joint", "PROCESS"),
    ("DEF-02", "Cosmetic scratch", "COSMETIC"),
    ("DEF-03", "LED not lighting", "COMPONENT"),
    ("DEF-04", "Incorrect screw torque", "PROCESS"),
    ("DEF-05", "Gasket misaligned", "ASSEMBLY"),
    ("DEF-06", "Driver failure on test", "COMPONENT"),
    ("DEF-07", "Low luminous flux", "PERFORMANCE"),
]

DOWNTIME_REASONS = [
    ("DT-01", "Material shortage", DowntimeCategory.UNPLANNED, True),
    ("DT-02", "Machine breakdown", DowntimeCategory.UNPLANNED, True),
    ("DT-03", "Changeover / setup", DowntimeCategory.UNPLANNED, True),
    ("DT-04", "Quality hold", DowntimeCategory.UNPLANNED, True),
    ("DT-05", "No operator", DowntimeCategory.UNPLANNED, True),
    ("DT-06", "Planned maintenance", DowntimeCategory.PLANNED, False),
    ("DT-07", "Break / lunch", DowntimeCategory.PLANNED, False),
    # Excluded from OEE: an idle machine with no demand has lost nothing.
    ("DT-08", "No work scheduled", DowntimeCategory.PLANNED, False),
]

PARTNERS = [
    ("CUST-01", "Northgate Logistics", True, False, "orders@northgate.example"),
    ("CUST-02", "Harbour Works Ltd", True, False, "purchasing@harbourworks.example"),
    ("SUPP-01", "Delta Castings", False, True, "sales@deltacastings.example"),
    ("SUPP-02", "Lumen Components", False, True, "sales@lumencomp.example"),
]


def _build_master(db: Session) -> dict:
    ref: dict = {"items": {}, "wc": {}, "loc": {}, "machines": {}, "users": {}, "defects": {}, "reasons": {}}

    for username, full_name, badge, role, password in USERS:
        user = User(
            username=username,
            full_name=full_name,
            badge_no=badge,
            role=role,
            password_hash=hash_password(password),
        )
        db.add(user)
        ref["users"][username] = user

    for code, name, loc_type in LOCATIONS:
        location = Location(code=code, name=name, location_type=loc_type)
        db.add(location)
        ref["loc"][code] = location

    for code, name, capacity, rate in WORK_CENTERS:
        wc = WorkCenter(code=code, name=name, capacity_per_hour=capacity, cost_rate_per_hour=rate)
        db.add(wc)
        ref["wc"][code] = wc

    for code, name, item_type, uom, cost, safety, lead in ITEMS:
        item = Item(
            code=code,
            name=name,
            item_type=item_type,
            uom=uom,
            standard_cost=cost,
            safety_stock=safety,
            lead_time_days=lead,
            is_lot_controlled=True,
        )
        db.add(item)
        ref["items"][code] = item

    for code, name, is_customer, is_supplier, contact in PARTNERS:
        db.add(Partner(code=code, name=name, is_customer=is_customer, is_supplier=is_supplier, contact=contact))

    for code, name, category in DEFECT_CODES:
        defect = DefectCode(code=code, name=name, category=category)
        db.add(defect)
        ref["defects"][code] = defect

    for code, name, category, affects in DOWNTIME_REASONS:
        reason = DowntimeReason(code=code, name=name, category=category, affects_availability=affects)
        db.add(reason)
        ref["reasons"][code] = reason

    db.flush()

    for code, name, wc_code, cycle in MACHINES:
        machine = Machine(
            code=code,
            name=name,
            work_center_id=ref["wc"][wc_code].id,
            ideal_cycle_seconds=cycle,
            status=MachineStatus.IDLE,
            status_since=datetime.now(),
        )
        db.add(machine)
        ref["machines"][code] = machine

    db.flush()

    # Preventive maintenance, staged so the sample plant shows the full range:
    # one service already overdue, one due within the week, the rest further out.
    for machine_code, name, interval, minutes, days_since in MAINTENANCE_PLANS:
        db.add(
            MaintenancePlan(
                machine_id=ref["machines"][machine_code].id,
                name=name,
                interval_days=interval,
                duration_minutes=minutes,
                last_done_at=datetime.now() - timedelta(days=days_since),
            )
        )

    for parent_code, lines in BOMS.items():
        bom = Bom(item_id=ref["items"][parent_code].id, version="A", description=f"{parent_code} production BOM")
        db.add(bom)
        db.flush()
        for index, (component, qty_per, scrap, op_seq) in enumerate(lines, start=1):
            db.add(
                BomLine(
                    bom_id=bom.id,
                    line_no=index * 10,
                    component_id=ref["items"][component].id,
                    qty_per=qty_per,
                    scrap_pct=scrap,
                    operation_seq=op_seq,
                )
            )

    for parent_code, steps in ROUTINGS.items():
        routing = Routing(item_id=ref["items"][parent_code].id, version="A", description=f"{parent_code} process plan")
        db.add(routing)
        db.flush()
        for seq, name, wc_code, setup, run, inspect, instructions in steps:
            db.add(
                RoutingOperation(
                    routing_id=routing.id,
                    seq=seq,
                    name=name,
                    work_center_id=ref["wc"][wc_code].id,
                    setup_minutes=setup,
                    run_minutes_per_unit=run,
                    requires_inspection=inspect,
                    instructions=instructions,
                )
            )

    # Final inspection plan for the flagship product.
    plan = InspectionPlan(
        code="IP-FG1001",
        name="FG-1001 final inspection",
        item_id=ref["items"]["FG-1001"].id,
        inspection_type=InspectionType.FINAL,
        operation_seq=30,
        sample_size=5,
    )
    db.add(plan)
    db.flush()
    for seq, name, char_type, uom, target, lsl, usl, method in [
        (10, "Luminous flux", CharacteristicType.NUMERIC, "lm", 10000, 9500, 10500, "Integrating sphere"),
        (20, "Power draw", CharacteristicType.NUMERIC, "W", 100, 95, 105, "Power analyser"),
        (30, "Insulation resistance", CharacteristicType.NUMERIC, "MOhm", 50, 10, None, "500 V megger"),
        (40, "Visual appearance", CharacteristicType.ATTRIBUTE, None, None, None, None, "Visual, 500 lux"),
    ]:
        db.add(
            InspectionCharacteristic(
                plan_id=plan.id,
                seq=seq,
                name=name,
                char_type=char_type,
                uom=uom,
                target=target,
                lower_limit=lsl,
                upper_limit=usl,
                method=method,
            )
        )

    db.add(
        Shift(
            code="DAY",
            name="Day shift 08:00-17:00, Mon-Fri",
            start_minute=SHIFT_START,
            end_minute=SHIFT_END,
            weekdays="1111100",
        )
    )

    db.flush()
    ref["plan"] = plan
    return ref


# ---------------------------------------------------------------------------
# Opening stock
# ---------------------------------------------------------------------------
OPENING_STOCK = {
    "RM-3001": 3600, "RM-3002": 12000, "RM-3003": 4200, "RM-3004": 3800,
    "RM-3005": 6400, "RM-3006": 3600, "RM-3007": 5600, "RM-3008": 56000,
    "RM-3009": 90, "CN-4001": 4800, "CN-4002": 6400, "SA-2001": 400,
}


def _receive_opening_stock(db: Session, ref: dict) -> None:
    raw = ref["loc"]["WH-RAW"]
    warehouse_user = ref["users"]["wh1"]
    received_at = datetime.now() - timedelta(days=HISTORY_DAYS + 4)

    for code, qty in OPENING_STOCK.items():
        item = ref["items"][code]
        # Two lots per part so FIFO picking and lot traceability have something to show.
        for index, share in enumerate((0.6, 0.4), start=1):
            lot_qty = round(qty * share, 3)
            lot_no = f"L{received_at.strftime('%y%m')}-{code.split('-')[1]}-{index}"
            inv.post_movement(
                db,
                movement_type=MovementType.RECEIPT,
                item_id=item.id,
                qty=lot_qty,
                lot_no=lot_no,
                to_location_id=raw.id,
                unit_cost=round(item.standard_cost * RNG.uniform(0.95, 1.05), 4),
                ref_type="GOODS_RECEIPT",
                ref_no=lot_no,
                user_id=warehouse_user.id,
                occurred_at=received_at + timedelta(hours=index),
                note="Opening stock",
            )
    db.flush()


# ---------------------------------------------------------------------------
# Shop-floor history
# ---------------------------------------------------------------------------
MACHINE_FOR_WC = {
    "WC-PREP": ["PRESS-01"],
    "WC-ASSY": ["ASSY-01", "ASSY-02"],
    "WC-TEST": ["TEST-01"],
    "WC-PACK": ["PACK-01"],
}


def _run_order(db: Session, ref: dict, *, item_code: str, qty: int, day: datetime, complete: bool) -> None:
    """Create, release, feed and (optionally) run one order to completion."""
    planner = ref["users"]["planner"]
    operators = [ref["users"]["operator1"], ref["users"]["operator2"]]
    raw = ref["loc"]["WH-RAW"]

    order = prod.create_order(
        db,
        item_id=ref["items"][item_code].id,
        qty=qty,
        planned_start=day.replace(hour=SHIFT_START_HOUR, minute=0),
        planned_end=day.replace(hour=17, minute=0),
        priority=RNG.choice([3, 5, 5, 7]),
        customer_id=None,
        sales_ref=f"SO-{RNG.randint(41000, 41999)}",
    )
    prod.release_order(db, order)

    for material in order.materials:
        try:
            prod.issue_material(
                db,
                order=order,
                material=material,
                qty=material.qty_required,
                from_location_id=raw.id,
                user_id=ref["users"]["wh1"].id,
            )
        except (inv.StockError, prod.ProductionError):
            # A genuine shortage is realistic history - leave that line short and
            # carry on. Nothing is rolled back: the partial kit really was issued.
            continue

    if not complete:
        return

    clock = day.replace(hour=SHIFT_START_HOUR, minute=RNG.randint(0, 25))
    for operation in sorted(order.operations, key=lambda op: op.seq):
        machine_code = RNG.choice(MACHINE_FOR_WC[operation.work_center.code])
        machine = ref["machines"][machine_code]

        # Scrap a few units at assembly and test, none at kitting or packing.
        scrap_rate = {10: 0.0, 20: 0.012, 30: 0.018, 40: 0.0}.get(operation.seq, 0.0)
        qty_scrap = min(int(qty * scrap_rate * RNG.uniform(0, 2.2)), max(qty - 1, 0))
        qty_good = qty - qty_scrap

        minutes = operation.setup_minutes + qty * operation.run_minutes_per_unit * RNG.uniform(1.05, 1.35)
        started_at = clock
        ended_at = started_at + timedelta(minutes=minutes)

        prod.confirm_operation(
            db,
            operation=operation,
            qty_good=qty_good,
            qty_scrap=qty_scrap,
            started_at=started_at,
            ended_at=ended_at,
            operator_id=RNG.choice(operators).id,
            defect_code_id=ref["defects"][RNG.choice(["DEF-01", "DEF-03", "DEF-05", "DEF-06"])].id
            if qty_scrap
            else None,
            machine_id=machine.id,
        )
        clock = ended_at + timedelta(minutes=RNG.randint(5, 25))

        # Re-read the order quantity that actually made it through this step.
        qty = int(qty_good)
        if qty <= 0:
            break

    _inspect_order(db, ref, order)


def _inspect_order(db: Session, ref: dict, order) -> None:
    """Final inspection of the produced lot - mostly passes, occasionally fails."""
    from .models.quality import Inspection, InspectionResult

    if order.qty_produced <= 0 or not order.output_lot_no:
        return

    plan = ref["plan"] if order.item.code == "FG-1001" else None
    qc = ref["users"]["qc1"]
    fails = RNG.random() < 0.18
    sample = 5

    inspection = Inspection(
        inspection_no=next_number(db, "INS"),
        plan_id=plan.id if plan else None,
        inspection_type=InspectionType.FINAL,
        item_id=order.item_id,
        lot_no=order.output_lot_no,
        order_id=order.id,
        qty_inspected=sample,
        qty_rejected=1 if fails else 0,
        qty_accepted=sample - (1 if fails else 0),
        result=Judgment.FAIL if fails else Judgment.PASS,
        inspector_id=qc.id,
        inspected_at=(order.actual_end or datetime.now()) + timedelta(minutes=25),
        note="Routine final inspection",
    )
    db.add(inspection)
    db.flush()

    if plan:
        for characteristic in plan.characteristics:
            for sample_no in range(1, sample + 1):
                if characteristic.char_type is CharacteristicType.ATTRIBUTE:
                    ok = not (fails and sample_no == 1)
                    db.add(
                        InspectionResult(
                            inspection_id=inspection.id,
                            characteristic_id=characteristic.id,
                            characteristic_name=characteristic.name,
                            sample_no=sample_no,
                            value_text="OK" if ok else "Scratch on lens bezel",
                            judgment=Judgment.PASS if ok else Judgment.FAIL,
                        )
                    )
                    continue

                target = characteristic.target or 1.0
                value = round(target * RNG.uniform(0.985, 1.015), 2)
                if fails and sample_no == 1 and characteristic.lower_limit is not None:
                    value = round(characteristic.lower_limit * 0.96, 2)
                judged = Judgment.PASS
                if characteristic.lower_limit is not None and value < characteristic.lower_limit:
                    judged = Judgment.FAIL
                if characteristic.upper_limit is not None and value > characteristic.upper_limit:
                    judged = Judgment.FAIL
                db.add(
                    InspectionResult(
                        inspection_id=inspection.id,
                        characteristic_id=characteristic.id,
                        characteristic_name=characteristic.name,
                        sample_no=sample_no,
                        value_numeric=value,
                        judgment=judged,
                    )
                )

    lots = list(
        db.scalars(
            select(StockLot).where(StockLot.item_id == order.item_id, StockLot.lot_no == order.output_lot_no)
        )
    )
    if fails:
        for lot in lots:
            lot.status = LotStatus.REJECTED
        db.add(
            NonConformance(
                ncr_no=next_number(db, "NCR"),
                item_id=order.item_id,
                lot_no=order.output_lot_no,
                order_id=order.id,
                inspection_id=inspection.id,
                defect_code_id=ref["defects"][RNG.choice(["DEF-02", "DEF-06", "DEF-07"])].id,
                qty=1,
                description=f"Raised automatically from inspection {inspection.inspection_no}",
                disposition=RNG.choice([Disposition.PENDING, Disposition.REWORK]),
                status=NcrStatus.OPEN,
                raised_by_id=qc.id,
            )
        )
    else:
        finished = inv.stock_location_for(db, order.item)
        for lot in lots:
            if lot.qty <= 0:
                continue
            source = lot.location_id
            lot.status = LotStatus.AVAILABLE
            if source != finished.id:
                inv.post_movement(
                    db,
                    movement_type=MovementType.TRANSFER,
                    item_id=lot.item_id,
                    qty=lot.qty,
                    lot_no=lot.lot_no,
                    from_location_id=source,
                    to_location_id=finished.id,
                    ref_type="INSPECTION",
                    ref_id=inspection.id,
                    ref_no=inspection.inspection_no,
                    user_id=qc.id,
                    occurred_at=inspection.inspected_at,
                    note="Released from quarantine after passing inspection",
                )
    db.flush()


SHIFT_START = 8 * 60      # 08:00
SHIFT_END = 17 * 60       # 17:00
SHIFT_MINUTES = SHIFT_END - SHIFT_START
UNPLANNED_CODES = ["DT-01", "DT-02", "DT-03", "DT-04", "DT-05"]
UNPLANNED_WEIGHTS = [3, 2, 5, 1, 2]


def _busy_minutes_by_machine(db: Session, day_start: datetime, day_end: datetime) -> dict[int, float]:
    """How long each machine was actually producing on a given day."""
    from .models.production import Confirmation, OrderOperation

    rows = db.execute(
        select(OrderOperation.machine_id, func.sum(Confirmation.duration_minutes))
        .join(Confirmation, Confirmation.operation_id == OrderOperation.id)
        .where(
            OrderOperation.machine_id.is_not(None),
            Confirmation.ended_at >= day_start,
            Confirmation.ended_at < day_end,
        )
        .group_by(OrderOperation.machine_id)
    ).all()
    return {machine_id: float(minutes or 0.0) for machine_id, minutes in rows}


def _generate_downtime(db: Session, ref: dict) -> None:
    """Account for every scheduled minute on every machine.

    Run *after* the production history so the stops are consistent with what the
    machines actually did. Each shift is split into: time producing, unplanned
    stops (which cost availability), a lunch break, and whatever is left over as
    "no work scheduled" - which is excluded from OEE, because an idle machine
    with no demand has not lost anything.
    """
    for day_offset in range(HISTORY_DAYS, 0, -1):
        day = (datetime.now() - timedelta(days=day_offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        if day.weekday() >= 5:
            continue

        shift_start = day + timedelta(minutes=SHIFT_START)
        busy_by_machine = _busy_minutes_by_machine(db, day, day + timedelta(days=1))

        for machine in ref["machines"].values():
            busy = min(busy_by_machine.get(machine.id, 0.0), SHIFT_MINUTES)
            cursor = shift_start + timedelta(minutes=busy)
            remaining = SHIFT_MINUTES - busy

            if busy > 0:
                # Stops scale with how hard the machine was worked.
                unplanned_budget = min(busy * RNG.uniform(0.08, 0.20), remaining)
                for _ in range(RNG.randint(1, 3)):
                    if unplanned_budget < 5:
                        break
                    minutes = min(round(RNG.uniform(8, 45)), unplanned_budget)
                    reason = ref["reasons"][RNG.choices(UNPLANNED_CODES, weights=UNPLANNED_WEIGHTS, k=1)[0]]
                    db.add(
                        DowntimeEvent(
                            machine_id=machine.id,
                            reason_id=reason.id,
                            started_at=cursor,
                            ended_at=cursor + timedelta(minutes=minutes),
                            duration_minutes=float(minutes),
                            reported_by_id=ref["users"]["operator1"].id,
                        )
                    )
                    cursor += timedelta(minutes=minutes)
                    unplanned_budget -= minutes
                    remaining -= minutes

                lunch = min(30.0, remaining)
                if lunch > 0:
                    db.add(
                        DowntimeEvent(
                            machine_id=machine.id,
                            reason_id=ref["reasons"]["DT-07"].id,
                            started_at=cursor,
                            ended_at=cursor + timedelta(minutes=lunch),
                            duration_minutes=lunch,
                            reported_by_id=ref["users"]["operator1"].id,
                        )
                    )
                    cursor += timedelta(minutes=lunch)
                    remaining -= lunch

            if remaining > 1:
                db.add(
                    DowntimeEvent(
                        machine_id=machine.id,
                        reason_id=ref["reasons"]["DT-08"].id,
                        started_at=cursor,
                        ended_at=cursor + timedelta(minutes=remaining),
                        duration_minutes=float(remaining),
                        note="No order queued for this machine",
                    )
                )

    # Leave one machine down right now so the live board has something to show.
    press = ref["machines"]["PRESS-01"]
    started = datetime.now() - timedelta(minutes=37)
    db.add(
        DowntimeEvent(
            machine_id=press.id,
            reason_id=ref["reasons"]["DT-02"].id,
            started_at=started,
            reported_by_id=ref["users"]["operator1"].id,
            note="Hydraulic pressure dropping - maintenance called",
        )
    )
    press.status = MachineStatus.DOWN
    press.status_since = started
    for code in ("ASSY-01", "TEST-01"):
        ref["machines"][code].status = MachineStatus.RUNNING
        ref["machines"][code].status_since = datetime.now() - timedelta(minutes=RNG.randint(15, 90))
    db.flush()


def _generate_history(db: Session, ref: dict) -> None:
    for day_offset in range(HISTORY_DAYS, 0, -1):
        day = (datetime.now() - timedelta(days=day_offset)).replace(
            hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0
        )
        if day.weekday() >= 5:  # weekend shutdown
            continue
        _run_order(db, ref, item_code="SA-2001", qty=RNG.choice([150, 180, 200]), day=day, complete=True)
        _run_order(db, ref, item_code="FG-1001", qty=RNG.choice([80, 100, 120]), day=day, complete=True)
        if day_offset % 3 == 0:
            _run_order(db, ref, item_code="FG-1002", qty=RNG.choice([30, 40]), day=day, complete=True)
        db.commit()

    # Live work in flight today, plus a couple of orders still waiting to start.
    today = datetime.now().replace(hour=SHIFT_START_HOUR, minute=0, second=0, microsecond=0)
    _run_order(db, ref, item_code="FG-1001", qty=110, day=today, complete=False)
    _run_order(db, ref, item_code="SA-2001", qty=180, day=today, complete=False)

    # A forward order book. Without a real backlog there is nothing for the
    # scheduler to sequence and no work centre can become a bottleneck, so the
    # optimisation module would have nothing to say.
    BACKLOG = [
        # (item, qty, due in N working days, priority)
        ("FG-1001", 120, 1, 3),
        ("SA-2001", 200, 1, 3),
        ("FG-1002",  40, 2, 5),
        ("FG-1001",  90, 2, 5),
        ("SA-2001", 180, 3, 5),
        ("FG-1001", 110, 3, 4),
        ("FG-1002",  55, 4, 5),
        ("FG-1001",  75, 5, 7),
        ("SA-2001", 160, 5, 5),
        ("FG-1002",  35, 6, 7),
        ("FG-1001", 100, 7, 5),
        ("SA-2001", 220, 8, 7),
    ]

    def working_day(offset: int) -> datetime:
        """Skip weekends - a due date on a Sunday is not a due date."""
        day = today
        moved = 0
        while moved < offset:
            day += timedelta(days=1)
            if day.weekday() < 5:
                moved += 1
        return day

    for item_code, qty, due_in, priority in BACKLOG:
        due = working_day(due_in)
        prod.create_order(
            db,
            item_id=ref["items"][item_code].id,
            qty=qty,
            planned_start=working_day(max(due_in - 1, 0)).replace(hour=8),
            planned_end=due.replace(hour=17),
            due_date=due.replace(hour=17),
            priority=priority,
            sales_ref=f"SO-{RNG.randint(42000, 42999)}",
        )

    # Release the near-term half so the floor has queued work, not just plans.
    releasable = list(
        db.scalars(
            select(ProductionOrder)
            .where(ProductionOrder.status == OrderStatus.DRAFT)
            .order_by(ProductionOrder.planned_end)
        )
    )[:6]
    for order in releasable:
        prod.release_order(db, order)

    db.flush()


# ---------------------------------------------------------------------------
def seed(reset: bool = False) -> None:
    if reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        if db.scalar(select(User).limit(1)) is not None:
            print("Database already contains data - use --reset to rebuild it.")
            return

        print("Seeding master data...")
        ref = _build_master(db)
        print("Receiving opening stock...")
        _receive_opening_stock(db, ref)
        print(f"Generating {HISTORY_DAYS} days of production history...")
        _generate_history(db, ref)
        print("Accounting for machine time (downtime and idle)...")
        _generate_downtime(db, ref)
        db.commit()

    _report()


def _report() -> None:
    from .models.production import Confirmation, ProductionOrder
    from .models.quality import Inspection

    with SessionLocal() as db:
        counts = {
            "users": len(list(db.scalars(select(User)))),
            "items": len(list(db.scalars(select(Item)))),
            "work orders": len(list(db.scalars(select(ProductionOrder)))),
            "confirmations": len(list(db.scalars(select(Confirmation)))),
            "stock lots": len(list(db.scalars(select(StockLot)))),
            "inspections": len(list(db.scalars(select(Inspection)))),
            "NCRs": len(list(db.scalars(select(NonConformance)))),
            "downtime events": len(list(db.scalars(select(DowntimeEvent)))),
        }
    print("\nSeed complete:")
    for label, value in counts.items():
        print(f"  {value:>6}  {label}")
    print("\nSign in with:")
    for username, full_name, _badge, role, password in USERS:
        print(f"  {username:<10} / {password:<12} {role:<10} {full_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the IPMS sample factory")
    parser.add_argument("--reset", action="store_true", help="drop all tables before seeding")
    args = parser.parse_args()
    try:
        seed(reset=args.reset)
    except Exception as exc:  # pragma: no cover - CLI convenience
        print(f"Seeding failed: {exc}", file=sys.stderr)
        raise
