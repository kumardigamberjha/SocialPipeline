"""prospect report llm tier provenance

Records which rung of the LLM cascade produced each audit, and whether that rung
is good enough to put in front of a client.

Before this, an audit written by a local 7B fallback was indistinguishable from
one written by Gemini — in the database, in the API response and in the exported
PDF. ``tier_grade`` is the column the export gate reads.

Existing rows are backfilled to ``internal_only``: their provenance was never
recorded, and unknown provenance must fail closed. Anyone who needs an old report
as a client deliverable regenerates it, which is cheap; the alternative is
shipping a report nobody can vouch for.

Revision ID: d0df7b6e6362
Revises: e7a3c91f04d2
Create Date: 2026-08-29 03:33:39.159887+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd0df7b6e6362'
down_revision: str | None = 'e7a3c91f04d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'youtube_prospect_reports',
        sa.Column('tier_index', sa.Integer(), nullable=True),
    )
    op.add_column(
        'youtube_prospect_reports',
        sa.Column('tier_name', sa.Text(), nullable=True),
    )
    # NOT NULL with a server default, so the backfill below is the only state a
    # pre-existing row can land in and no future insert can omit the grade.
    op.add_column(
        'youtube_prospect_reports',
        sa.Column(
            'tier_grade',
            sa.Text(),
            server_default=sa.text("'internal_only'"),
            nullable=False,
        ),
    )
    op.add_column(
        'youtube_prospect_reports',
        sa.Column('resolved_model', sa.Text(), nullable=True),
    )

    # Explicit and idempotent: the server_default already covers rows added by
    # the ALTER, but stating it means the intent survives a squashed migration.
    op.execute(
        "UPDATE youtube_prospect_reports "
        "SET tier_grade = 'internal_only' WHERE tier_grade IS NULL"
    )


def downgrade() -> None:
    op.drop_column('youtube_prospect_reports', 'resolved_model')
    op.drop_column('youtube_prospect_reports', 'tier_grade')
    op.drop_column('youtube_prospect_reports', 'tier_name')
    op.drop_column('youtube_prospect_reports', 'tier_index')
