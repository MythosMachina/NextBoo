"""questionable visibility preference

Revision ID: 20260310_0007
Revises: 20260310_0006
Create Date: 2026-03-10 20:10:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_0007"
down_revision: str | None = "20260310_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("can_view_questionable", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("users", "can_view_questionable")
