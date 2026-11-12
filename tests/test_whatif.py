import numpy as np
import pandas as pd
import pytest

from planner import policy, whatif
from planner.whatif import Scenario

KAPPA = 0.5


def make_rows(seed=0):
    """Small synthetic plan: 2 cities x 2 products x 3 stores, built with the real policy functions."""
    rng = np.random.default_rng(seed)
    rows = []
    for city in (12, 16):
        for prod in (4, 7):
            for store in range(3):
                f50_0, f50_1 = rng.integers(8, 20, 2)
                rows.append(dict(store_id=city * 100 + store, product_id=prod, city_id=city,
                                 on_hand=float(rng.integers(0, 15)), pending=float(rng.integers(0, 6)),
                                 forecast_today=float(f50_0), forecast_tomorrow=float(f50_1),
                                 p90_today=float(f50_0 + 4), p90_tomorrow=float(f50_1 + 5)))
    stores = pd.DataFrame(rows)
    f50 = stores[["forecast_today", "forecast_tomorrow"]].to_numpy()
    f90 = stores[["p90_today", "p90_tomorrow"]].to_numpy()
    target = policy.store_targets(f50, f90, KAPPA)
    order = policy.store_orders(target, stores.on_hand.to_numpy(), stores.pending.to_numpy())
    wh = (stores.groupby(["city_id", "product_id"], sort=False).size().rename("n").reset_index()[["city_id", "product_id"]])
    wh["shippable_now"] = [60.0, 25.0, 60.0, 25.0]
    wh_of = np.array([wh.index[(wh.city_id == c) & (wh.product_id == p)][0]
                      for c, p in zip(stores.city_id, stores.product_id)])
    ratio, _ = policy.allocation_ratio(order, wh.shippable_now.to_numpy(), wh_of, len(wh))
    stores["order_qty"] = order
    stores["ship_qty"] = order * ratio[wh_of]
    return stores, wh


def test_baseline_recompute_equals_stored_plan():
    stores, wh = make_rows()
    base = whatif.compute(stores, wh, KAPPA)
    assert np.allclose(base.order_qty, stores.order_qty)
    assert np.allclose(base.ship_qty, stores.ship_qty)


def test_stock_cut_lowers_shipments_only_in_that_city():
    stores, wh = make_rows()
    sc = Scenario("warehouse_stock_cut", 12, None, 50)
    before, after = whatif.compute(stores, wh, KAPPA), whatif.compute(stores, wh, KAPPA, sc)
    in_city = stores.city_id.to_numpy() == 12
    assert (after.ship_qty[in_city] <= before.ship_qty[in_city] + 1e-9).all()
    assert after.ship_qty[in_city].sum() < before.ship_qty[in_city].sum()
    assert np.allclose(after.ship_qty[~in_city], before.ship_qty[~in_city])
    assert np.allclose(after.order_qty, before.order_qty)      # a stock cut does not change what stores ask for


def test_stock_cut_never_ships_more_than_the_reduced_stock():
    stores, wh = make_rows()
    sc = Scenario("warehouse_stock_cut", 12, 4, 75)
    after = whatif.compute(stores, wh, KAPPA, sc)
    pool = after[(after.city_id == 12) & (after.product_id == 4)]
    limit = wh[(wh.city_id == 12) & (wh.product_id == 4)].shippable_now.iloc[0] * 0.25
    assert pool.ship_qty.sum() <= limit + 1e-6
    assert (after.ship_qty <= after.order_qty + 1e-9).all()


def test_total_cut_ships_nothing_in_scope():
    stores, wh = make_rows()
    after = whatif.compute(stores, wh, KAPPA, Scenario("warehouse_stock_cut", 16, None, 100))
    assert after[after.city_id == 16].ship_qty.sum() == pytest.approx(0)


def test_demand_increase_raises_orders_in_scope_only():
    stores, wh = make_rows()
    sc = Scenario("demand_change", None, 7, 30)
    before, after = whatif.compute(stores, wh, KAPPA), whatif.compute(stores, wh, KAPPA, sc)
    m = stores.product_id.to_numpy() == 7
    assert after.order_qty[m].sum() > before.order_qty[m].sum()
    assert np.allclose(after.order_qty[~m], before.order_qty[~m])


def test_demand_drop_never_gives_negative_orders():
    stores, wh = make_rows()
    after = whatif.compute(stores, wh, KAPPA, Scenario("demand_change", 12, None, -50))
    assert (after.order_qty >= 0).all()


def test_inbound_shortfall_raises_orders():
    stores, wh = make_rows()
    sc = Scenario("inbound_shortfall", 16, None, 100)
    before, after = whatif.compute(stores, wh, KAPPA), whatif.compute(stores, wh, KAPPA, sc)
    m = stores.city_id.to_numpy() == 16
    assert after.order_qty[m].sum() >= before.order_qty[m].sum()
    assert (after.order_qty[m] - before.order_qty[m]).sum() == pytest.approx(stores.pending[m].sum())


def test_compare_numbers_are_consistent():
    stores, wh = make_rows()
    sc = Scenario("warehouse_stock_cut", 12, None, 50)
    before, after = whatif.compute(stores, wh, KAPPA), whatif.compute(stores, wh, KAPPA, sc)
    c = whatif.compare(before, after)
    d = c["diff"]
    assert d["shipped_units"] == abs(c["after"]["shipped_units"] - c["before"]["shipped_units"])
    assert d["shipped_units_direction"] == "fewer"
    assert d["ordered_units_direction"] == "unchanged"
    assert c["lines_in_scope"] == 6
    assert all(t["shipped_after"] <= t["shipped_before"] for t in c["top_lines"])


@pytest.mark.parametrize("sc,expect", [
    (Scenario("warehouse_stock_cut", 12, None, 50), None),
    (Scenario("warehouse_stock_cut", None, 4, 50), "needs a city"),
    (Scenario("warehouse_stock_cut", 12, None, 0), "between"),
    (Scenario("warehouse_stock_cut", 12, None, 150), "between"),
    (Scenario("demand_change", None, None, 20), "which city or product"),
    (Scenario("demand_change", 99, None, 20), "No lines"),
    (Scenario("demand_change", 12, None, -80), "between"),
    (Scenario("order_more", 12, None, 20), "not supported"),
])
def test_check(sc, expect):
    stores, _ = make_rows()
    msg = whatif.check(stores, sc)
    if expect is None:
        assert msg is None
    else:
        assert expect in msg