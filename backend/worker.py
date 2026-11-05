"""One durable Postgres-backed worker; inference stays in the model API."""
from datetime import datetime, timedelta, timezone
import logging
import time
import uuid
import shutil

import httpx
from sqlalchemy import and_, or_, select
from .config import get_settings
from .db import Job, Session, Upload

log = logging.getLogger("worker")
OWNER = str(uuid.uuid4())
ACTIVE = ("preparing", "running")
settings = get_settings()


def claim():
    now = datetime.now(timezone.utc)
    with Session.begin() as session:
        job = session.scalar(select(Job).where(or_(Job.status == "queued", and_(Job.status.in_(ACTIVE), Job.lease_until < now)))
                             .order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
        if job is None:
            return None
        job.attempts += 1
        if job.attempts > 3:
            job.status, job.message, job.error_code = "failed", "Lượt xử lý bị gián đoạn nhiều lần. Vui lòng tải lại CT.", "WORKER_INTERRUPTED"
            return None
        job.status, job.message = "preparing", "Đang chuẩn bị ảnh CT"
        job.lease_owner = OWNER
        job.lease_until = now + timedelta(minutes=2)
        return str(job.id), job.model_id, job.model_version


def update(job_id, state):
    with Session.begin() as session:
        job = session.get(Job, uuid.UUID(job_id), with_for_update=True)
        if job.lease_owner != OWNER:
            raise RuntimeError("Worker lease has changed")
        job.status = state["status"] if state["status"] != "queued" else "preparing"
        job.progress = max(0, min(100, int(state.get("progress", 0))))
        job.message = state.get("message", "Đang xử lý")[:500]
        job.error_code = state.get("error_code")
        if job.status in ("completed", "awaiting_selection"):
            job.result = state["result"]
        job.lease_until = datetime.now(timezone.utc) + timedelta(minutes=2)


def process(job_id, model_id, version):
    failures = 0
    started = False
    with httpx.Client(base_url=settings.model_api_url, timeout=30) as client:
        while True:
            try:
                if not started:
                    response = client.post(f"/v1/jobs/{job_id}", json={"model_id": model_id, "model_version": version})
                else:
                    response = client.get(f"/v1/jobs/{job_id}")
                if response.status_code == 404:
                    if not started:
                        update(job_id, dict(status="failed", progress=0, message="Không tìm thấy file CT. Vui lòng tải lại file.", error_code="MISSING_INPUT"))
                        return
                    started = False
                    time.sleep(2)
                    continue
                if response.status_code in (409, 422):
                    update(job_id, dict(status="failed", progress=0, message="Cấu hình mô hình đã thay đổi hoặc CT không hợp lệ. Vui lòng tạo lượt xử lý mới.", error_code="MODEL_CHANGED"))
                    return
                response.raise_for_status()
                state = response.json()
                started, failures = True, 0
                update(job_id, state)
                if state["status"] in ("completed", "failed", "awaiting_selection"):
                    return
            except httpx.HTTPError:
                failures += 1
                if failures >= 30:
                    update(job_id, dict(status="failed", progress=0, message="Không kết nối được mô hình. Vui lòng thử lại sau.", error_code="MODEL_UNAVAILABLE"))
                    return
                update(job_id, dict(status="preparing", progress=0, message="Đang kết nối lại mô hình"))
                started = False
            time.sleep(2)


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            with Session.begin() as session:
                cutoff = datetime.now(timezone.utc) - timedelta(days=1)
                stale = session.scalars(select(Upload).where(Upload.status == "uploading", Upload.created_at < cutoff).with_for_update(skip_locked=True).limit(10)).all()
                for row in stale:
                    if session.get(Job, row.id) is None:
                        shutil.rmtree(settings.jobs_dir / str(row.id), ignore_errors=True)
                        row.status = "cancelled"
            job = claim()
            if job:
                log.info("Processing job %s", job[0])
                process(*job)
            else:
                time.sleep(2)
        except Exception:
            log.exception("Worker operation failed; leased work will be retried")
            time.sleep(5)


if __name__ == "__main__":
    main()
