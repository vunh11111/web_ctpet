from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import torch
from .config import get_settings


@dataclass
class Model:
    id: str
    label: str
    adapter: str
    checkpoint: Path
    options: dict
    version: str | None


def load_registry():
    settings = get_settings()
    entries = json.loads(Path(settings.model_registry_path).read_text()) if settings.model_registry_path else [
        dict(id="reggan-baseline", label=settings.model_label,
             adapter="model_service.adapters.reggan:RegGANAdapter", checkpoint=settings.model_checkpoint, options={"spacing_mm": 3.0})]
    models = {}
    for entry in entries:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", entry["id"]) or entry["id"] in models:
            raise ValueError("Model IDs must be unique URL-safe names")
        path = Path(entry["checkpoint"]).expanduser()
        digest = None
        if path.is_file():
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(8 * 1024**2), b""):
                    hasher.update(block)
            hasher.update(json.dumps({"adapter": entry["adapter"], "options": entry.get("options", {})}, sort_keys=True).encode())
            digest = hasher.hexdigest()
        models[entry["id"]] = Model(entry["id"], entry["label"], entry["adapter"], path, entry.get("options", {}), digest)
    return models


def public_models(models):
    device = get_settings().model_device
    device_ready = not device.startswith("cuda") or torch.cuda.is_available()
    return {"models": [dict(id=m.id, label=m.label, version=m.version,
                            ready=m.version is not None and device_ready,
                            message="Sẵn sàng" if m.version and device_ready else ("GPU chưa sẵn sàng" if not device_ready else "Chưa bổ sung checkpoint")) for m in models.values()]}
