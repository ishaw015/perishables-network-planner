import pandas as pd, numpy as np
from datasets import load_dataset

tr = pd.read_parquet("data/raw/freshretail_train.parquet")
ev = load_dataset("sky5268/FreshRetailNet-50K")["eval"].to_pandas()
for d in (tr, ev):
    d["dt"] = pd.to_datetime(d["dt"])

key = ["store_id", "product_id"]
print("== TRAIN date range:", tr.dt.min().date(), "->", tr.dt.max().date(), "| days:", tr.dt.nunique())
print("== EVAL  date range:", ev.dt.min().date(), "->", ev.dt.max().date(), "| days:", ev.dt.nunique())
print("cities:", tr.city_id.nunique(), "stores:", tr.store_id.nunique(),
      "products:", tr.product_id.nunique(), "series:", tr.groupby(key).ngroups)
print("same series in eval:", len(set(map(tuple, ev[key].drop_duplicates().values)) &
                                   set(map(tuple, tr[key].drop_duplicates().values))))

print("\n== rows per series (describe)")
print(tr.groupby(key).size().describe())

print("\n== stores per city")
print(tr.groupby("city_id").store_id.nunique().sort_values(ascending=False))

print("\n== categories")
for c in ["management_group_id", "first_category_id", "second_category_id", "third_category_id"]:
    print(c, tr[c].nunique())

print("\n== sale_amount")
print(tr.sale_amount.describe())
print("share of zero-sales rows:", (tr.sale_amount == 0).mean().round(3))

print("\n== stockout")
so = tr.stock_hour6_22_cnt
print(so.describe())
print("share of rows with >=1 stockout hour:", (so > 0).mean().round(3))
print("share fully out of stock (16 hrs):", (so >= 16).mean().round(3))
chk = tr.hours_stock_status.head(20000).apply(lambda a: int(np.sum(a[6:22])))
print("cnt == sum(status[6:22]) match:", (chk.values == so.head(20000).values).mean().round(3))

print("\n== mean sales: stockout vs no stockout")
print(tr.groupby(so > 0).sale_amount.mean())

print("\n== discount")
print(tr.discount.describe())
print("share discounted (<1):", (tr.discount < 1).mean().round(3))

print("\n== flags / missing")
print(tr[["holiday_flag", "activity_flag"]].mean())
print(tr.isna().sum()[lambda s: s > 0])