from pydantic import BaseModel


class SidebarSettingsRead(BaseModel):
    sidebar_general_limit: int
    sidebar_meta_limit: int
    sidebar_character_limit: int
    sidebar_artist_limit: int
    sidebar_series_limit: int
    sidebar_creature_limit: int


class SidebarSettingsUpdate(BaseModel):
    sidebar_general_limit: int
    sidebar_meta_limit: int
    sidebar_character_limit: int
    sidebar_artist_limit: int
    sidebar_series_limit: int
    sidebar_creature_limit: int


class SidebarSettingsResponse(BaseModel):
    data: SidebarSettingsRead
    meta: dict[str, str] = {}


class RateLimitSettingsRead(BaseModel):
    rate_limit_login_max_requests: int
    rate_limit_login_window_seconds: int
    rate_limit_search_max_requests: int
    rate_limit_search_window_seconds: int
    rate_limit_upload_max_requests: int
    rate_limit_upload_window_seconds: int
    rate_limit_admin_write_max_requests: int
    rate_limit_admin_write_window_seconds: int


class RateLimitSettingsUpdate(BaseModel):
    rate_limit_login_max_requests: int
    rate_limit_login_window_seconds: int
    rate_limit_search_max_requests: int
    rate_limit_search_window_seconds: int
    rate_limit_upload_max_requests: int
    rate_limit_upload_window_seconds: int
    rate_limit_admin_write_max_requests: int
    rate_limit_admin_write_window_seconds: int


class RateLimitSettingsResponse(BaseModel):
    data: RateLimitSettingsRead
    meta: dict[str, str] = {}


class AutoscalerSettingsRead(BaseModel):
    autoscaler_enabled: bool
    autoscaler_jobs_per_worker: int
    autoscaler_min_workers: int
    autoscaler_max_workers: int
    autoscaler_poll_seconds: int
    active_workers: list[str] = []
    current_worker_count: int = 0
    queue_depth: int = 0
    recommended_worker_count: int = 1
    last_scale_action: str | None = None
    last_scale_at: str | None = None
    last_error: str | None = None


class AutoscalerSettingsUpdate(BaseModel):
    autoscaler_enabled: bool
    autoscaler_jobs_per_worker: int
    autoscaler_min_workers: int
    autoscaler_max_workers: int
    autoscaler_poll_seconds: int


class AutoscalerSettingsResponse(BaseModel):
    data: AutoscalerSettingsRead
    meta: dict[str, str] = {}


class UploadPipelineBalancerStageRead(BaseModel):
    stage: str
    label: str
    min_workers: int
    max_workers: int
    jobs_per_worker: int
    current_workers: int = 0
    recommended_workers: int = 1
    queue_depth: int = 0
    oldest_queued_seconds: int = 0
    score: float = 0
    active_workers: list[str] = []


class UploadPipelineBalancerStageUpdate(BaseModel):
    stage: str
    min_workers: int
    max_workers: int
    jobs_per_worker: int


class UploadPipelineBalancerSettingsRead(BaseModel):
    upload_pipeline_balancer_enabled: bool
    upload_pipeline_balancer_poll_seconds: int
    upload_pipeline_balancer_flexible_slots: int
    stages: list[UploadPipelineBalancerStageRead] = []
    last_rebalance_at: str | None = None
    last_rebalance_summary: str | None = None
    last_error: str | None = None


class UploadPipelineBalancerSettingsUpdate(BaseModel):
    upload_pipeline_balancer_enabled: bool
    upload_pipeline_balancer_poll_seconds: int
    upload_pipeline_balancer_flexible_slots: int
    stages: list[UploadPipelineBalancerStageUpdate]


class UploadPipelineBalancerSettingsResponse(BaseModel):
    data: UploadPipelineBalancerSettingsRead
    meta: dict[str, str] = {}


class TaggerSettingsRead(BaseModel):
    provider: str
    retag_all_running: bool = False
    retag_all_pending: bool = False
    preview_backfill_running: bool = False
    preview_backfill_pending: bool = False
    near_duplicate_hamming_threshold: int = 6


class TaggerSettingsResponse(BaseModel):
    data: TaggerSettingsRead
    meta: dict[str, str] = {}


class RetagAllResponse(BaseModel):
    data: TaggerSettingsRead
    meta: dict[str, str] = {}


class PreviewBackfillResponse(BaseModel):
    data: TaggerSettingsRead
    meta: dict[str, str] = {}


class TermsOfServiceRead(BaseModel):
    title: str
    version: str
    paragraphs: list[str]
    updated_at: str | None = None


class TermsOfServiceUpdate(BaseModel):
    title: str
    paragraphs: list[str]


class TermsOfServiceResponse(BaseModel):
    data: TermsOfServiceRead
    meta: dict[str, str] = {}
