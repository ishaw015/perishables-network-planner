import pandas as pd, numpy as np
from datasets import load_dataset

sub = pd.read_parquet("data/processed/subset.parquet")
sub["dt"] = pd.to_datetime(sub["dt"])
ev = load_dataset("sky5268/FreshRetailNet-50K")["eval"].to_pandas()
ev["dt"] = pd.to_datetime(ev["dt"])
keys = sub[["store_id", "product_id"]].drop_duplicates()
ev = ev.merge(keys, on=["store_id", "product_id"])
ev.drop(columns=["hours_sale", "hours_stock_status"]).to_parquet("data/processed/eval_subset.parquet")
print("eval rows:", len(ev), "| series:", ev.groupby(["store_id", "product_id"]).ngroups,
      "|", ev.dt.min().date(), "->", ev.dt.max().date())

for d in (sub, ev):
    d["sid"] = d.store_id.astype(str) + "_" + d.product_id.astype(str)
ev["dow"] = ev.dt.dt.dayofweek

wide = sub.pivot(index="sid", columns="dt", values="sale_amount").sort_index(axis=1)
cnt = sub.pivot(index="sid", columns="dt", values="stock_hour6_22_cnt").sort_index(axis=1)

ma7 = wide.iloc[:, -7:].mean(axis=1)
ma28 = wide.iloc[:, -28:].mean(axis=1)
w28, c28 = wide.iloc[:, -28:], cnt.iloc[:, -28:]
ma28_in = w28.where(c28 <= 8).mean(axis=1).fillna(ma28)          # ignore badly stocked-out days

last7 = wide.iloc[:, -7:].copy()
last7.columns = [c.dayofweek for c in last7.columns]
wd = w28.copy(); wd.columns = [c.dayofweek for c in wd.columns]
wd = wd.T.groupby(level=0).mean().T                                # weekday average over 4 weeks

preds = {
    "moving avg 7d": ev.sid.map(ma7).values,
    "moving avg 28d": ev.sid.map(ma28).values,
    "28d avg, in-stock days only": ev.sid.map(ma28_in).values,
    "seasonal naive (same weekday last week)": np.array([last7.at[s, d] for s, d in zip(ev.sid, ev.dow)]),
    "weekday avg (4 weeks)": np.array([wd.at[s, d] for s, d in zip(ev.sid, ev.dow)]),
}

y = ev.sale_amount.values
ins = (ev.stock_hour6_22_cnt == 0).values
print(f"\nin-stock rows share in eval: {ins.mean():.3f}")
print(f"{'method':45s} {'WAPE all':>9s} {'WAPE in-stock':>14s} {'bias all':>9s}")
for name, p in preds.items():
    wape = lambda m: np.abs(y[m] - p[m]).sum() / y[m].sum()
    allm = np.ones(len(y), bool)
    print(f"{name:45s} {wape(allm):9.3f} {wape(ins):14.3f} {p.sum()/y.sum()-1:9.3f}")