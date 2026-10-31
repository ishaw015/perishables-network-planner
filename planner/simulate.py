import numpy as np
from . import policy

H_STORE, H_WH = 0.03, 0.02
WASTE_COST, LOST_MARGIN = 1.0, 0.5

def fefo(stock, amt, rmin):
    """take the oldest units first; column index = remaining shelf life in days"""
    taken = np.zeros_like(stock); rem = amt.astype(float).copy()
    for r in range(rmin, stock.shape[1]):
        t = np.minimum(stock[:, r], rem)
        taken[:, r] = t; stock[:, r] -= t; rem -= t
    return taken

def run(inp, L, kappa, pool=True, warm=7, snapshot=None, trace=None):
    """7 warm-up days (same week repeated) + 7 measured days. L = shelf life in days."""
    n, m, wh_of = inp.n, inp.m, inp.wh_of
    bc = lambda x: np.bincount(wh_of, weights=x, minlength=m)
    D, F50, F90 = (np.hstack([a, a]) for a in (inp.D, inp.F50, inp.F90))
    H, K, R = D.shape[1], max(4, L), L + 1
    DM = D[:, warm:].sum()

    S = np.zeros((n, R)); W = np.zeros((m, R))
    S[:, L-1] = np.ceil(2 * inp.MA7)
    W[:, L-1] = bc(np.ceil(3 * inp.MA7))
    arr_s, arr_w = {}, {}
    T = dict(sales=0., lost=0., waste=0., hold=0., recv_w=0.)
    init = None
    for t in range(H):
        if t == warm:
            init = S.sum() + W.sum() + sum(a.sum() for a in arr_s.values())
        meas = t >= warm
        if t in arr_s: S += arr_s.pop(t)
        if t in arr_w:
            a = arr_w.pop(t); W += a
            if meas: T["recv_w"] += a.sum()

        idx = [min(t + i, H - 1) for i in range(K)]
        w50, w90 = F50[:, idx], F90[:, idx]

        if snapshot is not None and t == snapshot:        # stop here and hand back the current state
            return dict(t=t, L=L, S=S.copy(), W=W.copy(),
                        pend_s=sum(a.sum(1) for a in arr_s.values()) if arr_s else np.zeros(n),
                        pend_w=sum(a.sum(1) for a in arr_w.values()) if arr_w else np.zeros(m),
                        w50=w50, w90=w90)
        # store orders, filled from the city warehouse, arrive tomorrow
        pend = sum(a.sum(1) for a in arr_s.values()) if arr_s else 0
        order = policy.store_orders(policy.store_targets(w50, w90, kappa), S.sum(1), pend)
        ratio, req = policy.allocation_ratio(order, W[:, 2:].sum(1), wh_of, m)
        take = fefo(W, req * ratio, rmin=2)
        share = np.where(req[wh_of] > 0, order / np.maximum(req[wh_of], 1e-9), 0.0)
        ship = take[wh_of] * share[:, None]
        nxt = np.zeros((n, R)); nxt[:, 1:-1] = ship[:, 2:]      # one day of shelf life used in transit
        arr_s[t + 1] = nxt

        # warehouse orders from the central warehouse, arrive in 2 days, fresh
        pend_w = sum(a.sum(1) for a in arr_w.values()) if arr_w else 0
        tw = policy.warehouse_targets(w50, w90, kappa, wh_of, m, pool)
        a = np.zeros((m, R)); a[:, L] = policy.warehouse_orders(tw, W.sum(1), pend_w)
        arr_w[t + 2] = a
        
        if trace is not None:
          trace[t] = dict(order_s=order.copy(), order_w=a[:, L].copy())
        # customers buy, oldest stock first
        taken = fefo(S, D[:, t], rmin=1)
        if meas:
            T["sales"] += taken.sum(); T["lost"] += D[:, t].sum() - taken.sum()
            T["waste"] += S[:, 1].sum() + W[:, 1].sum()
            T["hold"] += (S.sum() - S[:, 1].sum()) * H_STORE + (W.sum() - W[:, 1].sum()) * H_WH
        S2 = np.zeros_like(S); S2[:, 1:-1] = S[:, 2:]; S = S2
        W2 = np.zeros_like(W); W2[:, 1:-1] = W[:, 2:]; W = W2

    end = S.sum() + W.sum() + sum(a.sum() for a in arr_s.values())
    err = init + T["recv_w"] - T["sales"] - T["waste"] - end
    return dict(fill=100 * T["sales"] / DM, waste_pct=100 * T["waste"] / DM, end_stock=end, err=err,
                cost=T["waste"] * WASTE_COST + T["lost"] * LOST_MARGIN + T["hold"])