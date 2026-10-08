"""Hybrid analysis, source declaration, and persisted document language."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "92ba21b05a74"
down_revision = "7de0fd201813"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "documents",
        sa.Column("document_kind", sa.String(20), nullable=False, server_default="synthetic"),
    )
    op.create_check_constraint(
        "document_kind", "documents", "document_kind IN ('synthetic', 'real')"
    )
    op.add_column(
        "analysis_results",
        sa.Column("language", sa.String(20), nullable=False, server_default="english"),
    )
    op.add_column(
        "analysis_results",
        sa.Column("ai_review_status", sa.String(20), nullable=False, server_default="not_run"),
    )
    op.add_column("analysis_results", sa.Column("ai_overall_score", sa.Integer(), nullable=True))
    op.add_column("analysis_results", sa.Column("ai_rubric_version", sa.String(20), nullable=True))
    op.create_check_constraint(
        "analysis_language", "analysis_results", "language IN ('english', 'german')"
    )
    op.create_check_constraint(
        "ai_review_status", "analysis_results", "ai_review_status IN ('not_run', 'completed')"
    )
    op.create_check_constraint(
        "ai_overall_score_range", "analysis_results", "ai_overall_score BETWEEN 1 AND 5"
    )
    op.create_table(
        "ai_findings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.Uuid(),
            sa.ForeignKey("analysis_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("related_category", sa.String(30), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("quote_verified", sa.Boolean(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("model_score", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("uncertainties", postgresql.JSONB(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("model_score BETWEEN 1 AND 5", name="ai_model_score_range"),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ai_finding_score_range"),
        sa.CheckConstraint("quote_verified OR score IS NULL", name="ai_unverified_not_scored"),
    )
    op.create_index("ix_ai_findings_analysis_id", "ai_findings", ["analysis_id"])


def downgrade():
    op.drop_table("ai_findings")
    for name in ("ai_overall_score_range", "ai_review_status", "analysis_language"):
        op.drop_constraint(name, "analysis_results", type_="check")
    for name in ("ai_rubric_version", "ai_overall_score", "ai_review_status", "language"):
        op.drop_column("analysis_results", name)
    op.drop_constraint("document_kind", "documents", type_="check")
    op.drop_column("documents", "document_kind")
