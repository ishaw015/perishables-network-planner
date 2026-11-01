import random

from agent.facts import build_facts, connect
from agent.template import template_explanation
from agent.verify import numbers_in, verify


def corruptions(d):
    a, keys = d["answer"], d["used_facts"]
    out = {}
    nums = numbers_in(a)
    if nums:
        x = nums[len(nums) // 2]
        out["wrong_number"] = (a.replace(x, str(round(float(x.replace(",", "")) * 1.37 + 3, 1)), 1), keys)
    out["invented_number"] = (a + " Sales were 77 units yesterday.", keys)
    out["decision_language"] = (a + " You should order 5 more units.", keys)
    out["dropped_citations"] = (a, [])
    out["unknown_fact_key"] = (a, keys + ["store.profit"])
    out["wrong_date"] = (a + " This is the plan for 2023-01-01.", keys)
    if " units" in a:
        out["fused_number_text"] = (a.replace(" units", "units", 1), keys)
    if "the planner" in a:
        out["fused_words"] = (a.replace("the planner", "theplanner", 1), keys)
    return out


def main():
    with connect() as c:
        ids = [r["id"] for r in c.execute(
            "SELECT id FROM store_lines WHERE run_id=1 ORDER BY md5(id::text) LIMIT 60").fetchall()]
    caught, total, clean_ok = {}, {}, 0
    for lid in ids:
        facts = build_facts(lid)
        base = template_explanation(facts)
        clean_ok += verify(base, facts)["ok"]
        for name, (ans, keys) in corruptions(base).items():
            total[name] = total.get(name, 0) + 1
            r = verify({"answer": ans, "used_facts": keys}, facts)
            caught[name] = caught.get(name, 0) + (not r["ok"])
    print(f"Correct answers accepted: {clean_ok}/{len(ids)}")
    print("\nCorruption type -> caught by the checker")
    for name in total:
        print(f"  {name:20s} {caught[name]}/{total[name]}  ({100*caught[name]/total[name]:.0f}%)")


if __name__ == "__main__":
    main()