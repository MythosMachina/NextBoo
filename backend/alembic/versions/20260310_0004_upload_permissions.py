"""upload permissions

Revision ID: 20260310_0004
Revises: 20260310_0003
Create Date: 2026-03-10 17:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260310_0004"
down_revision = "20260310_0003"
branch_labels = None
depends_on = None


upload_request_status = sa.Enum("pending", "approved", "rejected", name="upload_request_status")


def upgrade() -> None:
    bind = op.get_bind()
    upload_request_status.create(bind, checkfirst=True)
    op.add_column("users", sa.Column("can_upload", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "upload_permission_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_focus", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", upload_request_status, nullable=False, server_default="pending"),
        sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_upload_permission_requests_user_id", "upload_permission_requests", ["user_id"])
    op.create_index("ix_upload_permission_requests_status", "upload_permission_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_upload_permission_requests_status", table_name="upload_permission_requests")
    op.drop_index("ix_upload_permission_requests_user_id", table_name="upload_permission_requests")
    op.drop_table("upload_permission_requests")
    op.drop_column("users", "can_upload")
    upload_request_status.drop(op.get_bind(), checkfirst=True)
