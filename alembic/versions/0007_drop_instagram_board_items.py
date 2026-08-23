"""drop the orphaned instagram_board_items table

0006 folded the Instagram Kanban into ``plan_items`` with
``platform='instagram'`` and deliberately left the old table behind, so the
frontend could cut over on its own schedule and so ``downgrade 0005`` had a
landing target. That cutover is done: the dashboard's second Kanban and the
``/api/instagram-analytics/board*`` endpoints that fed it are gone, along with
the ``board_compat`` translation shim. Nothing reads or writes this table.

``downgrade`` recreates it empty rather than restoring rows. That is not data
loss: 0006's own ``downgrade`` repopulates it from ``plan_items`` immediately
after this one runs, and it has been the only writer since 0006 anyway. What
this must guarantee is that the table *exists* by the time 0006's downgrade
issues its INSERT — hence the exact original DDL from 0002.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-23 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index('ix_instagram_board_items_user_status', table_name='instagram_board_items')
    op.drop_table('instagram_board_items')


def downgrade() -> None:
    # Byte-for-byte the DDL from 0002, so 0006's downgrade INSERT still fits.
    op.create_table(
        'instagram_board_items',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), server_default=sa.text("'idea'"), nullable=False),
        sa.Column('scheduled_date', sa.Date(), nullable=True),
        sa.Column('slides_count', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('likes', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('shares', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('saves', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('reach', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('image_prompt', sa.Text(), nullable=True),
        sa.Column('source', sa.Text(), server_default=sa.text("'manual'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_instagram_board_items_user_id_users'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_instagram_board_items')),
    )
    op.create_index(
        'ix_instagram_board_items_user_status',
        'instagram_board_items',
        ['user_id', 'status', sa.literal_column('created_at DESC')],
        unique=False,
    )
