"""add memories table

Revision ID: 20260430_120000
Revises: 20260429_223500
Create Date: 2026-04-30 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260430_120000"
down_revision = "20260429_223500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("scope", sa.String(length=50), nullable=False, server_default="companion"),
        sa.Column("memory_type", sa.String(length=50), nullable=False, server_default="episode"),
        sa.Column("content", sa.String(length=4000), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_memories_user_id", "memories", ["user_id"])
    op.create_index("ix_memories_scope", "memories", ["scope"])
    op.create_index("ix_memories_memory_type", "memories", ["memory_type"])


def downgrade() -> None:
    op.drop_index("ix_memories_memory_type", table_name="memories")
    op.drop_index("ix_memories_scope", table_name="memories")
    op.drop_index("ix_memories_user_id", table_name="memories")
    op.drop_table("memories")
