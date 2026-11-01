from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    id: int
    email: str
    role: str

class PlanRunOut(BaseModel):
    id: int
    plan_date: date
    shelf_life_days: int
    kappa: float
    note: Optional[str] = None
    created_at: datetime

class PlanSummaryOut(BaseModel):
    run: PlanRunOut
    lines: int
    orders: int
    holds: int
    warehouse_short: int
    stockout_likely: int
    stockout_possible: int
    expiring_series: int
    expiring_units: float
    ordered_units: float
    shipped_units: float
    short_units: float
    warehouse_pools: int
    warehouse_pools_short: int
    central_order_units: float
    decided_lines: int

class StoreLineOut(BaseModel):
    id: int
    run_id: int
    store_id: int
    product_id: int
    city_id: int
    on_hand: float
    pending: float
    forecast_today: float
    forecast_tomorrow: float
    p90_today: float
    p90_tomorrow: float
    target: float
    order_qty: float
    ship_qty: float
    short_qty: float
    expiring_units: float
    stockout_likely: bool
    stockout_possible: bool
    status: str
    decision_action: Optional[str] = None
    decision_qty: Optional[float] = None
    decided_at: Optional[datetime] = None

class WarehouseLineOut(BaseModel):
    id: int
    run_id: int
    city_id: int
    product_id: int
    on_hand: float
    shipped_today: float
    after_shipments: float
    pending: float
    target: float
    order_qty: float
    requested_by_stores: float
    shippable_now: float
    shortage: bool

class DecisionIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    final_qty: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    comment: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def check_quantity(self):
        if self.action == "edit" and self.final_qty is None:
            raise ValueError("final_qty is required when action is 'edit'")
        if self.action != "edit" and self.final_qty is not None:
            raise ValueError("final_qty is only allowed when action is 'edit'")
        return self

class DecisionOut(BaseModel):
    id: int
    store_line_id: int
    user_id: int
    action: str
    final_qty: float
    comment: Optional[str] = None
    decided_at: datetime