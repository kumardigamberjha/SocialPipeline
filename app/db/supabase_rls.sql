-- =============================================================================
-- Wings of AI — Row Level Security Migration
-- =============================================================================
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New Query)
--
-- This migration:
--   1. Fixes the dangerous default UUID on agent_runs.user_id
--   2. Enables RLS on agent_runs, task_steps, api_keys
--   3. Creates policies so users can only access their own data
--   4. Service role (backend workers) bypasses RLS automatically
-- =============================================================================

-- ─── 1. Fix agent_runs: remove dangerous default on user_id ─────────────────

ALTER TABLE agent_runs
  ALTER COLUMN user_id DROP DEFAULT;

-- Ensure user_id is NOT NULL going forward
ALTER TABLE agent_runs
  ALTER COLUMN user_id SET NOT NULL;

-- ─── 2. Add metadata column for image generation results ────────────────────

ALTER TABLE agent_runs
  ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

-- ─── 3. Enable Row Level Security ──────────────────────────────────────────

ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys   ENABLE ROW LEVEL SECURITY;

-- ─── 4. agent_runs policies ────────────────────────────────────────────────

-- Users can view their own runs
CREATE POLICY "agent_runs_select_own"
  ON agent_runs
  FOR SELECT
  USING (auth.uid()::text = user_id);

-- Users can insert runs for themselves
CREATE POLICY "agent_runs_insert_own"
  ON agent_runs
  FOR INSERT
  WITH CHECK (auth.uid()::text = user_id);

-- Users can update their own runs (e.g., cancel)
CREATE POLICY "agent_runs_update_own"
  ON agent_runs
  FOR UPDATE
  USING (auth.uid()::text = user_id);

-- ─── 5. task_steps policies ────────────────────────────────────────────────

-- Users can view task steps only if the parent run belongs to them
CREATE POLICY "task_steps_select_own"
  ON task_steps
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM agent_runs
      WHERE agent_runs.id::text = task_steps.run_id
        AND agent_runs.user_id = auth.uid()::text
    )
  );

-- Users can insert task steps only for their own runs
CREATE POLICY "task_steps_insert_own"
  ON task_steps
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM agent_runs
      WHERE agent_runs.id::text = task_steps.run_id
        AND agent_runs.user_id = auth.uid()::text
    )
  );

-- ─── 6. api_keys policies ─────────────────────────────────────────────────

-- Users can fully manage their own API keys
CREATE POLICY "api_keys_select_own"
  ON api_keys
  FOR SELECT
  USING (auth.uid()::text = user_id);

CREATE POLICY "api_keys_insert_own"
  ON api_keys
  FOR INSERT
  WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "api_keys_update_own"
  ON api_keys
  FOR UPDATE
  USING (auth.uid()::text = user_id);

CREATE POLICY "api_keys_delete_own"
  ON api_keys
  FOR DELETE
  USING (auth.uid()::text = user_id);

-- =============================================================================
-- NOTE: The backend uses `supabase_secret_key` (service_role), which
-- automatically bypasses RLS. Celery workers write to any user's rows
-- via service_role — this is the intended design.
--
-- Client-side (publishable key) access is now properly scoped per-user.
-- =============================================================================
