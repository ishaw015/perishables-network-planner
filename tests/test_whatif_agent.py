"""Tests for the disruption agent with the language model and the database replaced by fakes."""
import pytest

from agent import disruption
from tests.test_whatif import make_rows, KAPPA

RUN = {"plan_date": "2024-06-28", "kappa": KAPPA}


@pytest.fixture
def fakes(monkeypatch):
    stores, wh = make_rows()
    monkeypatch.setattr(disruption, "_load_rows", lambda run_id: (RUN, stores.copy(), wh.copy()))
    state = {"parse": None, "explain": None, "explain_calls": 0}

    def parse(text):
        if isinstance(state["parse"], Exception):
            raise state["parse"]
        return state["parse"]

    def explain(facts, feedback=""):
        state["explain_calls"] += 1
        return state["explain"](facts)

    monkeypatch.setattr(disruption, "_parse_call", parse)
    monkeypatch.setattr(disruption, "_explain_call", explain)
    return state


def good_answer(facts):
    used = ["scenario.lines_in_scope", "before.shipped_units", "after.shipped_units"]
    v = lambda k: facts[k]["value"]
    return {"answer": (f"This is a preview and the approved plan is unchanged. The disruption affects "
                       f"{v('scenario.lines_in_scope')} store lines, and units shipped to stores go from "
                       f"{v('before.shipped_units')} to {v('after.shipped_units')}."),
            "used_facts": used, "cannot_answer": False}


def bad_answer(facts):
    return {"answer": "Stores would receive 999999 units.", "used_facts": ["after.shipped_units"],
            "cannot_answer": False}


def test_stock_cut_end_to_end(fakes):
    fakes["parse"] = {"type": "warehouse_stock_cut", "city_id": 12, "product_id": None, "percent": 50}
    fakes["explain"] = good_answer
    res = disruption.what_if(1, "city 12 warehouse lost half its stock")
    assert res["status"] == "ok"
    assert res["after"]["shipped_units"] < res["before"]["shipped_units"]
    assert res["before"]["ordered_units"] == res["after"]["ordered_units"]
    assert res["lines_in_scope"] == 6
    assert res["explanation"]["source"] in ("gemini", "template")
    assert res["explanation"]["attempts"] <= disruption.MAX_ATTEMPTS


def test_bad_explanation_falls_back_to_template_after_two_attempts(fakes):
    fakes["parse"] = {"type": "demand_change", "city_id": None, "product_id": 7, "percent": 30}
    fakes["explain"] = bad_answer
    res = disruption.what_if(1, "product 7 demand up 30 percent")
    assert res["status"] == "ok"
    assert res["explanation"]["source"] == "template"
    assert fakes["explain_calls"] == disruption.MAX_ATTEMPTS
    assert "999999" not in res["explanation"]["answer"]
    assert "preview" in res["explanation"]["answer"].lower()


def test_numbers_come_from_the_planner_not_the_model(fakes):
    fakes["parse"] = {"type": "warehouse_stock_cut", "city_id": 16, "product_id": 4, "percent": 100}
    fakes["explain"] = bad_answer
    res = disruption.what_if(1, "city 16 product 4 warehouse is empty")
    assert res["after"]["shipped_units"] <= res["before"]["shipped_units"]
    assert res["lines_in_scope"] == 3


@pytest.mark.parametrize("parsed,status", [
    ({"type": "unsupported", "city_id": None, "product_id": None, "percent": None}, "unsupported"),
    ({"type": "warehouse_stock_cut", "city_id": 12, "product_id": None, "percent": None}, "clarify"),
    ({"type": "warehouse_stock_cut", "city_id": None, "product_id": None, "percent": 50}, "clarify"),
    ({"type": "warehouse_stock_cut", "city_id": 99, "product_id": None, "percent": 50}, "clarify"),
    ({"type": "demand_change", "city_id": 12, "product_id": None, "percent": 500}, "clarify"),
    ({"type": "order_more", "city_id": 12, "product_id": None, "percent": 10}, "unsupported"),
])
def test_stops_before_replanning(fakes, parsed, status):
    fakes["parse"] = parsed
    fakes["explain"] = good_answer
    res = disruption.what_if(1, "anything")
    assert res["status"] == status
    assert fakes["explain_calls"] == 0
    assert "message" in res


def test_unreadable_model_output_asks_to_rephrase(fakes):
    fakes["parse"] = ValueError("bad json")
    res = disruption.what_if(1, "???")
    assert res["status"] == "clarify"


def test_model_outage_is_reported_without_touching_the_plan(fakes):
    fakes["parse"] = RuntimeError("network down")
    res = disruption.what_if(1, "city 12 lost stock")
    assert res["status"] == "unavailable"


def test_agent_code_has_no_database_write_path():
    import inspect
    src = inspect.getsource(disruption).upper()
    for word in ("INSERT ", "UPDATE ", "DELETE ", ".COMMIT("):
        assert word not in src


def test_stockout_count_is_shown_only_for_demand_scenarios(fakes):
    seen = {}
    def grab(facts):
        seen["keys"] = set(facts)
        return good_answer(facts)
    fakes["explain"] = grab
    fakes["parse"] = {"type": "warehouse_stock_cut", "city_id": 12, "product_id": None, "percent": 50}
    res = disruption.what_if(1, "city 12 lost half its stock")
    assert "stockout_likely" not in res["before"] and "before.stockout_likely" not in seen["keys"]
    fakes["parse"] = {"type": "demand_change", "city_id": 12, "product_id": None, "percent": 30}
    res = disruption.what_if(1, "city 12 demand up 30 percent")
    assert "stockout_likely" in res["before"] and "before.stockout_likely" in seen["keys"]


def test_answer_mentioning_stockouts_without_a_stockout_fact_is_rejected(fakes):
    fakes["parse"] = {"type": "warehouse_stock_cut", "city_id": 12, "product_id": None, "percent": 50}
    fakes["explain"] = lambda facts: {**good_answer(facts),
                                      "answer": good_answer(facts)["answer"] + " Stockout counts changed too."}
    res = disruption.what_if(1, "city 12 lost half its stock")
    assert res["explanation"]["source"] == "template"
    assert "stockout" not in res["explanation"]["answer"].lower()
    assert fakes["explain_calls"] == disruption.MAX_ATTEMPTS


def test_stockout_wording_is_allowed_when_a_stockout_fact_exists():
    facts = {"after.stockout_likely": {"value": 203, "label": "x"}}
    assert disruption.extra_problems({"answer": "Likely stockouts rise."}, facts) == []
    assert disruption.extra_problems({"answer": "Likely stockouts rise."}, {"a.b": {"value": 1, "label": "x"}})