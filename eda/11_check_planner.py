import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))   # so "planner" can be imported

import pandas as pd
from planner.data import load_inputs
from planner.simulate import run

ref = pd.read_csv("results/sim_steady.csv")
inp = load_inputs()
cases = [("B k=0.5", 0.5, True), ("B k=1.0", 1.0, True), ("B k=1.0, no pooling", 1.0, False)]
all_ok = True
print(f"{'L':>2} {'policy':22s} {'fill new/old':>16s} {'waste% new/old':>16s} {'cost new/old':>22s}  match")
for L in (3, 4, 5, 7):
    for name, k, pool in cases:
        r = run(inp, L, k, pool=pool)
        e = ref[(ref.L == L) & (ref.policy == name)].iloc[0]
        ok = abs(r["fill"] - e.fill) < 0.01 and abs(r["waste_pct"] - e.waste_pct) < 0.01 \
             and abs(r["cost"] - e.cost) / e.cost < 1e-4 and abs(r["err"]) < 1e-6
        all_ok &= ok
        print(f"{L:>2} {name:22s} {r['fill']:7.2f}/{e.fill:7.2f} {r['waste_pct']:7.2f}/{e.waste_pct:7.2f} "
              f"{r['cost']:10.1f}/{e.cost:10.1f}  {'OK' if ok else 'DIFFERENT'}")
print("\nALL MATCH - the planner reproduces the tested simulation" if all_ok else "\nMISMATCH - do not continue, send me this output")