"""What-if re-planning from stored plan rows. Pure numpy/pandas: no database, no LLM.

It calls the same policy functions as the daily plan, so a what-if cannot disagree with the
planner's own rules. Scope of version 1: store orders and warehouse-to-store shipments.
Central re-orders and expiry flags need data that is not stored with the plan, so they are
not recomputed here.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import policy

# allowed size of each disruption, in percent
LIMITS = {
    "warehouse_stock_cut": (1, 100),    # share of shippable warehouse stock that is lost
    "demand_change": (-50, 100),        # demand above (+) or below (-) the forecast
    "inbound_shortfall": (1, 100),      # share of units already on the way that will not arrive
}


@dataclass(frozen=True)
class Scenario:
    type: str
    city_id: int | None
    product_id: int | None
    percent: float


def _scope(stores, sc):
    m = np.ones(len(stores), dtype=bool)
    if sc.city_id is not None:
        m &= stores["city_id"].to_numpy() == sc.city_id
    if sc.product_id is not None:
        m &= stores["product_id"].to_numpy() == sc.product_id
    return m


def check(stores, sc):
    """Return None if the scenario is valid for this plan, otherwise a short reason."""
    if sc.type not in LIMITS:
        return "That kind of disruption is not supported."
    lo, hi = LIMITS[sc.type]
    if not (lo <= sc.percent <= hi):
        return f"The size of the change must be between {lo} and {hi} percent."
    if sc.city_id is None and sc.product_id is None:
        return "Please say which city or product is affected."
    if sc.type == "warehouse_stock_cut" and sc.city_id is None:
        return "A warehouse stock cut needs a city."
    in_scope = _scope(stores, sc)
    if not in_scope.any():
        return "No lines in this plan match that city and product."
    if sc.type == "inbound_shortfall" and stores["pending"].to_numpy(float)[in_scope].sum() <= 0:
        return ("No stock is on its way for that city or product in this plan, "
                "so this disruption would change nothing.")
    return None


def compute(stores, wh, kappa, sc=None):
    """Recompute store orders and shipments from stored rows.
    sc=None recomputes the baseline, which must equal the stored plan."""
    on_hand = stores["on_hand"].to_numpy(float)
    pending = stores["pending"].to_numpy(float).copy()
    f50 = np.column_stack([stores["forecast_today"], stores["forecast_tomorrow"]]).astype(float)
    f90 = np.column_stack([stores["p90_today"], stores["p90_tomorrow"]]).astype(float)
    avail = wh["shippable_now"].to_numpy(float).copy()

    index = {(c, p): i for i, (c, p) in enumerate(zip(wh["city_id"], wh["product_id"]))}
    wh_of = np.array([index[(c, p)] for c, p in zip(stores["city_id"], stores["product_id"])])

    in_scope = np.zeros(len(stores), dtype=bool)
    if sc is not None:
        in_scope = _scope(stores, sc)
        if sc.type == "demand_change":
            mult = 1 + sc.percent / 100
            f50[in_scope] *= mult
            f90[in_scope] *= mult
        elif sc.type == "inbound_shortfall":
            pending[in_scope] *= 1 - sc.percent / 100
        elif sc.type == "warehouse_stock_cut":
            wm = wh["city_id"].to_numpy() == sc.city_id
            if sc.product_id is not None:
                wm &= wh["product_id"].to_numpy() == sc.product_id
            avail[wm] *= 1 - sc.percent / 100

    target = policy.store_targets(f50, f90, kappa)
    order = policy.store_orders(target, on_hand, pending)
    ratio, _ = policy.allocation_ratio(order, avail, wh_of, len(wh))
    ship = order * ratio[wh_of]
    short = order - ship

    out = stores[["store_id", "product_id", "city_id"]].copy()
    out["order_qty"] = order
    out["ship_qty"] = ship
    out["short_qty"] = short
    out["status"] = np.where(short > 0.5, "warehouse short", np.where(order > 0, "order", "hold"))
    out["stockout_likely"] = on_hand < f50[:, 0]
    out["stockout_possible"] = on_hand < f90[:, 0]
    out["in_scope"] = in_scope
    return out


def _stored_sum(col):
    """Sum as the database reports it: each line is stored to 2 decimals, then added up."""
    return int(round(float(np.round(col.to_numpy(float), 2).sum())))


def summarise(df):
    return {
        "ordered_units": _stored_sum(df["order_qty"]),
        "shipped_units": _stored_sum(df["ship_qty"]),
        "short_units": _stored_sum(df["short_qty"]),
        "lines_short": int((df["status"] == "warehouse short").sum()),
        "stockout_likely": int(df["stockout_likely"].sum()),
    }


def _direction(delta):
    return "unchanged" if delta == 0 else ("more" if delta > 0 else "fewer")


def compare(before, after, include_stockout=True):
    """Numbers for the explanation and the screen. All arithmetic happens here, in code.
    The likely-stockout count depends only on stock and forecast, so it can only change in a
    demand scenario; other scenarios leave it out rather than imply that risk is unchanged."""
    b, a = summarise(before), summarise(after)
    if not include_stockout:
        b.pop("stockout_likely"), a.pop("stockout_likely")
    diff = {}
    for k in b:
        d = a[k] - b[k]
        diff[k] = abs(d)
        diff[k + "_direction"] = _direction(d)
    change = after["ship_qty"].to_numpy() - before["ship_qty"].to_numpy()
    changed = np.abs(change) > 0.5
    diff["lines_changed"] = int(changed.sum())
    order_ = np.argsort(-np.abs(change))[:5]
    top = [{"store_id": int(after["store_id"].iloc[i]), "product_id": int(after["product_id"].iloc[i]),
            "city_id": int(after["city_id"].iloc[i]),
            "shipped_before": int(round(before["ship_qty"].iloc[i])),
            "shipped_after": int(round(after["ship_qty"].iloc[i]))}
           for i in order_ if changed[i]]
    return {"before": b, "after": a, "diff": diff, "lines_in_scope": int(after["in_scope"].sum()),
            "top_lines": top}