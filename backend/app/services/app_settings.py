from app.models.app_setting import AppSetting
from sqlalchemy.orm import Session


SIDEBAR_LIMIT_DEFAULTS = {
    "sidebar_general_limit": 30,
    "sidebar_meta_limit": 10,
    "sidebar_character_limit": 15,
    "sidebar_artist_limit": 15,
    "sidebar_series_limit": 15,
    "sidebar_creature_limit": 15,
}

TAGGER_PROVIDER_DEFAULT = "camie"
TAGGER_PROVIDER_KEY = "tagger_provider"
RETAG_ALL_ACTION = "retag_all"


def ensure_sidebar_settings(db: Session) -> None:
    changed = False
    for key, default_value in SIDEBAR_LIMIT_DEFAULTS.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting:
            continue
        db.add(AppSetting(key=key, value=str(default_value)))
        changed = True
    if changed:
        db.commit()


def ensure_tagger_settings(db: Session) -> None:
    setting = db.query(AppSetting).filter(AppSetting.key == TAGGER_PROVIDER_KEY).first()
    if setting:
        if setting.value != TAGGER_PROVIDER_DEFAULT:
            setting.value = TAGGER_PROVIDER_DEFAULT
            db.add(setting)
            db.commit()
        return
    db.add(AppSetting(key=TAGGER_PROVIDER_KEY, value=TAGGER_PROVIDER_DEFAULT))
    db.commit()


def get_sidebar_limits(db: Session) -> dict[str, int]:
    ensure_sidebar_settings(db)
    rows = (
        db.query(AppSetting)
        .filter(AppSetting.key.in_(tuple(SIDEBAR_LIMIT_DEFAULTS.keys())))
        .all()
    )
    values = {row.key: row.value for row in rows}
    limits: dict[str, int] = {}
    for key, default_value in SIDEBAR_LIMIT_DEFAULTS.items():
        try:
            parsed = int(values.get(key, str(default_value)))
        except ValueError:
            parsed = default_value
        limits[key] = max(parsed, 0)
    return limits


def get_tagger_provider(db: Session) -> str:
    ensure_tagger_settings(db)
    return TAGGER_PROVIDER_DEFAULT


def ingest_queue_name_for_provider(provider: str) -> str:
    normalized = TAGGER_PROVIDER_DEFAULT if not provider else provider.strip().lower()
    return f"jobs:ingest:{normalized}"


def maintenance_queue_name_for_provider(provider: str) -> str:
    normalized = TAGGER_PROVIDER_DEFAULT if not provider else provider.strip().lower()
    return f"jobs:maintenance:{normalized}"


def maintenance_pending_key(provider: str, action: str) -> str:
    normalized = TAGGER_PROVIDER_DEFAULT if not provider else provider.strip().lower()
    return f"maintenance:{normalized}:{action}:pending"


def maintenance_running_key(provider: str, action: str) -> str:
    normalized = TAGGER_PROVIDER_DEFAULT if not provider else provider.strip().lower()
    return f"maintenance:{normalized}:{action}:running"


def update_sidebar_limits(db: Session, updates: dict[str, int]) -> dict[str, int]:
    ensure_sidebar_settings(db)
    for key, value in updates.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if not setting:
            setting = AppSetting(key=key, value=str(value))
        else:
            setting.value = str(value)
        db.add(setting)
    db.commit()
    return get_sidebar_limits(db)
