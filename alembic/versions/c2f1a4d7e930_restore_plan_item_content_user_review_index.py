"""restore ix_plan_item_content_user_review

Revision ID: c2f1a4d7e930
Revises: a078269e582e
Create Date: 2026-08-24

b139d561a452 was generated with --autogenerate to add one YouTube column, and
swept up an unrelated drop:

    op.drop_index(op.f('ix_plan_item_content_user_review'), table_name='plan_item_content')

The index was created in 0008 but never declared in ``app/db/tables.py``, so
autogenerate saw an index the models did not know about and removed it. It backs
``queries.get_pending_review_contents`` — the assistant's user-wide review-queue
read, which ``ix_plan_item_content_item_created`` cannot serve because that one
leads with ``item_id``.

This recreates it with the definition from 0008. The model now declares it too,
so a future autogenerate will not drop it again.
"""

from alembic import op
import sqlalchemy as sa

revision = "c2f1a4d7e930"
down_revision = "a078269e582e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: b139d561a452's own downgrade() also recreates this index, so
    # a database that was stepped back and forward already has it.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_plan_item_content_user_review "
        "ON plan_item_content (user_id, review_status, created_at DESC)"
    )


def downgrade() -> None:
    op.drop_index("ix_plan_item_content_user_review", table_name="plan_item_content")
