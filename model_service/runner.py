from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gc
import importlib
import json
import logging
from pathlib import Path
import shutil
import threading
import zipfile

import nibabel as nib
import numpy as np
import torch
from common.archive import InputError, extract_archive
from .config import get_settings
from .volumes import load_volume, SeriesSelectionRequired

log = logging.getLogger("model")


class Runner:
    def __init__(self, models):
        self.models = models
        self.settings = get_settings()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
        self.lock = threading.Lock()
        self.active = set()
        self.adapter = None
        self.loaded_version = None

    def folder(self, job_id):
        return self.settings.jobs_dir / str(job_id)

    def read(self, job_id):
        path = self.folder(job_id) / "state.json"
        return json.loads(path.read_text()) if path.exists() else None

    def write(self, job_id, state):
        path = self.folder(job_id) / "state.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False))
        temporary.replace(path)

    def submit(self, job_id, model):
        with self.lock:
            state = self.read(job_id)
            if state and state["model_version"] != model.version:
                raise InputError("Model version differs from the existing job")
            if state and (state["status"] in ("completed", "failed", "awaiting_selection") or str(job_id) in self.active):
                return state
            state = dict(status="queued", progress=0, message="Đang chờ mô hình", model_id=model.id, model_version=model.version)
            self.write(job_id, state)
            self.active.add(str(job_id))
            self.pool.submit(self.process, job_id, model, state)
            return state

    def resume(self, job_id, uid=None):
        with self.lock:
            state = self.read(job_id)
            if not state or str(job_id) in self.active:
                raise InputError("Lượt xử lý chưa sẵn sàng để tiếp tục.")
            if uid is not None:
                options = (state.get("result") or {}).get("series_options", [])
                if state["status"] != "awaiting_selection" or uid not in {o["uid"] for o in options}:
                    raise InputError("Series CT không hợp lệ hoặc đã được chọn.")
                path = self.folder(job_id) / "selected-series.json"
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps({"uid": uid}))
                temporary.replace(path)
            elif state["status"] != "failed" or state.get("error_code") != "INVALID_CT":
                raise InputError("Lượt xử lý này không thể đọc lại.")
            state.update(status="queued", progress=0, result=None, error_code=None, message="Đang chờ đọc CT")
            self.write(job_id, state)
            return state

    def process(self, job_id, model, state):
        folder = self.folder(job_id)
        extracted = folder / "extracted"
        output = folder / "output"

        def progress(value, message):
            state.update(status="preparing" if value < 20 else "running", progress=value, message=message)
            self.write(job_id, state)
        try:
            output.mkdir(exist_ok=True)
            progress(3, "Đang đọc file CT")
            shutil.rmtree(extracted, ignore_errors=True)
            extract_archive(folder / "input.zip", extracted, self.settings.archive_limit_mb * 1024**2)
            selection = folder / "selected-series.json"
            uid = json.loads(selection.read_text())["uid"] if selection.exists() else None
            ct, input_meta = load_volume(extracted, self.settings.max_voxels, uid)
            progress(10, "Đang nạp mô hình")
            if self.loaded_version != model.version:
                self.adapter = None
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                module, name = model.adapter.split(":")
                factory = getattr(importlib.import_module(module), name)
                self.adapter = factory(model.checkpoint, self.settings.model_device, model.options)
                self.loaded_version = model.version
            pet, preview_ct, preview_pet = self.adapter.infer(ct, progress)
            if pet.shape != ct.shape or not np.allclose(pet.affine, ct.affine, atol=1e-4):
                raise ValueError("Adapter violated the output geometry contract")
            pet_values = pet.get_fdata(dtype=np.float32)
            if not np.isfinite(pet_values).all():
                raise ValueError("Nonfinite model output")
            if preview_ct.shape != preview_pet.shape or not np.allclose(preview_ct.affine, preview_pet.affine):
                raise ValueError("Preview images must share one physical grid")
            preview_values = preview_ct.get_fdata(dtype=np.float32)
            voxel_spacing = np.linalg.norm(preview_ct.affine[:3, :3], axis=0)
            if not np.allclose(voxel_spacing, voxel_spacing[0], atol=1e-4):
                raise ValueError("The preview adapter contract requires an isotropic grid")
            if nib.aff2axcodes(preview_ct.affine) != ("R", "A", "S"):
                raise ValueError("Preview images must be canonical RAS")
            progress(92, "Đang tạo ảnh xem trước và file PET")
            np.save(output / "preview_ct.npy", preview_values)
            np.save(output / "preview_pet.npy", preview_pet.get_fdata(dtype=np.float32))
            final = nib.Nifti1Image(pet_values, ct.affine)
            final.header.set_xyzt_units("mm")
            final.header["descrip"] = b"Synthetic PET; model raw scale, NOT calibrated SUV"
            nib.save(final, output / "predicted_pet.nii.gz")
            shape = list(preview_ct.shape)
            metadata = dict(model_id=model.id, model_label=model.label, model_version=model.version,
                generated_at=datetime.now(timezone.utc).isoformat(), synthetic=True, pet_units="model_raw_not_SUV",
                output_shape_xyz=list(ct.shape), output_affine_RAS_mm=ct.affine.tolist(),
                output_orientation="RAS", preview_shape_xyz=shape, preview_spacing_mm=voxel_spacing.tolist(),
                preview_affine_RAS_mm=preview_ct.affine.tolist(),
                default_indices={"axial": shape[2] // 2, "coronal": shape[1] // 2, "sagittal": shape[0] // 2},
                input_format=input_meta["input_format"], input_details=input_meta, download_format="NIfTI (.nii.gz) in ZIP")
            (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
            with zipfile.ZipFile(output / "pet.zip.part", "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(output / "predicted_pet.nii.gz", "predicted_pet.nii.gz")
                archive.write(output / "metadata.json", "metadata.json")
            (output / "pet.zip.part").replace(output / "pet.zip")
            state.update(status="completed", progress=100, message="Đã tạo ảnh PET", result=metadata)
            self.write(job_id, state)
        except SeriesSelectionRequired as exc:
            state.update(status="awaiting_selection", progress=5, message=str(exc),
                         result={"series_options": exc.options, "ignored_files": exc.ignored})
            self.write(job_id, state)
        except InputError as exc:
            state.update(status="failed", progress=0, message=str(exc), error_code="INVALID_CT")
            self.write(job_id, state)
        except Exception:
            log.exception("Inference failed for job %s", job_id)
            state.update(status="failed", progress=0, message="Mô hình chưa xử lý được ca CT này. Vui lòng thử lại hoặc liên hệ người quản lý demo.", error_code="INFERENCE_FAILED")
            self.write(job_id, state)
        finally:
            shutil.rmtree(extracted, ignore_errors=True)
            with self.lock:
                self.active.discard(str(job_id))
