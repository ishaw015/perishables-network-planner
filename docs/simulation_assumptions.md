# Simulation assumptions

The demand in this project is real retail data. The supply chain around it (warehouses, lead times, shelf life, stock and costs) is **simulated**, because the dataset has no warehouses or expiry. This page lists exactly what is assumed, so the results can be read in the right light.

## 1. What is real and what is simulated

| Part | Real or simulated | Notes |
|---|---|---|
| Daily and hourly sales, store and product ids | Real | FreshRetailNet-50K, subset of 3 cities (IDs 3, 12, 16), 284 stores, about 44 products, 90 days |
| Stockout hours | Real | Used to recover true demand (see section 3) |
| Discounts, holidays, weather | Real | Treated as known in advance when forecasting |
| Network structure | Simulated | 1 central warehouse, 3 city warehouses, 284 stores |
| Lead times | Simulated | 2 days to a city warehouse, 1 day to a store |
| Shelf life | Simulated | 3, 4, 5 and 7 days; oldest stock is sold first (FEFO) |
| Initial stock, deliveries, replenishment | Simulated | Decided by the ordering policy being tested |
| Costs | Simulated | See section 4 |

## 2. Simulation design

- **Network:** central warehouse to 3 city warehouses to 284 stores. When a city warehouse cannot cover all store requests, stock is shared pro rata.
- **Run length:** 14 days, of which the first 7 are a warm-up and the last 7 are measured. The evaluation week (26 June to 2 July 2024) is repeated to provide the warm-up.
- **Why a warm-up:** the first results were misleading, because stock that expired on a single day at the start dominated the waste. After adding the warm-up, earlier conclusions were redone.
- **Metrics:** fill rate, waste as a percentage of demand, ending stock and total cost.
- **Conservation check:** on every run, units in = units sold + units wasted + units remaining, with an error of about 1e-10.

## 3. Demand used in the simulation

- Recorded sales understate demand whenever a shelf is empty. Stockouts are common in this data (49.8% of rows in the subset, 44% overall; full-day stockouts 8.8%).
- True demand is recovered from the in-stock hours and the model-filled remainder. On the real evaluation week, true demand is about **17.6% above recorded sales**, and about **4.7%** of estimated demand is model-filled.
- The recovery was tested by hiding some in-stock hours and checking that the method brings the real sales back; the error roughly halves.
- Weather and discount values are assumed to be known in advance, which a live system would need to obtain from forecasts.

## 4. Unit costs (assumed)

| Item | Cost per unit |
|---|---|
| Waste (expired unit) | 1.0 |
| Lost margin (unmet demand) | 0.5 |
| Holding at a store | 0.03 per day |
| Holding at a warehouse | 0.02 per day |
| Transfer | 0.1 |

These are assumed values, not measured ones. The ranking of policies was checked at every shelf life, but absolute cost numbers should not be read as real money.

## 5. Policies compared

- **Policy A (baseline):** moving-average forecast with a fixed buffer of 1.25 to 1.75 times demand.
- **Policy B (this project):** LightGBM median and P90 forecasts, an order-up-to rule with safety factor kappa, and pooled warehouse safety stock.
- **Policy B without pooling:** store buffers are simply added up at the warehouse.

Policy A first looked unfairly weak, so its buffer was swept from 1.25 to 1.75 and it was given the same ordering and pooling as Policy B, to isolate the effect of the forecast.

## 6. Headline results (5-day shelf life)

| Policy | Fill % | Waste % | Cost |
|---|---|---|---|
| A, buffer 1.25 | 85.2 | 3.1 | 72.1k |
| A, buffer 1.5 | 90.4 | 8.3 | 92.2k |
| A, buffer 1.75 | 93.7 | 15.8 | 127.9k |
| B, kappa 0.5 | 93.2 | 1.2 | 38.7k |
| B, kappa 1.0 | 98.0 | 3.0 | 41.9k |
| B, no pooling | 97.5 | 14.1 | 109.0k |

Waste is a percentage of demand. Pooling cut waste by 3 to 10 times across shelf lives at the same service level. Shorter shelf life raises waste for every policy, but the ranking stays the same.

## 7. Limitations

- **One test week.** Results come from a single evaluation week, repeated for the warm-up.
- **Simulated supply side.** Lead times, costs, stock and shelf life are assumptions.
- **Known inputs.** Weather and discounts are assumed known in advance.
- **Different markets.** The results come from three cities of one retailer and may not transfer elsewhere.
- **Demo plan.** The plan shown in the app is day 3 of the measured week (28 June 2024), with simulated stock and no stock in transit.

