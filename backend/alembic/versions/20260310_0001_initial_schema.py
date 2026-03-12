"""initial schema

Revision ID: 20260310_0001
Revises:
Create Date: 2026-03-10 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260310_0001"
down_revision = None
branch_labels = None
depends_on = None


user_role = sa.Enum("admin", "moderator", "uploader", name="user_role")
rating = sa.Enum("safe", "questionable", "explicit", name="rating")
processing_status = sa.Enum("pending", "processing", "ready", "failed", "duplicate", name="processing_status")
tag_category = sa.Enum("general", "character", "copyright", "meta", "artist", name="tag_category")
tag_source = sa.Enum("wd", "user", "system", name="tag_source")
alias_type = sa.Enum("synonym", "redirect", "deprecated", name="alias_type")
job_type = sa.Enum("ingest", "reprocess", "thumb_regen", "retag", name="job_type")
job_status = sa.Enum("queued", "running", "retrying", "failed", "done", name="job_status")
import_source_type = sa.Enum("web", "zip", "folder", "api", name="import_source_type")
import_status = sa.Enum("pending", "running", "failed", "done", name="import_status")
variant_type = sa.Enum("original", "thumb", name="variant_type")


def upgrade() -> None:
    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    rating.create(bind, checkfirst=True)
    processing_status.create(bind, checkfirst=True)
    tag_category.create(bind, checkfirst=True)
    tag_source.create(bind, checkfirst=True)
    alias_type.create(bind, checkfirst=True)
    job_type.create(bind, checkfirst=True)
    job_status.create(bind, checkfirst=True)
    import_source_type.create(bind, checkfirst=True)
    import_status.create(bind, checkfirst=True)
    variant_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_view_explicit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name_normalized", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("category", tag_category, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name_normalized"),
    )
    op.create_index("ix_tags_name_normalized", "tags", ["name_normalized"])

    op.create_table(
        "imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", import_source_type, nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("submitted_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", import_status, nullable=False, server_default="pending"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_imports_source_type", "imports", ["source_type"])
    op.create_index("ix_imports_status", "imports", ["status"])

    op.create_table(
        "images",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("uuid_short", sa.String(length=16), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type_original", sa.String(length=128), nullable=False),
        sa.Column("file_size_original", sa.BigInteger(), nullable=False),
        sa.Column("file_size_stored", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("perceptual_hash", sa.String(length=64), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("aspect_ratio", sa.Numeric(10, 4), nullable=False),
        sa.Column("storage_ext", sa.String(length=16), nullable=False, server_default="png"),
        sa.Column("rating", rating, nullable=False, server_default="safe"),
        sa.Column("nsfw_score", sa.Float(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("import_batch_id", sa.Integer(), sa.ForeignKey("imports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("processing_status", processing_status, nullable=False, server_default="pending"),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("wd_model_version", sa.String(length=255), nullable=True),
        sa.Column("nsfw_model_version", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("uuid_short"),
        sa.UniqueConstraint("checksum_sha256"),
    )
    op.create_index("ix_images_uuid_short", "images", ["uuid_short"])
    op.create_index("ix_images_checksum_sha256", "images", ["checksum_sha256"])
    op.create_index("ix_images_perceptual_hash", "images", ["perceptual_hash"])
    op.create_index("ix_images_processing_status", "images", ["processing_status"])

    op.create_table(
        "tag_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alias_name", sa.String(length=255), nullable=False),
        sa.Column("target_tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias_type", alias_type, nullable=False, server_default="synonym"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("alias_name"),
    )
    op.create_index("ix_tag_aliases_alias_name", "tag_aliases", ["alias_name"])

    op.create_table(
        "tag_merges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merged_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_type", job_type, nullable=False),
        sa.Column("image_id", sa.String(length=36), sa.ForeignKey("images.id", ondelete="SET NULL"), nullable=True),
        sa.Column("queue_path", sa.String(length=512), nullable=False),
        sa.Column("status", job_status, nullable=False, server_default="queued"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_batch_id", sa.Integer(), sa.ForeignKey("imports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_image_id", "jobs", ["image_id"])
    op.create_index("ix_jobs_import_batch_id", "jobs", ["import_batch_id"])

    op.create_table(
        "image_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("image_id", sa.String(length=36), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_type", variant_type, nullable=False),
        sa.Column("relative_path", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_image_variants_image_id", "image_variants", ["image_id"])

    op.create_table(
        "image_tags",
        sa.Column("image_id", sa.String(length=36), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", tag_source, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("image_id", "tag_id", "source"),
    )


def downgrade() -> None:
    op.drop_table("image_tags")
    op.drop_index("ix_image_variants_image_id", table_name="image_variants")
    op.drop_table("image_variants")
    op.drop_index("ix_jobs_import_batch_id", table_name="jobs")
    op.drop_index("ix_jobs_image_id", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_job_type", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("tag_merges")
    op.drop_index("ix_tag_aliases_alias_name", table_name="tag_aliases")
    op.drop_table("tag_aliases")
    op.drop_index("ix_images_processing_status", table_name="images")
    op.drop_index("ix_images_perceptual_hash", table_name="images")
    op.drop_index("ix_images_checksum_sha256", table_name="images")
    op.drop_index("ix_images_uuid_short", table_name="images")
    op.drop_table("images")
    op.drop_index("ix_imports_status", table_name="imports")
    op.drop_index("ix_imports_source_type", table_name="imports")
    op.drop_table("imports")
    op.drop_index("ix_tags_name_normalized", table_name="tags")
    op.drop_table("tags")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

    variant_type.drop(op.get_bind(), checkfirst=True)
    import_status.drop(op.get_bind(), checkfirst=True)
    import_source_type.drop(op.get_bind(), checkfirst=True)
    job_status.drop(op.get_bind(), checkfirst=True)
    job_type.drop(op.get_bind(), checkfirst=True)
    alias_type.drop(op.get_bind(), checkfirst=True)
    tag_source.drop(op.get_bind(), checkfirst=True)
    tag_category.drop(op.get_bind(), checkfirst=True)
    processing_status.drop(op.get_bind(), checkfirst=True)
    rating.drop(op.get_bind(), checkfirst=True)
    user_role.drop(op.get_bind(), checkfirst=True)
