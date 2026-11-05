"""Initial durable job queue and artifact metadata."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    op.create_table("jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("input_bytes", sa.BigInteger(), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False),
        sa.Column("model_label", sa.String(160), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("lease_owner", sa.String(64)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('queued','preparing','running','completed','failed')", name="job_status"),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="job_progress"))
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_lease_until", "jobs", ["lease_until"])


def downgrade():
    op.drop_table("jobs")
