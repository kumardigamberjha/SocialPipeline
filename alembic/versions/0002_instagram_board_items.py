"""instagram board items

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-13 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('instagram_board_items',
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
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_instagram_board_items_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_instagram_board_items'))
    )
    op.create_index('ix_instagram_board_items_user_status', 'instagram_board_items', ['user_id', 'status', sa.literal_column('created_at DESC')], unique=False)


def downgrade() -> None:
    op.drop_index('ix_instagram_board_items_user_status', table_name='instagram_board_items')
    op.drop_table('instagram_board_items')
