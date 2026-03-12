from sqlalchemy import Engine, inspect, text


def ensure_runtime_user_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("users")}

    statements: list[str] = []
    if "invited_by_user_id" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN invited_by_user_id INTEGER")
    if "invite_quota" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN invite_quota INTEGER NOT NULL DEFAULT 2")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


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
    statements.append("ALTER TYPE tag_source RENAME VALUE 'WD' TO 'AUTO'")
    statements.append("ALTER TYPE tag_source RENAME VALUE 'wd' TO 'AUTO'")
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
