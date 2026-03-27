from sqlalchemy import Engine, inspect, text


def ensure_runtime_user_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("users")}

    statements: list[str] = []
    if "invited_by_user_id" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN invited_by_user_id INTEGER")
    if "invite_quota" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN invite_quota INTEGER NOT NULL DEFAULT 2")
    if "accepted_tos_at" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN accepted_tos_at TIMESTAMPTZ")
    if "accepted_tos_version" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN accepted_tos_version VARCHAR(64)")
    if "tos_declined_at" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN tos_declined_at TIMESTAMPTZ")
    if "tos_delete_after_at" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN tos_delete_after_at TIMESTAMPTZ")
    if "tos_restore_role" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN tos_restore_role VARCHAR(32)")
    if "tos_restore_can_upload" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN tos_restore_can_upload BOOLEAN")
    if "tos_restore_can_view_questionable" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN tos_restore_can_view_questionable BOOLEAN")
    if "tos_restore_can_view_explicit" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN tos_restore_can_view_explicit BOOLEAN")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TYPE user_role RENAME VALUE 'tos_deactivated' TO 'TOS_DEACTIVATED'"))
    except Exception:
        pass

    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'TOS_DEACTIVATED'"))
    except Exception:
        pass


def ensure_runtime_invite_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "user_invites" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("user_invites")}
    statements: list[str] = []
    if "email" in columns:
        statements.append("ALTER TABLE user_invites ALTER COLUMN email DROP NOT NULL")
    if "inviter_user_id" in columns:
        statements.append("ALTER TABLE user_invites ALTER COLUMN inviter_user_id DROP NOT NULL")
    if "granted_role" not in columns:
        statements.append("ALTER TABLE user_invites ADD COLUMN granted_role user_role")
    if "grant_can_upload" not in columns:
        statements.append("ALTER TABLE user_invites ADD COLUMN grant_can_upload BOOLEAN NOT NULL DEFAULT FALSE")
    if "grant_can_view_explicit" not in columns:
        statements.append("ALTER TABLE user_invites ADD COLUMN grant_can_view_explicit BOOLEAN NOT NULL DEFAULT FALSE")
    if "grant_invite_quota" not in columns:
        statements.append("ALTER TABLE user_invites ADD COLUMN grant_invite_quota INTEGER")
    if "rehabilitated_at" not in columns:
        statements.append("ALTER TABLE user_invites ADD COLUMN rehabilitated_at TIMESTAMPTZ")
    if "rehabilitated_by_user_id" not in columns:
        statements.append("ALTER TABLE user_invites ADD COLUMN rehabilitated_by_user_id INTEGER")

    for statement in statements:
        try:
            with engine.begin() as connection:
                connection.execute(text(statement))
        except Exception:
            continue


def ensure_runtime_app_settings(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "app_settings" in tables:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE app_settings (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(128) NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )


def ensure_runtime_rating_enums(engine: Engine) -> None:
    statements = [
        "ALTER TYPE rating RENAME VALUE 'SAFE' TO 'GENERAL'",
        "ALTER TYPE rating ADD VALUE IF NOT EXISTS 'SENSITIVE' BEFORE 'QUESTIONABLE'",
        "ALTER TYPE rating_rule_target RENAME VALUE 'SAFE' TO 'GENERAL'",
        "ALTER TYPE rating_rule_target ADD VALUE IF NOT EXISTS 'SENSITIVE' BEFORE 'QUESTIONABLE'",
        "ALTER TABLE images ALTER COLUMN rating SET DEFAULT 'GENERAL'",
    ]

    with engine.begin() as connection:
        for statement in statements:
            try:
                connection.execute(text(statement))
            except Exception:
                continue


def ensure_runtime_auto_tagger_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "images" not in tables:
        return

    image_columns = {column["name"] for column in inspector.get_columns("images")}
    statements: list[str] = []
    if "wd_model_version" in image_columns and "auto_model_version" not in image_columns:
        statements.append("ALTER TABLE images RENAME COLUMN wd_model_version TO auto_model_version")
    if "duration_seconds" not in image_columns:
        statements.append("ALTER TABLE images ADD COLUMN duration_seconds DOUBLE PRECISION")
    if "frame_rate" not in image_columns:
        statements.append("ALTER TABLE images ADD COLUMN frame_rate DOUBLE PRECISION")
    if "has_audio" not in image_columns:
        statements.append("ALTER TABLE images ADD COLUMN has_audio BOOLEAN NOT NULL DEFAULT FALSE")
    if "video_codec" not in image_columns:
        statements.append("ALTER TABLE images ADD COLUMN video_codec VARCHAR(64)")
    if "audio_codec" not in image_columns:
        statements.append("ALTER TABLE images ADD COLUMN audio_codec VARCHAR(64)")
    statements.append("ALTER TYPE tag_source RENAME VALUE 'WD' TO 'AUTO'")
    statements.append("ALTER TYPE tag_source RENAME VALUE 'wd' TO 'AUTO'")
    statements.append("ALTER TYPE variant_type ADD VALUE IF NOT EXISTS 'PREVIEW'")
    if "app_settings" in tables:
        statements.append(
            """
            UPDATE app_settings
            SET key = 'tagger_provider', updated_at = NOW()
            WHERE key = 'active_tagger_provider'
            """
        )

    for statement in statements:
        try:
            with engine.begin() as connection:
                connection.execute(text(statement))
        except Exception:
            continue


def ensure_runtime_vote_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements: list[str] = []

    if "image_votes" not in tables:
        statements.append(
            """
            CREATE TABLE image_votes (
                image_id VARCHAR(36) NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                value INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (image_id, user_id),
                CONSTRAINT image_votes_value_check CHECK (value IN (-1, 1))
            )
            """
        )
    if "user_vote_throttles" not in tables:
        statements.append(
            """
            CREATE TABLE user_vote_throttles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                window_started_at TIMESTAMPTZ NULL,
                actions_in_window INTEGER NOT NULL DEFAULT 0,
                cooldown_until TIMESTAMPTZ NULL
            )
            """
        )

    for statement in statements:
        with engine.begin() as connection:
            connection.execute(text(statement))


def ensure_runtime_comment_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements: list[str] = []
    if "image_comments" not in tables:
        statements.append(
            """
            CREATE TABLE image_comments (
                id SERIAL PRIMARY KEY,
                image_id VARCHAR(36) NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                parent_comment_id INTEGER NULL REFERENCES image_comments(id) ON DELETE CASCADE,
                body TEXT NOT NULL,
                is_edited BOOLEAN NOT NULL DEFAULT FALSE,
                is_flagged BOOLEAN NOT NULL DEFAULT FALSE,
                moderation_reason TEXT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    else:
        columns = {column["name"] for column in inspector.get_columns("image_comments")}
        if "parent_comment_id" not in columns:
            statements.append("ALTER TABLE image_comments ADD COLUMN parent_comment_id INTEGER NULL REFERENCES image_comments(id) ON DELETE CASCADE")
        if "is_flagged" not in columns:
            statements.append("ALTER TABLE image_comments ADD COLUMN is_flagged BOOLEAN NOT NULL DEFAULT FALSE")
        if "moderation_reason" not in columns:
            statements.append("ALTER TABLE image_comments ADD COLUMN moderation_reason TEXT NULL")

    if "comment_votes" not in tables:
        statements.append(
            """
            CREATE TABLE comment_votes (
                comment_id INTEGER NOT NULL REFERENCES image_comments(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                value INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (comment_id, user_id),
                CONSTRAINT comment_votes_value_check CHECK (value IN (-1, 1))
            )
            """
        )

    for statement in statements:
        with engine.begin() as connection:
            connection.execute(text(statement))


def ensure_runtime_danger_tag_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements: list[str] = []

    if "danger_tags" not in tables:
        statements.append(
            """
            CREATE TABLE danger_tags (
                id SERIAL PRIMARY KEY,
                tag_id INTEGER NOT NULL UNIQUE REFERENCES tags(id) ON DELETE CASCADE,
                is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                reason TEXT NULL,
                created_by_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

    if "image_danger_hits" not in tables:
        statements.append(
            """
            CREATE TABLE image_danger_hits (
                id SERIAL PRIMARY KEY,
                image_id VARCHAR(36) NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                reason TEXT NULL
            )
            """
        )

    for statement in statements:
        with engine.begin() as connection:
            connection.execute(text(statement))


def ensure_runtime_near_duplicate_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "near_duplicate_reviews" in tables:
        return

    statements = [
        """
        CREATE TABLE near_duplicate_reviews (
            id SERIAL PRIMARY KEY,
            image_id VARCHAR(36) NOT NULL REFERENCES images(id) ON DELETE CASCADE,
            similar_image_id VARCHAR(36) NOT NULL REFERENCES images(id) ON DELETE CASCADE,
            hamming_distance INTEGER NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'open',
            reviewed_by_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
            review_note TEXT NULL,
            reviewed_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_near_duplicate_reviews_image_id ON near_duplicate_reviews (image_id)",
        "CREATE INDEX IF NOT EXISTS ix_near_duplicate_reviews_similar_image_id ON near_duplicate_reviews (similar_image_id)",
        "CREATE INDEX IF NOT EXISTS ix_near_duplicate_reviews_status ON near_duplicate_reviews (status)",
        "CREATE INDEX IF NOT EXISTS ix_near_duplicate_reviews_hamming_distance ON near_duplicate_reviews (hamming_distance)",
    ]
    for statement in statements:
        with engine.begin() as connection:
            connection.execute(text(statement))


def ensure_runtime_board_import_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements: list[str] = []

    if "board_import_runs" not in tables:
        statements.extend(
            [
                """
                CREATE TABLE board_import_runs (
                    id SERIAL PRIMARY KEY,
                    board_name VARCHAR(255) NOT NULL,
                    tag_query TEXT NOT NULL,
                    requested_limit INTEGER NOT NULL DEFAULT 25,
                    hourly_limit INTEGER NOT NULL DEFAULT 1000,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    discovered_posts INTEGER NOT NULL DEFAULT 0,
                    downloaded_posts INTEGER NOT NULL DEFAULT 0,
                    queued_posts INTEGER NOT NULL DEFAULT 0,
                    completed_posts INTEGER NOT NULL DEFAULT 0,
                    duplicate_posts INTEGER NOT NULL DEFAULT 0,
                    skipped_posts INTEGER NOT NULL DEFAULT 0,
                    failed_posts INTEGER NOT NULL DEFAULT 0,
                    current_message TEXT NULL,
                    error_summary TEXT NULL,
                    source_import_batch_id INTEGER NULL REFERENCES imports(id) ON DELETE SET NULL,
                    submitted_by_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                    started_at TIMESTAMPTZ NULL,
                    finished_at TIMESTAMPTZ NULL,
                    last_event_at TIMESTAMPTZ NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """,
                "CREATE INDEX IF NOT EXISTS ix_board_import_runs_board_name ON board_import_runs (board_name)",
                "CREATE INDEX IF NOT EXISTS ix_board_import_runs_status ON board_import_runs (status)",
            ]
        )

    if "board_import_events" not in tables:
        statements.extend(
            [
                """
                CREATE TABLE board_import_events (
                    id SERIAL PRIMARY KEY,
                    run_id INTEGER NOT NULL REFERENCES board_import_runs(id) ON DELETE CASCADE,
                    level VARCHAR(16) NOT NULL DEFAULT 'info',
                    event_type VARCHAR(64) NOT NULL DEFAULT 'log',
                    message TEXT NOT NULL,
                    remote_post_id VARCHAR(255) NULL,
                    job_id INTEGER NULL,
                    image_id VARCHAR(36) NULL,
                    is_error BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """,
                "CREATE INDEX IF NOT EXISTS ix_board_import_events_run_id ON board_import_events (run_id)",
                "CREATE INDEX IF NOT EXISTS ix_board_import_events_event_type ON board_import_events (event_type)",
            ]
        )

    for statement in statements:
        with engine.begin() as connection:
            connection.execute(text(statement))


def ensure_runtime_backup_export_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "backup_exports" in tables:
        return

    statements = [
        """
        CREATE TABLE backup_exports (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            zip_relative_path VARCHAR(512) NULL,
            file_size BIGINT NULL,
            item_count INTEGER NOT NULL DEFAULT 0,
            current_message TEXT NULL,
            error_summary TEXT NULL,
            started_at TIMESTAMPTZ NULL,
            finished_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_backup_exports_user_id ON backup_exports (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_backup_exports_status ON backup_exports (status)",
    ]
    for statement in statements:
        with engine.begin() as connection:
            connection.execute(text(statement))


def ensure_runtime_upload_pipeline_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements: list[str] = []

    if "upload_pipeline_batches" not in tables:
        statements.extend(
            [
                """
                CREATE TABLE upload_pipeline_batches (
                    id SERIAL PRIMARY KEY,
                    submitted_by_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                    linked_import_id INTEGER NULL REFERENCES imports(id) ON DELETE SET NULL,
                    source_name VARCHAR(255) NOT NULL DEFAULT 'web',
                    status VARCHAR(32) NOT NULL DEFAULT 'received',
                    total_items INTEGER NOT NULL DEFAULT 0,
                    completed_items INTEGER NOT NULL DEFAULT 0,
                    duplicate_items INTEGER NOT NULL DEFAULT 0,
                    rejected_items INTEGER NOT NULL DEFAULT 0,
                    failed_items INTEGER NOT NULL DEFAULT 0,
                    finished_at TIMESTAMPTZ NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """,
                "CREATE INDEX IF NOT EXISTS ix_upload_pipeline_batches_status ON upload_pipeline_batches (status)",
                "CREATE INDEX IF NOT EXISTS ix_upload_pipeline_batches_submitted_by_user_id ON upload_pipeline_batches (submitted_by_user_id)",
                "CREATE INDEX IF NOT EXISTS ix_upload_pipeline_batches_linked_import_id ON upload_pipeline_batches (linked_import_id)",
            ]
        )
    else:
        statements.extend(
            [
                "ALTER TABLE upload_pipeline_batches ADD COLUMN IF NOT EXISTS linked_import_id INTEGER NULL REFERENCES imports(id) ON DELETE SET NULL",
                "CREATE INDEX IF NOT EXISTS ix_upload_pipeline_batches_linked_import_id ON upload_pipeline_batches (linked_import_id)",
            ]
        )

    if "upload_pipeline_items" not in tables:
        statements.extend(
            [
                """
                CREATE TABLE upload_pipeline_items (
                    id SERIAL PRIMARY KEY,
                    batch_id INTEGER NOT NULL REFERENCES upload_pipeline_batches(id) ON DELETE CASCADE,
                    submitted_by_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                    client_key VARCHAR(255) NULL,
                    original_filename VARCHAR(512) NOT NULL,
                    detected_mime_type VARCHAR(128) NULL,
                    media_family VARCHAR(32) NULL,
                    quarantine_path VARCHAR(1024) NULL,
                    normalized_path VARCHAR(1024) NULL,
                    checksum_sha256 VARCHAR(64) NULL,
                    source_size INTEGER NULL,
                    stage VARCHAR(32) NOT NULL DEFAULT 'ingress',
                    status VARCHAR(32) NOT NULL DEFAULT 'received',
                    detail_message TEXT NULL,
                    linked_import_id INTEGER NULL REFERENCES imports(id) ON DELETE SET NULL,
                    linked_job_id INTEGER NULL REFERENCES jobs(id) ON DELETE SET NULL,
                    linked_image_id VARCHAR(36) NULL REFERENCES images(id) ON DELETE SET NULL,
                    last_stage_change_at TIMESTAMPTZ NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """,
                "CREATE INDEX IF NOT EXISTS ix_upload_pipeline_items_batch_id ON upload_pipeline_items (batch_id)",
                "CREATE INDEX IF NOT EXISTS ix_upload_pipeline_items_submitted_by_user_id ON upload_pipeline_items (submitted_by_user_id)",
                "CREATE INDEX IF NOT EXISTS ix_upload_pipeline_items_checksum_sha256 ON upload_pipeline_items (checksum_sha256)",
                "CREATE INDEX IF NOT EXISTS ix_upload_pipeline_items_stage ON upload_pipeline_items (stage)",
                "CREATE INDEX IF NOT EXISTS ix_upload_pipeline_items_status ON upload_pipeline_items (status)",
                "CREATE INDEX IF NOT EXISTS ix_upload_pipeline_items_linked_import_id ON upload_pipeline_items (linked_import_id)",
                "CREATE INDEX IF NOT EXISTS ix_upload_pipeline_items_linked_job_id ON upload_pipeline_items (linked_job_id)",
                "CREATE INDEX IF NOT EXISTS ix_upload_pipeline_items_linked_image_id ON upload_pipeline_items (linked_image_id)",
            ]
        )

    for statement in statements:
        with engine.begin() as connection:
            connection.execute(text(statement))
