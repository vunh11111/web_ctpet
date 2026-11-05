from io import BytesIO
from pathlib import Path
import numpy as np
from PIL import Image
from common.archive import InputError

CT_WINDOWS = {"soft": (-160, 240), "lung": (-1000, 400), "bone": (-500, 1500)}
PET_STOPS = np.array([[0, 0, 4], [28, 16, 68], [79, 18, 123], [129, 37, 129],
                      [181, 54, 122], [229, 80, 100], [251, 135, 97], [254, 194, 135], [252, 253, 191]], dtype=float)
PET_LUT = np.column_stack([np.interp(np.linspace(0, 8, 256), np.arange(9), PET_STOPS[:, c]) for c in range(3)]).astype(np.uint8)


def render(folder: Path, kind: str, plane: str, index: int, window: str, pet_max: int):
    if kind not in ("ct", "pet") or plane not in ("axial", "coronal", "sagittal"):
        raise InputError("Mặt cắt không hợp lệ.")
    volume = np.load(folder / f"preview_{kind}.npy", mmap_mode="r")
    axis = {"axial": 2, "coronal": 1, "sagittal": 0}[plane]
    if not 0 <= index < volume.shape[axis]:
        raise InputError("Vị trí lát cắt không hợp lệ.")
    image = np.take(volume, index, axis=axis).T[::-1]
    if kind == "ct":
        if window not in CT_WINDOWS:
            raise InputError("Cửa sổ CT không hợp lệ.")
        low, high = CT_WINDOWS[window]
        pixels = (np.clip((image - low) / (high - low), 0, 1) * 255).astype(np.uint8)
        output = Image.fromarray(pixels).convert("RGB")
    else:
        if not 1000 <= pet_max <= 32767:
            raise InputError("Thang hiển thị PET không hợp lệ.")
        pixels = (np.clip(image / pet_max, 0, 1) * 255).astype(np.uint8)
        output = Image.fromarray(PET_LUT[pixels])
    # Preview arrays are on the common isotropic grid; pixel aspect is physical aspect.
    output.thumbnail((768, 768), Image.Resampling.LANCZOS)
    data = BytesIO()
    output.save(data, format="PNG")
    return data.getvalue()
