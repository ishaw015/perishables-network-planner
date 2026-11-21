export type PlanRun = { id: number; plan_date: string; shelf_life_days: number; kappa: number; note: string | null };

export type Summary = {
  run: PlanRun; lines: number; orders: number; holds: number; warehouse_short: number;
  stockout_likely: number; stockout_possible: number; expiring_series: number; expiring_units: number;
  ordered_units: number; shipped_units: number; short_units: number; decided_lines: number;
};

export type StoreLine = {
  id: number; store_id: number; product_id: number; city_id: number;
  on_hand: number; pending: number; forecast_today: number; p90_today: number;
  target: number; order_qty: number; ship_qty: number; short_qty: number; expiring_units: number;
  stockout_likely: boolean; stockout_possible: boolean; status: string;
  decision_action: string | null; decision_qty: number | null;
};

export type Explanation = {
  answer: string; used_facts: string[]; cannot_answer: boolean; source: string; attempts: number;
};

export type Totals = {
  ordered_units: number; shipped_units: number; short_units: number; lines_short: number;
  stockout_likely?: number;   // only present for demand scenarios
};

export type WhatIfResult = {
  status: "ok" | "clarify" | "unsupported";
  message: string | null;
  scenario: { type: string; city_id: number | null; product_id: number | null; percent: number } | null;
  before: Totals | null; after: Totals | null;
  lines_in_scope: number | null; lines_changed: number | null;
  top_lines: { store_id: number; product_id: number; city_id: number; shipped_before: number; shipped_after: number }[] | null;
  explanation: Explanation | null;
};