"""Initial schema for proposal history.

Revision ID: 001
Revises:
Create Date: 2025-11-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create proposal_history table."""
    op.create_table(
        "proposal_history",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("profile_id", sa.String(length=100), nullable=False),
        sa.Column("job_title", sa.String(length=300), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=False),
        sa.Column("job_summary", sa.String(length=500), nullable=False),
        sa.Column("proposal_text", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("matched_skills", sa.JSON(), nullable=False),
        sa.Column("relevant_projects", sa.JSON(), nullable=False),
        sa.Column("skill_match_percentage", sa.Float(), nullable=False),
        sa.Column("budget_alignment", sa.String(length=50), nullable=False),
        sa.Column("timeline_feasibility", sa.String(length=50), nullable=False),
        sa.Column("budget_range", sa.String(length=100), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("retrieval_chunks", sa.Integer(), nullable=False),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_confidence", "proposal_history", ["confidence_score"])
    op.create_index("idx_profile_created", "proposal_history", ["profile_id", "created_at"])
    op.create_index(op.f("ix_proposal_history_created_at"), "proposal_history", ["created_at"])
    op.create_index(op.f("ix_proposal_history_profile_id"), "proposal_history", ["profile_id"])


def downgrade() -> None:
    """Drop proposal_history table."""
    op.drop_index(op.f("ix_proposal_history_profile_id"), table_name="proposal_history")
    op.drop_index(op.f("ix_proposal_history_created_at"), table_name="proposal_history")
    op.drop_index("idx_profile_created", table_name="proposal_history")
    op.drop_index("idx_confidence", table_name="proposal_history")
    op.drop_table("proposal_history")
