"""add generated_images for the image studio

Revision ID: c066c437910e
Revises: c2f1a4d7e930
Create Date: 2026-08-24 03:26:29.765378+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c066c437910e'
down_revision: str | None = 'c2f1a4d7e930'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('generated_images',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('negative_prompt', sa.Text(), nullable=True),
    sa.Column('model', sa.Text(), nullable=False),
    sa.Column('aspect_ratio', sa.Text(), nullable=False),
    sa.Column('image_size', sa.Text(), nullable=False),
    sa.Column('seed', sa.BigInteger(), nullable=True),
    sa.Column('filename', sa.Text(), nullable=False),
    sa.Column('duration_s', sa.Double(), nullable=True),
    # IsoDateTime is a TypeDecorator over DateTime(timezone=True) — identical DDL,
    # and spelling it this way keeps the migration free of app imports (autogenerate
    # emitted the app.db.types name without importing it, which would NameError here).
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_generated_images_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_generated_images'))
    )
    op.create_index('ix_generated_images_user_created', 'generated_images', ['user_id', sa.literal_column('created_at DESC')], unique=False)


def downgrade() -> None:
    op.drop_index('ix_generated_images_user_created', table_name='generated_images')
    op.drop_table('generated_images')
