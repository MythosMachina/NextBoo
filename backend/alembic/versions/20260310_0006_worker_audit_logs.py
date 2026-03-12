"""worker audit logs

Revision ID: 20260310_0006
Revises: 20260310_0005
Create Date: 2026-03-10 19:10:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260310_0006"
down_revision: str | None = "20260310_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("import_batch_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["import_batch_id"], ["imports.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_worker_audit_logs_job_id", "worker_audit_logs", ["job_id"])
    op.create_index("ix_worker_audit_logs_import_batch_id", "worker_audit_logs", ["import_batch_id"])
    op.create_index("ix_worker_audit_logs_event_type", "worker_audit_logs", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_worker_audit_logs_event_type", table_name="worker_audit_logs")
    op.drop_index("ix_worker_audit_logs_import_batch_id", table_name="worker_audit_logs")
    op.drop_index("ix_worker_audit_logs_job_id", table_name="worker_audit_logs")
    op.drop_table("worker_audit_logs")
