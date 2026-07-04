"""add tokui templates and learner runtime tables

Revision ID: a9c2d4e6f8b1
Revises: d4e5f6a7b8c9
Create Date: 2026-07-04 01:10:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = "a9c2d4e6f8b1"
down_revision = "d4e5f6a7b8c9"
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
    if not _table_exists("shifu_draft_tokui_templates"):
        op.create_table(
            "shifu_draft_tokui_templates",
            sa.Column("id", sa.BIGINT(), autoincrement=True, nullable=False),
            sa.Column("tokui_template_bid", sa.String(length=36), nullable=False, server_default="", comment="TokUI template business identifier"),
            sa.Column("shifu_bid", sa.String(length=36), nullable=False, server_default="", comment="Shifu business identifier"),
            sa.Column("outline_item_bid", sa.String(length=36), nullable=False, server_default="", comment="Outline item business identifier"),
            sa.Column("teacher_intent", sa.Text(), nullable=False, comment="Teacher intent"),
            sa.Column("prompt_template", mysql.LONGTEXT(), nullable=False, comment="Teacher prompt template"),
            sa.Column("concept", sa.String(length=255), nullable=False, server_default="", comment="Concept"),
            sa.Column("audience", sa.String(length=255), nullable=False, server_default="", comment="Audience"),
            sa.Column("material_refs", mysql.LONGTEXT(), nullable=False, comment="Material references JSON"),
            sa.Column("media_refs", mysql.LONGTEXT(), nullable=False, comment="Media references JSON"),
            sa.Column("generation_options", mysql.LONGTEXT(), nullable=False, comment="Generation options JSON"),
            sa.Column("context_policy", mysql.LONGTEXT(), nullable=False, comment="Learner context policy JSON"),
            sa.Column("preview_dsl", mysql.LONGTEXT(), nullable=False, comment="Latest teacher preview TokUI DSL"),
            sa.Column("preview_interaction_schema", mysql.LONGTEXT(), nullable=False, comment="Latest teacher preview interaction schema JSON"),
            sa.Column("preview_generation_status", sa.String(length=32), nullable=False, server_default="idle", comment="Preview generation status"),
            sa.Column("preview_validation_status", sa.String(length=32), nullable=False, server_default="unvalidated", comment="Preview validation status"),
            sa.Column("preview_validation_error", mysql.LONGTEXT(), nullable=False, comment="Preview validation error JSON"),
            sa.Column("preview_parser_version", sa.String(length=64), nullable=False, server_default="", comment="TokUI parser version"),
            sa.Column("template_hash", sa.String(length=64), nullable=False, server_default="", comment="Template hash"),
            sa.Column("deleted", sa.SmallInteger(), nullable=False, server_default=sa.text("0"), comment="Deletion flag: 0=active, 1=deleted"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Creation timestamp"),
            sa.Column("created_user_bid", sa.String(length=36), nullable=False, server_default="", comment="Creator user business identifier"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Last update timestamp"),
            sa.Column("updated_user_bid", sa.String(length=36), nullable=False, server_default="", comment="Last updater user business identifier"),
            sa.PrimaryKeyConstraint("id"),
            comment="Draft TokUI generation templates",
        )
        op.create_index("ix_draft_tokui_template_outline_active", "shifu_draft_tokui_templates", ["shifu_bid", "outline_item_bid", "deleted"], unique=False)
        op.create_index("ix_shifu_draft_tokui_templates_tokui_template_bid", "shifu_draft_tokui_templates", ["tokui_template_bid"], unique=False)
        op.create_index("ix_shifu_draft_tokui_templates_template_hash", "shifu_draft_tokui_templates", ["template_hash"], unique=False)

    if not _table_exists("shifu_published_tokui_templates"):
        op.create_table(
            "shifu_published_tokui_templates",
            sa.Column("id", sa.BIGINT(), autoincrement=True, nullable=False),
            sa.Column("published_template_bid", sa.String(length=36), nullable=False, server_default="", comment="Published TokUI template business identifier"),
            sa.Column("source_draft_template_bid", sa.String(length=36), nullable=False, server_default="", comment="Source draft TokUI template business identifier"),
            sa.Column("shifu_bid", sa.String(length=36), nullable=False, server_default="", comment="Shifu business identifier"),
            sa.Column("outline_item_bid", sa.String(length=36), nullable=False, server_default="", comment="Outline item business identifier"),
            sa.Column("teacher_intent", sa.Text(), nullable=False, comment="Teacher intent"),
            sa.Column("prompt_template", mysql.LONGTEXT(), nullable=False, comment="Teacher prompt template"),
            sa.Column("concept", sa.String(length=255), nullable=False, server_default="", comment="Concept"),
            sa.Column("audience", sa.String(length=255), nullable=False, server_default="", comment="Audience"),
            sa.Column("material_refs", mysql.LONGTEXT(), nullable=False, comment="Material references JSON"),
            sa.Column("media_refs", mysql.LONGTEXT(), nullable=False, comment="Media references JSON"),
            sa.Column("generation_options", mysql.LONGTEXT(), nullable=False, comment="Generation options JSON"),
            sa.Column("context_policy", mysql.LONGTEXT(), nullable=False, comment="Learner context policy JSON"),
            sa.Column("preview_dsl", mysql.LONGTEXT(), nullable=False, comment="Teacher preview sample TokUI DSL"),
            sa.Column("preview_interaction_schema", mysql.LONGTEXT(), nullable=False, comment="Teacher preview interaction schema JSON"),
            sa.Column("template_hash", sa.String(length=64), nullable=False, server_default="", comment="Template hash"),
            sa.Column("template_version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="Published template version"),
            sa.Column("published_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Published timestamp"),
            sa.Column("published_user_bid", sa.String(length=36), nullable=False, server_default="", comment="Publisher user business identifier"),
            sa.Column("deleted", sa.SmallInteger(), nullable=False, server_default=sa.text("0"), comment="Deletion flag: 0=active, 1=deleted"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Creation timestamp"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Last update timestamp"),
            sa.PrimaryKeyConstraint("id"),
            comment="Published TokUI generation template snapshots",
        )
        op.create_index("ix_published_tokui_template_outline_active", "shifu_published_tokui_templates", ["shifu_bid", "outline_item_bid", "deleted"], unique=False)
        op.create_index("ix_published_tokui_template_hash_active", "shifu_published_tokui_templates", ["published_template_bid", "template_hash", "deleted"], unique=False)
        op.create_index("ix_shifu_published_tokui_templates_template_hash", "shifu_published_tokui_templates", ["template_hash"], unique=False)

    if not _table_exists("learn_tokui_artifacts"):
        op.create_table(
            "learn_tokui_artifacts",
            sa.Column("id", sa.BIGINT(), autoincrement=True, nullable=False),
            sa.Column("tokui_artifact_bid", sa.String(length=36), nullable=False, server_default="", comment="TokUI artifact business identifier"),
            sa.Column("published_template_bid", sa.String(length=36), nullable=False, server_default="", comment="Published TokUI template business identifier"),
            sa.Column("template_hash", sa.String(length=64), nullable=False, server_default="", comment="Template hash"),
            sa.Column("shifu_bid", sa.String(length=36), nullable=False, server_default="", comment="Shifu business identifier"),
            sa.Column("outline_item_bid", sa.String(length=36), nullable=False, server_default="", comment="Outline item business identifier"),
            sa.Column("progress_record_bid", sa.String(length=36), nullable=False, server_default="", comment="Learn progress record business identifier"),
            sa.Column("user_bid", sa.String(length=36), nullable=False, server_default="", comment="User business identifier"),
            sa.Column("context_hash", sa.String(length=64), nullable=False, server_default="", comment="Context hash"),
            sa.Column("dsl", mysql.LONGTEXT(), nullable=False, comment="Generated TokUI DSL"),
            sa.Column("interaction_schema", mysql.LONGTEXT(), nullable=False, comment="Interaction schema JSON"),
            sa.Column("generation_status", sa.String(length=32), nullable=False, server_default="pending", comment="Generation status"),
            sa.Column("validation_status", sa.String(length=32), nullable=False, server_default="unvalidated", comment="Validation status"),
            sa.Column("validation_error", mysql.LONGTEXT(), nullable=False, comment="Validation error JSON"),
            sa.Column("parser_version", sa.String(length=64), nullable=False, server_default="", comment="TokUI parser version"),
            sa.Column("repair_attempted", sa.SmallInteger(), nullable=False, server_default=sa.text("0"), comment="Repair attempted flag"),
            sa.Column("fallback_text", sa.Text(), nullable=False, comment="Learner fallback explanation"),
            sa.Column("deleted", sa.SmallInteger(), nullable=False, server_default=sa.text("0"), comment="Deletion flag: 0=active, 1=deleted"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Creation timestamp"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Last update timestamp"),
            sa.PrimaryKeyConstraint("id"),
            comment="Learner TokUI runtime artifacts",
        )
        op.create_index("ix_learn_tokui_artifact_reuse", "learn_tokui_artifacts", ["user_bid", "progress_record_bid", "template_hash", "deleted", "validation_status"], unique=False)
        op.create_index("ix_learn_tokui_artifacts_tokui_artifact_bid", "learn_tokui_artifacts", ["tokui_artifact_bid"], unique=False)
        op.create_index("ix_learn_tokui_artifacts_published_template_bid", "learn_tokui_artifacts", ["published_template_bid"], unique=False)

    if not _table_exists("learn_tokui_responses"):
        op.create_table(
            "learn_tokui_responses",
            sa.Column("id", sa.BIGINT(), autoincrement=True, nullable=False),
            sa.Column("tokui_response_bid", sa.String(length=36), nullable=False, server_default="", comment="TokUI response business identifier"),
            sa.Column("tokui_artifact_bid", sa.String(length=36), nullable=False, server_default="", comment="TokUI artifact business identifier"),
            sa.Column("published_template_bid", sa.String(length=36), nullable=False, server_default="", comment="Published TokUI template business identifier"),
            sa.Column("template_hash", sa.String(length=64), nullable=False, server_default="", comment="Template hash"),
            sa.Column("schema_hash", sa.String(length=64), nullable=False, server_default="", comment="Interaction schema hash"),
            sa.Column("shifu_bid", sa.String(length=36), nullable=False, server_default="", comment="Shifu business identifier"),
            sa.Column("outline_item_bid", sa.String(length=36), nullable=False, server_default="", comment="Outline item business identifier"),
            sa.Column("progress_record_bid", sa.String(length=36), nullable=False, server_default="", comment="Learn progress record business identifier"),
            sa.Column("user_bid", sa.String(length=36), nullable=False, server_default="", comment="User business identifier"),
            sa.Column("field_id", sa.String(length=128), nullable=False, server_default="", comment="Field id"),
            sa.Column("field_type", sa.String(length=64), nullable=False, server_default="", comment="Field type"),
            sa.Column("field_label", sa.String(length=255), nullable=False, server_default="", comment="Field label"),
            sa.Column("value_json", mysql.LONGTEXT(), nullable=False, comment="Value JSON"),
            sa.Column("submitted_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Submitted timestamp"),
            sa.Column("deleted", sa.SmallInteger(), nullable=False, server_default=sa.text("0"), comment="Deletion flag: 0=active, 1=deleted"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Creation timestamp"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Last update timestamp"),
            sa.PrimaryKeyConstraint("id"),
            comment="Learner TokUI structured responses",
        )
        op.create_index("ix_learn_tokui_response_artifact_field", "learn_tokui_responses", ["tokui_artifact_bid", "field_id", "deleted"], unique=False)
        op.create_index("ix_learn_tokui_response_progress", "learn_tokui_responses", ["user_bid", "progress_record_bid", "template_hash", "deleted"], unique=False)
        op.create_index("ix_learn_tokui_responses_schema_hash", "learn_tokui_responses", ["schema_hash"], unique=False)


def downgrade():
    _drop_table_if_exists("learn_tokui_responses")
    _drop_table_if_exists("learn_tokui_artifacts")
    _drop_table_if_exists("shifu_published_tokui_templates")
    _drop_table_if_exists("shifu_draft_tokui_templates")
