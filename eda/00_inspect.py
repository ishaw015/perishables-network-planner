from datasets import load_dataset
d = load_dataset("sky5268/FreshRetailNet-50K")
print(d)
df = d["train"].to_pandas()
print(df.shape)
print(df.columns.tolist())
print(df.head(3).T)
df.to_parquet("data/raw/freshretail_train.parquet")