"""user admin actions

Revision ID: 20260310_0005
Revises: 20260310_0004
Create Date: 2026-03-10 17:40:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260310_0005"
down_revision = "20260310_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_banned", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "banned_emails",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("banned_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_banned_emails_email", "banned_emails", ["email"])


def downgrade() -> None:
    op.drop_index("ix_banned_emails_email", table_name="banned_emails")
    op.drop_table("banned_emails")
    op.drop_column("users", "is_banned")
