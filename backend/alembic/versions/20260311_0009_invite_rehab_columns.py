"""invite rehab columns

Revision ID: 20260311_0009
Revises: 20260310_0008
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0009"
down_revision = "20260310_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_invites", sa.Column("rehabilitated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_invites", sa.Column("rehabilitated_by_user_id", sa.Integer(), nullable=True))
    op.create_index("ix_user_invites_rehabilitated_by_user_id", "user_invites", ["rehabilitated_by_user_id"])
    op.create_foreign_key(
        "fk_user_invites_rehabilitated_by_user_id_users",
        "user_invites",
        "users",
        ["rehabilitated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_user_invites_rehabilitated_by_user_id_users", "user_invites", type_="foreignkey")
    op.drop_index("ix_user_invites_rehabilitated_by_user_id", table_name="user_invites")
    op.drop_column("user_invites", "rehabilitated_by_user_id")
    op.drop_column("user_invites", "rehabilitated_at")
