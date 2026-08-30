"""instagram snapshot: per-range stats and fetch coverage

The snapshot carried one ``stats_json`` blob, which is why
``/stats?time_range=`` was accepted and then ignored — 7 days, 30 days and
all-time all read the same row. ``stats_by_range_json`` holds the whole set the
sync now computes, and ``coverage_json`` records what that fetch could see
(how many of the account's posts were paginated, how many carry insights) so
the achievements page can tell a lifetime total from a partial sample instead
of presenting either as fact.

Revision ID: d51c8ab37f04
Revises: c066c437910e
Create Date: 2026-08-24 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd51c8ab37f04'
down_revision: str | None = 'c066c437910e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default so the rows already in the table stay readable: an older
    # snapshot simply has no per-range breakdown, and the cache falls back to
    # its single stats blob for the default range.
    op.add_column(
        "instagram_snapshots",
        sa.Column(
            "stats_by_range_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "instagram_snapshots",
        sa.Column(
            "coverage_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("instagram_snapshots", "coverage_json")
    op.drop_column("instagram_snapshots", "stats_by_range_json")
