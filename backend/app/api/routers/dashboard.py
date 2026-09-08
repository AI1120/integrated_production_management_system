"""Plant dashboard - one call that answers 'how is the factory running right now?'."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...enums import LotStatus, NcrStatus, OrderStatus
from ...models.equipment import Machine
from ...models.inventory import StockLot
from ...models.master import Item
from ...models.production import Confirmation, OrderOperation, ProductionOrder
from ...models.quality import DefectCode, NonConformance
from ...models.user import User
from ...schemas.dashboard import DashboardRead, KpiCard, StatusSlice, TrendPoint
from ...services import oee_service
from ..deps import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardRead)
def dashboard(days: int = 7, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> DashboardRead:
    now = datetime.now()
    window_start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Confirmations at the final routing step of each order - the only ones that
    # represent finished units. Built once; a correlated subquery inside the day
    # loop would self-reference OrderOperation and lose its FROM clause.
    last_seq = (
        select(OrderOperation.order_id.label("order_id"), func.max(OrderOperation.seq).label("max_seq"))
        .group_by(OrderOperation.order_id)
        .subquery()
    )
    final_operation_ids = (
        select(OrderOperation.id)
        .join(
            last_seq,
            (OrderOperation.order_id == last_seq.c.order_id) & (OrderOperation.seq == last_seq.c.max_seq),
        )
        .scalar_subquery()
    )

    # --- daily production trend ---
    trend: list[TrendPoint] = []
    period_good = period_scrap = 0.0
    for offset in range(days):
        day_start = window_start + timedelta(days=offset)
        day_end = day_start + timedelta(days=1)
        good, scrap = db.execute(
            select(
                func.coalesce(func.sum(Confirmation.qty_good), 0.0),
                func.coalesce(func.sum(Confirmation.qty_scrap), 0.0),
            )
            .where(
                Confirmation.ended_at >= day_start,
                Confirmation.ended_at < day_end,
                Confirmation.operation_id.in_(final_operation_ids),
            )
        ).one()
        good, scrap = float(good or 0.0), float(scrap or 0.0)
        period_good += good
        period_scrap += scrap
        trend.append(TrendPoint(label=day_start.strftime("%d %b"), good=good, scrap=scrap))

    # --- order + machine state ---
    order_status = [
        StatusSlice(label=str(status), value=count)
        for status, count in db.execute(
            select(ProductionOrder.status, func.count(ProductionOrder.id)).group_by(ProductionOrder.status)
        ).all()
    ]
    machine_status = [
        StatusSlice(label=str(status), value=count)
        for status, count in db.execute(
            select(Machine.status, func.count(Machine.id))
            .where(Machine.is_active.is_(True))
            .group_by(Machine.status)
        ).all()
    ]

    open_orders = db.scalar(
        select(func.count(ProductionOrder.id)).where(
            ProductionOrder.status.in_([OrderStatus.RELEASED, OrderStatus.IN_PROGRESS])
        )
    ) or 0
    late_orders = db.scalar(
        select(func.count(ProductionOrder.id)).where(
            ProductionOrder.status.in_([OrderStatus.RELEASED, OrderStatus.IN_PROGRESS]),
            ProductionOrder.planned_end < now,
        )
    ) or 0
    open_ncrs = db.scalar(
        select(func.count(NonConformance.id)).where(NonConformance.status != NcrStatus.CLOSED)
    ) or 0

    today_good, today_scrap = db.execute(
        select(
            func.coalesce(func.sum(Confirmation.qty_good), 0.0),
            func.coalesce(func.sum(Confirmation.qty_scrap), 0.0),
        ).where(Confirmation.ended_at >= today_start)
    ).one()

    # --- OEE across the whole plant for the window ---
    results = oee_service.plant_oee(db, window_start, now)
    def _avg(field: str) -> float:
        values = [getattr(r, field) for r in results if r.loading_minutes > 0]
        return round(sum(values) / len(values), 4) if values else 0.0

    plant = {
        "availability": _avg("availability"),
        "performance": _avg("performance"),
        "quality": _avg("quality"),
        "oee": _avg("oee"),
        "machines": [r.as_dict() for r in results],
    }

    period_total = period_good + period_scrap
    yield_pct = round(period_good / period_total * 100, 1) if period_total else 0.0

    kpis = [
        KpiCard(key="today_good", label="Good units today", value=float(today_good or 0.0), unit="pcs"),
        KpiCard(key="today_scrap", label="Scrap today", value=float(today_scrap or 0.0), unit="pcs"),
        KpiCard(key="yield", label=f"Yield ({days}d)", value=yield_pct, unit="%",
                hint=f"{period_good:g} good of {period_total:g} produced"),
        KpiCard(key="oee", label=f"Plant OEE ({days}d)", value=round(plant["oee"] * 100, 1), unit="%",
                hint=f"A {plant['availability']*100:.0f}% x P {plant['performance']*100:.0f}% x Q {plant['quality']*100:.0f}%"),
        KpiCard(key="open_orders", label="Open work orders", value=float(open_orders), unit=""),
        KpiCard(key="late_orders", label="Past due", value=float(late_orders), unit="",
                hint="Released or running, planned end in the past"),
        KpiCard(key="open_ncrs", label="Open NCRs", value=float(open_ncrs), unit=""),
    ]

    # --- quality + stock watchlists ---
    top_defects = [
        {"code": code, "name": name, "count": count, "qty": float(qty or 0.0)}
        for code, name, count, qty in db.execute(
            select(DefectCode.code, DefectCode.name, func.count(NonConformance.id), func.sum(NonConformance.qty))
            .join(NonConformance, NonConformance.defect_code_id == DefectCode.id)
            .where(NonConformance.created_at >= window_start)
            .group_by(DefectCode.id)
            .order_by(func.sum(NonConformance.qty).desc())
            .limit(5)
        ).all()
    ]

    low_stock = []
    for item, qty in db.execute(
        select(Item, func.coalesce(func.sum(StockLot.qty), 0.0))
        .outerjoin(
            StockLot,
            (StockLot.item_id == Item.id) & (StockLot.status == LotStatus.AVAILABLE) & (StockLot.qty > 0),
        )
        .where(Item.is_active.is_(True), Item.safety_stock > 0)
        .group_by(Item.id)
    ).all():
        qty = float(qty or 0.0)
        if qty < item.safety_stock:
            low_stock.append(
                {
                    "item_id": item.id,
                    "code": item.code,
                    "name": item.name,
                    "uom": item.uom,
                    "on_hand": qty,
                    "safety_stock": item.safety_stock,
                    "shortfall": round(item.safety_stock - qty, 3),
                }
            )
    low_stock.sort(key=lambda row: row["shortfall"], reverse=True)

    return DashboardRead(
        generated_at=now,
        window_start=window_start,
        window_end=now,
        kpis=kpis,
        production_trend=trend,
        order_status=order_status,
        machine_status=machine_status,
        downtime_pareto=oee_service.downtime_pareto(db, window_start, now),
        top_defects=top_defects,
        low_stock=low_stock[:8],
        plant_oee=plant,
    )
