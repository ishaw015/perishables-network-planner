# Planner validation

This page collects the evidence that each part of the planner works: the demand estimate, the forecast, the ordering policy, the plan served by the API, and the AI features. Every number comes from the project's own runs and tests. Simulation settings are in `simulation_assumptions.md`.

## 1. Demand reconstruction

Recorded sales understate demand when a shelf is empty, so true demand is estimated from the in-stock hours (scaled by a typical hourly sales profile; filled from the forecast when under 50% of a typical day was in stock; scale-up capped at 4 times the forecast).

**Test:** hide some hours that were in stock and see whether the method recovers the real sales.

| | WAPE (lower is better) | Bias |
|---|---|---|
| Observed sales only | 0.481 | −0.481 |
| Reconstructed | 0.234 | −0.039 |

On the real evaluation week, true demand is about **17.6% above recorded sales**, and 13.7% of rows are filled from the forecast. **Caveat:** the test hides hours at random, while real stockouts follow demand, so real accuracy is probably lower. A sensitivity run on observed-only demand is reported alongside.

## 2. Forecast

One global LightGBM model for all series, with direct forecasts for days 1 to 7, Tweedie loss, and weather and discount assumed known in advance. WAPE is total absolute error divided by total sales, measured on the evaluation week.

| Method | WAPE |
|---|---|
| Weekday average | 0.443 |
| Seasonal naive | 0.436 |
| 28-day average | 0.435 |
| 7-day moving average | 0.395 |
| LightGBM (plain) | 0.364 |
| **LightGBM (stockout-aware)** | **0.355** |

- Gain over the 7-day average: **−0.040 WAPE, 95% confidence interval [−0.044, −0.036]** (bootstrap over series).
- Stockout-aware training drops training rows whose target day was mostly stockout, which gives a further gain.
- Top features: 7-day average, 28-day average, in-stock average, product, discount.
- **P90 coverage:** the raw P90 forecast covered 84.5% of outcomes, so it was scaled (k = 1.195) to reach 94.4%. This is a policy setting, not perfect calibration.

## 3. What the forecast is worth (simulation)

To isolate the forecast, the moving-average baseline was given the same ordering rule and pooling (about 93% fill).

| Shelf life | Waste % LightGBM | Waste % moving average | Cost LightGBM | Cost moving average |
|---|---|---|---|---|
| 4 days | 5.0 | about 8.1 | 58k | about 77k |
| 5 days | 1.2 | about 3.0 | 38.7k | about 52k |
| 7 days | 0.2 | about 0.3 | 33.6k | about 39k |

- The forecast alone saves **15 to 26% of cost** and needs roughly 17 to 20% less stock for the same fill.
- Of the total saving from Policy A to Policy B, **72 to 84% comes from the ordering structure and pooling**, and 16 to 28% from the forecast. The forecast helps, but the system design helps more.
- Sensitivity (5 days, observed-only demand): A costs 126k against 103k for B. The gap is smaller, but the ranking is the same.

## 4. Simulation checks

- **Conservation:** on every run, units in = units sold + units wasted + units remaining, with an error of about 1e-10.
- **Warm-up:** a 7-day warm-up before the 7 measured days removed a start-up artifact that had inflated waste. Earlier conclusions were redone.
- **Fair baseline:** the baseline's buffer was swept from 1.25 to 1.75 and it was given the same ordering and pooling, after the first baseline looked unfairly weak.
- **Result (5-day shelf life):** Policy B with kappa 1.0 reaches **98.0% fill, 3.0% waste, cost 41.9k**. Policy A with buffer 1.5 reaches 90.4% fill, 8.3% waste, cost 92.2k. Pooling cuts waste by 3 to 10 times at the same service level.

## 5. Planner correctness

- **Shared code:** the simulation and the API call the same policy functions, so what was tested is what is served.
- **Plan equals simulation:** the stored plan matched the simulation in all 12 test cases.
 
- **A bug caught by that check:** warehouse orders ignored today's store shipments (1,494 units against about 89,000 of store orders). It was fixed and a test was added.
- **What-if recompute equals the stored plan:** `python -m db.check_whatif` recomputes all 4,529 store lines from stored rows with the same policy functions. The largest difference is 0.0000.
- **Totals reconciliation:** the database stores quantities in single precision, so summing them in the database introduced rounding noise (88,848 shown against 88,847 true). The API now sums in double precision, and the Daily plan and What-if screens agree (shipped 88,847; ordered 89,343; short 495). Totals are rounded separately, so shipped plus short can differ from ordered by 1.
- **Risk flags:** a first version flagged 54% of series as at risk, which is too many to act on. They are now split into *likely* (stock below today's median forecast, 163 lines) and *possible* (stock below the P90 forecast, 2,426 lines).

## 6. Automated tests

`python -m pytest -q` runs **74 tests, all passing**.

| File | Tests | What it checks |
|---|---|---|
| `tests/test_api.py` | 22 | Login, protected routes, input validation (422), plan summary, filtered and paged lines, approve/edit/reject, the 3x-target edit cap, audit log |
| `tests/test_agent_api.py` | 6 | The explain endpoint |
| `tests/test_agent_guardrails.py` | 14 | The AI code has no way to write to the database, imports no API code, and imports only the allowed planner module |
| `tests/test_whatif.py` | 17 | What-if maths: baseline equals stored plan, stock cut, demand change, in-transit shortfall, shipping limits, input checks |
| `tests/test_whatif_agent.py` | 15 | The what-if agent with the language model and database faked: end to end, template fallback, planner-owned numbers, refusal paths, no stockout claims when none is computed |
| **Total** | **74** | |

## 7. AI features

Gemini never decides quantities: the planner code computes every number, and a verifier rejects any answer containing a number that is not in the plan facts.

**Explain agent** (74 questions: 54 answerable, 10 unanswerable, 10 boundary):

| Check | Result |
|---|---|
| Raw Gemini drafts passing the verifier first time | 87.8% |
| Final answers passing the verifier (after retry and fallback) | 74 / 74 |
| Answerable questions answered | 54 / 54 |
| Unanswerable questions declined | 10 / 10 |
| Boundary questions with no new quantity given | 10 / 10 |
| Corrupted answers caught (8 corruption types) | 60 / 60 each |
| Second-model judge | 30 of 73 scored so far: all faithful, relevance 5.0 / 5 (partial) |

**Disruption (What-if) agent** (`python -m evaluation.whatif_eval`, 39 typed sentences):

| Check | Result |
|---|---|
| Parse accuracy (type, city, product, amount) | 19 / 19 |
| Expected response (preview, ask for detail, or refuse) | 39 / 39 |
| Quantity leaks, including 6 attempts to make the AI set quantities and 1 injected instruction | 0 |
| Explanations passing the verifier first time | 14 / 14 |

## 8. Limitations of this validation

- One evaluation week, repeated for the simulation warm-up.
- The supply side (lead times, costs, stock, shelf life) is simulated.
- The reconstruction test hides hours at random, so it is optimistic.
- The AI test sets are targeted tests written by the author, not independent benchmarks, and the second-model judge has scored only part of the explain answers so far.
- The demo plan has no stock in transit, so the "delivery does not arrive" what-if is covered by unit tests only.