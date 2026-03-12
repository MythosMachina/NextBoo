"""social gate invites and strikes

Revision ID: 20260310_0008
Revises: 20260310_0007
Create Date: 2026-03-10 18:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260310_0008"
down_revision: str | None = "20260310_0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


invite_status = sa.Enum("pending", "accepted", "revoked", name="invite_status")
strike_source_type = sa.Enum("manual", "invitee_ban", "threshold_auto_ban", name="strike_source_type")


def upgrade() -> None:
    op.add_column("users", sa.Column("invited_by_user_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("invite_quota", sa.Integer(), nullable=False, server_default="2"))
    op.create_foreign_key(
        op.f("fk_users_invited_by_user_id_users"),
        "users",
        "users",
        ["invited_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    invite_status.create(op.get_bind(), checkfirst=True)
    strike_source_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "user_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", invite_status, nullable=False, server_default="pending"),
        sa.Column("inviter_user_id", sa.Integer(), nullable=False),
        sa.Column("invited_user_id", sa.Integer(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["invited_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inviter_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_invites")),
    )
    op.create_index(op.f("ix_user_invites_code"), "user_invites", ["code"], unique=True)
    op.create_index(op.f("ix_user_invites_email"), "user_invites", ["email"], unique=False)
    op.create_index(op.f("ix_user_invites_invited_user_id"), "user_invites", ["invited_user_id"], unique=False)
    op.create_index(op.f("ix_user_invites_inviter_user_id"), "user_invites", ["inviter_user_id"], unique=False)

    op.create_table(
        "user_strikes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=False),
        sa.Column("issued_by_user_id", sa.Integer(), nullable=True),
        sa.Column("related_user_id", sa.Integer(), nullable=True),
        sa.Column("source", strike_source_type, nullable=False, server_default="manual"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_strikes")),
    )
    op.create_index(op.f("ix_user_strikes_target_user_id"), "user_strikes", ["target_user_id"], unique=False)
    op.create_index(op.f("ix_user_strikes_issued_by_user_id"), "user_strikes", ["issued_by_user_id"], unique=False)
    op.create_index(op.f("ix_user_strikes_related_user_id"), "user_strikes", ["related_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_strikes_related_user_id"), table_name="user_strikes")
    op.drop_index(op.f("ix_user_strikes_issued_by_user_id"), table_name="user_strikes")
    op.drop_index(op.f("ix_user_strikes_target_user_id"), table_name="user_strikes")
    op.drop_table("user_strikes")
    op.drop_index(op.f("ix_user_invites_inviter_user_id"), table_name="user_invites")
    op.drop_index(op.f("ix_user_invites_invited_user_id"), table_name="user_invites")
    op.drop_index(op.f("ix_user_invites_email"), table_name="user_invites")
    op.drop_index(op.f("ix_user_invites_code"), table_name="user_invites")
    op.drop_table("user_invites")
    op.drop_constraint(op.f("fk_users_invited_by_user_id_users"), "users", type_="foreignkey")
    op.drop_column("users", "invite_quota")
    op.drop_column("users", "invited_by_user_id")

    bind = op.get_bind()
    invite_status.drop(bind, checkfirst=True)
    strike_source_type.drop(bind, checkfirst=True)
