"""Optimisation findings across process, time and cost.

Everything here is derived from the schedule and the cost roll-up - nothing is
entered by hand and nothing is guessed. Each finding carries the number it was
derived from, because a recommendation a planner cannot check is a
recommendation a planner will not act on.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..enums import OperationStatus
from ..models.master import WorkCenter
from . import calendar_service as cal
from . import costing_service as costing
from . import scheduling_service as sched

# A work centre above this much of its capacity is treated as the constraint.
BOTTLENECK_THRESHOLD = 0.85
# Below this, a work centre is carrying far less than the constraint.
UNDERUSED_THRESHOLD = 0.40


def bottleneck(schedule: sched.Schedule) -> dict | None:
    """The work centre that sets plant throughput.

    Every other centre's spare capacity is worthless while this one is full:
    an hour recovered anywhere else produces nothing extra, and an hour
    recovered here produces an hour of plant output.
    """
    loaded = [row for row in schedule.utilisation if row["capacity_hours"] > 0]
    if not loaded:
        return None

    top = max(loaded, key=lambda r: r["utilisation"])
    if top["loaded_hours"] <= 0:
        return None

    others = [r for r in loaded if r["work_center_id"] != top["work_center_id"]]
    slack = round(sum(r["capacity_hours"] - r["loaded_hours"] for r in others), 2)

    return {
        **top,
        "is_constraint": top["utilisation"] >= BOTTLENECK_THRESHOLD,
        "idle_capacity_elsewhere_hours": slack,
        "setup_share": round(top["setup_hours"] / top["loaded_hours"], 4) if top["loaded_hours"] else 0.0,
    }


def flow_efficiency(schedule: sched.Schedule) -> dict:
    """How much of an order's elapsed time is actual work.

    On most floors the answer is a small fraction, and that gap - queueing
    between operations - is where lead time really goes. Cutting run times is
    the expensive way to shorten lead time; cutting queue is the cheap one.
    """
    if not schedule.orders:
        return {"orders": 0, "work_hours": 0.0, "flow_hours": 0.0, "efficiency": 0.0, "queue_hours": 0.0}

    work = sum(op.minutes for op in schedule.operations) / 60.0
    flow = sum(
        (order.end - order.start).total_seconds() / 3600.0 for order in schedule.orders
    )
    return {
        "orders": len(schedule.orders),
        "work_hours": round(work, 2),
        "flow_hours": round(flow, 2),
        "queue_hours": round(max(flow - work, 0.0), 2),
        "efficiency": round(work / flow, 4) if flow > 0 else 0.0,
    }


def setup_consolidation(db: Session, schedule: sched.Schedule) -> list[dict]:
    """Setup paid more than once for the same part at the same work centre.

    Two open orders for the same item each pay their own setup. Run them
    back to back and the second setup is avoidable - the machine is already
    tooled for that part.
    """
    rates = {wc.id: wc.cost_rate_per_hour for wc in db.scalars(select(WorkCenter))}

    # (item, work centre) -> the operations queued for it
    groups: dict[tuple[str, int], list[sched.ScheduledOperation]] = {}
    for op in schedule.operations:
        if op.setup_minutes <= 0:
            continue
        groups.setdefault((op.item_code, op.work_center_id), []).append(op)

    findings = []
    for (item_code, wc_id), ops in groups.items():
        if len(ops) < 2:
            continue
        saveable = (len(ops) - 1) * ops[0].setup_minutes
        findings.append(
            {
                "item_code": item_code,
                "work_center_code": ops[0].work_center_code,
                "orders": len(ops),
                "setup_minutes_each": ops[0].setup_minutes,
                "saveable_minutes": round(saveable, 1),
                "saveable_hours": round(saveable / 60.0, 2),
                "saveable_cost": round(saveable / 60.0 * rates.get(wc_id, 0.0), 2),
                "order_nos": sorted({op.order_no for op in ops}),
            }
        )

    findings.sort(key=lambda f: f["saveable_minutes"], reverse=True)
    return findings


def recommendations(
    db: Session,
    schedule: sched.Schedule,
    comparison: dict,
    cost: dict,
    scrap: list[dict],
    setups: list[dict],
    flow: dict,
) -> list[dict]:
    """Ranked, evidenced actions. Severity is by size of the prize, not by tone."""
    findings: list[dict] = []

    # --- process: the constraint ---
    neck = bottleneck(schedule)
    if neck:
        if neck["is_constraint"]:
            findings.append({
                "area": "process",
                "severity": "high",
                "title": f"{neck['work_center_code']} is the constraint at {neck['utilisation'] * 100:.0f}% loaded",
                "detail": (
                    f"{neck['loaded_hours']:.0f} h of work against {neck['capacity_hours']:.0f} h of capacity on "
                    f"{neck['machines']} machine(s). Plant output is capped here, and there are "
                    f"{neck['idle_capacity_elsewhere_hours']:.0f} h of idle capacity at other centres that cannot help."
                ),
                "action": "Add a shift or a machine here, or move work off it. Improving any other centre changes nothing.",
                "value": f"{neck['loaded_hours']:.0f} h loaded",
            })
        else:
            # Naming the busiest resource is still useful below the constraint
            # threshold - it is where the next order lands, and the first place
            # capacity should go. Calling it a bottleneck when it is not would
            # send the improvement team somewhere that is not costing anything.
            headroom = neck["capacity_hours"] - neck["loaded_hours"]
            findings.append({
                "area": "process",
                "severity": "low",
                "title": f"No capacity constraint - {neck['work_center_code']} is busiest at {neck['utilisation'] * 100:.0f}%",
                "detail": (
                    f"{neck['loaded_hours']:.0f} h loaded against {neck['capacity_hours']:.0f} h available, "
                    f"{headroom:.0f} h of headroom. This order book is limited by sequencing and queueing, "
                    "not by machine capacity."
                ),
                "action": "Do not buy capacity. Attack the queue and the release sequence first.",
                "value": f"{headroom:.0f} h spare",
            })

        # Line balance: the spread between the busiest and the quietest centre.
        loaded_rows = [r for r in schedule.utilisation if r["capacity_hours"] > 0 and r["loaded_hours"] > 0]
        if len(loaded_rows) >= 2:
            busiest = max(loaded_rows, key=lambda r: r["utilisation"])
            quietest = min(loaded_rows, key=lambda r: r["utilisation"])
            spread = busiest["utilisation"] - quietest["utilisation"]
            if spread >= 0.25:
                findings.append({
                    "area": "process",
                    "severity": "medium" if spread >= 0.45 else "low",
                    "title": f"Line is unbalanced by {spread * 100:.0f} points across work centres",
                    "detail": (
                        f"{busiest['work_center_code']} runs at {busiest['utilisation'] * 100:.0f}% while "
                        f"{quietest['work_center_code']} runs at {quietest['utilisation'] * 100:.0f}%. "
                        "The quiet centres finish early and then wait."
                    ),
                    "action": (
                        f"Move content from {busiest['work_center_code']} to {quietest['work_center_code']} in the "
                        "routing, or staff them differently. Balanced lines carry the same order book in less time."
                    ),
                    "value": f"{spread * 100:.0f} pt spread",
                })

        if neck["setup_share"] > 0.20:
            findings.append({
                "area": "process",
                "severity": "medium",
                "title": f"Setup is {neck['setup_share'] * 100:.0f}% of loaded time at {neck['work_center_code']}",
                "detail": (
                    f"{neck['setup_hours']:.1f} h of the {neck['loaded_hours']:.1f} h queued at the constraint is "
                    "changeover, not production."
                ),
                "action": "Sequence like parts together, or attack changeover time directly (SMED).",
                "value": f"{neck['setup_hours']:.1f} h",
            })

    underused = [
        r for r in schedule.utilisation
        if 0 < r["utilisation"] < UNDERUSED_THRESHOLD and r["capacity_hours"] > 0
    ]
    if underused and neck and neck["is_constraint"]:
        names = ", ".join(r["work_center_code"] for r in underused[:3])
        findings.append({
            "area": "process",
            "severity": "low",
            "title": f"Capacity is unbalanced: {names} under {UNDERUSED_THRESHOLD * 100:.0f}% loaded",
            "detail": "These centres finish early and then wait on the constraint.",
            "action": "Rebalance the routing, or accept the imbalance and stop staffing them to full shifts.",
            "value": f"{len(underused)} centres",
        })

    # --- time: sequencing and queue ---
    if comparison["improvement"] > 0.01:
        findings.append({
            "area": "time",
            "severity": "high" if comparison["improvement_pct"] > 25 else "medium",
            "title": f"Switching to {comparison['best_rule']} cuts {comparison['objective_label'].lower()} by {comparison['improvement_pct']:.0f}%",
            "detail": (
                f"Same orders, same machines, different running order: "
                f"{comparison['improvement']:.1f} fewer hours than the current priority sequence."
            ),
            "action": f"Release work in {comparison['best_rule']} order.",
            "value": f"−{comparison['improvement']:.1f} h",
        })

    if flow["efficiency"] and flow["efficiency"] < 0.5:
        findings.append({
            "area": "time",
            "severity": "medium",
            "title": f"Only {flow['efficiency'] * 100:.0f}% of order lead time is actual work",
            "detail": (
                f"{flow['work_hours']:.0f} h of work spread over {flow['flow_hours']:.0f} h of elapsed shift time — "
                f"{flow['queue_hours']:.0f} h is queueing between operations."
            ),
            "action": "Shrink batch sizes or overlap operations. Lead time here is a queueing problem, not a speed problem.",
            "value": f"{flow['queue_hours']:.0f} h queued",
        })

    if schedule.late_orders:
        findings.append({
            "area": "time",
            "severity": "high" if schedule.late_orders > 2 else "medium",
            "title": f"{schedule.late_orders} order(s) finish after their due date",
            "detail": (
                f"Worst case is {schedule.max_lateness_hours:.1f} h late; "
                f"{schedule.total_lateness_hours:.1f} h of lateness in total."
            ),
            "action": "Re-promise the dates, or bring capacity forward at the constraint.",
            "value": f"{schedule.total_lateness_hours:.1f} h late",
        })

    if schedule.unscheduled:
        findings.append({
            "area": "time",
            "severity": "high",
            "title": f"{len(schedule.unscheduled)} order(s) do not fit the horizon at all",
            "detail": "; ".join(f"{u['order_no']}: {u['reason']}" for u in schedule.unscheduled[:3]),
            "action": "Extend the horizon, add capacity, or cut the order book.",
            "value": f"{len(schedule.unscheduled)} orders",
        })

    # --- cost: variance, scrap, setup ---
    for finding in setups[:1]:
        if finding["saveable_minutes"] >= 15:
            findings.append({
                "area": "cost",
                "severity": "medium",
                "title": f"Batching {finding['item_code']} at {finding['work_center_code']} saves {finding['saveable_minutes']:.0f} min of setup",
                "detail": (
                    f"{finding['orders']} open orders for the same part each pay "
                    f"{finding['setup_minutes_each']:.0f} min of changeover: "
                    + ", ".join(finding["order_nos"][:4])
                    + (" and others" if len(finding["order_nos"]) > 4 else "")
                ),
                "action": "Run them consecutively so the machine is tooled once.",
                "value": f"{finding['saveable_cost']:.2f} saved",
            })

    if cost["standard_total"] > 0 and abs(cost["variance_pct"]) >= 2:
        over = cost["total_variance"] > 0
        findings.append({
            "area": "cost",
            "severity": "high" if abs(cost["variance_pct"]) > 10 else "medium",
            "title": f"Actual cost is {abs(cost['variance_pct']):.1f}% {'over' if over else 'under'} standard",
            "detail": (
                f"{cost['actual_total']:,.0f} actual against {cost['standard_total']:,.0f} standard across "
                f"{cost['orders']} orders. Material {cost['material_variance']:+,.0f}, "
                f"labour {cost['labour_variance']:+,.0f}."
            ),
            "action": "Standards are stale or the process has drifted. Check the largest-variance orders first.",
            "value": f"{cost['total_variance']:+,.0f}",
        })

    if scrap:
        top = scrap[0]
        total_scrap = sum(s["cost"] for s in scrap)
        if total_scrap > 0:
            findings.append({
                "area": "cost",
                "severity": "high" if top["cost"] / total_scrap > 0.4 else "medium",
                "title": f"{top['code']} — {top['name']} is the most expensive defect",
                "detail": (
                    f"{top['cost']:,.0f} of {total_scrap:,.0f} total scrap value over the window "
                    f"({top['cost'] / total_scrap * 100:.0f}%), from {top['qty']:.0f} units."
                ),
                "action": "Fix this one first. Ranked by money it dwarfs the more frequent defects.",
                "value": f"{top['cost']:,.0f}",
            })

    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    return findings


def full_report(
    db: Session,
    *,
    rule: str = "PRIORITY",
    horizon_days: int = 30,
    objective: str = "total_lateness_hours",
    cost_days: int = 30,
) -> dict:
    """One pass over process, time and cost."""
    now = datetime.now()
    schedule = sched.build_schedule(db, rule=rule, horizon_start=now, horizon_days=horizon_days)
    comparison = sched.compare_rules(db, horizon_start=now, horizon_days=horizon_days, objective=objective)
    cost = costing.cost_summary(db, days=cost_days)
    scrap = costing.scrap_cost_by_defect(db, days=cost_days)
    setups = setup_consolidation(db, schedule)
    flow = flow_efficiency(schedule)

    return {
        "generated_at": now,
        "schedule": schedule,
        "comparison": comparison,
        "bottleneck": bottleneck(schedule),
        "flow": flow,
        "setups": setups,
        "cost": cost,
        "scrap_cost": scrap,
        "recommendations": recommendations(db, schedule, comparison, cost, scrap, setups, flow),
    }
