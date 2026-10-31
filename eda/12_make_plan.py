import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np, pandas as pd
from planner.data import load_inputs
from planner.simulate import run
from planner.plan import make_plan

L, KAPPA, DAY = 5, 0.5, 9
inp = load_inputs()
snap = run(inp, L, KAPPA, snapshot=DAY)
stores, wh = make_plan(inp, snap, KAPPA)

# the plan must equal what the verified simulation actually ordered on that day
trace = {}
run(inp, L, KAPPA, trace=trace)
assert np.allclose(trace[DAY]["order_s"], stores.order_qty), "store orders differ from the simulation"
assert np.allclose(trace[DAY]["order_w"], wh.order_qty), "warehouse orders differ from the simulation"
print("plan matches the simulation for store orders and warehouse orders")

date = pd.Timestamp("2024-06-26") + pd.Timedelta(days=DAY % 7)
print(f"\nplan for {date.date()} | shelf life {L} days | kappa {KAPPA}")
print("store-product rows:", len(stores), "| warehouse pools:", len(wh))
print(stores.status.value_counts().to_string())
print("likely stockout today:", int(stores.stockout_likely.sum()),
      "| possible (below P90):", int(stores.stockout_possible.sum()))
print("series with units expected to expire:", int((stores.expiring_units > 0.5).sum()),
      "| units:", round(stores.expiring_units.sum()))
print("ordered by stores:", round(stores.order_qty.sum()), "| shipped:", round(stores.ship_qty.sum()),
      "| warehouse short:", round(stores.short_qty.sum()))
print("warehouse orders to central:", round(wh.order_qty.sum()), "| pools short:", int(wh.shortage.sum()))

assert (stores.order_qty >= -1e-9).all() and (stores.ship_qty <= stores.order_qty + 1e-9).all()
assert np.allclose(np.maximum(0, stores.target - stores.on_hand - stores.pending), stores.order_qty)
assert (stores.groupby(inp.wh_of).ship_qty.sum().values <= wh.shippable_now.values + 1e-6).all()
assert (stores.expiring_units <= stores.on_hand + 1e-9).all()
print("arithmetic checks passed")

pd.set_option("display.width", 220)
print("\n-- warehouses that cannot cover store orders")
print(wh[wh.shortage].round(1).head(8).to_string(index=False))
print("\n-- 5 largest warehouse orders to central")
print(wh.sort_values("order_qty", ascending=False).head(5).round(1).to_string(index=False))

stores.to_csv("results/example_plan_stores.csv", index=False)
wh.to_csv("results/example_plan_warehouses.csv", index=False)