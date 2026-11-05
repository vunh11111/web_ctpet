"""Bounded float32 volume transport. Header + x-fast voxels in patient LPS mm."""
import gzip
import itertools
import json
from pathlib import Path
import struct

import numpy as np
from scipy.ndimage import gaussian_filter, affine_transform


def preview_affine(metadata):
    if "preview_affine_RAS_mm" in metadata:
        return np.asarray(metadata["preview_affine_RAS_mm"], dtype=float)
    # Old jobs: RegGAN's resample_to_output creates an axis-aligned RAS grid
    # spanning the input voxel centers. Its origin is the minimum world corner.
    affine = np.asarray(metadata["output_affine_RAS_mm"], dtype=float)
    shape = metadata["output_shape_xyz"]
    corners = np.asarray(list(itertools.product(*[(0, n - 1) for n in shape])))
    world = corners @ affine[:3, :3].T + affine[:3, 3]
    result = np.diag([*metadata["preview_spacing_mm"], 1.])
    result[:3, 3] = world.min(axis=0)
    return result


def encode_volume(folder: Path, kind: str):
    if kind not in ("ct", "pet"):
        raise ValueError("Unknown volume")
    metadata = json.loads((folder / "metadata.json").read_text())
    values = np.load(folder / f"preview_{kind}.npy", mmap_mode="r", allow_pickle=False)
    if values.ndim != 3 or list(values.shape) != metadata["preview_shape_xyz"]:
        raise ValueError("Preview geometry mismatch")
    # Use a continuous scale: 161 voxels must not suddenly become 81 voxels.
    # Both modalities share voxel centers and a low-pass filter before resampling.
    step = max(1., (max(values.shape) - 1) / 159)
    if step > 1:
        shape = tuple(min(160, int(np.floor((n - 1) / step + 1e-8)) + 1) for n in values.shape)
        filtered = gaussian_filter(np.asarray(values, dtype=np.float32), sigma=step / 2, mode="nearest")
        data = affine_transform(filtered, np.eye(3) * step, output_shape=shape,
                                order=1, mode="nearest", prefilter=False).astype("<f4")
    else:
        data = np.asarray(values, dtype="<f4")
    ras = preview_affine(metadata)
    if ras.shape != (4, 4) or not np.isfinite(ras).all():
        raise ValueError("Invalid preview affine")
    lps = np.diag([-1., -1., 1., 1.]) @ ras
    lps[:3, :3] *= step
    spacing = np.linalg.norm(lps[:3, :3], axis=0)
    if np.any(spacing <= 0):
        raise ValueError("Invalid preview spacing")
    direction = lps[:3, :3] / spacing
    if not np.allclose(direction.T @ direction, np.eye(3), atol=1e-5):
        raise ValueError("Sheared preview grid requires resampling")
    header = {"version": 1, "kind": kind, "dimensions": list(data.shape),
              "spacing": spacing.tolist(), "origin": lps[:3, 3].tolist(),
              # vtkImageData direction stores consecutive direction cosines per axis.
              "direction": direction.flatten(order="F").tolist(), "coordinate_system": "LPS",
              "dtype": "float32-le", "voxel_order": "x-fast", "units": "HU" if kind == "ct" else "model_raw_not_SUV",
              "decimation": step, "antialias": step > 1, "source_shape": list(values.shape)}
    raw = json.dumps(header, separators=(",", ":")).encode()
    # Pad JSON to a float32 boundary so JS can directly view the payload.
    raw += b" " * (-len(raw) % 4)
    return gzip.compress(struct.pack("<I", len(raw)) + raw + data.tobytes(order="F"), compresslevel=1)
