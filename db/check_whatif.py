"""Check that recomputing a plan from its stored rows reproduces the stored plan.
Run from the project root:  python -m db.check_whatif [run_id]"""
import sys

import numpy as np
import pandas as pd

from agent.disruption import _load_rows
from agent.facts import connect
from planner import whatif

run_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
with connect() as conn:
    if run_id is None:
        run_id = conn.execute("SELECT max(id) AS id FROM plan_runs").fetchone()["id"]
    stored = pd.DataFrame(conn.execute(
        "SELECT store_id, product_id, city_id, order_qty, ship_qty FROM store_lines WHERE run_id = %s ORDER BY id",
        (run_id,)).fetchall()).apply(pd.to_numeric)

run, stores, wh = _load_rows(run_id)
base = whatif.compute(stores, wh, run["kappa"])
d_order = np.abs(base.order_qty.to_numpy() - stored.order_qty.to_numpy())
d_ship = np.abs(base.ship_qty.to_numpy() - stored.ship_qty.to_numpy())
print(f"run {run_id} | plan date {run['plan_date']} | kappa {run['kappa']} | lines {len(stored)}")
print(f"largest difference in order_qty: {d_order.max():.4f} | in ship_qty: {d_ship.max():.4f}")
print(f"lines differing by more than 0.01: orders {int((d_order > 0.01).sum())}, shipments {int((d_ship > 0.01).sum())}")
print("RESULT:", "OK, recomputed plan equals the stored plan" if max(d_order.max(), d_ship.max()) < 0.01
      else "MISMATCH, do not trust what-if numbers until this is explained")