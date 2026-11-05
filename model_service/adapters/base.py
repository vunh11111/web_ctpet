from typing import Callable, Protocol
from pathlib import Path
import nibabel as nib

Progress = Callable[[int, str], None]


class ModelAdapter(Protocol):
    """Implement this contract to add an architecture without touching FE/BE.

    infer returns (PET on input CT grid, CT preview grid, PET preview grid).
    All images use xyz NIfTI arrays and RAS world coordinates in millimetres.
    """
    def __init__(self, checkpoint: Path, device: str, options: dict): ...
    def infer(self, ct: nib.Nifti1Image, progress: Progress) -> tuple: ...
