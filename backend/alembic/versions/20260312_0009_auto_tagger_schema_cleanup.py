"""rename wd schema remnants to auto

Revision ID: 20260312_0009
Revises: 20260310_0008
Create Date: 2026-03-12 11:55:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260312_0009"
down_revision = "20260310_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    try:
        op.execute("ALTER TABLE images RENAME COLUMN wd_model_version TO auto_model_version")
    except Exception:
        pass

    try:
        op.execute("ALTER TYPE tag_source RENAME VALUE 'WD' TO 'AUTO'")
    except Exception:
        pass

    try:
        op.execute("ALTER TYPE tag_source RENAME VALUE 'wd' TO 'AUTO'")
    except Exception:
        pass

    try:
        op.execute(
            """
            UPDATE app_settings
            SET key = 'tagger_provider', updated_at = NOW()
            WHERE key = 'active_tagger_provider'
            """
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.execute(
            """
            UPDATE app_settings
            SET key = 'active_tagger_provider', updated_at = NOW()
            WHERE key = 'tagger_provider'
            """
        )
    except Exception:
        pass

    try:
        op.execute("ALTER TYPE tag_source RENAME VALUE 'AUTO' TO 'WD'")
    except Exception:
        pass

    try:
        op.execute("ALTER TABLE images RENAME COLUMN auto_model_version TO wd_model_version")
    except Exception:
        pass
