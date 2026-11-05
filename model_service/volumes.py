from pathlib import Path
import math
import nibabel as nib
import numpy as np
import pydicom
import SimpleITK as sitk
from common.archive import InputError


def validate_image(image, max_voxels):
    shape = image.shape
    if len(shape) not in (3, 4) or math.prod(shape) > max_voxels:
        raise InputError("CT vượt giới hạn kích thước của demo.")
    if len(shape) == 4 and shape[-1] == 1:
        image = nib.Nifti1Image(image.get_fdata(dtype=np.float32)[..., 0], image.affine)
        shape = image.shape
    if len(shape) != 3 or min(shape) < 2 or math.prod(shape) > max_voxels:
        raise InputError("Cần một ảnh CT 3D trong giới hạn kích thước, không phải ảnh 2D hoặc chuỗi thời gian.")
    if np.iscomplexobj(image.dataobj) or not np.isfinite(image.affine).all():
        raise InputError("Dữ liệu hoặc tọa độ CT không hợp lệ.")
    spacing = np.linalg.norm(image.affine[:3, :3], axis=0)
    if np.any(spacing < .1) or np.any(spacing > 20) or abs(np.linalg.det(image.affine[:3, :3])) < 1e-8:
        raise InputError("Voxel spacing của CT không hợp lệ. Vui lòng kiểm tra file gốc.")
    values = image.get_fdata(dtype=np.float32)
    if not np.isfinite(values).all():
        raise InputError("CT chứa giá trị bị lỗi. Vui lòng xuất lại ảnh CT.")
    if float(values.min()) < -20000 or float(values.max()) > 100000:
        raise InputError("Thang giá trị CT bất thường. NIfTI cần chứa HU đã hiệu chỉnh.")
    return nib.as_closest_canonical(nib.Nifti1Image(values, image.affine))


class SeriesSelectionRequired(InputError):
    def __init__(self, options, ignored):
        super().__init__("ZIP có nhiều series CT. Vui lòng chọn series cần tạo PET.")
        self.options, self.ignored = options, ignored


def load_volume(folder: Path, max_voxels: int, series_uid: str | None = None):
    files = [p for p in folder.rglob("*") if p.is_file()]
    niftis = [p for p in files if p.name.lower().endswith((".nii", ".nii.gz"))]
    if niftis:
        if len(niftis) != 1:
            raise InputError("ZIP chứa nhiều ảnh NIfTI. Vui lòng chỉ gửi một ảnh CT 3D.")
        try:
            return validate_image(nib.load(niftis[0]), max_voxels), {"input_format": "NIfTI"}
        except InputError:
            raise
        except Exception as exc:
            raise InputError("Không đọc được ảnh NIfTI. Vui lòng kiểm tra file CT.") from exc
    series = {}
    ignored = 0
    for path in files:
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True)
        except (pydicom.errors.InvalidDicomError, OSError, ValueError):
            continue
        if ds.get("Modality") != "CT":
            ignored += 1
            continue
        # Modality alone is insufficient: screenshots may also be tagged CT.
        if str(ds.get("SOPClassUID", "")) == "1.2.840.10008.5.1.4.1.1.7":
            ignored += 1
            continue
        image_type = " ".join(str(x) for x in ds.get("ImageType", []))
        if "LOCALIZER" in image_type.upper() or "SCOUT" in image_type.upper():
            ignored += 1
            continue
        if int(ds.get("NumberOfFrames", 1)) != 1:
            raise InputError("DICOM CT nhiều frame chưa được hỗ trợ. Vui lòng xuất CT thành NIfTI hoặc DICOM từng lát.")
        if not all(k in ds for k in ("SeriesInstanceUID", "ImagePositionPatient", "ImageOrientationPatient")):
            raise InputError("DICOM thiếu thông tin vị trí lát cắt. Vui lòng xuất lại series CT.")
        series.setdefault(str(ds.SeriesInstanceUID), []).append((path, ds))
    if not series:
        raise InputError("Không tìm thấy CT. ZIP cần chứa một series DICOM CT hoặc một file .nii/.nii.gz.")
    options = []
    for uid, items in series.items():
        ds = items[0][1]
        options.append(dict(uid=uid, label=str(ds.get("SeriesDescription", "Series CT"))[:160],
                            number=str(ds.get("SeriesNumber", ""))[:20], slices=len(items),
                            rows=int(ds.Rows), columns=int(ds.Columns),
                            slice_thickness_mm=str(ds.get("SliceThickness", ""))[:24]))
    if series_uid is None and len(series) > 1:
        raise SeriesSelectionRequired(options, ignored)
    if series_uid is not None and series_uid not in series:
        raise InputError("Series CT đã chọn không tồn tại trong ZIP.")
    selected_uid = series_uid or next(iter(series))
    slices = series[selected_uid]
    if len(slices) < 2:
        raise InputError("Series CT cần có ít nhất hai lát cắt.")
    orientation = np.asarray(slices[0][1].ImageOrientationPatient, dtype=float)
    normal = np.cross(orientation[:3], orientation[3:])
    for _, ds in slices:
        if not np.allclose(ds.ImageOrientationPatient, orientation, atol=1e-4):
            raise InputError("Các lát DICOM không cùng hướng. Vui lòng xuất lại một series CT hoàn chỉnh.")
    slices.sort(key=lambda item: np.dot(np.asarray(item[1].ImagePositionPatient, float), normal))
    positions = [np.dot(np.asarray(ds.ImagePositionPatient, float), normal) for _, ds in slices]
    increments = np.diff(positions)
    if increments.min() <= 1e-4 or not np.allclose(increments, np.median(increments), rtol=.02, atol=.1):
        raise InputError("CT có lát trùng hoặc khoảng cách lát không đều. Vui lòng xuất lại series CT.")
    rows, columns = int(slices[0][1].Rows), int(slices[0][1].Columns)
    if len(slices) * rows * columns > max_voxels:
        raise InputError("CT vượt giới hạn kích thước của demo.")
    try:
        reader = sitk.ImageSeriesReader()
        reader.SetFileNames([str(p) for p, _ in slices])
        reader.SetOutputPixelType(sitk.sitkFloat32)
        volume = reader.Execute()  # GDCM applies each slice's RescaleSlope/Intercept exactly once.
        values = sitk.GetArrayFromImage(volume).transpose(2, 1, 0)
        affine = np.eye(4)
        affine[:3, :3] = np.asarray(volume.GetDirection()).reshape(3, 3) @ np.diag(volume.GetSpacing())
        affine[:3, 3] = volume.GetOrigin()
        affine = np.diag([-1., -1., 1., 1.]) @ affine  # DICOM LPS -> NIfTI RAS.
        return validate_image(nib.Nifti1Image(values, affine), max_voxels), {"input_format": "DICOM", "source_slices": len(slices), "selected_series_uid": selected_uid, "ignored_files": ignored}
    except InputError:
        raise
    except Exception as exc:
        raise InputError("Không đọc được pixel DICOM. Vui lòng thử xuất CT thành NIfTI.") from exc
