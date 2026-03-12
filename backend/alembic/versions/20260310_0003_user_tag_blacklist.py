"""user tag blacklist

Revision ID: 20260310_0003
Revises: 20260310_0002
Create Date: 2026-03-10 16:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260310_0003"
down_revision = "20260310_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tag_blacklist", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("users", "tag_blacklist")
