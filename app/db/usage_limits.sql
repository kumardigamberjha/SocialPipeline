-- =============================================================================
-- Wings of AI — Usage Limits Table Migration
-- =============================================================================
-- Run this in the Supabase SQL Editor AFTER supabase_rls.sql
-- =============================================================================

-- ─── 1. Create usage_limits table ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS usage_limits (
    user_id    UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    plan       TEXT NOT NULL DEFAULT 'free'
               CHECK (plan IN ('free', 'pro', 'enterprise')),
    runs_this_month   INT NOT NULL DEFAULT 0,
    max_runs_per_month INT NOT NULL DEFAULT 10,
    reset_at   TIMESTAMPTZ NOT NULL DEFAULT (date_trunc('month', now()) + INTERVAL '1 month'),
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─── 2. Enable RLS ────────────────────────────────────────────────────────

ALTER TABLE usage_limits ENABLE ROW LEVEL SECURITY;

-- Users can read their own usage
CREATE POLICY "usage_limits_select_own"
    ON usage_limits
    FOR SELECT
    USING (auth.uid() = user_id);

-- Only service role (backend) can insert/update usage_limits
-- (handled automatically since service_role bypasses RLS)

-- ─── 3. Auto-create usage_limits row on user registration ─────────────────

CREATE OR REPLACE FUNCTION create_usage_limits_for_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO usage_limits (user_id, plan, runs_this_month, max_runs_per_month, reset_at)
    VALUES (
        NEW.id,
        'free',
        0,
        10,
        date_trunc('month', now()) + INTERVAL '1 month'
    )
    ON CONFLICT (user_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_user_created_usage_limits
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION create_usage_limits_for_new_user();

-- ─── 4. Index for fast lookups ────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_usage_limits_plan ON usage_limits(plan);
CREATE INDEX IF NOT EXISTS idx_usage_limits_stripe_customer
    ON usage_limits(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;
