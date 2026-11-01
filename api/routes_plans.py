from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.types.json import Jsonb
from .database import get_conn
from .schemas import (PlanRunOut, PlanSummaryOut, StoreLineOut, WarehouseLineOut, DecisionIn, DecisionOut)
from .security import current_user

router = APIRouter(tags=["plans"])

def _run_or_404(conn, run_id: int):
    run = conn.execute("SELECT * FROM plan_runs WHERE id = %s", (run_id,)).fetchone()
    if run is None:
        raise HTTPException(status_code=404, detail=f"Plan run {run_id} not found")
    return run

@router.get("/plans", response_model=list[PlanRunOut])
def list_plans(conn=Depends(get_conn), user=Depends(current_user)):
    return conn.execute("SELECT * FROM plan_runs ORDER BY plan_date DESC, id DESC").fetchall()

@router.get("/plans/{run_id}/summary", response_model=PlanSummaryOut)
def plan_summary(run_id: int, conn=Depends(get_conn), user=Depends(current_user)):
    run = _run_or_404(conn, run_id)
    s = conn.execute("""
        SELECT COUNT(*) AS lines,
               COUNT(*) FILTER (WHERE status = 'order') AS orders,
               COUNT(*) FILTER (WHERE status = 'hold') AS holds,
               COUNT(*) FILTER (WHERE status = 'warehouse short') AS warehouse_short,
               COUNT(*) FILTER (WHERE stockout_likely) AS stockout_likely,
               COUNT(*) FILTER (WHERE stockout_possible) AS stockout_possible,
               COUNT(*) FILTER (WHERE expiring_units > 0.5) AS expiring_series,
               COALESCE(SUM(expiring_units), 0)::float AS expiring_units,
               COALESCE(SUM(order_qty), 0)::float AS ordered_units,
               COALESCE(SUM(ship_qty), 0)::float AS shipped_units,
               COALESCE(SUM(short_qty), 0)::float AS short_units
        FROM store_lines WHERE run_id = %s""", (run_id,)).fetchone()
    w = conn.execute("""
        SELECT COUNT(*) AS warehouse_pools,
               COUNT(*) FILTER (WHERE shortage) AS warehouse_pools_short,
               COALESCE(SUM(order_qty), 0)::float AS central_order_units
        FROM warehouse_lines WHERE run_id = %s""", (run_id,)).fetchone()
    d = conn.execute("""
        SELECT COUNT(DISTINCT d.store_line_id) AS decided_lines
        FROM decisions d JOIN store_lines l ON l.id = d.store_line_id WHERE l.run_id = %s""", (run_id,)).fetchone()
    return {"run": run, **s, **w, **d}

@router.get("/plans/{run_id}/store-lines", response_model=list[StoreLineOut])
def store_lines(run_id: int,
                status: Optional[Literal["order", "hold", "warehouse short"]] = None,
                city_id: Optional[int] = None,
                stockout: Optional[Literal["likely", "possible"]] = None,
                expiring: bool = False,
                undecided: bool = False,
                sort: Literal["order_qty", "short_qty", "expiring_units", "on_hand", "target"] = "order_qty",
                limit: int = Query(50, ge=1, le=200),
                offset: int = Query(0, ge=0),
                conn=Depends(get_conn), user=Depends(current_user)):
    _run_or_404(conn, run_id)
    where, params = ["l.run_id = %s"], [run_id]
    if status:
        where.append("l.status = %s"); params.append(status)
    if city_id is not None:
        where.append("l.city_id = %s"); params.append(city_id)
    if stockout == "likely":
        where.append("l.stockout_likely")
    if stockout == "possible":
        where.append("l.stockout_possible")
    if expiring:
        where.append("l.expiring_units > 0.5")
    if undecided:
        where.append("d.action IS NULL")
    sql = f"""
        SELECT l.*, d.action AS decision_action, d.final_qty AS decision_qty, d.decided_at AS decided_at
        FROM store_lines l
        LEFT JOIN LATERAL (
            SELECT action, final_qty, decided_at FROM decisions
            WHERE store_line_id = l.id ORDER BY decided_at DESC, id DESC LIMIT 1) d ON TRUE
        WHERE {' AND '.join(where)}
        ORDER BY l.{sort} DESC, l.id
        LIMIT %s OFFSET %s"""
    return conn.execute(sql, params + [limit, offset]).fetchall()

@router.get("/plans/{run_id}/warehouse-lines", response_model=list[WarehouseLineOut])
def warehouse_lines(run_id: int, shortage: Optional[bool] = None, city_id: Optional[int] = None,
                    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                    conn=Depends(get_conn), user=Depends(current_user)):
    _run_or_404(conn, run_id)
    where, params = ["run_id = %s"], [run_id]
    if shortage is not None:
        where.append("shortage = %s"); params.append(shortage)
    if city_id is not None:
        where.append("city_id = %s"); params.append(city_id)
    sql = f"SELECT * FROM warehouse_lines WHERE {' AND '.join(where)} ORDER BY order_qty DESC, id LIMIT %s OFFSET %s"
    return conn.execute(sql, params + [limit, offset]).fetchall()

@router.post("/store-lines/{line_id}/decision", response_model=DecisionOut, status_code=201)
def decide(line_id: int, body: DecisionIn, conn=Depends(get_conn), user=Depends(current_user)):
    line = conn.execute("SELECT id, target, order_qty FROM store_lines WHERE id = %s", (line_id,)).fetchone()
    if line is None:
        raise HTTPException(status_code=404, detail=f"Store line {line_id} not found")
    if body.action == "edit" and body.final_qty > max(3 * line["target"], 10):
        raise HTTPException(status_code=422,
                            detail="final_qty is more than 3 times the order-up-to target; please check the number")
    final_qty = {"approve": line["order_qty"], "reject": 0.0}.get(body.action, body.final_qty)
    dec = conn.execute("""
        INSERT INTO decisions (store_line_id, user_id, action, final_qty, comment)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, store_line_id, user_id, action, final_qty, comment, decided_at""",
        (line_id, user["id"], body.action, final_qty, body.comment)).fetchone()
    conn.execute("INSERT INTO audit_log (user_id, action, entity, entity_id, detail) VALUES (%s, 'decision', 'store_line', %s, %s)",
                 (user["id"], line_id, Jsonb({"action": body.action, "final_qty": final_qty,
                                              "recommended": line["order_qty"]})))
    conn.commit()
    return dec