"""The existing frozen RegGAN baseline; no TTA and no training at serving time."""
from pathlib import Path
import nibabel as nib
from nibabel.processing import resample_from_to, resample_to_output
import numpy as np
import torch
from torch import nn
from common.archive import InputError


class ResnetBlock(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.conv_block = nn.Sequential(nn.ReflectionPad2d(1), nn.Conv2d(dim, dim, 3),
            nn.InstanceNorm2d(dim), nn.ReLU(True), nn.ReflectionPad2d(1),
            nn.Conv2d(dim, dim, 3), nn.InstanceNorm2d(dim))

    def forward(self, x):
        return x + self.conv_block(x)


class Generator(nn.Module):
    def __init__(self):
        super().__init__()
        self.model_head = nn.Sequential(nn.ReflectionPad2d(3), nn.Conv2d(1, 64, 7), nn.InstanceNorm2d(64), nn.ReLU(True),
            nn.Conv2d(64, 128, 3, 2, 1), nn.InstanceNorm2d(128), nn.ReLU(True),
            nn.Conv2d(128, 256, 3, 2, 1), nn.InstanceNorm2d(256), nn.ReLU(True))
        self.model_body = nn.Sequential(*[ResnetBlock(256) for _ in range(9)])
        self.model_tail = nn.Sequential(nn.ConvTranspose2d(256, 128, 3, 2, 1, output_padding=1),
            nn.InstanceNorm2d(128), nn.ReLU(True), nn.ConvTranspose2d(128, 64, 3, 2, 1, output_padding=1),
            nn.InstanceNorm2d(64), nn.ReLU(True), nn.ReflectionPad2d(3), nn.Conv2d(64, 1, 7), nn.Tanh())

    def forward(self, x):
        return self.model_tail(self.model_body(self.model_head(x)))


class RegGANAdapter:
    def __init__(self, checkpoint: Path, device: str, options: dict):
        self.device = torch.device(device)
        self.spacing = float(options.get("spacing_mm", 3.0))
        if self.spacing != 3.0:
            raise ValueError("This baseline's verified training grid is 3 mm")
        self.preview_spacing = float(options.get("preview_spacing_mm", 1.5))
        # This is a trusted operator-configured checkpoint, never an uploaded user file.
        state = torch.load(checkpoint, map_location="cpu", weights_only=False, mmap=True)
        self.generator = Generator()
        self.generator.load_state_dict(state.get("generator", state), strict=True)
        self.generator.to(self.device).eval().requires_grad_(False)
        del state

    def infer(self, ct, progress):
        progress(15, "Đang chuẩn hóa ảnh CT")
        iso = resample_to_output(ct, voxel_sizes=(self.spacing,) * 3, order=1, cval=-1000)
        values = iso.get_fdata(dtype=np.float32)
        # Source loader uses (I,P,L) axes in zyx order. Canonical input is xyz RAS.
        model_volume = values[::-1, ::-1, ::-1].transpose(2, 1, 0)
        depth, height, width = model_volume.shape
        if height > 256 or width > 256:
            raise InputError("Vùng chụp CT quá rộng cho baseline hiện tại (tối đa 768 mm). Vui lòng chọn CT phù hợp.")
        py, px = (256 - height) // 2, (256 - width) // 2
        predictions = []
        with torch.inference_mode():
            for z, image in enumerate(model_volume):
                canvas = np.full((256, 256), -1000., np.float32)
                canvas[py:py + height, px:px + width] = image
                normalized = np.clip(canvas + 1024., 0, 4095.) / 4095. * 2. - 1.
                tensor = torch.from_numpy(normalized)[None, None].to(self.device)
                prediction = self.generator(tensor).squeeze().cpu().numpy()
                prediction = np.clip((prediction * .5 + .5) * 32767., 0, 32767.)
                predictions.append(prediction[py:py + height, px:px + width])
                progress(20 + int(65 * (z + 1) / depth), f"Đang sinh PET · lát {z + 1}/{depth}")
        pet_xyz = np.stack(predictions).transpose(2, 1, 0)[::-1, ::-1, ::-1].copy()
        pet_iso = nib.Nifti1Image(pet_xyz, iso.affine)
        progress(88, "Đang khôi phục kích thước ảnh PET")
        pet = resample_from_to(pet_iso, (ct.shape, ct.affine), order=1, cval=0)
        progress(90, "Đang tạo ảnh xem trước độ nét cao")
        preview_ct = resample_to_output(ct, voxel_sizes=(self.preview_spacing,) * 3, order=1, cval=-1000)
        preview_pet = resample_from_to(pet_iso, (preview_ct.shape, preview_ct.affine), order=1, cval=0)
        return pet, preview_ct, preview_pet
