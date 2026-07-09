"""add tokui image generation jobs

Revision ID: b8f1c2d3e4a5
Revises: a9c2d4e6f8b1
Create Date: 2026-07-05 12:20:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = "b8f1c2d3e4a5"
down_revision = "a9c2d4e6f8b1"
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
    if not _table_exists("tokui_image_generation_jobs"):
        op.create_table(
            "tokui_image_generation_jobs",
            sa.Column("id", sa.BIGINT(), autoincrement=True, nullable=False),
            sa.Column("job_bid", sa.String(length=36), nullable=False, server_default="", comment="Image generation job business identifier"),
            sa.Column("retry_of_job_bid", sa.String(length=36), nullable=False, server_default="", comment="Previous job business identifier when this is a retry"),
            sa.Column("shifu_bid", sa.String(length=36), nullable=False, server_default="", comment="Shifu business identifier"),
            sa.Column("outline_item_bid", sa.String(length=36), nullable=False, server_default="", comment="Outline item business identifier"),
            sa.Column("tokui_template_bid", sa.String(length=36), nullable=False, server_default="", comment="Draft TokUI template business identifier"),
            sa.Column("created_user_bid", sa.String(length=36), nullable=False, server_default="", comment="Creator user business identifier"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="queued", comment="Job status"),
            sa.Column("teacher_prompt", mysql.LONGTEXT(), nullable=False, comment="Teacher image prompt"),
            sa.Column("optimized_prompt", mysql.LONGTEXT(), nullable=False, comment="LLM optimized image prompt"),
            sa.Column("final_provider_prompt", mysql.LONGTEXT(), nullable=False, comment="Prompt sent to image provider"),
            sa.Column("prompt_optimization_status", sa.String(length=32), nullable=False, server_default="pending", comment="Prompt optimization status"),
            sa.Column("prompt_optimization_error", sa.Text(), nullable=False, comment="Prompt optimization error"),
            sa.Column("prompt_optimizer_model", sa.String(length=128), nullable=False, server_default="", comment="Prompt optimizer model"),
            sa.Column("prompt_optimizer_enabled", sa.SmallInteger(), nullable=False, server_default=sa.text("1"), comment="Prompt optimizer enabled snapshot: 0=no, 1=yes"),
            sa.Column("prompt_optimizer_temperature", sa.DECIMAL(precision=4, scale=2), nullable=False, server_default=sa.text("0"), comment="Prompt optimizer temperature"),
            sa.Column("prompt_optimizer_template_snapshot", mysql.LONGTEXT(), nullable=False, comment="Prompt optimizer system prompt snapshot"),
            sa.Column("provider_base_url", sa.String(length=512), nullable=False, server_default="", comment="Image provider base URL snapshot"),
            sa.Column("provider_model", sa.String(length=128), nullable=False, server_default="", comment="Image provider model snapshot"),
            sa.Column("provider_size", sa.String(length=64), nullable=False, server_default="", comment="Image provider size snapshot"),
            sa.Column("provider_timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("120"), comment="Image provider timeout snapshot"),
            sa.Column("candidate_count", sa.Integer(), nullable=False, server_default=sa.text("3"), comment="Number of image candidates requested"),
            sa.Column("selected_candidate_bid", sa.String(length=36), nullable=False, server_default="", comment="Selected image candidate business identifier"),
            sa.Column("error_message", sa.Text(), nullable=False, comment="Job error message"),
            sa.Column("deleted", sa.SmallInteger(), nullable=False, server_default=sa.text("0"), comment="Deletion flag: 0=active, 1=deleted"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Creation timestamp"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Last update timestamp"),
            sa.PrimaryKeyConstraint("id"),
            comment="TokUI teacher image generation jobs",
        )
        op.create_index("ix_tokui_image_job_bid", "tokui_image_generation_jobs", ["job_bid"], unique=False)
        op.create_index("ix_tokui_image_job_outline_active", "tokui_image_generation_jobs", ["shifu_bid", "outline_item_bid", "deleted"], unique=False)
        op.create_index("ix_tokui_image_job_creator_time", "tokui_image_generation_jobs", ["created_user_bid", "created_at"], unique=False)
        op.create_index("ix_tokui_image_job_retry_of", "tokui_image_generation_jobs", ["retry_of_job_bid"], unique=False)

    if not _table_exists("tokui_image_generation_candidates"):
        op.create_table(
            "tokui_image_generation_candidates",
            sa.Column("id", sa.BIGINT(), autoincrement=True, nullable=False),
            sa.Column("candidate_bid", sa.String(length=36), nullable=False, server_default="", comment="Candidate business identifier"),
            sa.Column("job_bid", sa.String(length=36), nullable=False, server_default="", comment="Image generation job business identifier"),
            sa.Column("candidate_index", sa.Integer(), nullable=False, server_default=sa.text("0"), comment="Candidate index in the job"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="queued", comment="Candidate status"),
            sa.Column("resource_id", sa.String(length=36), nullable=False, server_default="", comment="Stored Resource identifier"),
            sa.Column("resource_url", sa.String(length=1024), nullable=False, server_default="", comment="Stored image URL"),
            sa.Column("title", sa.String(length=255), nullable=False, server_default="", comment="Candidate title"),
            sa.Column("description", sa.Text(), nullable=False, comment="Candidate description"),
            sa.Column("provider_payload_json", mysql.LONGTEXT(), nullable=False, comment="Provider payload summary JSON"),
            sa.Column("error_message", sa.Text(), nullable=False, comment="Candidate generation error"),
            sa.Column("selected", sa.SmallInteger(), nullable=False, server_default=sa.text("0"), comment="Selected flag"),
            sa.Column("deleted", sa.SmallInteger(), nullable=False, server_default=sa.text("0"), comment="Deletion flag: 0=active, 1=deleted"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Creation timestamp"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="Last update timestamp"),
            sa.PrimaryKeyConstraint("id"),
            comment="TokUI teacher image generation candidates",
        )
        op.create_index("ix_tokui_image_candidate_bid", "tokui_image_generation_candidates", ["candidate_bid"], unique=False)
        op.create_index("ix_tokui_image_candidate_job_index", "tokui_image_generation_candidates", ["job_bid", "candidate_index"], unique=False)
        op.create_index("ix_tokui_image_candidate_job_status", "tokui_image_generation_candidates", ["job_bid", "status", "deleted"], unique=False)


def downgrade():
    _drop_table_if_exists("tokui_image_generation_candidates")
    _drop_table_if_exists("tokui_image_generation_jobs")
