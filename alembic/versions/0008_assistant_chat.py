"""assistant chat: conversations, messages and confirmable actions

Backs the centralized assistant — the chat surface that answers "aaj kya post
karna hai?" from the user's own planner rows.

Three tables. ``assistant_conversations`` and ``assistant_messages`` are ordinary
chat history. ``assistant_actions`` is the interesting one: it is not a log, it
is a **capability store**. The assistant never writes planner data directly; it
proposes an action, which lands here as a ``proposed`` row, and only a request
naming that row's id can execute it. The row is therefore single-use (``status``
gates re-execution), expiring (``expires_at``), and tenant-scoped (``user_id`` in
the WHERE clause of every fetch). The CHECK constraints are real rather than
Pydantic-only — unlike ``plan_items.production_status`` — because the verb and
status sets are closed and the executor branches on them exhaustively.

Also creates ``ix_plan_item_content_user_review``. That index belongs to this
migration rather than a separate one because the assistant introduces the first
user-wide read of ``plan_item_content``: every existing query scopes by
``item_id`` and is served by ``ix_plan_item_content_item_created``, which has no
leading ``user_id``. Without the new index, "what's pending review?" is a
sequential scan of a table shared by every tenant.

``downgrade`` drops all of it. Chat history is genuinely discardable — it is a
transcript of answers derived from planner rows that still exist, not a source of
record — so there is nothing here to preserve on the way back down.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-23 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'assistant_conversations',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_assistant_conversations_user_id_users'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_assistant_conversations')),
    )
    op.create_index(
        'ix_assistant_conversations_user_updated',
        'assistant_conversations',
        ['user_id', sa.literal_column('updated_at DESC')],
        unique=False,
    )

    op.create_table(
        'assistant_messages',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('conversation_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f('ck_assistant_messages_role')),
        sa.ForeignKeyConstraint(
            ['conversation_id'], ['assistant_conversations.id'],
            name=op.f('fk_assistant_messages_conversation_id_assistant_conversations'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_assistant_messages_user_id_users'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_assistant_messages')),
    )
    # `id` is a tiebreaker, not decoration: a question and its answer are written
    # in one transaction and can share now() to the microsecond, which would make
    # the replayed transcript order non-deterministic.
    op.create_index(
        'ix_assistant_messages_conv_created',
        'assistant_messages',
        ['conversation_id', 'created_at', 'id'],
        unique=False,
    )

    op.create_table(
        'assistant_actions',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('message_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('item_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('content_id', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('verb', sa.Text(), nullable=False),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('status', sa.Text(), server_default=sa.text("'proposed'"), nullable=False),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "verb IN ('mark_published', 'reschedule', 'generate_content', "
            "'approve_draft', 'reject_draft')",
            name=op.f('ck_assistant_actions_verb'),
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'executing', 'executed', 'cancelled', "
            "'failed', 'expired')",
            name=op.f('ck_assistant_actions_status'),
        ),
        # Ties target to verb, so a malformed row is impossible even by direct
        # SQL: review verbs carry a content_id, the other three never do.
        sa.CheckConstraint(
            "(verb IN ('approve_draft', 'reject_draft')) = (content_id IS NOT NULL)",
            name=op.f('ck_assistant_actions_target_valid'),
        ),
        sa.ForeignKeyConstraint(
            ['message_id'], ['assistant_messages.id'],
            name=op.f('fk_assistant_actions_message_id_assistant_messages'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_assistant_actions_user_id_users'), ondelete='CASCADE',
        ),
        # CASCADE so deleting the item vaporizes a pending capability rather
        # than leaving one pointing at a tombstone.
        sa.ForeignKeyConstraint(
            ['item_id'], ['plan_items.id'],
            name=op.f('fk_assistant_actions_item_id_plan_items'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['content_id'], ['plan_item_content.id'],
            name=op.f('fk_assistant_actions_content_id_plan_item_content'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_assistant_actions')),
    )
    op.create_index(
        'ix_assistant_actions_user_status',
        'assistant_actions',
        ['user_id', 'status', sa.literal_column('created_at DESC')],
        unique=False,
    )

    # The assistant is the first user-wide reader of plan_item_content; the
    # existing ix_plan_item_content_item_created leads with item_id and cannot
    # serve it.
    op.create_index(
        'ix_plan_item_content_user_review',
        'plan_item_content',
        ['user_id', 'review_status', sa.literal_column('created_at DESC')],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_plan_item_content_user_review', table_name='plan_item_content')

    op.drop_index('ix_assistant_actions_user_status', table_name='assistant_actions')
    op.drop_table('assistant_actions')

    op.drop_index('ix_assistant_messages_conv_created', table_name='assistant_messages')
    op.drop_table('assistant_messages')

    op.drop_index('ix_assistant_conversations_user_updated', table_name='assistant_conversations')
    op.drop_table('assistant_conversations')
