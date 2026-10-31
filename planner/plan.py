import numpy as np, pandas as pd
from . import policy

def make_plan(inp, snap, kappa, pool=True):
    """Returns (stores, warehouses) tables for one planning day."""
    S, W = snap["S"], snap["W"]
    w50, w90 = snap["w50"], snap["w90"]
    wh_of, m = inp.wh_of, inp.m
    on_hand = S.sum(1)
    target = policy.store_targets(w50, w90, kappa)
    order = policy.store_orders(target, on_hand, snap["pend_s"])
    shippable = W[:, 2:].sum(1)
    ratio, req = policy.allocation_ratio(order, shippable, wh_of, m)
    ship = order * ratio[wh_of]
    at_risk, likely, possible = policy.risk_flags(w50, w90, S, on_hand)

    stores = pd.DataFrame(dict(
        store_id=inp.store_id, product_id=inp.product_id, city_id=inp.city_id,
        on_hand=on_hand, pending=snap["pend_s"],
        forecast_today=w50[:, 0], forecast_tomorrow=w50[:, 1],
        p90_today=w90[:, 0], p90_tomorrow=w90[:, 1],
        target=target, order_qty=order, ship_qty=ship, short_qty=order - ship,
        expiring_units=at_risk, stockout_likely=likely, stockout_possible=possible))
    stores["status"] = np.where(stores.short_qty > 0.5, "warehouse short",
                                np.where(stores.order_qty > 0, "order", "hold"))

    shipped_today = req * ratio
    after = W.sum(1) - shipped_today               # warehouse stock left after today's shipments to stores
    tw = policy.warehouse_targets(w50, w90, kappa, wh_of, m, pool)
    wo = policy.warehouse_orders(tw, after, snap["pend_w"])
    first = pd.Series(np.arange(inp.n)).groupby(wh_of).first().values
    wh = pd.DataFrame(dict(
        city_id=inp.city_id[first], product_id=inp.product_id[first],
        on_hand=W.sum(1), shipped_today=shipped_today, after_shipments=after,
        pending=snap["pend_w"], target=tw, order_qty=wo,
        requested_by_stores=req, shippable_now=shippable))
    wh["shortage"] = wh.requested_by_stores > wh.shippable_now + 0.5
    return stores, wh