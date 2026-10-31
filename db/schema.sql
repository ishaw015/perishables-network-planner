CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'planner' CHECK (role IN ('planner', 'admin')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plan_runs (
  id SERIAL PRIMARY KEY,
  plan_date DATE NOT NULL,
  shelf_life_days INT NOT NULL,
  kappa REAL NOT NULL,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS store_lines (
  id BIGSERIAL PRIMARY KEY,
  run_id INT NOT NULL REFERENCES plan_runs(id) ON DELETE CASCADE,
  store_id INT NOT NULL,
  product_id INT NOT NULL,
  city_id INT NOT NULL,
  on_hand REAL, pending REAL,
  forecast_today REAL, forecast_tomorrow REAL, p90_today REAL, p90_tomorrow REAL,
  target REAL, order_qty REAL, ship_qty REAL, short_qty REAL, expiring_units REAL,
  stockout_likely BOOLEAN, stockout_possible BOOLEAN,
  status TEXT NOT NULL CHECK (status IN ('order', 'hold', 'warehouse short'))
);

CREATE INDEX IF NOT EXISTS idx_store_lines_run_status ON store_lines (run_id, status);
CREATE INDEX IF NOT EXISTS idx_store_lines_run_city ON store_lines (run_id, city_id);

CREATE TABLE IF NOT EXISTS warehouse_lines (
  id BIGSERIAL PRIMARY KEY,
  run_id INT NOT NULL REFERENCES plan_runs(id) ON DELETE CASCADE,
  city_id INT NOT NULL,
  product_id INT NOT NULL,
  on_hand REAL, shipped_today REAL, after_shipments REAL, pending REAL, target REAL,
  order_qty REAL, requested_by_stores REAL, shippable_now REAL,
  shortage BOOLEAN
);

CREATE INDEX IF NOT EXISTS idx_wh_lines_run ON warehouse_lines (run_id);

CREATE TABLE IF NOT EXISTS decisions (
  id BIGSERIAL PRIMARY KEY,
  store_line_id BIGINT NOT NULL REFERENCES store_lines(id) ON DELETE CASCADE,
  user_id INT NOT NULL REFERENCES users(id),
  action TEXT NOT NULL CHECK (action IN ('approve', 'edit', 'reject')),
  final_qty REAL,
  comment TEXT,
  decided_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
  id BIGSERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id),
  action TEXT NOT NULL,
  entity TEXT NOT NULL,
  entity_id BIGINT,
  detail JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)