from __future__ import annotations

import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass(slots=True)
class NextBooConfig:
    base_url: str
    username: str
    password: str
    admin_username: str | None = None
    admin_password: str | None = None


class NextBooClient:
    def __init__(self, config: NextBooConfig) -> None:
        self.config = config
        self.session = requests.Session()

    def _api(self, path: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/api/v1{path}"

    def _login_session(self, session: requests.Session, username: str, password: str) -> dict[str, Any]:
        backoff = 1.0
        last_response = None
        for _ in range(5):
            response = session.post(
                self._api("/auth/login"),
                data={"username": username, "password": password},
                timeout=30,
            )
            last_response = response
            if response.status_code != 429:
                response.raise_for_status()
                payload = response.json()["data"]
                access_token = payload["access_token"]
                session.headers.update({"Authorization": f"Bearer {access_token}"})
                return payload
            time.sleep(backoff)
            backoff *= 2
        assert last_response is not None
        last_response.raise_for_status()
        raise RuntimeError("login failed unexpectedly")

    def login(self) -> None:
        self._login_session(self.session, self.config.username, self.config.password)

    def admin_session(self) -> requests.Session:
        if not self.config.admin_username or not self.config.admin_password:
            raise RuntimeError("Admin credentials are not configured")
        session = requests.Session()
        self._login_session(session, self.config.admin_username, self.config.admin_password)
        return session

    def _post_upload(self, files_payload: list[tuple[str, tuple[str, Any, str]]], form_data: list[tuple[str, str]]):
        backoff = 1.0
        last_response = None
        for _ in range(5):
            response = self.session.post(
                self._api("/uploads"),
                files=files_payload,
                data=form_data,
                timeout=120,
            )
            last_response = response
            if response.status_code != 429:
                break
            time.sleep(backoff)
            backoff *= 2
        assert last_response is not None
        response = last_response
        response.raise_for_status()
        return response.json()

    def upload_files(self, items: list[tuple[Path, str]]) -> dict[str, Any]:
        handles: list[Any] = []
        files_payload: list[tuple[str, tuple[str, Any, str]]] = []
        form_data: list[tuple[str, str]] = []
        try:
            for path, client_key in items:
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                handle = path.open("rb")
                handles.append(handle)
                files_payload.append(("files", (path.name, handle, content_type)))
                form_data.append(("client_keys", client_key))
            return self._post_upload(files_payload, form_data)
        finally:
            for handle in handles:
                handle.close()

    def upload_file(self, path: Path, *, client_key: str) -> int:
        payload = self.upload_files([(path, client_key)])
        accepted = payload["data"]
        rejected = payload["rejected"]
        if rejected and not accepted:
            raise RuntimeError(f"Upload rejected for {path.name}: {rejected[0]['error']}")
        if not accepted:
            raise RuntimeError(f"Upload returned no accepted jobs for {path.name}")
        return int(accepted[0]["job_id"])

    def list_my_upload_ids(self, *, limit: int = 20) -> list[str]:
        response = self.session.get(
            self._api("/users/me/uploads"),
            params={"limit": limit},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return [str(item["id"]) for item in payload.get("uploads", [])]

    def wait_for_job(
        self,
        job_id: int,
        *,
        known_upload_ids: set[str] | None = None,
        poll_seconds: float = 2.0,
        timeout_seconds: float = 600.0,
    ) -> str:
        deadline = time.time() + timeout_seconds
        missing_count = 0
        while time.time() < deadline:
            response = self.session.get(
                self._api("/uploads/status"),
                params={"job_ids": str(job_id)},
                timeout=30,
            )
            response.raise_for_status()
            jobs = response.json()["data"]
            if not jobs:
                missing_count += 1
                if known_upload_ids is not None and missing_count >= 2:
                    current_ids = self.list_my_upload_ids()
                    for image_id in current_ids:
                        if image_id not in known_upload_ids:
                            return image_id
                time.sleep(poll_seconds)
                continue
            missing_count = 0
            job = jobs[0]
            status = job["status"]
            if status == "done":
                image_id = job.get("image_id")
                if not image_id:
                    raise RuntimeError(f"Job {job_id} completed without image_id")
                return image_id
            if status == "failed":
                raise RuntimeError(f"Job {job_id} failed: {job.get('last_error') or 'unknown error'}")
            time.sleep(poll_seconds)
        raise TimeoutError(f"Timed out waiting for upload job {job_id}")

    def add_tags(self, image_id: str, tags: list[str]) -> None:
        if not tags:
            return
        response = self.session.patch(
            self._api(f"/images/{image_id}/metadata"),
            json={"add_tag_names": tags},
            timeout=30,
        )
        response.raise_for_status()

    def get_rate_limits(self, session: requests.Session) -> dict[str, int]:
        response = session.get(self._api("/admin/settings/rate-limits"), timeout=30)
        response.raise_for_status()
        return response.json()["data"]

    def patch_rate_limits(self, session: requests.Session, payload: dict[str, int]) -> dict[str, int]:
        response = session.patch(
            self._api("/admin/settings/rate-limits"),
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["data"]
