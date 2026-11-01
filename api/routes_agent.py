from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

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