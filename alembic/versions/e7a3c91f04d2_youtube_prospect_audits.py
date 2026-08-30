"""youtube prospect audits: third-party channel reports for outreach

Adds the two tables behind the prospect audit feature. A prospect is a channel
the user does *not* own, looked up once and pitched — deliberately kept out of
``youtube_competitors``, which drives the weekly sync and feeds every analysis
prompt, so that a one-off lookup never silently joins the user's competitive
set.

``youtube_prospects`` stores the channel plus the Python-computed metrics and
the outreach line derived from them, so the copy shown later always matches the
figures it was generated from even after the real channel has moved on.
``youtube_prospect_reports`` keeps each generated audit/roadmap as history
rather than overwriting, so a re-run cannot destroy a version already sent.

Revision ID: e7a3c91f04d2
Revises: d51c8ab37f04
Create Date: 2026-08-27 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e7a3c91f04d2'
down_revision: str | None = 'd51c8ab37f04'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "youtube_prospects",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("handle", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("thumbnail_url", sa.Text()),
        sa.Column("country", sa.Text()),
        sa.Column("subscriber_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("view_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("video_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics_json", postgresql.JSONB()),
        sa.Column("headline_json", postgresql.JSONB()),
        sa.Column("outreach_line", sa.Text()),
        sa.Column("outreach_status", sa.Text(), nullable=False, server_default=sa.text("'new'")),
        sa.Column(
            "duration_available", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("last_report_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.UniqueConstraint("user_id", "channel_id", name="uq_youtube_prospects_user_channel"),
    )
    op.create_index(
        "ix_youtube_prospects_user_created",
        "youtube_prospects",
        ["user_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "youtube_prospect_reports",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "prospect_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("youtube_prospects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("weeks", sa.Integer()),
        sa.Column("model", sa.Text()),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index(
        "ix_youtube_prospect_reports_prospect_kind",
        "youtube_prospect_reports",
        ["prospect_id", "kind", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_youtube_prospect_reports_user",
        "youtube_prospect_reports",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_youtube_prospect_reports_user", table_name="youtube_prospect_reports")
    op.drop_index(
        "ix_youtube_prospect_reports_prospect_kind", table_name="youtube_prospect_reports"
    )
    op.drop_table("youtube_prospect_reports")
    op.drop_index("ix_youtube_prospects_user_created", table_name="youtube_prospects")
    op.drop_table("youtube_prospects")
