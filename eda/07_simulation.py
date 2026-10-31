import numpy as np, pandas as pd

UNIT = 10
H_STORE, H_WH = 0.03, 0.02        # holding cost per unit-day
WASTE_COST, LOST_MARGIN = 1.0, 0.5

dm = pd.read_parquet("data/processed/demand_eval.parquet")
fc = pd.read_parquet("data/processed/forecasts_eval.parquet")
sids = np.array(sorted(dm.sid.unique())); n = len(sids)

def mat(df, col, scale=1.0):
    return df.pivot(index="sid", columns="h", values=col).reindex(sids).values * scale   # (n, 7)

D = mat(dm, "units")
F50 = mat(fc, "p_stockout_aware", UNIT); F90 = mat(fc, "p90_calibrated", UNIT)
MA7 = mat(fc, "p_baseline", UNIT)[:, 0]
GAP = np.maximum(F90 - F50, 0)
meta = dm.drop_duplicates("sid").set_index("sid").loc[sids]
wh_of, uniq = pd.factorize((meta.city_id.astype(str) + "_" + meta.product_id.astype(str)).values)
m = len(uniq)
bc = lambda x: np.bincount(wh_of, weights=x, minlength=m)
print(f"series {n} | warehouse-product pools {m} | total demand units {D.sum():.0f}")

def fefo(stock, amt, rmin):
    """take oldest-expiry units first (index = remaining life in days), modifies stock"""
    taken = np.zeros_like(stock); rem = amt.astype(float).copy()
    for r in range(rmin, stock.shape[1]):
        t = np.minimum(stock[:, r], rem)
        taken[:, r] = t; stock[:, r] -= t; rem -= t
    return taken

def simulate(policy, kappa, L):
    R = L + 1
    S = np.zeros((n, R)); W = np.zeros((m, R))
    S[:, L-1] = np.ceil(2 * MA7)
    W[:, L-1] = bc(np.ceil(3 * MA7))
    init = S.sum() + W.sum()
    arr_s, arr_w = {}, {}
    T = dict(sales=0., lost=0., waste_s=0., waste_w=0., hold=0., recv_w=0.)
    for t in range(7):
        if t in arr_s: S += arr_s.pop(t)
        if t in arr_w:
            a = arr_w.pop(t); W += a; T["recv_w"] += a.sum()
        d0, d1 = min(t, 6), min(t + 1, 6)
        # ---- store ordering (arrives next day) ----
        if policy == "A":
            tgt = np.ceil(1.25 * 2 * MA7)
        else:
            tgt = np.ceil(F50[:, d0] + F50[:, d1] + kappa * (GAP[:, d0] + GAP[:, d1]))
        pend = sum(a.sum(1) for a in arr_s.values()) if arr_s else 0
        order = np.maximum(0, tgt - S.sum(1) - pend)
        req = bc(order)
        avail = W[:, 2:].sum(1)                                  # units that can still be sold after 1 day in transit
        ratio = np.where(req > 0, np.minimum(1.0, avail / np.maximum(req, 1e-9)), 0.0)
        take = fefo(W, req * ratio, rmin=2)
        share = np.where(req[wh_of] > 0, order / np.maximum(req[wh_of], 1e-9), 0.0)
        ship = take[wh_of] * share[:, None]
        nxt = np.zeros((n, R)); nxt[:, 1:-1] = ship[:, 2:]       # one day of life used in transit
        arr_s[t + 1] = nxt
        # ---- warehouse ordering from central (arrives in 2 days, fresh) ----
        pend_w = sum(a.sum(1) for a in arr_w.values()) if arr_w else 0
        days = [min(t + 1, 6), min(t + 2, 6), min(t + 3, 6)]
        if policy == "A":
            tw = np.ceil(1.25 * 3 * bc(MA7))
        else:
            mean = sum(bc(F50[:, d]) for d in days)
            g = sum(GAP[:, d] for d in days)
            tw = np.ceil(mean + kappa * np.sqrt(bc(g ** 2)))     # pooled safety stock
        a = np.zeros((m, R)); a[:, L] = np.maximum(0, tw - W.sum(1) - pend_w)
        arr_w[t + 2] = a
        # ---- demand ----
        taken = fefo(S, D[:, t], rmin=1)
        sales = taken.sum()
        T["sales"] += sales; T["lost"] += D[:, t].sum() - sales
        # ---- end of day: expiry, holding, ageing ----
        T["waste_s"] += S[:, 1].sum(); T["waste_w"] += W[:, 1].sum()
        T["hold"] += (S.sum() - S[:, 1].sum()) * H_STORE + (W.sum() - W[:, 1].sum()) * H_WH
        S2 = np.zeros_like(S); S2[:, 1:-1] = S[:, 2:]; S = S2
        W2 = np.zeros_like(W); W2[:, 1:-1] = W[:, 2:]; W = W2
    end = S.sum() + W.sum() + sum(a.sum() for a in arr_s.values())
    err = init + T["recv_w"] - T["sales"] - T["waste_s"] - T["waste_w"] - end
    waste = T["waste_s"] + T["waste_w"]
    return dict(fill=100 * T["sales"] / D.sum(), lost=T["lost"], waste=waste,
                waste_pct=100 * waste / D.sum(), end_stock=end,
                cost=waste * WASTE_COST + T["lost"] * LOST_MARGIN + T["hold"], err=err)

policies = [("A naive: store 7-day avg +25%", "A", 0), ("B forecast, median (k=0)", "B", 0.0),
            ("B forecast, k=0.5", "B", 0.5), ("B forecast, P90 (k=1)", "B", 1.0)]
rows = []
for L in (3, 5, 7):
    for name, pol, k in policies:
        r = simulate(pol, k, L); r.update(shelf_life=L, policy=name); rows.append(r)
res = pd.DataFrame(rows)[["shelf_life", "policy", "fill", "lost", "waste", "waste_pct", "end_stock", "cost", "err"]]
pd.set_option("display.width", 200)
print(res.round(1).to_string(index=False))
print("\nmax conservation error (should be ~0):", res.err.abs().max())
res.to_csv("results/sim_stage1.csv", index=False)