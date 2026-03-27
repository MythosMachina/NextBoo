from app.models.app_setting import AppSetting
from sqlalchemy.orm import Session
import hashlib
import json


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
PREVIEW_BACKFILL_ACTION = "preview_backfill"
NEAR_DUPLICATE_THRESHOLD_KEY = "near_duplicate_hamming_threshold"
NEAR_DUPLICATE_THRESHOLD_DEFAULT = 6
RATE_LIMIT_DEFAULTS = {
    "rate_limit_login_max_requests": 5,
    "rate_limit_login_window_seconds": 60,
    "rate_limit_search_max_requests": 120,
    "rate_limit_search_window_seconds": 60,
    "rate_limit_upload_max_requests": 30,
    "rate_limit_upload_window_seconds": 600,
    "rate_limit_admin_write_max_requests": 60,
    "rate_limit_admin_write_window_seconds": 60,
}
AUTOSCALER_DEFAULTS = {
    "autoscaler_enabled": 0,
    "autoscaler_jobs_per_worker": 100,
    "autoscaler_min_workers": 1,
    "autoscaler_max_workers": 4,
    "autoscaler_poll_seconds": 30,
}
UPLOAD_PIPELINE_STAGE_DEFAULTS = {
    "scanning": {"label": "Scanning", "min_workers": 1, "max_workers": 6, "jobs_per_worker": 100},
    "dedupe": {"label": "Dedupe", "min_workers": 1, "max_workers": 4, "jobs_per_worker": 200},
    "normalize": {"label": "Normalize", "min_workers": 1, "max_workers": 8, "jobs_per_worker": 40},
    "dispatch": {"label": "Dispatch", "min_workers": 1, "max_workers": 3, "jobs_per_worker": 150},
    "ingest_image": {"label": "Final Ingest Image", "min_workers": 1, "max_workers": 8, "jobs_per_worker": 25},
    "ingest_video": {"label": "Final Ingest Video", "min_workers": 1, "max_workers": 4, "jobs_per_worker": 4},
}
UPLOAD_PIPELINE_BALANCER_DEFAULTS = {
    "upload_pipeline_balancer_enabled": 1,
    "upload_pipeline_balancer_poll_seconds": 5,
    "upload_pipeline_balancer_flexible_slots": 0,
}
TOS_TITLE_KEY = "tos_title"
TOS_PARAGRAPHS_KEY = "tos_paragraphs"
DEFAULT_TOS_TITLE = "NextBoo Terms of Service"
DEFAULT_TOS_PARAGRAPHS = [
    "NextBoo is a self-hosted media index. By creating an account, you agree to use the service lawfully and to comply with all rules published by the platform operator.",
    "You may only upload or organize content that you are allowed to possess, process, and distribute under the laws and regulations that apply to you and to the platform operator.",
    "The platform operator may review, edit, restrict, or remove content, tags, comments, accounts, or invites at any time in order to enforce legal obligations, moderation policies, or operational safety requirements.",
    "Automated tagging, rating, duplicate detection, moderation cues, and importer workflows are assistive tools only. They do not guarantee correctness and do not replace human review.",
    "You must not use NextBoo to upload malware, abusive material, unlawful content, or media that violates the rights, privacy, or safety of other people.",
    "Accounts, invites, votes, comments, and imports may be limited, suspended, or removed when they are used for abuse, spam, evasion, or other disruptive behavior.",
    "The person or organization hosting NextBoo is responsible for deciding what content is allowed on that installation. If you do not agree with the local rules, do not use the service.",
    "By completing registration, you acknowledge that moderation decisions may be made manually and that continued access to the service is not guaranteed.",
]


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


def ensure_rate_limit_settings(db: Session) -> None:
    changed = False
    for key, default_value in RATE_LIMIT_DEFAULTS.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting:
            continue
        db.add(AppSetting(key=key, value=str(default_value)))
        changed = True
    if changed:
        db.commit()


def ensure_autoscaler_settings(db: Session) -> None:
    changed = False
    for key, default_value in AUTOSCALER_DEFAULTS.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting:
            continue
        db.add(AppSetting(key=key, value=str(default_value)))
        changed = True
    if changed:
        db.commit()


def upload_pipeline_stage_setting_key(stage: str, key: str) -> str:
    return f"upload_pipeline_stage_{stage}_{key}"


def ensure_upload_pipeline_balancer_settings(db: Session) -> None:
    changed = False
    for key, default_value in UPLOAD_PIPELINE_BALANCER_DEFAULTS.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting:
            continue
        db.add(AppSetting(key=key, value=str(default_value)))
        changed = True
    for stage, defaults in UPLOAD_PIPELINE_STAGE_DEFAULTS.items():
        for field in ("min_workers", "max_workers", "jobs_per_worker"):
            key = upload_pipeline_stage_setting_key(stage, field)
            setting = db.query(AppSetting).filter(AppSetting.key == key).first()
            if setting:
                continue
            db.add(AppSetting(key=key, value=str(defaults[field])))
            changed = True
    if changed:
        db.commit()


def ensure_tos_settings(db: Session) -> None:
    changed = False
    title_setting = db.query(AppSetting).filter(AppSetting.key == TOS_TITLE_KEY).first()
    if not title_setting:
        db.add(AppSetting(key=TOS_TITLE_KEY, value=DEFAULT_TOS_TITLE))
        changed = True
    paragraphs_setting = db.query(AppSetting).filter(AppSetting.key == TOS_PARAGRAPHS_KEY).first()
    if not paragraphs_setting:
        db.add(AppSetting(key=TOS_PARAGRAPHS_KEY, value=json.dumps(DEFAULT_TOS_PARAGRAPHS)))
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


def ensure_near_duplicate_settings(db: Session) -> None:
    setting = db.query(AppSetting).filter(AppSetting.key == NEAR_DUPLICATE_THRESHOLD_KEY).first()
    if setting:
        return
    db.add(AppSetting(key=NEAR_DUPLICATE_THRESHOLD_KEY, value=str(NEAR_DUPLICATE_THRESHOLD_DEFAULT)))
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


def get_rate_limit_settings(db: Session) -> dict[str, int]:
    ensure_rate_limit_settings(db)
    rows = db.query(AppSetting).filter(AppSetting.key.in_(tuple(RATE_LIMIT_DEFAULTS.keys()))).all()
    values = {row.key: row.value for row in rows}
    limits: dict[str, int] = {}
    for key, default_value in RATE_LIMIT_DEFAULTS.items():
        try:
            parsed = int(values.get(key, str(default_value)))
        except ValueError:
            parsed = default_value
        limits[key] = max(parsed, 1)
    return limits


def get_autoscaler_settings(db: Session) -> dict[str, int | bool]:
    ensure_autoscaler_settings(db)
    rows = db.query(AppSetting).filter(AppSetting.key.in_(tuple(AUTOSCALER_DEFAULTS.keys()))).all()
    values = {row.key: row.value for row in rows}
    return {
        "autoscaler_enabled": values.get("autoscaler_enabled", "0") == "1",
        "autoscaler_jobs_per_worker": max(int(values.get("autoscaler_jobs_per_worker", "100")), 1),
        "autoscaler_min_workers": max(int(values.get("autoscaler_min_workers", "1")), 1),
        "autoscaler_max_workers": max(int(values.get("autoscaler_max_workers", "4")), 1),
        "autoscaler_poll_seconds": max(int(values.get("autoscaler_poll_seconds", "30")), 5),
    }


def get_upload_pipeline_balancer_settings(db: Session) -> dict[str, object]:
    ensure_upload_pipeline_balancer_settings(db)
    keys = list(UPLOAD_PIPELINE_BALANCER_DEFAULTS.keys())
    for stage in UPLOAD_PIPELINE_STAGE_DEFAULTS:
        for field in ("min_workers", "max_workers", "jobs_per_worker"):
            keys.append(upload_pipeline_stage_setting_key(stage, field))
    rows = db.query(AppSetting).filter(AppSetting.key.in_(tuple(keys))).all()
    values = {row.key: row.value for row in rows}
    stages: list[dict[str, object]] = []
    for stage, defaults in UPLOAD_PIPELINE_STAGE_DEFAULTS.items():
        min_workers = max(int(values.get(upload_pipeline_stage_setting_key(stage, "min_workers"), str(defaults["min_workers"]))), 1)
        max_workers = max(int(values.get(upload_pipeline_stage_setting_key(stage, "max_workers"), str(defaults["max_workers"]))), 1)
        jobs_per_worker = max(int(values.get(upload_pipeline_stage_setting_key(stage, "jobs_per_worker"), str(defaults["jobs_per_worker"]))), 1)
        if max_workers < min_workers:
            max_workers = min_workers
        stages.append(
            {
                "stage": stage,
                "label": defaults["label"],
                "min_workers": min_workers,
                "max_workers": max_workers,
                "jobs_per_worker": jobs_per_worker,
            }
        )
    return {
        "upload_pipeline_balancer_enabled": True,
        "upload_pipeline_balancer_poll_seconds": max(int(values.get("upload_pipeline_balancer_poll_seconds", "5")), 5),
        "upload_pipeline_balancer_flexible_slots": 0,
        "stages": stages,
    }


def _parse_tos_paragraphs(raw_value: str | None) -> list[str]:
    if not raw_value:
        return list(DEFAULT_TOS_PARAGRAPHS)
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            paragraphs = [str(item).strip() for item in parsed if str(item).strip()]
            return paragraphs or list(DEFAULT_TOS_PARAGRAPHS)
    except Exception:
        pass
    return list(DEFAULT_TOS_PARAGRAPHS)


def _build_tos_version(title: str, paragraphs: list[str]) -> str:
    digest = hashlib.sha256(
        json.dumps({"title": title, "paragraphs": paragraphs}, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest[:16]


def get_terms_of_service(db: Session) -> dict[str, str | list[str] | None]:
    ensure_tos_settings(db)
    rows = db.query(AppSetting).filter(AppSetting.key.in_((TOS_TITLE_KEY, TOS_PARAGRAPHS_KEY))).all()
    values = {row.key: row for row in rows}
    title = (values.get(TOS_TITLE_KEY).value if values.get(TOS_TITLE_KEY) else DEFAULT_TOS_TITLE).strip() or DEFAULT_TOS_TITLE
    paragraphs = _parse_tos_paragraphs(values.get(TOS_PARAGRAPHS_KEY).value if values.get(TOS_PARAGRAPHS_KEY) else None)
    updated_at = None
    if values.get(TOS_PARAGRAPHS_KEY):
        updated_at = values[TOS_PARAGRAPHS_KEY].updated_at.isoformat() if values[TOS_PARAGRAPHS_KEY].updated_at else None
    elif values.get(TOS_TITLE_KEY):
        updated_at = values[TOS_TITLE_KEY].updated_at.isoformat() if values[TOS_TITLE_KEY].updated_at else None
    return {
        "title": title,
        "version": _build_tos_version(title, paragraphs),
        "paragraphs": paragraphs,
        "updated_at": updated_at,
    }


def update_terms_of_service(db: Session, *, title: str, paragraphs: list[str]) -> dict[str, str | list[str] | None]:
    ensure_tos_settings(db)
    clean_title = title.strip() or DEFAULT_TOS_TITLE
    clean_paragraphs = [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]
    if not clean_paragraphs:
        clean_paragraphs = list(DEFAULT_TOS_PARAGRAPHS)

    title_setting = db.query(AppSetting).filter(AppSetting.key == TOS_TITLE_KEY).first()
    if not title_setting:
        title_setting = AppSetting(key=TOS_TITLE_KEY, value=clean_title)
    else:
        title_setting.value = clean_title
    db.add(title_setting)

    paragraphs_setting = db.query(AppSetting).filter(AppSetting.key == TOS_PARAGRAPHS_KEY).first()
    payload = json.dumps(clean_paragraphs)
    if not paragraphs_setting:
        paragraphs_setting = AppSetting(key=TOS_PARAGRAPHS_KEY, value=payload)
    else:
        paragraphs_setting.value = payload
    db.add(paragraphs_setting)
    db.commit()
    return get_terms_of_service(db)


def get_tagger_provider(db: Session) -> str:
    ensure_tagger_settings(db)
    return TAGGER_PROVIDER_DEFAULT


def get_near_duplicate_threshold(db: Session) -> int:
    ensure_near_duplicate_settings(db)
    setting = db.query(AppSetting).filter(AppSetting.key == NEAR_DUPLICATE_THRESHOLD_KEY).first()
    if not setting:
        return NEAR_DUPLICATE_THRESHOLD_DEFAULT
    try:
        return max(int(setting.value), 1)
    except ValueError:
        return NEAR_DUPLICATE_THRESHOLD_DEFAULT


def update_near_duplicate_threshold(db: Session, value: int) -> int:
    ensure_near_duplicate_settings(db)
    setting = db.query(AppSetting).filter(AppSetting.key == NEAR_DUPLICATE_THRESHOLD_KEY).first()
    if not setting:
        setting = AppSetting(key=NEAR_DUPLICATE_THRESHOLD_KEY, value=str(max(value, 1)))
    else:
        setting.value = str(max(value, 1))
    db.add(setting)
    db.commit()
    return get_near_duplicate_threshold(db)


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


def update_rate_limit_settings(db: Session, updates: dict[str, int]) -> dict[str, int]:
    ensure_rate_limit_settings(db)
    for key, value in updates.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if not setting:
            setting = AppSetting(key=key, value=str(value))
        else:
            setting.value = str(value)
        db.add(setting)
    db.commit()
    return get_rate_limit_settings(db)


def update_autoscaler_settings(db: Session, updates: dict[str, int | bool]) -> dict[str, int | bool]:
    ensure_autoscaler_settings(db)
    for key, value in updates.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if not setting:
            setting = AppSetting(key=key, value=str(value))
        else:
            if isinstance(value, bool):
                setting.value = "1" if value else "0"
            else:
                setting.value = str(value)
        db.add(setting)
    db.commit()
    settings = get_autoscaler_settings(db)
    if settings["autoscaler_max_workers"] < settings["autoscaler_min_workers"]:
        update_autoscaler_settings(
            db,
            {"autoscaler_max_workers": int(settings["autoscaler_min_workers"])},
        )
        settings = get_autoscaler_settings(db)
    return settings


def update_upload_pipeline_balancer_settings(db: Session, updates: dict[str, object]) -> dict[str, object]:
    ensure_upload_pipeline_balancer_settings(db)
    scalar_updates = {
        "upload_pipeline_balancer_enabled": updates.get("upload_pipeline_balancer_enabled"),
        "upload_pipeline_balancer_poll_seconds": updates.get("upload_pipeline_balancer_poll_seconds"),
        "upload_pipeline_balancer_flexible_slots": updates.get("upload_pipeline_balancer_flexible_slots"),
    }
    for key, value in scalar_updates.items():
        if value is None:
            continue
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if not setting:
            setting = AppSetting(key=key, value="1" if value else "0" if isinstance(value, bool) else str(value))
        else:
            setting.value = "1" if value else "0" if isinstance(value, bool) else str(value)
        db.add(setting)

    for stage_update in updates.get("stages", []):
        stage = str(stage_update.get("stage") or "").strip()
        if stage not in UPLOAD_PIPELINE_STAGE_DEFAULTS:
            continue
        min_workers = max(int(stage_update.get("min_workers", 1)), 1)
        max_workers = max(int(stage_update.get("max_workers", 1)), 1)
        jobs_per_worker = max(int(stage_update.get("jobs_per_worker", 1)), 1)
        if max_workers < min_workers:
            max_workers = min_workers
        for field, value in (
            ("min_workers", min_workers),
            ("max_workers", max_workers),
            ("jobs_per_worker", jobs_per_worker),
        ):
            key = upload_pipeline_stage_setting_key(stage, field)
            setting = db.query(AppSetting).filter(AppSetting.key == key).first()
            if not setting:
                setting = AppSetting(key=key, value=str(value))
            else:
                setting.value = str(value)
            db.add(setting)

    db.commit()
    return get_upload_pipeline_balancer_settings(db)
