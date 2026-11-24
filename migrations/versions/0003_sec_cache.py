"""Share processed SEC sources across research runs."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"


def upgrade():
    op.create_table(
        "sec_source_cache",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("stored_at", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("sec_source_cache")
