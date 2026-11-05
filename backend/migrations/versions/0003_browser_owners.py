"""Keep browser sessions separate when the login screen is disabled."""
from alembic import op
import sqlalchemy as sa
revision = "0003"
down_revision = "0002"
branch_labels = depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("owner", sa.String(80), nullable=True))
    op.add_column("uploads", sa.Column("owner", sa.String(80), nullable=True))


def downgrade():
    op.drop_column("jobs", "owner")
    op.drop_column("uploads", "owner")
