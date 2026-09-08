"""Order costing and variance analysis.

Two numbers exist for every order: what it *should* have cost from master data,
and what it *did* cost from the events the floor recorded. The gap between them
is the only honest place to look for savings — a standard cost on its own tells
you what you assumed, not what happened.

  Standard material = Σ (required qty × standard cost)
  Standard labour   = Σ (setup + qty × run rate) ÷ 60 × work-centre rate
  Actual material   = Σ (issued qty × the cost of the lot actually picked)
  Actual labour     = Σ (confirmed minutes ÷ 60 × work-centre rate)

Scrap is reported separately rather than buried in the variance, because it is
the one loss with a named cause attached to it.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..enums import MovementType, OrderStatus
from ..models.inventory import StockMovement
from ..models.master import Item, WorkCenter
from ..models.production import Confirmation, OrderMaterial, OrderOperation, ProductionOrder
from ..models.quality import DefectCode


@dataclass
class OrderCost:
    order_id: int
    order_no: str
    item_code: str
    item_name: str
    status: str
    qty_ordered: float
    qty_produced: float
    qty_scrapped: float

    standard_material: float
    standard_labour: float
    standard_total: float

    actual_material: float
    actual_labour: float
    actual_total: float

    material_variance: float
    labour_variance: float
    total_variance: float

    scrap_cost: float
    unit_cost_standard: float
    unit_cost_actual: float

    def as_dict(self) -> dict:
        return asdict(self)


def _money(value: float) -> float:
    return round(float(value or 0.0), 2)


def cost_order(db: Session, order: ProductionOrder) -> OrderCost:
    rates = {
        wc.id: wc.cost_rate_per_hour
        for wc in db.scalars(select(WorkCenter))
    }

    # --- standard ---
    standard_material = sum(
        line.qty_required * (line.component.standard_cost or 0.0) for line in order.materials
    )
    standard_labour = sum(
        (op.setup_minutes + order.qty_ordered * op.run_minutes_per_unit)
        / 60.0
        * rates.get(op.work_center_id, 0.0)
        for op in order.operations
    )

    # --- actual material: what was really picked, at the cost of the real lots ---
    actual_material = float(
        db.scalar(
            select(func.coalesce(func.sum(StockMovement.qty * StockMovement.unit_cost), 0.0)).where(
                StockMovement.ref_type == "PRODUCTION_ORDER",
                StockMovement.ref_id == order.id,
                StockMovement.movement_type == MovementType.ISSUE,
            )
        )
        or 0.0
    )

    # --- actual labour: confirmed minutes at the rate of the centre that ran them ---
    rows = db.execute(
        select(OrderOperation.work_center_id, func.coalesce(func.sum(Confirmation.duration_minutes), 0.0))
        .join(Confirmation, Confirmation.operation_id == OrderOperation.id)
        .where(OrderOperation.order_id == order.id)
        .group_by(OrderOperation.work_center_id)
    ).all()
    actual_labour = sum(minutes / 60.0 * rates.get(wc_id, 0.0) for wc_id, minutes in rows)

    scrap_cost = order.qty_scrapped * (order.item.standard_cost or 0.0)

    standard_total = standard_material + standard_labour
    actual_total = actual_material + actual_labour

    return OrderCost(
        order_id=order.id,
        order_no=order.order_no,
        item_code=order.item.code,
        item_name=order.item.name,
        status=str(order.status),
        qty_ordered=order.qty_ordered,
        qty_produced=order.qty_produced,
        qty_scrapped=order.qty_scrapped,
        standard_material=_money(standard_material),
        standard_labour=_money(standard_labour),
        standard_total=_money(standard_total),
        actual_material=_money(actual_material),
        actual_labour=_money(actual_labour),
        actual_total=_money(actual_total),
        material_variance=_money(actual_material - standard_material),
        labour_variance=_money(actual_labour - standard_labour),
        total_variance=_money(actual_total - standard_total),
        scrap_cost=_money(scrap_cost),
        unit_cost_standard=_money(standard_total / order.qty_ordered) if order.qty_ordered else 0.0,
        unit_cost_actual=_money(actual_total / order.qty_produced) if order.qty_produced else 0.0,
    )


def cost_orders(db: Session, *, days: int = 30, limit: int = 100) -> list[OrderCost]:
    """Cost every order that produced something in the window."""
    since = datetime.now() - timedelta(days=days)
    orders = db.scalars(
        select(ProductionOrder)
        .options(
            selectinload(ProductionOrder.materials).selectinload(OrderMaterial.component),
            selectinload(ProductionOrder.operations),
            selectinload(ProductionOrder.item),
        )
        .where(
            ProductionOrder.status.in_([OrderStatus.COMPLETED, OrderStatus.CLOSED, OrderStatus.IN_PROGRESS]),
            ProductionOrder.created_at >= since,
        )
        .order_by(ProductionOrder.id.desc())
        .limit(limit)
    )
    return [cost_order(db, order) for order in orders]


def scrap_cost_by_defect(db: Session, *, days: int = 30, limit: int = 8) -> list[dict]:
    """What each defect code actually cost, not how often it occurred.

    A frequent cheap defect and a rare expensive one look identical on a count
    Pareto. Ranking by money is what tells you which one to fix first.
    """
    since = datetime.now() - timedelta(days=days)
    rows = db.execute(
        select(
            DefectCode.code,
            DefectCode.name,
            DefectCode.category,
            func.count(Confirmation.id),
            func.coalesce(func.sum(Confirmation.qty_scrap), 0.0),
            func.coalesce(func.sum(Confirmation.qty_scrap * Item.standard_cost), 0.0),
        )
        .join(Confirmation, Confirmation.defect_code_id == DefectCode.id)
        .join(OrderOperation, Confirmation.operation_id == OrderOperation.id)
        .join(ProductionOrder, OrderOperation.order_id == ProductionOrder.id)
        .join(Item, ProductionOrder.item_id == Item.id)
        .where(Confirmation.ended_at >= since, Confirmation.qty_scrap > 0)
        .group_by(DefectCode.id)
        .order_by(func.sum(Confirmation.qty_scrap * Item.standard_cost).desc())
        .limit(limit)
    ).all()

    return [
        {
            "code": code,
            "name": name,
            "category": category,
            "events": int(events),
            "qty": round(float(qty or 0.0), 2),
            "cost": _money(cost),
        }
        for code, name, category, events, qty, cost in rows
    ]


def cost_summary(db: Session, *, days: int = 30) -> dict:
    """Plant-level roll-up over the window."""
    orders = cost_orders(db, days=days, limit=500)
    if not orders:
        return {
            "orders": 0, "standard_total": 0.0, "actual_total": 0.0, "total_variance": 0.0,
            "material_variance": 0.0, "labour_variance": 0.0, "scrap_cost": 0.0,
            "variance_pct": 0.0, "worst_orders": [],
        }

    standard = sum(o.standard_total for o in orders)
    actual = sum(o.actual_total for o in orders)
    worst = sorted(orders, key=lambda o: o.total_variance, reverse=True)[:5]

    return {
        "orders": len(orders),
        "standard_total": _money(standard),
        "actual_total": _money(actual),
        "total_variance": _money(actual - standard),
        "material_variance": _money(sum(o.material_variance for o in orders)),
        "labour_variance": _money(sum(o.labour_variance for o in orders)),
        "scrap_cost": _money(sum(o.scrap_cost for o in orders)),
        "variance_pct": round((actual - standard) / standard * 100, 1) if standard else 0.0,
        "worst_orders": [o.as_dict() for o in worst],
    }
