import pandas as pd, numpy as np
from datasets import load_dataset

UNIT = 10                                   # sale_amount x 10 -> units for the simulation
fc = pd.read_parquet("data/processed/forecasts_eval.parquet")
keys = pd.read_parquet("data/processed/eval_subset.parquet")[["store_id", "product_id"]].drop_duplicates()

ev = load_dataset("sky5268/FreshRetailNet-50K")["eval"].to_pandas()
ev = ev.merge(keys, on=["store_id", "product_id"])
ev["dt"] = pd.to_datetime(ev["dt"])
ev["sid"] = ev.store_id.astype(str) + "_" + ev.product_id.astype(str)
ev["h"] = (ev.dt - pd.Timestamp("2024-06-25")).dt.days
ev = ev.merge(fc[["sid", "h", "p_stockout_aware", "p90_calibrated"]], on=["sid", "h"], how="left")
assert len(ev) == 31703 and ev.p_stockout_aware.notna().all(), (len(ev),)

HS = np.array(ev.hours_sale.tolist(), dtype=float)          # (rows, 24)
ST = np.array(ev.hours_stock_status.tolist(), dtype=int)    # 1 = out of stock
sales = ev.sale_amount.values
cnt = ev.stock_hour6_22_cnt.values
fcst = ev.p_stockout_aware.values
print("max |sum of hourly sales - daily sales|:", np.abs(HS.sum(1) - sales).max().round(4))

# typical shape of a day, from days with no stockout in the 6-22 window
clean = (cnt == 0) & (sales > 0)
profile = HS[clean].sum(0) / HS[clean].sum()
print("hourly profile:", profile.round(3))

def reconstruct(HSm, STm, fc_, thresh=0.5):
    obs = HSm.sum(1)
    lost = (profile[6:22] * STm[:, 6:22]).sum(1)             # share of a typical day lost to stockout
    share = 1 - lost
    est = np.where(share >= thresh, obs / np.maximum(share, 1e-9), np.maximum(obs, fc_))
    est = np.minimum(est, np.maximum(4 * fc_, obs))           # cap extreme scale-ups
    est = np.maximum(est, obs)
    return est, np.where(share >= thresh, "hourly", "forecast fill")

# ---- validation: hide sales after a random hour on days with no stockout ----
rng = np.random.default_rng(0)
idx = rng.choice(np.where(clean)[0], size=min(20000, clean.sum()), replace=False)
cut = rng.choice([9, 11, 13, 15, 17, 19], size=len(idx))
mask = np.arange(24)[None, :] >= cut[:, None]
HSc = HS[idx] * (~mask)
STc = mask.astype(int)
true = HS[idx].sum(1)
est_t, meth_t = reconstruct(HSc, STc, fcst[idx])
obs_t = HSc.sum(1)
w = lambda p: np.abs(p - true).sum() / true.sum()
print("\n== reconstruction test (artificial stockouts on clean days)")
print(f"just use observed sales : WAPE {w(obs_t):.3f} | bias {obs_t.sum()/true.sum()-1:+.3f}")
print(f"reconstructed demand    : WAPE {w(est_t):.3f} | bias {est_t.sum()/true.sum()-1:+.3f}")
print("share using forecast fill:", round((meth_t == "forecast fill").mean(), 3))

# ---- reconstruct the real eval week ----
est, method = reconstruct(HS, ST, fcst)
ev["observed"] = sales
ev["demand_est"] = est
ev["method"] = method
ev["so_bucket"] = pd.cut(cnt, [-1, 0, 4, 8, 15, 16], labels=["0", "1-4", "5-8", "9-15", "16"])
print("\n== real eval week: observed vs reconstructed")
g = ev.groupby("so_bucket", observed=True).agg(rows=("observed", "size"), observed=("observed", "sum"),
                                               demand_est=("demand_est", "sum"))
g["uplift_%"] = (g.demand_est / g.observed - 1) * 100
print(g.round(1))
print("overall uplift %:", round((est.sum() / sales.sum() - 1) * 100, 1))
print("method share:\n", ev.method.value_counts(normalize=True).round(3))

ev["units"] = np.rint(ev.demand_est * UNIT).astype(int)
ev["observed_units"] = np.rint(ev.observed * UNIT).astype(int)
out = ev[["sid", "store_id", "product_id", "city_id", "management_group_id", "dt", "h",
          "observed", "stockout_hrs" if "stockout_hrs" in ev else "stock_hour6_22_cnt",
          "demand_est", "method", "units", "observed_units", "p_stockout_aware", "p90_calibrated"]]
out.to_parquet("data/processed/demand_eval.parquet")
print("\nsaved data/processed/demand_eval.parquet", out.shape)
print("units per series per day:", out.units.describe().round(1).to_dict())