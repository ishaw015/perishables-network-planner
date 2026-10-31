"""Ordering policy for the perishable network. Pure numpy functions, no file access.
Used by the simulation (planner/simulate.py) and later by the API.

Forecast windows: f50 and f90 have one row per store-product and one column per day,
column 0 = today, 1 = tomorrow, ... (at least 4 columns). Units are whole product units.
"""
import numpy as np

def gap(f50, f90):
    """how far the P90 forecast is above the median forecast"""
    return np.maximum(f90 - f50, 0.0)

def store_targets(f50, f90, kappa):
    """order-up-to level for a store: demand of today and tomorrow plus a safety cushion.
    kappa = 0 -> median forecast; kappa = 1 -> full P90 cushion."""
    g = gap(f50, f90)
    return np.ceil(f50[:, 0] + f50[:, 1] + kappa * (g[:, 0] + g[:, 1]))

def store_orders(target, on_hand, pending):
    return np.maximum(0.0, target - on_hand - pending)

def warehouse_targets(f50, f90, kappa, wh_of, m, pool=True):
    """order-up-to level for each city warehouse and product: stores' demand for the next 3 days
    plus a safety cushion. pool=True sizes the cushion with the square root of the summed squares
    (assumes store errors are independent); pool=False simply adds the stores' cushions."""
    g = gap(f50, f90)
    bc = lambda x: np.bincount(wh_of, weights=x, minlength=m)
    mean = sum(bc(f50[:, i]) for i in (1, 2, 3))
    gsum = g[:, 1] + g[:, 2] + g[:, 3]
    safety = np.sqrt(bc(gsum ** 2)) if pool else bc(gsum)
    return np.ceil(mean + kappa * safety)

def warehouse_orders(target, on_hand, pending):
    return np.maximum(0.0, target - on_hand - pending)

def allocation_ratio(order, available, wh_of, m):
    """if a warehouse cannot cover all store orders for a product, every store gets the same share"""
    req = np.bincount(wh_of, weights=order, minlength=m)
    ratio = np.where(req > 0, np.minimum(1.0, available / np.maximum(req, 1e-9)), 0.0)
    return ratio, req
  
def risk_flags(f50, f90, stock_by_life, on_hand):
    """expiring units: units expected to expire unsold (oldest stock is sold first);
    stockout risk: stock on hand is below the median forecast demand for today.
    stock_by_life columns = remaining shelf life in days; f50 needs at least L columns."""
    L = stock_by_life.shape[1] - 1
    cum_forecast = np.cumsum(f50[:, :L], axis=1)
    cum_stock = np.cumsum(stock_by_life[:, 1:], axis=1)
    at_risk = np.maximum(0.0, cum_stock - cum_forecast).max(axis=1)
    return at_risk, on_hand < f50[:, 0], on_hand < f90[:, 0]     # expiring units, likely stockout, possible stockout