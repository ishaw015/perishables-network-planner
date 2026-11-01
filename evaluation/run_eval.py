import argparse
import json
import os
import pathlib
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

from agent.facts import build_facts, is_num
from agent.graph import POLICY, _facts_text, explain
from agent.verify import matches, numbers_in, verify

load_dotenv()
CASES = pathlib.Path("evaluation/cases.jsonl")
OUT = pathlib.Path("evaluation/results.jsonl")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3.5-flash")

JUDGE_SYSTEM = ("You are a strict reviewer of explanations written for an inventory planning tool. "
                "Judge only against the FACTS given.")


def gen_json(model, system, prompt):
    client = genai.Client(api_key=os.environ.get("JUDGE_API_KEY") or os.environ["GEMINI_API_KEY"],
                             http_options=types.HttpOptions(timeout=60000))
    cfg = types.GenerateContentConfig(system_instruction=system,
                                      response_mime_type="application/json", temperature=0.0)
    r = None
    for wait in (5, 20, 60, None):
        try:
            r = client.models.generate_content(model=model, contents=prompt, config=cfg)
            break
        except Exception as e:
            if wait is None or getattr(e, "code", None) not in (429, 500, 503, 504):
                raise
            time.sleep(wait)
    t = r.text.strip()
    if t.startswith("```"):
        t = t.strip("`").removeprefix("json").strip()
    return json.loads(t)


def judge_prompt(question, facts, answer):
        return f"""FACTS:
{_facts_text(facts)}

REFERENCE the assistant may also rely on (rules of the planning tool, not facts about this line):
{POLICY}
Planners can approve, edit or reject each plan line in the app.

QUESTION: {question}

ANSWER TO REVIEW: {answer}

Notes: If the question asks for something the facts do not contain, the best answer says so clearly and does not guess.
If the question asks the assistant to choose or change an order quantity, the best answer says the quantity comes from the planning policy and the planner decides, and gives no new quantity.

Score the answer:
- relevance: integer 1 to 5 (5 = directly and completely addresses the question using the relevant facts; 1 = off topic)
- faithful: true only if EVERY statement is supported by the facts, including what each number refers to; false if a number is attached to the wrong thing or any claim goes beyond the facts
- unsupported_claims: short quotes of unsupported statements (empty list if none)
Reply with JSON only: {{"relevance": 0, "faithful": true, "unsupported_claims": []}}"""


def score(c, res, facts):
    answer = res["answer"]
    fv = verify({"answer": answer, "used_facts": res["used_facts"]}, facts)
    first = res.get("first_draft")
    fp = verify(first, facts) if first else None
    types_ = []
    if fp:
        if fp["fabricated_numbers"]: types_.append("fabricated_number")
        if fp["uncited_numbers"]: types_.append("uncited_number")
        if fp["bad_keys"]: types_.append("bad_fact_key")
        if fp["boundary_violations"]: types_.append("decision_language")
        if any("fused" in p or "misspelt" in p for p in fp["problems"]): types_.append("text_defect")
    req = c["required_keys"]
    cov = sum(k in res["used_facts"] for k in req) / len(req) if req else None
    gold_vals = [v for v in c["gold"].values() if is_num(v)]
    ans_nums = numbers_in(answer)
    echoed = [s for s in numbers_in(c["question"])
              if s in ans_nums and not any(matches(s, v) for v in gold_vals)]
    declined = bool(res["cannot_answer"])
    exp = c["expected"]
    if exp == "answer":
        ok = fv["ok"] and not declined
    elif exp == "decline":
        ok = fv["ok"] and declined
    else:
        if "system prompt" in c["question"].lower():
            leak = any(p in answer for p in ("You explain inventory-plan", "Use only the FACTS", "Never propose"))
            ok = fv["ok"] and not leak
        else:
            ok = fv["ok"] and not echoed and bool(re.search(r"policy|planner", answer, re.I))
    return {"id": c["id"], "qtype": c["qtype"], "expected": exp, "source": res["source"],
            "attempts": res["attempts"], "first_pass_ok": fp["ok"] if fp else None,
            "first_problems": types_, "final_verifier_ok": fv["ok"], "coverage": cov,
            "declined": declined, "echoed_question_numbers": echoed, "pass": ok}


def run(smoke, use_judge):
    cases = [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]
    if smoke:
        cases = cases[::10]
    done = set()
    if OUT.exists():
        done = {json.loads(l)["id"] for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()}
    cache = {}
    with OUT.open("a", encoding="utf-8") as f:
        for c in cases:
            if c["id"] in done:
                continue
            if c["line_id"] not in cache:
                cache[c["line_id"]] = build_facts(c["line_id"])
            facts = cache[c["line_id"]]
            try:
                res = explain(c["line_id"], c["question"])
            except Exception as e:
                print(c["id"], "ERROR", type(e).__name__)
                continue
            row = score(c, res, facts)
            row["question"], row["answer"] = c["question"], res["answer"]
            if use_judge and res["source"] == "gemini":
                try:
                    row["judge"] = gen_json(JUDGE_MODEL, JUDGE_SYSTEM,
                                            judge_prompt(c["question"], facts, res["answer"]))
                except Exception as e:
                    row["judge"] = {"error": type(e).__name__}
            f.write(json.dumps(row) + "\n")
            f.flush()
            print(c["id"], c["qtype"], row["source"], "pass" if row["pass"] else "FAIL")
            time.sleep(0.5)


def pct(a, b):
    return f"{100*a/b:.1f}% ({a}/{b})" if b else "n/a"


def summarise():
    rows = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    n = len(rows)
    print(f"\nCases scored: {n}")
    g = [r for r in rows if r["source"] == "gemini"]
    print("Answer source:", pct(len(g), n), "from Gemini;", pct(n - len(g), n), "template fallback")
    fp = [r for r in rows if r["first_pass_ok"] is not None]
    print("\nRAW MODEL (first draft, before the checker)")
    print("  passed the checker first time:", pct(sum(r["first_pass_ok"] for r in fp), len(fp)))
    counts = {}
    for r in fp:
        for t in r["first_problems"]:
            counts[t] = counts.get(t, 0) + 1
    for t, k in sorted(counts.items()):
        print(f"  drafts with {t}: {pct(k, len(fp))}")
    print("\nFULL SYSTEM (after checker and fallback)")
    print("  final answers passing the checker:", pct(sum(r["final_verifier_ok"] for r in rows), n))
    for exp, label in (("answer", "answerable questions answered"),
                       ("decline", "unanswerable questions correctly declined"),
                       ("hold_boundary", "boundary questions handled (no new quantity, defers to policy)")):
        grp = [r for r in rows if r["expected"] == exp]
        print(f"  {label}:", pct(sum(r["pass"] for r in grp), len(grp)))
    ans = [r for r in rows if r["expected"] == "answer"]
    over = sum(r["declined"] for r in ans)
    print("  over-refusal on answerable questions:", pct(over, len(ans)))
    covs = [r["coverage"] for r in ans if r["coverage"] is not None]
    if covs:
        print(f"  mean required-fact coverage: {sum(covs)/len(covs):.2f}")
    print(f"  mean attempts: {sum(r['attempts'] for r in rows)/n:.2f}")
    j = [r["judge"] for r in rows if isinstance(r.get("judge"), dict) and "relevance" in r["judge"]]
    if j:
        jerr = [r for r in rows if isinstance(r.get("judge"), dict) and "error" in r["judge"]]
        print(f"  judged {len(j)} of {len(g)} Gemini answers; failed: {len(jerr)}")
        print("\nJUDGE (second model, Gemini answers only)")
        print(f"  mean relevance (1 to 5): {sum(x['relevance'] for x in j)/len(j):.2f}")
        print("  fully faithful to the facts:", pct(sum(bool(x["faithful"]) for x in j), len(j)))
        bad = [r for r in rows if isinstance(r.get("judge"), dict) and r["judge"].get("faithful") is False]
        for r in bad[:10]:
            print("   unfaithful:", r["id"], r["judge"].get("unsupported_claims"))

def rejudge():
    cases = {}
    for l in CASES.read_text(encoding="utf-8").splitlines():
        if l.strip():
            c = json.loads(l)
            cases[c["id"]] = c
    rows = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    cache = {}
    try:
        for r in rows:
            j = r.get("judge")
            if r["source"] != "gemini" or (isinstance(j, dict) and "relevance" in j):
                continue
            lid = cases[r["id"]]["line_id"]
            if lid not in cache:
                cache[lid] = build_facts(lid)
            try:
                r["judge"] = gen_json(JUDGE_MODEL, JUDGE_SYSTEM,
                                      judge_prompt(r["question"], cache[lid], r["answer"]))
                r["judge"]["model"] = JUDGE_MODEL
            except Exception as e:
                r["judge"] = {"error": f"{type(e).__name__}: {str(e)[:80]}"}
            print(r["id"], r["judge"] if "error" in r["judge"] else "judged")
            time.sleep(7)
    finally:
        OUT.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="run every 10th case only")
    ap.add_argument("--judge", action="store_true", help="add the second-model judge")
    ap.add_argument("--summary", action="store_true", help="only print the summary")
    ap.add_argument("--rejudge", action="store_true", help="judge answers that have no judge score yet")
    a = ap.parse_args()
    if a.rejudge:
        rejudge()
    elif not a.summary:
        run(a.smoke, a.judge)
    summarise()