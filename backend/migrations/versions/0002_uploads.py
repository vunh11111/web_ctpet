"""Durable offsets for bounded, retriable chunk uploads."""
from alembic import op
import sqlalchemy as sa
revision = "0002"
down_revision = "0001"
branch_labels = depends_on = None


def upgrade():
    op.create_table("uploads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("offset", sa.BigInteger(), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("model_label", sa.String(160), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.drop_table("uploads")
