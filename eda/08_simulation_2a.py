import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

UNIT = 10
H_STORE, H_WH = 0.03, 0.02
WASTE_COST, LOST_MARGIN = 1.0, 0.5

dm = pd.read_parquet("data/processed/demand_eval.parquet")
fc = pd.read_parquet("data/processed/forecasts_eval.parquet")
sids = np.array(sorted(dm.sid.unique())); n = len(sids)

def mat(df, col, scale=1.0):
    return df.pivot(index="sid", columns="h", values=col).reindex(sids).values * scale

D = mat(dm, "units"); D_obs = mat(dm, "observed_units")
F50 = mat(fc, "p_stockout_aware", UNIT); F90 = mat(fc, "p90_calibrated", UNIT)
MA7 = mat(fc, "p_baseline", UNIT)[:, 0]
GAP = np.maximum(F90 - F50, 0)
meta = dm.drop_duplicates("sid").set_index("sid").loc[sids]
wh_of, uniq = pd.factorize((meta.city_id.astype(str) + "_" + meta.product_id.astype(str)).values)
m = len(uniq)
bc = lambda x: np.bincount(wh_of, weights=x, minlength=m)

def fefo(stock, amt, rmin):
    taken = np.zeros_like(stock); rem = amt.astype(float).copy()
    for r in range(rmin, stock.shape[1]):
        t = np.minimum(stock[:, r], rem)
        taken[:, r] = t; stock[:, r] -= t; rem -= t
    return taken

def simulate(policy, kappa, L, buf=1.25, cap=False, DEM=None):
    DEM = D if DEM is None else DEM
    R = L + 1
    S = np.zeros((n, R)); W = np.zeros((m, R))
    S[:, L-1] = np.ceil(2 * MA7)
    W[:, L-1] = bc(np.ceil(3 * MA7))
    init = S.sum() + W.sum()
    arr_s, arr_w = {}, {}
    T = dict(sales=0., lost=0., waste_s=0., waste_w=0., hold=0., recv_w=0.)
    ncov = min(3, max(1, L - 2)) if cap else 3          # days of demand the warehouse plans for
    for t in range(7):
        if t in arr_s: S += arr_s.pop(t)
        if t in arr_w:
            a = arr_w.pop(t); W += a; T["recv_w"] += a.sum()
        d0, d1 = min(t, 6), min(t + 1, 6)
        if policy == "A":
            tgt = np.ceil(buf * 2 * MA7)
        else:
            tgt = np.ceil(F50[:, d0] + F50[:, d1] + kappa * (GAP[:, d0] + GAP[:, d1]))
        pend = sum(a.sum(1) for a in arr_s.values()) if arr_s else 0
        order = np.maximum(0, tgt - S.sum(1) - pend)
        req = bc(order)
        avail = W[:, 2:].sum(1)
        ratio = np.where(req > 0, np.minimum(1.0, avail / np.maximum(req, 1e-9)), 0.0)
        take = fefo(W, req * ratio, rmin=2)
        share = np.where(req[wh_of] > 0, order / np.maximum(req[wh_of], 1e-9), 0.0)
        ship = take[wh_of] * share[:, None]
        nxt = np.zeros((n, R)); nxt[:, 1:-1] = ship[:, 2:]
        arr_s[t + 1] = nxt
        pend_w = sum(a.sum(1) for a in arr_w.values()) if arr_w else 0
        days = [min(t + 1 + i, 6) for i in range(ncov)]
        if policy == "A":
            tw = np.ceil(buf * ncov * bc(MA7))
        else:
            mean = sum(bc(F50[:, d]) for d in days)
            g = sum(GAP[:, d] for d in days)
            tw = np.ceil(mean + kappa * np.sqrt(bc(g ** 2)))
        a = np.zeros((m, R)); a[:, L] = np.maximum(0, tw - W.sum(1) - pend_w)
        arr_w[t + 2] = a
        taken = fefo(S, DEM[:, t], rmin=1)
        sales = taken.sum()
        T["sales"] += sales; T["lost"] += DEM[:, t].sum() - sales
        T["waste_s"] += S[:, 1].sum(); T["waste_w"] += W[:, 1].sum()
        T["hold"] += (S.sum() - S[:, 1].sum()) * H_STORE + (W.sum() - W[:, 1].sum()) * H_WH
        S2 = np.zeros_like(S); S2[:, 1:-1] = S[:, 2:]; S = S2
        W2 = np.zeros_like(W); W2[:, 1:-1] = W[:, 2:]; W = W2
    end = S.sum() + W.sum() + sum(a.sum() for a in arr_s.values())
    err = init + T["recv_w"] - T["sales"] - T["waste_s"] - T["waste_w"] - end
    waste = T["waste_s"] + T["waste_w"]
    return dict(fill=100 * T["sales"] / DEM.sum(), lost=T["lost"], waste=waste,
                waste_pct=100 * waste / DEM.sum(), end_stock=end,
                cost=waste * WASTE_COST + T["lost"] * LOST_MARGIN + T["hold"], err=err)

rows = []
for L in (3, 5, 7):
    for b in (1.0, 1.25, 1.5, 1.75, 2.0):
        r = simulate("A", 0, L, buf=b); r.update(shelf_life=L, family="A naive (buffer)", param=b); rows.append(r)
    for k in (0, 0.25, 0.5, 0.75, 1.0, 1.25):
        r = simulate("B", k, L); r.update(shelf_life=L, family="B forecast (kappa)", param=k); rows.append(r)
        r = simulate("B", k, L, cap=True); r.update(shelf_life=L, family="B + expiry-aware cover (kappa)", param=k); rows.append(r)
res = pd.DataFrame(rows)
pd.set_option("display.width", 200)
for L in (3, 5, 7):
    print(f"\n===== shelf life {L} days =====")
    print(res[res.shelf_life == L][["family", "param", "fill", "waste_pct", "end_stock", "cost"]].round(1).to_string(index=False))
print("\nmax conservation error:", res.err.abs().max())
res.to_csv("results/sim_stage2a.csv", index=False)

fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
for ax, L in zip(axes, (3, 5, 7)):
    for fam, g in res[res.shelf_life == L].groupby("family"):
        g = g.sort_values("param")
        ax.plot(g.waste_pct, g.fill, marker="o", label=fam)
    ax.set_title(f"Shelf life {L} days"); ax.set_xlabel("waste (% of demand)"); ax.set_ylabel("fill rate (%)")
    ax.grid(alpha=0.3)
axes[0].legend(fontsize=8)
plt.tight_layout(); plt.savefig("results/sim_stage2a_frontier.png", dpi=150)

print("\n== sensitivity to the demand estimate (shelf life 5)")
for nm, DD in [("reconstructed demand", D), ("observed sales only", D_obs)]:
    for lab, kw in [("A buffer 1.25", dict(policy="A", kappa=0, buf=1.25)), ("B kappa 1", dict(policy="B", kappa=1.0))]:
        r = simulate(L=5, DEM=DD, **kw)
        print(f"{nm:22s} {lab:15s} fill {r['fill']:.1f}% | waste {r['waste_pct']:.1f}% | cost {r['cost']:.0f}")