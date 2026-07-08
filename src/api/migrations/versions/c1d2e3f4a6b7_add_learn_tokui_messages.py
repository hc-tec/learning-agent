"""add learn tokui messages

Revision ID: c1d2e3f4a6b7
Revises: b8f1c2d3e4a5
Create Date: 2026-07-08 11:25:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = "c1d2e3f4a6b7"
down_revision = "b8f1c2d3e4a5"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _drop_table_if_exists(table_name: str) -> None:
    if _table_exists(table_name):
        op.drop_table(table_name)


def upgrade():
    if _table_exists("learn_tokui_messages"):
        return
    op.create_table(
        "learn_tokui_messages",
        sa.Column("id", sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("tokui_message_bid", sa.String(length=36), nullable=False, server_default="", comment="TokUI conversation message business identifier"),
        sa.Column("tokui_artifact_bid", sa.String(length=36), nullable=False, server_default="", comment="Related TokUI artifact business identifier"),
        sa.Column("published_template_bid", sa.String(length=36), nullable=False, server_default="", comment="Published TokUI template business identifier"),
        sa.Column("template_hash", sa.String(length=64), nullable=False, server_default="", comment="Template hash"),
        sa.Column("shifu_bid", sa.String(length=36), nullable=False, server_default="", comment="Shifu business identifier"),
        sa.Column("outline_item_bid", sa.String(length=36), nullable=False, server_default="", comment="Outline item business identifier"),
        sa.Column("progress_record_bid", sa.String(length=36), nullable=False, server_default="", comment="Learn progress record business identifier"),
        sa.Column("user_bid", sa.String(length=36), nullable=False, server_default="", comment="User business identifier"),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="user", comment="LLM message role: system/user/assistant"),
        sa.Column("message_type", sa.String(length=64), nullable=False, server_default="generation", comment="Message type"),
        sa.Column("content", mysql.LONGTEXT(), nullable=False, comment="Message content"),
        sa.Column("payload_json", mysql.LONGTEXT(), nullable=False, comment="Metadata JSON"),
        sa.Column("deleted", sa.SmallInteger(), nullable=False, server_default=sa.text("0"), comment="Deletion flag: 0=active, 1=deleted"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Creation timestamp"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Last update timestamp"),
        sa.PrimaryKeyConstraint("id"),
        comment="Learner TokUI LLM conversation messages",
    )
    op.create_index("ix_learn_tokui_messages_tokui_message_bid", "learn_tokui_messages", ["tokui_message_bid"], unique=False)
    op.create_index("ix_learn_tokui_message_conversation", "learn_tokui_messages", ["user_bid", "progress_record_bid", "template_hash", "deleted", "id"], unique=False)
    op.create_index("ix_learn_tokui_message_artifact", "learn_tokui_messages", ["tokui_artifact_bid", "deleted"], unique=False)
    op.create_index("ix_learn_tokui_messages_role", "learn_tokui_messages", ["role"], unique=False)
    op.create_index("ix_learn_tokui_messages_message_type", "learn_tokui_messages", ["message_type"], unique=False)


def downgrade():
    _drop_table_if_exists("learn_tokui_messages")
