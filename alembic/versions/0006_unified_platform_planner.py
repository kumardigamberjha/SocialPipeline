"""unified platform-aware planner

Folds the Instagram Kanban board (``instagram_board_items``) into the generic
planner tables so there is one data model behind every platform. After this,
adding a platform is a Pydantic ``Literal`` edit plus a dropdown entry — no new
table, no new router, no migration.

Three schema moves make that possible:

* ``platform`` on ``content_plans`` and (denormalized) on ``plan_items``.
* ``plan_items.meta`` JSONB for the platform-specific fields that do not
  deserve a column on every row.
* ``plan_items.scheduled_date`` becomes nullable — a backlog "idea" card has no
  date, and a placeholder date would make every one of them read as overdue.

``instagram_board_items`` is deliberately left in place: it gives ``downgrade``
a landing target, and it keeps a known-good copy of the board through the
rollback window. 0007 drops it once the frontend has cut over.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-22 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Columns ──────────────────────────────────────────────────────────────
    # Every NOT NULL column carries a server_default so the ALTER works on the
    # populated table; 'youtube' is correct for every pre-merge row.
    op.add_column(
        'content_plans',
        sa.Column('platform', sa.Text(), server_default=sa.text("'youtube'"), nullable=False),
    )
    op.add_column(
        'plan_items',
        sa.Column('platform', sa.Text(), server_default=sa.text("'youtube'"), nullable=False),
    )
    op.add_column(
        'plan_items',
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()),
                  server_default=sa.text("'{}'::jsonb"), nullable=False),
    )

    # A Kanban 'idea' card is legitimately undated.
    op.alter_column('plan_items', 'scheduled_date', existing_type=sa.Date(), nullable=True)

    # The synthetic per-platform board plan is neither weekly nor monthly.
    op.drop_constraint(op.f('ck_content_plans_plan_type_valid'), 'content_plans', type_='check')
    op.create_check_constraint(
        op.f('ck_content_plans_plan_type_valid'),
        'content_plans',
        "plan_type IN ('weekly', 'monthly', 'board')",
    )

    # ── Indexes ──────────────────────────────────────────────────────────────
    op.create_index(
        'ix_content_plans_user_platform', 'content_plans',
        ['user_id', 'platform', sa.literal_column('start_date DESC')], unique=False,
    )
    # Makes find-or-create of the board plan race-free.
    op.create_index(
        'uq_content_plans_user_platform_board', 'content_plans',
        ['user_id', 'platform'], unique=True,
        postgresql_where=sa.text("plan_type = 'board'"),
    )
    op.create_index(
        'ix_plan_items_user_platform_status', 'plan_items',
        ['user_id', 'platform', 'production_status', sa.literal_column('created_at DESC')],
        unique=False,
    )
    op.create_index(
        'ix_plan_items_user_platform_scheduled', 'plan_items',
        ['user_id', 'platform', 'scheduled_date'], unique=False,
    )
    # Now covered as the leading column of both composites above, including the
    # ON DELETE CASCADE lookup when a user is deleted.
    op.drop_index(op.f('ix_plan_items_user_id'), table_name='plan_items')

    # ── Backfill: instagram_board_items -> content_plans + plan_items ────────
    # One synthetic board plan per user who has cards. The NOT EXISTS guards
    # make both statements idempotent, which matters because the migration and
    # the application deploy are not atomic across pods: re-running this block
    # once after the deploy settles picks up anything an old pod wrote in
    # between.
    op.execute("""
        INSERT INTO content_plans
            (id, user_id, name, plan_type, niche, start_date, end_date,
             status, platform, created_at)
        SELECT gen_random_uuid(),
               b.user_id,
               'Instagram Board',
               'board',
               'instagram',
               COALESCE(MIN(b.scheduled_date), CURRENT_DATE),
               COALESCE(MAX(b.scheduled_date), CURRENT_DATE),
               'active',
               'instagram',
               MIN(b.created_at)
          FROM instagram_board_items b
         WHERE NOT EXISTS (
                   SELECT 1 FROM content_plans p
                    WHERE p.user_id   = b.user_id
                      AND p.platform  = 'instagram'
                      AND p.plan_type = 'board')
         GROUP BY b.user_id
    """)

    # Cards become plan items. The primary key is PRESERVED so any id the
    # running Instagram dashboard already holds still resolves after the swap.
    # Instagram's four statuses are first-class ProductionStatus values now, so
    # the status copy is an identity.
    op.execute("""
        INSERT INTO plan_items
            (id, plan_id, user_id, topic, scheduled_date, publish_date,
             event_time, event_duration_minutes, notes, topic_source,
             video_format, production_status, platform, meta,
             created_at, updated_at)
        SELECT b.id,
               p.id,
               b.user_id,
               b.title,
               b.scheduled_date,
               NULL, NULL, NULL, NULL,
               CASE WHEN b.source = 'manual' THEN 'manual' ELSE 'ai' END,
               'full',
               CASE WHEN b.status IN ('idea','in_production','scheduled','published')
                    THEN b.status ELSE 'idea' END,
               'instagram',
               jsonb_strip_nulls(jsonb_build_object(
                   'type',         b.type,
                   'caption',      b.caption,
                   'image_prompt', b.image_prompt
               )) || jsonb_build_object(
                   'slides_count', b.slides_count,
                   'source',       b.source,
                   'likes',        b.likes,
                   'shares',       b.shares,
                   'saves',        b.saves,
                   'reach',        b.reach
               ),
               b.created_at,
               b.updated_at
          FROM instagram_board_items b
          JOIN content_plans p
            ON p.user_id   = b.user_id
           AND p.platform  = 'instagram'
           AND p.plan_type = 'board'
         WHERE NOT EXISTS (SELECT 1 FROM plan_items pi WHERE pi.id = b.id)
    """)


def downgrade() -> None:
    # Copy back anything the compat shim wrote while the merged schema was live,
    # or the downgrade silently destroys every post-migration card.
    op.execute("""
        INSERT INTO instagram_board_items
            (id, user_id, title, type, status, scheduled_date, slides_count,
             likes, shares, saves, reach, caption, image_prompt, source,
             created_at, updated_at)
        SELECT i.id,
               i.user_id,
               i.topic,
               COALESCE(i.meta->>'type', 'reel'),
               CASE WHEN i.production_status IN ('idea','in_production','scheduled','published')
                    THEN i.production_status ELSE 'idea' END,
               i.scheduled_date,
               COALESCE((i.meta->>'slides_count')::int, 1),
               COALESCE((i.meta->>'likes')::int, 0),
               COALESCE((i.meta->>'shares')::int, 0),
               COALESCE((i.meta->>'saves')::int, 0),
               COALESCE((i.meta->>'reach')::int, 0),
               i.meta->>'caption',
               i.meta->>'image_prompt',
               COALESCE(i.meta->>'source', 'manual'),
               i.created_at,
               i.updated_at
          FROM plan_items i
         WHERE i.platform = 'instagram'
           AND NOT EXISTS (SELECT 1 FROM instagram_board_items b WHERE b.id = i.id)
    """)
    # plan_items cascade from content_plans.
    op.execute("DELETE FROM content_plans WHERE platform = 'instagram' AND plan_type = 'board'")

    # Restore NOT NULL: any remaining undated item falls back to its creation date.
    op.execute(
        "UPDATE plan_items SET scheduled_date = created_at::date WHERE scheduled_date IS NULL"
    )

    op.create_index(op.f('ix_plan_items_user_id'), 'plan_items', ['user_id'], unique=False)
    op.drop_index('ix_plan_items_user_platform_scheduled', table_name='plan_items')
    op.drop_index('ix_plan_items_user_platform_status', table_name='plan_items')
    op.drop_index('uq_content_plans_user_platform_board', table_name='content_plans')
    op.drop_index('ix_content_plans_user_platform', table_name='content_plans')

    op.drop_constraint(op.f('ck_content_plans_plan_type_valid'), 'content_plans', type_='check')
    op.create_check_constraint(
        op.f('ck_content_plans_plan_type_valid'),
        'content_plans',
        "plan_type IN ('weekly', 'monthly')",
    )

    op.alter_column('plan_items', 'scheduled_date', existing_type=sa.Date(), nullable=False)
    op.drop_column('plan_items', 'meta')
    op.drop_column('plan_items', 'platform')
    op.drop_column('content_plans', 'platform')
