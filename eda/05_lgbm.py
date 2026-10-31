import pandas as pd, numpy as np, lightgbm as lgb

sub = pd.read_parquet("data/processed/subset.parquet")
ev = pd.read_parquet("data/processed/eval_subset.parquet")
df = pd.concat([sub, ev], ignore_index=True)
df["dt"] = pd.to_datetime(df["dt"])
df["sid"] = df.store_id.astype(str) + "_" + df.product_id.astype(str)
df.loc[~df.discount.between(0.01, 1.0), "discount"] = np.nan

def piv(col):
    return df.pivot(index="sid", columns="dt", values=col).sort_index(axis=1)

Yp = piv("sale_amount"); sids = Yp.index; dates = Yp.columns
Yv = Yp.values; C = piv("stock_hour6_22_cnt").values
DISC = piv("discount").values; HOL = piv("holiday_flag").values
ACT = piv("activity_flag").values; TEMP = piv("avg_temperature").values
dow = np.array([d.weekday() for d in dates])
assert Yv.shape == (4529, 97), Yv.shape

scols = ["city_id", "management_group_id", "first_category_id", "product_id"]
static = df.drop_duplicates("sid").set_index("sid").loc[sids, scols]

def build(T, H=range(1, 8)):
    w28, c28 = Yv[:, T-27:T+1], C[:, T-27:T+1]; m28 = c28 <= 8; n28 = m28.sum(1)
    w7, c7 = Yv[:, T-6:T+1], C[:, T-6:T+1]; m7 = c7 <= 8; n7 = m7.sum(1)
    base = dict(
        ma7=w7.mean(1), ma28=w28.mean(1),
        ma7_in=np.where(n7 > 0, (w7*m7).sum(1)/np.maximum(n7, 1), w7.mean(1)),
        ma28_in=np.where(n28 > 0, (w28*m28).sum(1)/np.maximum(n28, 1), w28.mean(1)),
        last=Yv[:, T], so7=c7.mean(1), std14=Yv[:, T-13:T+1].std(1))
    rows = []
    for h in H:
        d = T + h
        f = pd.DataFrame(base)
        f["h"] = h; f["lagw"] = Yv[:, d-7]; f["lagw_so"] = C[:, d-7]
        f["dow"] = dow[d]; f["disc"] = DISC[:, d]; f["hol"] = HOL[:, d]
        f["act"] = ACT[:, d]; f["temp"] = TEMP[:, d]
        for c in scols:
            f[c] = pd.Categorical(static[c].values, categories=sorted(static[c].unique()))
        f["y"] = Yv[:, d]; f["c_t"] = C[:, d]
        rows.append(f)
    return pd.concat(rows, ignore_index=True)

feats = None
tr_v = pd.concat([build(T) for T in range(27, 76)], ignore_index=True)   # targets up to day 82
va = build(82)                                                           # targets 83-89
tr_f = pd.concat([build(T) for T in range(27, 83)], ignore_index=True)  # targets up to day 89
te = build(89)                                                           # real eval week
feats = [c for c in te.columns if c not in ("y", "c_t")]
print("rows:", len(tr_v), len(va), len(tr_f), len(te))

y, ins = te.y.values, (te.c_t == 0).values
def report(name, p):
    w = lambda m: np.abs(y[m] - p[m]).sum() / y[m].sum()
    print(f"{name:45s} WAPE all {w(np.ones(len(y), bool)):.3f} | in-stock {w(ins):.3f} | bias {p.sum()/y.sum()-1:+.3f}")

report("check: 7-day moving average (expect 0.395)", te.ma7.values)

params = dict(objective="tweedie", tweedie_variance_power=1.2, learning_rate=0.05,
              num_leaves=63, min_child_samples=100, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.8, verbose=-1)

def run(name, keep):
    a, v, f = tr_v[keep(tr_v)], va[keep(va)], tr_f[keep(tr_f)]
    m = lgb.LGBMRegressor(**params, n_estimators=1000)
    m.fit(a[feats], a.y, eval_set=[(v[feats], v.y)], callbacks=[lgb.early_stopping(30, verbose=False)])
    best = m.best_iteration_
    m2 = lgb.LGBMRegressor(**params, n_estimators=best).fit(f[feats], f.y)
    report(f"{name} (trees={best})", m2.predict(te[feats]))
    return m2

m_plain = run("LightGBM, plain", lambda d: np.ones(len(d), bool))
m_mask = run("LightGBM, drop days with >=9 stockout hrs", lambda d: (d.c_t < 9).values)

imp = pd.Series(m_plain.booster_.feature_importance("gain"), index=feats).sort_values(ascending=False)
print("\ntop features (gain):\n", (imp / imp.sum()).round(3).head(10))

q = lgb.LGBMRegressor(objective="quantile", alpha=0.9, learning_rate=0.05, num_leaves=63,
                      min_child_samples=100, subsample=0.8, subsample_freq=1,
                      colsample_bytree=0.8, n_estimators=300, verbose=-1).fit(tr_f[feats], tr_f.y)
p90 = q.predict(te[feats])
print(f"\nP90 model: share of actuals <= prediction: all {(y <= p90).mean():.3f} | in-stock {(y[ins] <= p90[ins]).mean():.3f}")

# ---- bootstrap confidence intervals (resample whole series) ----
n = len(sids)
sid_i = np.tile(np.arange(n), 7)            # build() lists all series for h=1, then h=2, ...
P = {"7-day moving avg": te.ma7.values,
     "LightGBM plain": m_plain.predict(te[feats]),
     "LightGBM stockout-aware": m_mask.predict(te[feats])}
ae = {k: np.bincount(sid_i, weights=np.abs(y - p), minlength=n) for k, p in P.items()}
ys = np.bincount(sid_i, weights=y, minlength=n)
rng = np.random.default_rng(0)
boots = [rng.integers(0, n, n) for _ in range(500)]
base = np.array([ae["7-day moving avg"][i].sum() / ys[i].sum() for i in boots])
print("\n== WAPE with 95% bootstrap interval (resampling series)")
for k in P:
    w = np.array([ae[k][i].sum() / ys[i].sum() for i in boots])
    d = w - base
    print(f"{k:26s} {w.mean():.3f} [{np.percentile(w,2.5):.3f}, {np.percentile(w,97.5):.3f}]"
          f" | diff vs baseline {d.mean():+.3f} [{np.percentile(d,2.5):+.3f}, {np.percentile(d,97.5):+.3f}]")

# ---- calibrate P90 using the validation week ----
qp = dict(objective="quantile", alpha=0.9, learning_rate=0.05, num_leaves=63, min_child_samples=100,
          subsample=0.8, subsample_freq=1, colsample_bytree=0.8, n_estimators=300, verbose=-1)
qv = lgb.LGBMRegressor(**qp).fit(tr_v[feats], tr_v.y)
pv = qv.predict(va[feats]); ok = pv > 0
k90 = np.quantile(va.y.values[ok] / pv[ok], 0.9)
p90c = k90 * p90
print(f"\nP90 scale factor k={k90:.3f} | coverage after calibration: all {(y <= p90c).mean():.3f}"
      f" | in-stock {(y[ins] <= p90c[ins]).mean():.3f}")

# ---- save forecasts for the simulation ----
out = pd.DataFrame({"sid": np.array(sids)[sid_i], "h": te.h.values,
                    "date": dates[89 + te.h.values].values, "actual": y,
                    "stockout_hrs": te.c_t.values,
                    "p_baseline": P["7-day moving avg"], "p_plain": P["LightGBM plain"],
                    "p_stockout_aware": P["LightGBM stockout-aware"], "p90_calibrated": p90c})
out.to_parquet("data/processed/forecasts_eval.parquet")
print("saved data/processed/forecasts_eval.parquet", out.shape)