from contextlib import asynccontextmanager
from pathlib import Path
import logging
import shutil
import uuid

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from common.archive import InputError, inspect_archive
from .config import get_settings
from .db import Job, Session, engine
from . import auth

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    auth.validate_configuration()
    settings.jobs_dir.mkdir(parents=True, exist_ok=True)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    yield
    engine.dispose()


app = FastAPI(title="Điện Biên CT → PET API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(SQLAlchemyError)
async def db_error(request, exc):
    logger.exception("Database operation failed", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Dịch vụ lưu dữ liệu tạm thời chưa sẵn sàng. Vui lòng thử lại."})


@app.middleware("http")
async def upload_limit(request: Request, call_next):
    length = request.headers.get("content-length")
    if request.url.path == "/api/jobs" and length:
        try:
            if int(length) > (settings.upload_limit_mb + 2) * 1024**2:
                return JSONResponse(status_code=413, content={"detail": f"ZIP tối đa {settings.upload_limit_mb} MB."})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Yêu cầu tải lên không hợp lệ."})
    return await call_next(request)


@app.middleware("http")
async def require_session(request: Request, call_next):
    public = {"/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/guest"}
    if request.method != "OPTIONS" and request.url.path not in public:
        try:
            request.state.username = auth.authenticate(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers={"Cache-Control": "no-store"})
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# CORS wraps authentication, including 401 responses and preflight requests.
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "Authorization", "Content-Range"],
                   expose_headers=["Content-Disposition"])


@app.get("/api/auth/status")
def auth_status():
    return {"required": settings.auth_enabled, "mode": settings.auth_mode, "upload_limit_mb": settings.upload_limit_mb}


@app.post("/api/auth/guest")
def guest_session(request: Request):
    return auth.guest_session(request)


@app.post("/api/auth/login")
def login(payload: auth.Login, request: Request):
    return auth.login(request, payload)


@app.get("/api/auth/session")
def session(request: Request):
    return {"username": request.state.username}


def model_request(method, path, **kwargs):
    try:
        response = httpx.request(method, settings.model_api_url + path, timeout=15, **kwargs)
        if 400 <= response.status_code < 500:
            detail = response.json().get("detail", "Yêu cầu không hợp lệ.")
            raise HTTPException(response.status_code, detail)
        response.raise_for_status()
        return response
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Dịch vụ mô hình chưa sẵn sàng. Vui lòng thử lại sau.") from exc


def require_job(job_id, principal):
    with Session() as session:
        job = session.get(Job, job_id)
        if job is None or not auth.can_access(job.owner, principal):
            raise HTTPException(404, "Không tìm thấy lượt xử lý này.")
        return job


def serialize(job):
    return dict(id=str(job.id), filename=job.filename, input_bytes=job.input_bytes,
                status=job.status, progress=job.progress, message=job.message,
                model_id=job.model_id, model_label=job.model_label, model_version=job.model_version,
                created_at=job.created_at.isoformat(), error_code=job.error_code, result=job.result)


@app.get("/api/health")
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "database": "postgresql"}


@app.get("/api/models")
def models():
    return model_request("GET", "/v1/models").json()


@app.post("/api/jobs", status_code=202)
def create_job(request: Request, file: UploadFile = File(...), model_id: str = Form(...)):
    available = model_request("GET", "/v1/models").json()["models"]
    model = next((m for m in available if m["id"] == model_id and m["ready"]), None)
    if model is None:
        raise HTTPException(409, "Mô hình chưa sẵn sàng. Vui lòng chọn mô hình khác hoặc thử lại sau.")
    filename = Path((file.filename or "CT.zip").replace("\\", "/")).name[:200]
    if not filename.lower().endswith(".zip"):
        raise HTTPException(415, "Vui lòng chọn file ZIP chứa ảnh CT DICOM hoặc NIfTI.")
    job_id = uuid.uuid4()
    folder = settings.jobs_dir / str(job_id)
    folder.mkdir(parents=True)
    partial = folder / "input.zip.part"
    total = 0
    try:
        with partial.open("wb") as output:
            while chunk := file.file.read(4 * 1024**2):
                total += len(chunk)
                if total > settings.upload_limit_mb * 1024**2:
                    raise HTTPException(413, f"ZIP tối đa {settings.upload_limit_mb} MB.")
                output.write(chunk)
        inspect_archive(partial, settings.archive_limit_mb * 1024**2)
        partial.rename(folder / "input.zip")
        with Session.begin() as session:
            job = Job(id=job_id, owner=request.state.username, filename=filename, input_bytes=total, model_id=model["id"],
                      model_label=model["label"], model_version=model["version"])
            session.add(job)
            session.flush()
        return serialize(job)
    except InputError as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        file.file.close()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: uuid.UUID, request: Request):
    return serialize(require_job(job_id, request.state.username))


@app.get("/api/jobs/{job_id}/preview/{kind}/{plane}")
def preview(job_id: uuid.UUID, kind: str, plane: str, request: Request, index: int = 0,
            window: str = "soft", pet_max: int = 12000):
    job = require_job(job_id, request.state.username)
    if job.status != "completed":
        raise HTTPException(409, "Ảnh đang được xử lý. Vui lòng đợi hoàn tất.")
    if kind not in ("ct", "pet") or plane not in ("axial", "coronal", "sagittal"):
        raise HTTPException(404, "Mặt cắt không hợp lệ.")
    response = model_request("GET", f"/v1/jobs/{job_id}/preview/{kind}/{plane}",
                             params=dict(index=index, window=window, pet_max=pet_max))
    return Response(response.content, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/jobs/{job_id}/download")
def download(job_id: uuid.UUID, request: Request):
    job = require_job(job_id, request.state.username)
    path = settings.jobs_dir / str(job_id) / "output" / "pet.zip"
    if job.status != "completed" or not path.is_file():
        raise HTTPException(409, "PET chưa sẵn sàng để tải xuống.")
    return FileResponse(path, media_type="application/zip", filename=f"PET_{str(job_id)[:8]}.zip")


@app.get("/api/jobs/{job_id}/volume/{kind}")
def volume_preview(job_id: uuid.UUID, kind: str, request: Request):
    from .volume_preview import encode_volume
    job = require_job(job_id, request.state.username)
    if kind not in ("ct", "pet"):
        raise HTTPException(404, "Volume không hợp lệ.")
    if job.status != "completed":
        raise HTTPException(409, "Ảnh chưa xử lý xong.")
    try:
        content = encode_volume(settings.jobs_dir / str(job_id) / "output", kind)
    except (OSError, ValueError, KeyError):
        logger.exception("Cannot encode preview volume for %s", job_id)
        raise HTTPException(409, "Chưa đọc được ảnh 3D. Bạn vẫn có thể xem ba mặt cắt.")
    return Response(content, media_type="application/octet-stream", headers={"Content-Encoding": "gzip"})


from .uploads import router as upload_router
app.include_router(upload_router)


class SeriesChoice(BaseModel):
    uid: str = Field(min_length=1, max_length=64)


def resume_input(job_id, principal, uid=None):
    require_job(job_id, principal)
    with Session.begin() as session:
        job = session.get(Job, job_id, with_for_update=True)
        expected = "awaiting_selection" if uid is not None else "failed"
        if job.status != expected or (uid is None and job.error_code != "INVALID_CT"):
            raise HTTPException(409, "Lượt xử lý không ở trạng thái chờ đọc CT.")
        endpoint = "select-series" if uid is not None else "retry-input"
        # Model resume is idempotent across a lost response / DB rollback.
        state = model_request("GET", f"/v1/jobs/{job_id}").json()
        if state["status"] != "queued":
            model_request("POST", f"/v1/jobs/{job_id}/{endpoint}", **({"json": {"uid": uid}} if uid is not None else {}))
        job.status, job.progress, job.message = "queued", 0, "Đang chờ đọc CT"
        job.result, job.error_code, job.lease_owner, job.lease_until = None, None, None, None
        job.attempts = 0
    return serialize(job)


@app.post("/api/jobs/{job_id}/select-series")
def select_series(job_id: uuid.UUID, payload: SeriesChoice, request: Request):
    return resume_input(job_id, request.state.username, payload.uid)


@app.post("/api/jobs/{job_id}/retry-input")
def retry_input(job_id: uuid.UUID, request: Request):
    return resume_input(job_id, request.state.username)
