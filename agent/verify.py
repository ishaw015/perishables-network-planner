import re
from agent.facts import is_num
from spellchecker import SpellChecker

    
NUM = re.compile(r"(?<![A-Z0-9_.])-?\d[\d,]*(?:\.\d+)?")
FUSED = re.compile(r"[a-z]\d|\d[A-Za-z]")   # "has2066", "38.76units"
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SPELL = SpellChecker()
WORD = re.compile(r"[A-Za-z]{6,}")
DOMAIN = {"kappa", "fefo", "rata", "stockout", "stockouts", "shippable", "median", "warehouse", "warehouses"}

# wording that means the model is deciding a quantity
BOUNDARY = [
    r"\byou should (order|increase|decrease|reduce|raise|cut|set)",
    r"\bI (recommend|suggest|advise) (ordering|increasing|decreasing|reducing|raising|cutting|setting|that you)",
    r"\b(order|ordering) [\d,.]+ (units )?instead",
    r"\bbetter to (order|increase|decrease|reduce)",
    r"\bshould (be )?(increased|reduced|raised|lowered|changed|set) to",
    r"\bI (would|will) order\b",
]
def unknown_words(text, facts):
    """Long words not in an English dictionary (e.g. 'unitsto'). Words from the facts are allowed."""
    allowed = set(DOMAIN)
    for k, v in facts.items():
        allowed.update(w.lower() for w in re.findall(r"[A-Za-z]+", k + " " + v["label"]))
    return [w for w in WORD.findall(text)
            if w.lower() not in allowed and w.lower() not in _SPELL]
    
def numbers_in(text: str):
    text = DATE.sub(" ", text)
    return [m.group().rstrip(",") for m in NUM.finditer(text)]


def matches(claimed: str, value: float) -> bool:
    """True if `claimed` is a correct rounding of `value` at its own precision."""
    c = claimed.replace(",", "")
    d = len(c.split(".")[1]) if "." in c else 0
    return abs(float(c) - float(value)) <= 0.5 * 10 ** (-d) + 1e-9


def verify(draft, facts: dict) -> dict:
    problems, bad_keys, uncited, fabricated, boundary = [], [], [], [], []
    if not isinstance(draft, dict) or not str(draft.get("answer", "")).strip():
        return {"ok": False, "problems": ["empty or malformed answer"], "bad_keys": [],
                "uncited_numbers": [], "fabricated_numbers": [], "boundary_violations": [],
                "numbers_checked": 0}
    answer = draft["answer"]
    keys = list(draft.get("used_facts") or [])

    bad_keys = [k for k in keys if k not in facts]
    if bad_keys:
        problems.append(f"cited facts that do not exist: {bad_keys}")

    cited_vals = [facts[k]["value"] for k in keys if k in facts and is_num(facts[k]["value"])]
    all_vals = [v["value"] for v in facts.values() if is_num(v["value"])]
    nums = numbers_in(answer)
    for s in nums:
        if any(matches(s, v) for v in cited_vals):
            continue
        if any(matches(s, v) for v in all_vals):
            uncited.append(s)          # real number, but its fact was not cited
        else:
            fabricated.append(s)       # matches nothing in the facts
    if fabricated:
        problems.append(f"numbers not found in the facts: {fabricated}")
    if uncited:
        problems.append(f"numbers whose fact key was not listed in used_facts: {uncited}")

    plan_date = facts.get("plan.plan_date", {}).get("value")
    for d in DATE.findall(answer):
        if d != plan_date:
            fabricated.append(d)
            problems.append(f"date {d} does not match the plan date")

    boundary = [p for p in BOUNDARY if re.search(p, answer, re.I)]
    if boundary:
        problems.append("answer tells the planner what quantity to order")
        
    if FUSED.search(DATE.sub(" ", answer)):
        problems.append("text has words fused to numbers (missing spaces); rewrite with normal spacing")
    odd = unknown_words(DATE.sub(" ", answer), facts)
    if odd:
        problems.append(f"possible missing spaces or misspelt words: {odd}")
    return {"ok": not problems, "problems": problems, "bad_keys": bad_keys,
            "uncited_numbers": uncited, "fabricated_numbers": fabricated,
            "boundary_violations": boundary, "numbers_checked": len(nums)}