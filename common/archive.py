"""Bounded ZIP handling, shared by upload validation and the model importer."""
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile


class InputError(ValueError):
    pass


def inspect_archive(path: Path, limit_bytes: int, max_files: int = 6000):
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > max_files:
                raise InputError("ZIP chứa quá nhiều file. Vui lòng gửi một series CT.")
            total, seen = 0, set()
            for entry in entries:
                name = entry.filename.replace("\\", "/")
                parts = PurePosixPath(name)
                if parts.is_absolute() or ".." in parts.parts or ":" in name or "\x00" in name:
                    raise InputError("Đường dẫn trong ZIP không hợp lệ. Vui lòng tạo lại file ZIP.")
                if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                    raise InputError("ZIP không được chứa liên kết hoặc đặt mật khẩu.")
                if name.casefold() in seen:
                    raise InputError("ZIP có tên file trùng nhau. Vui lòng tạo lại file ZIP.")
                seen.add(name.casefold())
                total += entry.file_size
                if total > limit_bytes:
                    raise InputError("CT sau giải nén vượt dung lượng cho phép.")
                if entry.file_size > 50 * 1024**2 and entry.file_size / max(entry.compress_size, 1) > 1000:
                    raise InputError("ZIP có tỷ lệ nén bất thường. Vui lòng tạo lại file ZIP.")
            if not entries or total == 0:
                raise InputError("File ZIP rỗng. Vui lòng chọn ZIP chứa CT.")
            return entries
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise InputError("Không đọc được ZIP. Vui lòng kiểm tra hoặc nén lại file CT.") from exc


def extract_archive(path: Path, destination: Path, limit_bytes: int):
    inspect_archive(path, limit_bytes)
    destination.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                name = entry.filename.replace("\\", "/")
                if entry.is_dir() or name.startswith("__MACOSX/") or Path(name).name.startswith("."):
                    continue
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open("wb") as output:
                    while block := source.read(1024 * 1024):
                        total += len(block)
                        if total > limit_bytes:
                            raise InputError("CT sau giải nén vượt dung lượng cho phép.")
                        output.write(block)
    except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise InputError("ZIP bị lỗi khi giải nén. Vui lòng tạo lại file ZIP.") from exc
