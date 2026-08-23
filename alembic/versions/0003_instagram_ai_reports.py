"""instagram ai reports

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-13 07:02:03.958166+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('instagram_ai_reports',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('report_type', sa.Text(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("report_type IN ('strategy', 'roadmap')", name=op.f('ck_instagram_ai_reports_instagram_ai_report_type_valid')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_instagram_ai_reports_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_instagram_ai_reports'))
    )
    op.create_index('ix_instagram_ai_reports_user_type_created', 'instagram_ai_reports', ['user_id', 'report_type', sa.literal_column('created_at DESC')], unique=False)


def downgrade() -> None:
    op.drop_index('ix_instagram_ai_reports_user_type_created', table_name='instagram_ai_reports')
    op.drop_table('instagram_ai_reports')
