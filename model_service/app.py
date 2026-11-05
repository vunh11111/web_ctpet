from contextlib import asynccontextmanager
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import torch
from common.archive import InputError
from .config import get_settings
from .preview import render
from .registry import load_registry, public_models
from .runner import Runner

runner = None


@asynccontextmanager
async def lifespan(app):
    global runner
    torch.set_num_threads(2)
    runner = Runner(load_registry())
    yield
    runner.pool.shutdown(wait=True)


app = FastAPI(title="CT → PET Model API", version="0.1.0", lifespan=lifespan)


class Submit(BaseModel):
    model_id: str
    model_version: str


@app.get("/v1/health")
def health():
    return {"status": "ok"}


@app.get("/v1/models")
def models():
    return public_models(runner.models)


@app.post("/v1/jobs/{job_id}", status_code=202)
def submit(job_id: uuid.UUID, payload: Submit):
    model = runner.models.get(payload.model_id)
    if model is None or model.version is None or model.version != payload.model_version:
        raise HTTPException(409, "Model is unavailable or its version changed")
    if not (runner.folder(job_id) / "input.zip").is_file():
        raise HTTPException(404, "Input archive does not exist")
    try:
        return runner.submit(job_id, model)
    except InputError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/v1/jobs/{job_id}")
def state(job_id: uuid.UUID):
    state = runner.read(job_id)
    if state is None:
        raise HTTPException(404, "Unknown inference job")
    return state


@app.get("/v1/jobs/{job_id}/preview/{kind}/{plane}")
def preview(job_id: uuid.UUID, kind: str, plane: str, index: int = 0, window: str = "soft", pet_max: int = 12000):
    state = runner.read(job_id)
    if not state or state["status"] != "completed":
        raise HTTPException(409, "Inference has not completed")
    try:
        content = render(runner.folder(job_id) / "output", kind, plane, index, window, pet_max)
        return Response(content, media_type="image/png")
    except InputError as exc:
        raise HTTPException(422, str(exc)) from exc


class Selection(BaseModel):
    uid: str


@app.post("/v1/jobs/{job_id}/select-series")
def select_series(job_id: uuid.UUID, payload: Selection):
    try:
        return runner.resume(job_id, payload.uid)
    except InputError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/v1/jobs/{job_id}/retry-input")
def retry_input(job_id: uuid.UUID):
    try:
        return runner.resume(job_id)
    except InputError as exc:
        raise HTTPException(409, str(exc)) from exc
