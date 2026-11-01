import pathlib
import re
import psycopg
import pytest

from agent.facts import build_facts, connect, fmt
from agent.template import template_explanation
from agent.verify import verify

LINE = 600  # warehouse-short line from the example plan


@pytest.fixture(scope="module")
def facts():
    return build_facts(LINE)


def test_database_connection_is_read_only():
    with connect() as c:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            c.execute("UPDATE store_lines SET order_qty = order_qty WHERE id = 600")


def test_agent_code_has_no_write_path():
    for p in pathlib.Path("agent").glob("*.py"):
        src = p.read_text()
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|ALTER|DROP)\b", src), p
        assert not re.search(r"^\s*(from|import)\s+(planner|api)\b", src, re.M), p


def test_derived_arithmetic_matches_policy(facts):
    t = facts["store.target"]["value"]
    base = facts["derived.forecast_two_days"]["value"] + facts["derived.safety_buffer"]["value"]
    assert t - 1 < base <= t          # target is the rounded-up policy value
    assert abs(facts["derived.gap_to_target"]["value"] - facts["store.order_qty"]["value"]) < 1e-3


def test_template_passes_verifier(facts):
    assert verify(template_explanation(facts), facts)["ok"]


def test_correct_answer_accepted(facts):
    oq = fmt(facts["store.order_qty"]["value"])
    d = {"answer": f"The plan orders {oq} units.", "used_facts": ["store.order_qty"]}
    assert verify(d, facts)["ok"]


def test_wrong_number_rejected(facts):
    d = {"answer": "The plan orders 99 units.", "used_facts": ["store.order_qty"]}
    r = verify(d, facts)
    assert not r["ok"] and "99" in r["fabricated_numbers"]


def test_uncited_number_flagged(facts):
    oq = fmt(facts["store.order_qty"]["value"])
    d = {"answer": f"The plan orders {oq} units.", "used_facts": []}
    r = verify(d, facts)
    assert not r["ok"] and oq in r["uncited_numbers"]


def test_unknown_fact_key_rejected(facts):
    d = {"answer": "Fine.", "used_facts": ["store.profit"]}
    assert not verify(d, facts)["ok"]


def test_decision_language_rejected(facts):
    d = {"answer": "You should order more units here.", "used_facts": []}
    assert verify(d, facts)["boundary_violations"]


def test_wrong_date_rejected(facts):
    d = {"answer": "This is the plan for 2023-01-01.", "used_facts": ["plan.plan_date"]}
    assert not verify(d, facts)["ok"]
    
def test_number_glued_to_word_is_still_checked(facts):
    d = {"answer": "The warehouse has2066 shippable units.", "used_facts": ["pool.shippable_now"]}
    assert verify(d, facts)["numbers_checked"] == 1


def test_fused_text_rejected(facts):
    oq = fmt(facts["store.order_qty"]["value"])
    d = {"answer": f"The plan orders {oq}units.", "used_facts": ["store.order_qty"]}
    r = verify(d, facts)
    assert not r["ok"] and any("fused" in p for p in r["problems"])
    
def test_words_fused_together_rejected(facts):
    d = {"answer": "The store needs to order 43 unitsto reach its target.",
         "used_facts": ["store.order_qty"]}
    r = verify(d, facts)
    assert not r["ok"] and any("misspelt" in p for p in r["problems"])


def test_normal_answer_has_no_unknown_words(facts):
    from agent.verify import unknown_words
    assert unknown_words("The order quantity comes from the planning policy and the planner can approve it.", facts) == []