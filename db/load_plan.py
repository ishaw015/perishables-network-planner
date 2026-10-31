import os
import pandas as pd
import psycopg
from dotenv import load_dotenv

load_dotenv()
url = os.environ["DATABASE_URL"]

PLAN_DATE, SHELF_LIFE, KAPPA = "2024-06-28", 5, 0.5
NOTE = "Example plan from the simulated world (day 3 of the measured week); stock is simulated."

stores = pd.read_csv("results/example_plan_stores.csv")
wh = pd.read_csv("results/example_plan_warehouses.csv")
store_cols = ["store_id", "product_id", "city_id", "on_hand", "pending", "forecast_today", "forecast_tomorrow",
              "p90_today", "p90_tomorrow", "target", "order_qty", "ship_qty", "short_qty", "expiring_units",
              "stockout_likely", "stockout_possible", "status"]
wh_cols = ["city_id", "product_id", "on_hand", "shipped_today", "after_shipments", "pending", "target",
           "order_qty", "requested_by_stores", "shippable_now", "shortage"]

with psycopg.connect(url) as conn, conn.cursor() as cur:
    cur.execute("INSERT INTO plan_runs (plan_date, shelf_life_days, kappa, note) VALUES (%s, %s, %s, %s) RETURNING id",
                (PLAN_DATE, SHELF_LIFE, KAPPA, NOTE))
    run_id = cur.fetchone()[0]
    for table, df, cols in (("store_lines", stores, store_cols), ("warehouse_lines", wh, wh_cols)):
        with cur.copy(f"COPY {table} (run_id, {', '.join(cols)}) FROM STDIN") as cp:
            for rec in df[cols].to_dict("records"):
                cp.write_row((run_id, *[rec[c] for c in cols]))
    cur.execute("SELECT status, COUNT(*), ROUND(SUM(order_qty)::numeric) FROM store_lines "
                "WHERE run_id = %s GROUP BY status ORDER BY 1", (run_id,))
    print("run", run_id, "store lines by status (status, count, ordered units):")
    for row in cur.fetchall():
        print("  ", row)
    cur.execute("SELECT COUNT(*), ROUND(SUM(order_qty)::numeric), SUM(shortage::int) FROM warehouse_lines WHERE run_id = %s", (run_id,))
    print("warehouse lines (count, ordered units, pools short):", cur.fetchone())