# Expiry-Aware Multi-Echelon Inventory Planning for Perishables

Decision-support system for planning orders in a three-tier fresh-food network
(central warehouse -> city warehouses -> stores). Forecasts demand while correcting for
stockout-censored sales, recommends orders with shelf life in mind, and is evaluated by simulation.

Final-year project, B.Tech Computing and Data Science, SAI University.

## Data
FreshRetailNet-50K (Hugging Face: `sky5268/FreshRetailNet-50K`, CC BY 4.0). Data files are not
stored in this repository; scripts download them.

## Status
- Forecasting (LightGBM, stockout-aware): done
- Demand reconstruction for stockout-censored sales: done
- Network simulation (ordering, pooled warehouse buffer, transfers): done
- Planner module, FastAPI, PostgreSQL, LLM agents, n8n, Next.js: in progress

See `docs/results_so_far.md` for results and limitations.

## Run
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python eda\00_inspect.py      # downloads data
python eda\01_profile.py
python eda\03_subset.py
python eda\05_lgbm.py
python eda\06_demand.py
python eda\10_simulation_steady.py
```