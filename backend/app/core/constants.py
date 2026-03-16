from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    MODERATOR = "moderator"
    UPLOADER = "uploader"
    TOS_DEACTIVATED = "tos_deactivated"


class Rating(StrEnum):
    GENERAL = "general"
    SENSITIVE = "sensitive"
    QUESTIONABLE = "questionable"
    EXPLICIT = "explicit"


class VisibilityStatus(StrEnum):
    VISIBLE = "visible"
    HIDDEN = "hidden"
    DELETED = "deleted"


class ReportReason(StrEnum):
    WRONG_RATING = "wrong_rating"
    BAD_TAGS = "bad_tags"
    DUPLICATE = "duplicate"
    ILLEGAL_CONTENT = "illegal_content"
    OTHER = "other"


class ReportStatus(StrEnum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DUPLICATE = "duplicate"


class TagCategory(StrEnum):
    GENERAL = "general"
    CHARACTER = "character"
    COPYRIGHT = "copyright"
    META = "meta"
    ARTIST = "artist"


class TagSource(StrEnum):
    AUTO = "auto"
    USER = "user"
    SYSTEM = "system"


class AliasType(StrEnum):
    SYNONYM = "synonym"
    REDIRECT = "redirect"
    DEPRECATED = "deprecated"


class JobType(StrEnum):
    INGEST = "ingest"
    REPROCESS = "reprocess"
    THUMB_REGEN = "thumb_regen"
    RETAG = "retag"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    FAILED = "failed"
    DONE = "done"


class ImportSourceType(StrEnum):
    WEB = "web"
    ZIP = "zip"
    FOLDER = "folder"
    API = "api"


class ImportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    FAILED = "failed"
    DONE = "done"


class UploadRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class VariantType(StrEnum):
    ORIGINAL = "original"
    THUMB = "thumb"
    PREVIEW = "preview"


SYSTEM_TAGS = {"image", "animated", "video"}


class InviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class StrikeSourceType(StrEnum):
    MANUAL = "manual"
    INVITEE_BAN = "invitee_ban"
    THRESHOLD_AUTO_BAN = "threshold_auto_ban"
