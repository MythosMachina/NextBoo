"""moderation tables

Revision ID: 20260310_0002
Revises: 20260310_0001
Create Date: 2026-03-10 15:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260310_0002"
down_revision = "20260310_0001"
branch_labels = None
depends_on = None


visibility_status = sa.Enum("visible", "hidden", "deleted", name="visibility_status")
report_reason = sa.Enum("wrong_rating", "bad_tags", "duplicate", "illegal_content", "other", name="report_reason")
report_status = sa.Enum("open", "in_review", "resolved", "rejected", name="report_status")


def upgrade() -> None:
    bind = op.get_bind()
    visibility_status.create(bind, checkfirst=True)
    report_reason.create(bind, checkfirst=True)
    report_status.create(bind, checkfirst=True)

    op.create_table(
        "image_moderation",
        sa.Column("image_id", sa.String(length=36), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visibility_status", visibility_status, nullable=False, server_default="visible"),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("acted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("image_id"),
    )
    op.create_index("ix_image_moderation_visibility_status", "image_moderation", ["visibility_status"])

    op.create_table(
        "image_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("image_id", sa.String(length=36), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reported_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", report_reason, nullable=False, server_default="other"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", report_status, nullable=False, server_default="open"),
        sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_image_reports_image_id", "image_reports", ["image_id"])
    op.create_index("ix_image_reports_status", "image_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_image_reports_status", table_name="image_reports")
    op.drop_index("ix_image_reports_image_id", table_name="image_reports")
    op.drop_table("image_reports")
    op.drop_index("ix_image_moderation_visibility_status", table_name="image_moderation")
    op.drop_table("image_moderation")

    report_status.drop(op.get_bind(), checkfirst=True)
    report_reason.drop(op.get_bind(), checkfirst=True)
    visibility_status.drop(op.get_bind(), checkfirst=True)
