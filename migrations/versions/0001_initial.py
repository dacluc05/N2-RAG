"""Initial MySQL schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None


def upgrade():
    options = {"mysql_charset":"utf8mb4","mysql_engine":"InnoDB"}
    op.create_table("research_runs",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("fingerprint",sa.String(64),unique=True),
        sa.Column("ticker",sa.String(12),nullable=False),
        sa.Column("as_of",sa.Date(),nullable=False),
        sa.Column("request",sa.JSON(),nullable=False),
        sa.Column("status",sa.String(20),nullable=False),
        sa.Column("created_at",sa.DateTime(),nullable=False),
        sa.Column("lease_until",sa.DateTime()), **options)
    op.create_index("ix_run_history","research_runs",["ticker","created_at"])
    op.create_table("pipeline_events",sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("run_id",sa.String(36),sa.ForeignKey("research_runs.id",ondelete="CASCADE"),nullable=False),
        sa.Column("status",sa.String(20),nullable=False),sa.Column("message",sa.Text(),nullable=False),
        sa.Column("created_at",sa.DateTime(),nullable=False), **options)
    op.create_index("ix_pipeline_events_run_id","pipeline_events",["run_id"])
    op.create_table("companies",sa.Column("cik",sa.Integer(),primary_key=True,autoincrement=False),
        sa.Column("payload",sa.JSON(),nullable=False), **options)
    op.create_table("analysis_reports",
        sa.Column("run_id",sa.String(36),sa.ForeignKey("research_runs.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("cik",sa.Integer(),sa.ForeignKey("companies.cik"),nullable=False),
        sa.Column("payload",sa.JSON(),nullable=False), **options)
    op.create_index("ix_analysis_reports_cik","analysis_reports",["cik"])
    op.create_table("analysis_claims",
        sa.Column("run_id",sa.String(36),sa.ForeignKey("analysis_reports.run_id",ondelete="CASCADE"),primary_key=True),
        sa.Column("claim_id",sa.String(24),primary_key=True),
        sa.Column("status",sa.String(24),nullable=False),sa.Column("payload",sa.JSON(),nullable=False), **options)
    op.create_table("document_chunks",
        sa.Column("run_id",sa.String(36),sa.ForeignKey("analysis_reports.run_id",ondelete="CASCADE"),primary_key=True),
        sa.Column("evidence_id",sa.String(64),primary_key=True),
        sa.Column("document_id",sa.String(64),nullable=False),sa.Column("payload",sa.JSON(),nullable=False), **options)
    op.create_index("ix_document_chunks_document_id","document_chunks",["document_id"])
    op.create_table("claim_evidence",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("run_id",sa.String(36),sa.ForeignKey("analysis_reports.run_id",ondelete="CASCADE"),nullable=False),
        sa.Column("claim_id",sa.String(24),nullable=False),sa.Column("evidence_id",sa.String(64),nullable=False),
        sa.Column("relation",sa.String(12),nullable=False),
        sa.UniqueConstraint("run_id","claim_id","evidence_id","relation"), **options)
    op.create_index("ix_claim_evidence_run_id","claim_evidence",["run_id"])
    op.create_table("user_feedback",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("run_id",sa.String(36),sa.ForeignKey("analysis_reports.run_id",ondelete="CASCADE"),nullable=False),
        sa.Column("score",sa.Integer(),nullable=False),sa.Column("note",sa.Text(),nullable=False),
        sa.Column("created_at",sa.DateTime(),nullable=False), **options)
    op.create_index("ix_user_feedback_run_id","user_feedback",["run_id"])


def downgrade():
    for name in ("user_feedback","claim_evidence","document_chunks","analysis_claims",
                 "analysis_reports","companies","pipeline_events","research_runs"):
        op.drop_table(name)
