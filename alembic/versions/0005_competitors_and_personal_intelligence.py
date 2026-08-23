"""competitors and personal intelligence

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-21 19:47:06.935939+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Order matters: youtube_competitors references discovery_runs, and
    # youtube_competitor_videos references youtube_competitors.
    op.create_table('user_goals',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('platform', sa.Text(), server_default=sa.text("'youtube'"), nullable=False),
    sa.Column('metric', sa.Text(), server_default=sa.text("'subscribers'"), nullable=False),
    sa.Column('target_value', sa.Double(), server_default=sa.text('0'), nullable=False),
    sa.Column('baseline_value', sa.Double(), server_default=sa.text('0'), nullable=False),
    sa.Column('baseline_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deadline', sa.Date(), nullable=True),
    sa.Column('status', sa.Text(), server_default=sa.text("'active'"), nullable=False),
    sa.Column('progress', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_goals_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_goals'))
    )
    op.create_index('ix_user_goals_user_status', 'user_goals', ['user_id', 'status', 'deadline'], unique=False)
    op.create_table('user_rules',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('scope', sa.Text(), server_default=sa.text("'global'"), nullable=False),
    sa.Column('category', sa.Text(), server_default=sa.text("'behavior'"), nullable=False),
    sa.Column('rule_text', sa.Text(), nullable=False),
    sa.Column('priority', sa.Integer(), server_default=sa.text('100'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_rules_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_rules'))
    )
    op.create_index('ix_user_rules_user_active', 'user_rules', ['user_id', 'is_active', 'scope', 'priority'], unique=False)
    op.create_table('youtube_competitor_discovery_runs',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('niche', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), server_default=sa.text("'pending'"), nullable=False),
    sa.Column('candidates', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('approved_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('rejected_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('quota_units_spent', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_youtube_competitor_discovery_runs_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_youtube_competitor_discovery_runs'))
    )
    op.create_index('ix_competitor_runs_user_created', 'youtube_competitor_discovery_runs', ['user_id', sa.literal_column('created_at DESC')], unique=False)
    op.create_table('youtube_competitors',
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('channel_id', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('handle', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('thumbnail_url', sa.Text(), nullable=True),
    sa.Column('uploads_playlist_id', sa.Text(), nullable=True),
    sa.Column('country', sa.Text(), nullable=True),
    sa.Column('subscriber_count', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('view_count', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('video_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('niche', sa.Text(), nullable=True),
    sa.Column('relevance_score', sa.Double(), server_default=sa.text('0'), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=True),
    sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.Text(), server_default=sa.text("'approved'"), nullable=False),
    sa.Column('priority', sa.Integer(), server_default=sa.text('100'), nullable=False),
    sa.Column('discovered_by', sa.Text(), server_default=sa.text("'llm'"), nullable=False),
    sa.Column('source_run_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sync_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['source_run_id'], ['youtube_competitor_discovery_runs.id'], name=op.f('fk_youtube_competitors_source_run_id_youtube_competitor_discovery_runs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_youtube_competitors_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'channel_id', name='pk_youtube_competitors')
    )
    op.create_index('ix_youtube_competitors_sync', 'youtube_competitors', ['user_id', 'status', 'priority', sa.literal_column('last_synced_at ASC NULLS FIRST')], unique=False)
    op.create_index('ix_youtube_competitors_user_status', 'youtube_competitors', ['user_id', 'status', sa.literal_column('created_at DESC'), 'channel_id'], unique=False)
    op.create_table('youtube_competitor_videos',
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('video_id', sa.Text(), nullable=False),
    sa.Column('channel_id', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_seconds', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('is_short', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('views', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('likes', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('comments', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('thumbnail_url', sa.Text(), nullable=True),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id', 'channel_id'], ['youtube_competitors.user_id', 'youtube_competitors.channel_id'], name='fk_competitor_videos_competitor', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_youtube_competitor_videos_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'video_id', name='pk_youtube_competitor_videos')
    )
    op.create_index('ix_competitor_videos_channel', 'youtube_competitor_videos', ['user_id', 'channel_id', sa.literal_column('published_at DESC')], unique=False)


def downgrade() -> None:
    # Reverse order of upgrade().
    op.drop_index('ix_competitor_videos_channel', table_name='youtube_competitor_videos')
    op.drop_table('youtube_competitor_videos')
    op.drop_index('ix_youtube_competitors_user_status', table_name='youtube_competitors')
    op.drop_index('ix_youtube_competitors_sync', table_name='youtube_competitors')
    op.drop_table('youtube_competitors')
    op.drop_index('ix_competitor_runs_user_created', table_name='youtube_competitor_discovery_runs')
    op.drop_table('youtube_competitor_discovery_runs')
    op.drop_index('ix_user_rules_user_active', table_name='user_rules')
    op.drop_table('user_rules')
    op.drop_index('ix_user_goals_user_status', table_name='user_goals')
    op.drop_table('user_goals')
