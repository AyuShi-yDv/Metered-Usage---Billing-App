"""initial billing schema"""
from alembic import op
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")
    statements = """
    CREATE TABLE accounts (id uuid PRIMARY KEY, name varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE plans (id uuid PRIMARY KEY, name varchar(80) UNIQUE NOT NULL, included_calls bigint NOT NULL CHECK(included_calls >= 0), overage_cents_per_1000 integer NOT NULL CHECK(overage_cents_per_1000 >= 0), monthly_base_fee_cents integer NOT NULL CHECK(monthly_base_fee_cents >= 0));
    CREATE TABLE account_plans (id uuid PRIMARY KEY, account_id uuid NOT NULL REFERENCES accounts(id), plan_id uuid NOT NULL REFERENCES plans(id), effective_from timestamptz NOT NULL, effective_to timestamptz, CHECK(effective_to IS NULL OR effective_to>effective_from), EXCLUDE USING gist (account_id WITH =, tstzrange(effective_from, effective_to, '[)') WITH &&));
    CREATE TABLE billing_events (event_id uuid PRIMARY KEY, account_id uuid NOT NULL REFERENCES accounts(id), endpoint varchar(256) NOT NULL, occurred_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT now(), duration_ms integer NOT NULL CHECK(duration_ms BETWEEN 0 AND 3600000), status_code smallint NOT NULL CHECK(status_code BETWEEN 100 AND 599));
    CREATE INDEX billing_events_account_occurred_idx ON billing_events(account_id, occurred_at);
    CREATE INDEX billing_events_account_time_endpoint_idx ON billing_events(account_id, occurred_at, endpoint) INCLUDE(duration_ms);
    CREATE TABLE rollup_tasks (account_id uuid NOT NULL, hour_start timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(account_id, hour_start));
    CREATE TABLE hourly_usage_rollups (account_id uuid NOT NULL, hour_start timestamptz NOT NULL, endpoint varchar(256) NOT NULL, billable_calls bigint NOT NULL CHECK(billable_calls >= 0), total_calls bigint NOT NULL CHECK(total_calls >= 0), PRIMARY KEY(account_id,hour_start,endpoint));
    CREATE INDEX hourly_usage_rollups_account_hour_idx ON hourly_usage_rollups(account_id,hour_start);
    CREATE TABLE invoices (id uuid PRIMARY KEY, account_id uuid NOT NULL REFERENCES accounts(id), period_start timestamptz NOT NULL, period_end timestamptz NOT NULL CHECK(period_end>period_start), status varchar(16) NOT NULL CHECK(status IN ('draft','final')), base_fee_cents integer NOT NULL CHECK(base_fee_cents >= 0), overage_cents integer NOT NULL CHECK(overage_cents >= 0), total_cents integer NOT NULL CHECK(total_cents >= 0), UNIQUE(account_id,period_start));
    CREATE TABLE invoice_lines (id uuid PRIMARY KEY, invoice_id uuid NOT NULL REFERENCES invoices(id), description varchar(256) NOT NULL, quantity bigint NOT NULL CHECK(quantity >= 0), amount_cents integer NOT NULL CHECK(amount_cents >= 0), source_period_start timestamptz);
    CREATE TABLE late_adjustments (id uuid PRIMARY KEY, account_id uuid NOT NULL REFERENCES accounts(id), source_period_start timestamptz NOT NULL, amount_cents integer NOT NULL CHECK(amount_cents >= 0), created_at timestamptz NOT NULL DEFAULT now(), applied_invoice_id uuid REFERENCES invoices(id));
    """
    for statement in statements.split(";"):
        if statement.strip(): op.execute(statement)
def downgrade():
    for statement in ["DROP TABLE late_adjustments", "DROP TABLE invoice_lines", "DROP TABLE invoices", "DROP TABLE hourly_usage_rollups", "DROP TABLE rollup_tasks", "DROP TABLE billing_events", "DROP TABLE account_plans", "DROP TABLE plans", "DROP TABLE accounts"]:
        op.execute(statement)
