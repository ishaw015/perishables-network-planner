import numpy as np, pandas as pd

UNIT = 10
H_STORE, H_WH = 0.03, 0.02
WASTE_COST, LOST_MARGIN, TRANSFER_COST = 1.0, 0.5, 0.1
WARM, H = 7, 14                     # 7 warm-up days (not measured) + 7 measured days

dm = pd.read_parquet("data/processed/demand_eval.parquet")
fc = pd.read_parquet("data/processed/forecasts_eval.parquet")
sids = np.array(sorted(dm.sid.unique())); n = len(sids)

def mat(df, col, scale=1.0):
    return df.pivot(index="sid", columns="h", values=col).reindex(sids).values * scale

twice = lambda a: np.hstack([a, a])                  # the same week repeated
D = twice(mat(dm, "units"))
F50 = twice(mat(fc, "p_stockout_aware", UNIT)); F90 = twice(mat(fc, "p90_calibrated", UNIT))
MA7 = mat(fc, "p_baseline", UNIT)[:, 0]
GAP = np.maximum(F90 - F50, 0)
DM = D[:, WARM:].sum()
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

def simulate(policy, kappa, L, buf=1.25, transfers=False, pool=True):
    R = L + 1
    S = np.zeros((n, R)); W = np.zeros((m, R))
    S[:, L-1] = np.ceil(2 * MA7)
    W[:, L-1] = bc(np.ceil(3 * MA7))
    arr_s, arr_w = {}, {}
    T = dict(sales=0., lost=0., waste_s=0., waste_w=0., hold=0., recv_w=0., moved=0., daily=[])
    init = None
    for t in range(H):
        if t == WARM:
            init = S.sum() + W.sum() + sum(a.sum() for a in arr_s.values())
        meas = t >= WARM
        if t in arr_s: S += arr_s.pop(t)
        if t in arr_w:
            a = arr_w.pop(t); W += a
            if meas: T["recv_w"] += a.sum()
        d0, d1 = min(t, H-1), min(t + 1, H-1)
        if policy == "A":
            tgt = np.ceil(buf * 2 * MA7)
        else:
            tgt = np.ceil(F50[:, d0] + F50[:, d1] + kappa * (GAP[:, d0] + GAP[:, d1]))
        pend = sum(a.sum(1) for a in arr_s.values()) if arr_s else 0
        order = np.maximum(0, tgt - S.sum(1) - pend)

        trans_in = np.zeros((n, R))
        if transfers:
            Fcum = np.cumsum(np.stack([F50[:, min(t + i, H-1)] for i in range(L)], axis=1), axis=1)
            cum = np.cumsum(S[:, 1:], axis=1)
            at_risk = np.maximum(0, cum - Fcum).max(1)
            shippable = S[:, 2:].sum(1)
            donor = np.where(order == 0, np.minimum(at_risk, shippable), 0.0)
            want = np.minimum(order, np.ceil(F50[:, d1]))
            bd, bw = bc(donor), bc(want)
            q = np.minimum(bd, bw)
            out = donor * np.where(bd > 0, q / np.maximum(bd, 1e-9), 0.0)[wh_of]
            taken = fefo(S, out, rmin=2)
            poolb = np.stack([bc(taken[:, r]) for r in range(R)], axis=1)
            rshare = want * np.where(bw > 0, 1.0 / np.maximum(bw, 1e-9), 0.0)[wh_of]
            recv = poolb[wh_of] * rshare[:, None]
            trans_in[:, 1:-1] = recv[:, 2:]
            order = order - want * np.where(bw > 0, q / np.maximum(bw, 1e-9), 0.0)[wh_of]
            if meas: T["moved"] += taken.sum()

        req = bc(order)
        avail = W[:, 2:].sum(1)
        ratio = np.where(req > 0, np.minimum(1.0, avail / np.maximum(req, 1e-9)), 0.0)
        take = fefo(W, req * ratio, rmin=2)
        share = np.where(req[wh_of] > 0, order / np.maximum(req[wh_of], 1e-9), 0.0)
        ship = take[wh_of] * share[:, None]
        nxt = np.zeros((n, R)); nxt[:, 1:-1] = ship[:, 2:]
        arr_s[t + 1] = nxt + trans_in

        pend_w = sum(a.sum(1) for a in arr_w.values()) if arr_w else 0
        days = [min(t + 1 + i, H-1) for i in range(3)]
        if policy == "A":
            tw = np.ceil(buf * 3 * bc(MA7))
        else:
            mean = sum(bc(F50[:, d]) for d in days)
            g = sum(GAP[:, d] for d in days)
            safety = np.sqrt(bc(g ** 2)) if pool else bc(g)       # pooled vs not pooled
            tw = np.ceil(mean + kappa * safety)
        a = np.zeros((m, R)); a[:, L] = np.maximum(0, tw - W.sum(1) - pend_w)
        arr_w[t + 2] = a

        taken = fefo(S, D[:, t], rmin=1)
        if meas:
            T["sales"] += taken.sum(); T["lost"] += D[:, t].sum() - taken.sum()
            T["waste_s"] += S[:, 1].sum(); T["waste_w"] += W[:, 1].sum()
            T["daily"].append((S[:, 1].sum(), W[:, 1].sum()))
            T["hold"] += (S.sum() - S[:, 1].sum()) * H_STORE + (W.sum() - W[:, 1].sum()) * H_WH
        S2 = np.zeros_like(S); S2[:, 1:-1] = S[:, 2:]; S = S2
        W2 = np.zeros_like(W); W2[:, 1:-1] = W[:, 2:]; W = W2
    end = S.sum() + W.sum() + sum(a.sum() for a in arr_s.values())
    err = init + T["recv_w"] - T["sales"] - T["waste_s"] - T["waste_w"] - end
    waste = T["waste_s"] + T["waste_w"]
    return dict(daily=T["daily"], fill=100 * T["sales"] / DM, waste=waste, waste_pct=100 * waste / DM,
                moved=T["moved"], end_stock=end, err=err,
                cost=waste * WASTE_COST + T["lost"] * LOST_MARGIN + T["hold"] + T["moved"] * TRANSFER_COST)

rows = []
for L in (3, 4, 5, 7):
    for b in (1.25, 1.5, 1.75):
        r = simulate("A", 0, L, buf=b); r.update(L=L, policy=f"A buffer {b}"); rows.append(r)
    for k in (0.5, 1.0):
        r = simulate("B", k, L); r.update(L=L, policy=f"B k={k}"); rows.append(r)
        r = simulate("B", k, L, transfers=True); r.update(L=L, policy=f"B k={k} + transfers"); rows.append(r)
    r = simulate("B", 1.0, L, pool=False); r.update(L=L, policy="B k=1.0, no pooling"); rows.append(r)
res = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(res[["L", "policy", "fill", "waste_pct", "moved", "end_stock", "cost"]].round(1).to_string(index=False))
print("\nmax conservation error:", res.err.abs().max())
res.drop(columns="daily").to_csv("results/sim_steady.csv", index=False)

print("\n== waste per measured day (stores | warehouses)")
for L, pol, k, buf in [(5, "B", 1.0, 1.25), (5, "A", 0, 1.5), (4, "B", 1.0, 1.25)]:
    ds = np.array(simulate(pol, k, L, buf=buf)["daily"])
    print(f"L={L} {pol}: stores {ds[:,0].round(0).astype(int).tolist()} | warehouses {ds[:,1].round(0).astype(int).tolist()}")
    
print("\n== does the LightGBM forecast matter? same ordering and pooling, moving-average forecast instead")
F50_real, GAP_real = F50, GAP
MA = np.repeat(MA7[:, None], H, axis=1)
rows2 = []
for c in (0.2, 0.35, 0.5, 0.75):
    F50, GAP = MA, c * MA
    for L in (4, 5, 7):
        r = simulate("B", 1.0, L); r.update(L=L, policy=f"B-ordering, MA forecast, buffer c={c}"); rows2.append(r)
F50, GAP = F50_real, GAP_real
for L in (4, 5, 7):
    for k in (0.5, 1.0):
        r = simulate("B", k, L); r.update(L=L, policy=f"B-ordering, LightGBM forecast, k={k}"); rows2.append(r)
res2 = pd.DataFrame(rows2).sort_values(["L", "policy"])
print(res2[["L", "policy", "fill", "waste_pct", "end_stock", "cost"]].round(1).to_string(index=False))