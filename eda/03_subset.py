import pandas as pd, numpy as np

tr = pd.read_parquet("data/raw/freshretail_train.parquet")
tr["dt"] = pd.to_datetime(tr["dt"])
cities = [12, 16, 3]
K, MIN_CARRY = 20, 8

parts = []
for c in cities:
    d = tr[tr.city_id == c]
    cov = d.groupby("product_id").store_id.nunique().sort_values(ascending=False)
    print(f"city {c}: stores={d.store_id.nunique()} | products in >=20 stores={(cov>=20).sum()}"
          f" | >=40={(cov>=40).sum()} | >=60={(cov>=60).sum()}")
    top = cov.head(K).index
    s = d[d.product_id.isin(top)]
    carry = s.groupby("store_id").product_id.nunique()
    parts.append(s[s.store_id.isin(carry[carry >= MIN_CARRY].index)])
sub = pd.concat(parts)

print("\n== subset summary")
print(sub.groupby("city_id").agg(stores=("store_id", "nunique"),
      products=("product_id", "nunique"),
      rows=("dt", "size")))
print("series:", sub.groupby(["store_id", "product_id"]).ngroups, "| rows:", len(sub))
byc = sub.groupby("product_id").city_id.nunique()
print("products shared by 2+ cities:", (byc >= 2).sum(), "| by all 3:", (byc == 3).sum())
print("zero-sales share:", round((sub.sale_amount == 0).mean(), 3))
print("stockout share:", round((sub.stock_hour6_22_cnt > 0).mean(), 3))
print("full-day stockout share:", round((sub.stock_hour6_22_cnt >= 16).mean(), 3))
print("invalid discount share:", round((~sub.discount.between(0.01, 1.0)).mean(), 4))
print("management groups:\n", sub.drop_duplicates("product_id").management_group_id.value_counts())

sub.drop(columns=["hours_sale", "hours_stock_status"]).to_parquet("data/processed/subset.parquet")
print("saved data/processed/subset.parquet")