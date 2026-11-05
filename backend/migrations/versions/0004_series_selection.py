"""Pause jobs while the doctor chooses a CT series."""
from alembic import op
revision = "0004"
down_revision = "0003"
branch_labels = depends_on = None


def upgrade():
    op.drop_constraint("job_status", "jobs", type_="check")
    op.create_check_constraint("job_status", "jobs", "status IN ('queued','preparing','running','completed','failed','awaiting_selection')")


def downgrade():
    op.execute("UPDATE jobs SET status='failed' WHERE status='awaiting_selection'")
    op.drop_constraint("job_status", "jobs", type_="check")
    op.create_check_constraint("job_status", "jobs", "status IN ('queued','preparing','running','completed','failed')")
