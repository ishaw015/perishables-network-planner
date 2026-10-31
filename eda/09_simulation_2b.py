import numpy as np, pandas as pd

UNIT = 10
H_STORE, H_WH = 0.03, 0.02
WASTE_COST, LOST_MARGIN, TRANSFER_COST = 1.0, 0.5, 0.1

dm = pd.read_parquet("data/processed/demand_eval.parquet")
fc = pd.read_parquet("data/processed/forecasts_eval.parquet")
sids = np.array(sorted(dm.sid.unique())); n = len(sids)

def mat(df, col, scale=1.0):
    return df.pivot(index="sid", columns="h", values=col).reindex(sids).values * scale

D = mat(dm, "units")
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

def simulate(policy, kappa, L, buf=1.25, transfers=False):
    R = L + 1
    S = np.zeros((n, R)); W = np.zeros((m, R))
    S[:, L-1] = np.ceil(2 * MA7)
    W[:, L-1] = bc(np.ceil(3 * MA7))
    init = S.sum() + W.sum()
    arr_s, arr_w = {}, {}
    T = dict(sales=0., lost=0., waste_s=0., waste_w=0., hold=0., recv_w=0., moved=0., short=0., daily=[])
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

        trans_in = np.zeros((n, R))
        if transfers:
            Fcum = np.cumsum(np.stack([F50[:, min(t + i, 6)] for i in range(L)], axis=1), axis=1)
            cum = np.cumsum(S[:, 1:], axis=1)                 # stock that must sell within r days (oldest first)
            at_risk = np.maximum(0, cum - Fcum).max(1)         # units expected to expire unsold
            shippable = S[:, 2:].sum(1)
            donor = np.where(order == 0, np.minimum(at_risk, shippable), 0.0)
            want = np.minimum(order, np.ceil(F50[:, d1]))
            bd, bw = bc(donor), bc(want)
            q = np.minimum(bd, bw)
            out = donor * np.where(bd > 0, q / np.maximum(bd, 1e-9), 0.0)[wh_of]
            taken = fefo(S, out, rmin=2)
            pool = np.stack([bc(taken[:, r]) for r in range(R)], axis=1)
            rshare = want * np.where(bw > 0, 1.0 / np.maximum(bw, 1e-9), 0.0)[wh_of]
            recv = pool[wh_of] * rshare[:, None]
            trans_in[:, 1:-1] = recv[:, 2:]
            order = order - want * np.where(bw > 0, q / np.maximum(bw, 1e-9), 0.0)[wh_of]
            T["moved"] += taken.sum()

        req = bc(order)
        avail = W[:, 2:].sum(1)
        ratio = np.where(req > 0, np.minimum(1.0, avail / np.maximum(req, 1e-9)), 0.0)
        take = fefo(W, req * ratio, rmin=2)
        share = np.where(req[wh_of] > 0, order / np.maximum(req[wh_of], 1e-9), 0.0)
        ship = take[wh_of] * share[:, None]
        T["short"] += order.sum() - ship.sum()
        nxt = np.zeros((n, R)); nxt[:, 1:-1] = ship[:, 2:]
        arr_s[t + 1] = nxt + trans_in

        pend_w = sum(a.sum(1) for a in arr_w.values()) if arr_w else 0
        days = [min(t + 1 + i, 6) for i in range(3)]
        if policy == "A":
            tw = np.ceil(buf * 3 * bc(MA7))
        else:
            mean = sum(bc(F50[:, d]) for d in days)
            g = sum(GAP[:, d] for d in days)
            tw = np.ceil(mean + kappa * np.sqrt(bc(g ** 2)))
        a = np.zeros((m, R)); a[:, L] = np.maximum(0, tw - W.sum(1) - pend_w)
        arr_w[t + 2] = a

        taken = fefo(S, D[:, t], rmin=1)
        sales = taken.sum()
        T["sales"] += sales; T["lost"] += D[:, t].sum() - sales
        T["waste_s"] += S[:, 1].sum(); T["waste_w"] += W[:, 1].sum()
        T["daily"].append((S[:, 1].sum(), W[:, 1].sum()))
        T["hold"] += (S.sum() - S[:, 1].sum()) * H_STORE + (W.sum() - W[:, 1].sum()) * H_WH
        S2 = np.zeros_like(S); S2[:, 1:-1] = S[:, 2:]; S = S2
        W2 = np.zeros_like(W); W2[:, 1:-1] = W[:, 2:]; W = W2
    end = S.sum() + W.sum() + sum(a.sum() for a in arr_s.values())
    err = init + T["recv_w"] - T["sales"] - T["waste_s"] - T["waste_w"] - end
    waste = T["waste_s"] + T["waste_w"]
    return dict(daily=T["daily"], short=T["short"], fill=100 * T["sales"] / D.sum(), waste=waste, waste_pct=100 * waste / D.sum(),
                moved=T["moved"], end_stock=end, err=err,
                cost=waste * WASTE_COST + T["lost"] * LOST_MARGIN + T["hold"] + T["moved"] * TRANSFER_COST)

rows = []
for L in (3, 4, 5, 7):
    for k in (0.5, 1.0):
        for tr in (False, True):
            r = simulate("B", k, L, transfers=tr)
            r.update(shelf_life=L, kappa=k, policy="B + transfers" if tr else "B ordering only")
            rows.append(r)
    r = simulate("A", 0, L, buf=1.5); r.update(shelf_life=L, kappa=np.nan, policy="A naive (buffer 1.5)"); rows.append(r)
res = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(res[["shelf_life", "policy", "kappa", "fill", "waste_pct", "moved", "end_stock", "cost"]].round(1).to_string(index=False))
print("\nmax conservation error:", res.err.abs().max())
res.to_csv("results/sim_stage2b.csv", index=False)

print("\n== where does waste happen? units wasted per day (day 1..7)")
for L, pol, k, buf in [(5, "B", 1.0, 1.25), (5, "A", 0, 1.5), (4, "B", 1.0, 1.25)]:
    r = simulate(pol, k, L, buf=buf)
    ds = np.array(r["daily"])
    lost = (1 - r["fill"] / 100) * D.sum()
    print(f"L={L} {pol}: stores {ds[:,0].round(0).astype(int).tolist()} | warehouses {ds[:,1].round(0).astype(int).tolist()}")
    print(f"      lost sales {lost:.0f} units | warehouse could not supply stores' orders: {r['short']:.0f} units")