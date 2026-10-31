from dataclasses import dataclass
import numpy as np, pandas as pd

UNIT = 10     # sale_amount x 10 -> whole units

@dataclass
class Inputs:
    sids: np.ndarray
    store_id: np.ndarray
    product_id: np.ndarray
    city_id: np.ndarray
    wh_of: np.ndarray      # warehouse-product pool index for each store-product series
    wh_keys: np.ndarray
    D: np.ndarray          # realised demand units, shape (n, 7)
    F50: np.ndarray        # median forecast units
    F90: np.ndarray        # calibrated P90 forecast units
    MA7: np.ndarray        # 7-day moving average, used only for the starting stock

    @property
    def n(self): return len(self.sids)

    @property
    def m(self): return len(self.wh_keys)

def load_inputs(demand_path="data/processed/demand_eval.parquet",
                forecast_path="data/processed/forecasts_eval.parquet"):
    dm = pd.read_parquet(demand_path)
    fc = pd.read_parquet(forecast_path)
    sids = np.array(sorted(dm.sid.unique()))

    def mat(df, col, scale=1.0):
        return df.pivot(index="sid", columns="h", values=col).reindex(sids).values * scale

    meta = dm.drop_duplicates("sid").set_index("sid").loc[sids]
    wh_of, keys = pd.factorize((meta.city_id.astype(str) + "_" + meta.product_id.astype(str)).values)
    return Inputs(sids=sids, store_id=meta.store_id.values, product_id=meta.product_id.values,
                  city_id=meta.city_id.values, wh_of=wh_of, wh_keys=np.asarray(keys),
                  D=mat(dm, "units"), F50=mat(fc, "p_stockout_aware", UNIT),
                  F90=mat(fc, "p90_calibrated", UNIT), MA7=mat(fc, "p_baseline", UNIT)[:, 0])