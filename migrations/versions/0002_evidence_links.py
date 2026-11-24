"""Enforce claim and evidence identity within a research run."""
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_foreign_key("fk_evidence_link_claim","claim_evidence","analysis_claims",
                          ["run_id","claim_id"],["run_id","claim_id"],ondelete="CASCADE")
    op.create_foreign_key("fk_evidence_link_chunk","claim_evidence","document_chunks",
                          ["run_id","evidence_id"],["run_id","evidence_id"],ondelete="CASCADE")


def downgrade():
    for key in ("fk_evidence_link_chunk","fk_evidence_link_claim"):
        op.drop_constraint(key,"claim_evidence",type_="foreignkey")
