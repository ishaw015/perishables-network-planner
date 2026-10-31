import pandas as pd, numpy as np

tr = pd.read_parquet("data/raw/freshretail_train.parquet")
tr["dt"] = pd.to_datetime(tr["dt"])
key = ["store_id", "product_id"]

# relative sales vs each series' own mean
mean = tr.groupby(key).sale_amount.transform("mean")
tr["rel"] = tr.sale_amount / mean.replace(0, np.nan)

print("== relative sales by out-of-stock hours (within-series)")
tr["so"] = pd.cut(tr.stock_hour6_22_cnt, [-1, 0, 4, 8, 15, 16],
                  labels=["0", "1-4", "5-8", "9-15", "16"])
print(tr.groupby("so", observed=True).rel.agg(["mean", "count"]))

print("\n== relative sales by discount bucket (within-series)")
tr["db"] = pd.cut(tr.discount, [-0.01, 0.5, 0.8, 0.9, 0.99, 1.0, 1.2])
print(tr.groupby("db", observed=True).rel.agg(["mean", "count"]))
print("discount == 0:", (tr.discount == 0).sum(), "| discount > 1:", (tr.discount > 1).sum())

print("\n== relative sales by day of week (0=Mon)")
print(tr.groupby(tr.dt.dt.dayofweek).rel.mean().round(3))

print("\n== holiday / activity effect")
print(tr.groupby("holiday_flag").rel.mean().round(3))
print(tr.groupby("activity_flag").rel.mean().round(3))

print("\n== coverage")
print("products per store:\n", tr.groupby("store_id").product_id.nunique().describe())
print("stores per product:\n", tr.groupby("product_id").store_id.nunique().describe())

print("\n== series per city")
print(tr.groupby("city_id").apply(lambda d: pd.Series({
    "stores": d.store_id.nunique(), "products": d.product_id.nunique(),
    "series": d.groupby(key).ngroups})).sort_values("series", ascending=False))

print("\n== series per management group")
print(tr.groupby("management_group_id").apply(lambda d: d.groupby(key).ngroups))

print("\n== hourly sales profile (sample of 300k rows)")
s = tr.sample(300000, random_state=0)
print(np.vstack(s.hours_sale.values).mean(axis=0).round(3))
print("hourly stock-out share:")
print(np.vstack(s.hours_stock_status.values).mean(axis=0).round(2))