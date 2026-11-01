import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

LEAD_TIME_STORE_DAYS = 1       # warehouse -> store (simulated)
LEAD_TIME_WAREHOUSE_DAYS = 2   # central -> city warehouse (simulated)


def connect():
    """Read-only connection: the agent can never change the plan."""
    conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
    conn.read_only = True
    return conn


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fmt(x):
    """Number as shown to the model and in templates: up to 2 decimals."""
    s = f"{float(x):.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


STORE_LABELS = {
    "on_hand": "stock on hand at the store today (units)",
    "pending": "units already on the way to the store",
    "forecast_today": "median demand forecast for today (units)",
    "forecast_tomorrow": "median demand forecast for tomorrow (units)",
    "p90_today": "high-demand (P90) forecast for today (units)",
    "p90_tomorrow": "high-demand (P90) forecast for tomorrow (units)",
    "target": "order-up-to target (units)",
    "order_qty": "units the store needs to order to reach its target",
    "ship_qty": "units the city warehouse can ship to the store today",
    "short_qty": "units the city warehouse cannot ship today",
    "expiring_units": "units expected to expire before they sell",
    "stockout_likely": "true if stock is below the median forecast for today",
    "stockout_possible": "true if stock is below the P90 forecast for today",
    "status": "plan status: order, hold or warehouse short",
}
POOL_LABELS = {
    "on_hand": "city warehouse stock for this product (units)",
    "pending": "units already on the way to the city warehouse",
    "target": "city warehouse order-up-to target (units)",
    "requested_by_stores": "units all stores in the city asked for today",
    "shippable_now": "units the city warehouse can ship today",
    "shortage": "true if the warehouse cannot cover all store requests",
}


def build_facts(line_id: int) -> dict:
    """Return {key: {"value": ..., "label": ...}} for one store line."""
    with connect() as conn:
        r = conn.execute(
            """SELECT s.*, p.plan_date, p.shelf_life_days, p.kappa
               FROM store_lines s JOIN plan_runs p ON p.id = s.run_id
               WHERE s.id = %s""", (line_id,)).fetchone()
        if r is None:
            raise KeyError(f"store line {line_id} not found")
        pool = conn.execute(
            """SELECT * FROM warehouse_lines
               WHERE run_id=%s AND city_id=%s AND product_id=%s""",
            (r["run_id"], r["city_id"], r["product_id"])).fetchone()
        dec = conn.execute(
            """SELECT action, final_qty FROM decisions
               WHERE store_line_id=%s ORDER BY decided_at DESC LIMIT 1""",
            (line_id,)).fetchone()

    f = {}

    def put(key, value, label):
        if value is not None:
            f[key] = {"value": value, "label": label}

    put("line.id", r["id"], "store line id")
    put("line.store_id", r["store_id"], "store id")
    put("line.product_id", r["product_id"], "product id")
    put("line.city_id", r["city_id"], "city id")
    put("plan.plan_date", str(r["plan_date"]), "date of the plan")
    put("plan.shelf_life_days", r["shelf_life_days"], "shelf life in days (simulated)")
    put("plan.kappa", r["kappa"], "safety factor kappa used by the policy")
    put("plan.lead_time_store_days", LEAD_TIME_STORE_DAYS, "warehouse to store lead time in days (simulated)")
    put("plan.lead_time_warehouse_days", LEAD_TIME_WAREHOUSE_DAYS, "central to city warehouse lead time in days (simulated)")
    for k, label in STORE_LABELS.items():
        put(f"store.{k}", r[k], label)
    if pool:
        for k, label in POOL_LABELS.items():
            put(f"pool.{k}", pool[k], label)
        if pool["requested_by_stores"] is not None and pool["shippable_now"] is not None:
            put("derived.pool_shortfall",
                pool["requested_by_stores"] - pool["shippable_now"],
                "units requested by stores minus units the warehouse can ship (computed)")
    # arithmetic is done here, never by the model
    if None not in (r["target"], r["on_hand"], r["pending"]):
        put("derived.gap_to_target", r["target"] - r["on_hand"] - r["pending"],
            "target minus stock on hand minus pending (computed)")
    if None not in (r["forecast_today"], r["forecast_tomorrow"]):
        put("derived.forecast_two_days", r["forecast_today"] + r["forecast_tomorrow"],
            "median forecast for today plus tomorrow (computed)")
    if None not in (r["p90_today"], r["p90_tomorrow"], r["forecast_today"],
                    r["forecast_tomorrow"], r["kappa"]):
        put("derived.safety_buffer",
            r["kappa"] * ((r["p90_today"] - r["forecast_today"])
                          + (r["p90_tomorrow"] - r["forecast_tomorrow"])),
            "kappa times the P90-minus-median gaps for today and tomorrow (computed)")
    if dec:  # the planner's comment is deliberately NOT included (untrusted text)
        put("decision.action", dec["action"], "planner decision already recorded")
        put("decision.final_qty", dec["final_qty"], "quantity set by the planner, if edited")
    return f