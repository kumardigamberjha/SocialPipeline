"""youtube video analytics fields

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-13 12:18:18.565245+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('youtube_videos_live', sa.Column('impressions', sa.BigInteger(), server_default=sa.text('0'), nullable=False))
    op.add_column('youtube_videos_live', sa.Column('impressions_ctr', sa.Double(), server_default=sa.text('0'), nullable=False))
    op.add_column('youtube_videos_live', sa.Column('average_view_duration_seconds', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('youtube_videos_live', sa.Column('average_view_percentage', sa.Double(), server_default=sa.text('0'), nullable=False))
    op.add_column('youtube_videos_live', sa.Column('analytics_synced_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('youtube_videos_live', 'analytics_synced_at')
    op.drop_column('youtube_videos_live', 'average_view_percentage')
    op.drop_column('youtube_videos_live', 'average_view_duration_seconds')
    op.drop_column('youtube_videos_live', 'impressions_ctr')
    op.drop_column('youtube_videos_live', 'impressions')
