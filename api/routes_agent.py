from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from agent.disruption import what_if
from agent.graph import explain
from .database import get_conn
from .security import current_user

router = APIRouter(tags=["agent"])


class ExplainIn(BaseModel):
    question: str = Field(
        default="Why does the plan order this quantity for this store and product?",
        min_length=3, max_length=300)


class ExplainOut(BaseModel):
    answer: str
    used_facts: list[str]
    cannot_answer: bool
    source: str          # "gemini" or "template"
    attempts: int


@router.post("/store-lines/{line_id}/explain", response_model=ExplainOut)
def explain_line(line_id: int, body: ExplainIn, conn=Depends(get_conn), user=Depends(current_user)):
    if conn.execute("SELECT 1 FROM store_lines WHERE id = %s", (line_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Store line {line_id} not found")
    try:
        res = explain(line_id, body.question)
    except Exception:
        raise HTTPException(status_code=503,
                            detail="The explanation service is unavailable. The plan itself is not affected.")
    conn.execute(
        "INSERT INTO audit_log (user_id, action, entity, entity_id, detail) VALUES (%s, 'explain', 'store_line', %s, %s)",
        (user["id"], line_id, Jsonb({"question": body.question[:300], "source": res["source"],
                                     "attempts": res["attempts"], "cannot_answer": res["cannot_answer"]})))
    conn.commit()
    return res


# ---------- what-if (disruption) preview: never writes to the plan tables ----------
class WhatIfIn(BaseModel):
    text: str = Field(min_length=3, max_length=300,
                      examples=["the city 12 warehouse lost half its stock"])


class WhatIfExplanation(BaseModel):
    answer: str
    used_facts: list[str]
    cannot_answer: bool
    source: str          # "gemini" or "template"
    attempts: int


class WhatIfOut(BaseModel):
    status: str          # ok, clarify, unsupported
    message: Optional[str] = None
    scenario: Optional[dict] = None
    before: Optional[dict] = None
    after: Optional[dict] = None
    lines_in_scope: Optional[int] = None
    lines_changed: Optional[int] = None
    top_lines: Optional[list[dict]] = None
    explanation: Optional[WhatIfExplanation] = None


@router.post("/plan-runs/{run_id}/what-if", response_model=WhatIfOut)
def what_if_run(run_id: int, body: WhatIfIn, conn=Depends(get_conn), user=Depends(current_user)):
    if conn.execute("SELECT 1 FROM plan_runs WHERE id = %s", (run_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Plan run {run_id} not found")
    res = what_if(run_id, body.text)
    if res["status"] == "unavailable":
        raise HTTPException(status_code=503, detail=res["message"])
    detail = {"text": body.text[:300], "status": res["status"]}
    if res["status"] == "ok":
        detail.update(scenario=res["scenario"], source=res["explanation"]["source"],
                      attempts=res["explanation"]["attempts"])
    conn.execute(
        "INSERT INTO audit_log (user_id, action, entity, entity_id, detail) VALUES (%s, 'what_if', 'plan_run', %s, %s)",
        (user["id"], run_id, Jsonb(detail)))
    conn.commit()
    return res