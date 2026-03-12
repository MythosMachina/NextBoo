"""bootstrap admin invite support

Revision ID: 20260312_0010
Revises: 20260312_0009
Create Date: 2026-03-12 11:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260312_0010"
down_revision = "20260312_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("user_invites", "email", existing_type=sa.String(length=255), nullable=True)
    op.alter_column("user_invites", "inviter_user_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("user_invites", sa.Column("granted_role", sa.Enum("admin", "moderator", "uploader", name="user_role"), nullable=True))
    op.add_column("user_invites", sa.Column("grant_can_upload", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user_invites", sa.Column("grant_can_view_explicit", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user_invites", sa.Column("grant_invite_quota", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_invites", "grant_invite_quota")
    op.drop_column("user_invites", "grant_can_view_explicit")
    op.drop_column("user_invites", "grant_can_upload")
    op.drop_column("user_invites", "granted_role")
    op.alter_column("user_invites", "inviter_user_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("user_invites", "email", existing_type=sa.String(length=255), nullable=False)
