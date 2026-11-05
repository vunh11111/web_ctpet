"""8 MiB HTTP chunks keep large CT uploads below proxy body-size limits."""
import os
from pathlib import Path
import re
import shutil
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from common.archive import InputError, inspect_archive
from .config import get_settings
from .db import Job, Session, Upload
from .auth import can_access

router = APIRouter(prefix="/api/uploads")
settings = get_settings()
CHUNK = 8 * 1024**2


class Begin(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    total_bytes: int = Field(gt=0)
    model_id: str = Field(min_length=1, max_length=64)


def info(row):
    return {"id": str(row.id), "offset": row.offset, "total_bytes": row.total_bytes, "status": row.status, "chunk_bytes": CHUNK}


@router.post("", status_code=201)
def begin(payload: Begin, request: Request):
    from .app import model_request
    if payload.total_bytes > settings.upload_limit_mb * 1024**2:
        raise HTTPException(413, f"ZIP tối đa {settings.upload_limit_mb} MB.")
    filename = Path(payload.filename.replace("\\", "/")).name
    if not filename.lower().endswith(".zip"):
        raise HTTPException(415, "Vui lòng chọn file ZIP chứa CT.")
    models = model_request("GET", "/v1/models").json()["models"]
    model = next((m for m in models if m["id"] == payload.model_id and m["ready"]), None)
    if not model:
        raise HTTPException(409, "Mô hình chưa sẵn sàng.")
    with Session.begin() as session:
        row = Upload(owner=request.state.username, filename=filename, total_bytes=payload.total_bytes, model_id=model["id"], model_label=model["label"], model_version=model["version"])
        session.add(row); session.flush()
        folder = settings.jobs_dir / str(row.id)
        folder.mkdir(parents=True)
        (folder / "input.zip.part").touch()
    return info(row)


@router.get("/{upload_id}")
def status(upload_id: uuid.UUID, request: Request):
    with Session() as session:
        row = session.get(Upload, upload_id)
        if not row or not can_access(row.owner, request.state.username):
            raise HTTPException(404, "Không tìm thấy lượt tải lên.")
        return info(row)


@router.put("/{upload_id}")
async def chunk(upload_id: uuid.UUID, request: Request):
    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", request.headers.get("content-range", ""))
    if not match:
        raise HTTPException(422, "Thông tin phần tải lên không hợp lệ.")
    start, end, total = map(int, match.groups())
    if end < start or end - start + 1 > CHUNK or end >= total:
        raise HTTPException(413, "Phần tải lên vượt kích thước cho phép.")
    data = bytearray()
    async for block in request.stream():
        data.extend(block)
        if len(data) > CHUNK:
            raise HTTPException(413, "Phần tải lên vượt kích thước cho phép.")
    if len(data) != end - start + 1:
        raise HTTPException(422, "Phần tải lên chưa đầy đủ. Vui lòng thử lại.")
    # Keep synchronous disk/DB work in FastAPI's thread pool.
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(save_chunk, upload_id, start, end, total, data, request.state.username)


def save_chunk(upload_id, start, end, total, data, principal):
    with Session.begin() as session:
        row = session.get(Upload, upload_id, with_for_update=True)
        if row and not can_access(row.owner, principal):
            raise HTTPException(404, "Không tìm thấy lượt tải lên.")
        if not row or row.status != "uploading":
            raise HTTPException(409, "Lượt tải lên không còn hoạt động.")
        if total != row.total_bytes:
            raise HTTPException(422, "Kích thước CT không khớp.")
        path = settings.jobs_dir / str(upload_id) / "input.zip.part"
        if start < row.offset:
            with path.open("rb") as stream:
                stream.seek(start)
                if end < row.offset and stream.read(len(data)) == data:
                    return info(row)  # Lost acknowledgement: safely retry the same chunk.
            raise HTTPException(409, "Nội dung phần tải lên không khớp.")
        if start != row.offset:
            raise HTTPException(409, "Thứ tự phần tải lên không khớp.")
        with path.open("r+b") as stream:
            stream.seek(start); stream.write(data); stream.flush(); os.fsync(stream.fileno())
        row.offset = end + 1
        return info(row)


@router.post("/{upload_id}/complete", status_code=202)
def complete(upload_id: uuid.UUID, request: Request):
    from .app import serialize
    error = None
    with Session.begin() as session:
        row = session.get(Upload, upload_id, with_for_update=True)
        if not row or not can_access(row.owner, request.state.username):
            raise HTTPException(404, "Không tìm thấy lượt tải lên.")
        job = session.get(Job, upload_id)
        if job:
            return serialize(job)
        if row.status != "uploading" or row.offset != row.total_bytes:
            raise HTTPException(409, "CT chưa được tải lên đầy đủ.")
        folder = settings.jobs_dir / str(upload_id)
        path = folder / "input.zip.part"
        if not path.exists() and (folder / "input.zip").exists():
            path = folder / "input.zip"
        try:
            inspect_archive(path, settings.archive_limit_mb * 1024**2)
        except InputError as exc:
            row.status = "failed"
            error = str(exc)
            shutil.rmtree(folder, ignore_errors=True)
        if error is None:
            # Rename is idempotent across a crash before the database commit.
            if path.name != "input.zip":
                path.replace(folder / "input.zip")
            job = Job(id=row.id, owner=row.owner, filename=row.filename, input_bytes=row.total_bytes,
                      model_id=row.model_id, model_label=row.model_label, model_version=row.model_version)
            session.add(job); session.flush(); row.status = "completed"
    if error:
        raise HTTPException(422, error)
    return serialize(job)


@router.delete("/{upload_id}", status_code=204)
def cancel(upload_id: uuid.UUID, request: Request):
    with Session.begin() as session:
        row = session.get(Upload, upload_id, with_for_update=True)
        if row and not can_access(row.owner, request.state.username):
            raise HTTPException(404, "Không tìm thấy lượt tải lên.")
        if row and row.status == "uploading":
            row.status = "cancelled"
            shutil.rmtree(settings.jobs_dir / str(upload_id), ignore_errors=True)
