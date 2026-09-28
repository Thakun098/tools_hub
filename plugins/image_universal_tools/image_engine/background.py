"""CPU-only rembg backend with an offline model integrity gate."""

import hashlib
import os

from .image_policy import load_image
from .output_paths import AtomicOutput


_SESSION_CACHE = {}


def _verify_local_model(model_root, model):
    if not isinstance(model, dict):
        raise ValueError("ไม่มีข้อมูลตรวจสอบโมเดล")
    file_name = str(model.get("file_name", ""))
    if not file_name or os.path.basename(file_name) != file_name:
        raise ValueError("ชื่อไฟล์โมเดลไม่ถูกต้อง")
    root = os.path.abspath(model_root)
    path = os.path.abspath(os.path.join(root, file_name))
    if os.path.commonpath([path, root]) != root:
        raise ValueError("ตำแหน่งโมเดลไม่ปลอดภัย")
    try:
        expected_size = int(model["size_bytes"])
        algorithm, expected = str(model["checksum"]).split(":", 1)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("ข้อมูลตรวจสอบโมเดลไม่ถูกต้อง") from error
    if algorithm not in {"md5", "sha256"} or not os.path.isfile(path) or os.path.getsize(path) != expected_size:
        raise ValueError("ไฟล์โมเดลไม่ถูกต้อง กรุณาดาวน์โหลดใหม่")
    digest = hashlib.new(algorithm)
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected.lower():
        raise ValueError("checksum ของโมเดลไม่ถูกต้อง กรุณาดาวน์โหลดใหม่")
    return path


def _build_offline_session(model_name, verified_path):
    import pooch
    from rembg import new_session

    verified_path = os.path.normcase(os.path.abspath(verified_path))
    stat = os.stat(verified_path)
    cache_key = (model_name, verified_path, stat.st_size, stat.st_mtime_ns)
    cached = _SESSION_CACHE.get(cache_key)
    if cached is not None:
        return cached
    original_retrieve = pooch.retrieve

    def local_only_retrieve(_url, _known_hash, *, fname=None, path=None, **_kwargs):
        candidate = os.path.normcase(os.path.abspath(os.path.join(os.fspath(path), os.fspath(fname))))
        if candidate != verified_path:
            raise RuntimeError("image engine ปิดกั้นการดาวน์โหลดโมเดลที่ไม่ได้รับอนุญาต")
        return verified_path

    pooch.retrieve = local_only_retrieve
    try:
        session = new_session(model_name, providers=["CPUExecutionProvider"])
    finally:
        pooch.retrieve = original_retrieve
    _SESSION_CACHE.clear()
    _SESSION_CACHE[cache_key] = session
    return session


def remove_background(input_path, output_path, settings, model_root, model, max_pixels):
    model_name = str(settings.get("model_name", "isnet-general-use"))
    allowed = {"u2netp", "isnet-general-use", "birefnet-general-lite"}
    if model_name not in allowed:
        raise ValueError("ไม่รองรับโมเดลที่เลือก")
    verified_path = _verify_local_model(model_root, model)
    os.environ["U2NET_HOME"] = os.path.abspath(model_root)
    os.environ.pop("MODEL_CHECKSUM_DISABLED", None)
    from rembg import remove

    loaded = load_image(input_path, max_pixels=max_pixels)
    session = _build_offline_session(model_name, verified_path)
    result = remove(loaded.image, session=session).convert("RGBA")
    with AtomicOutput(output_path) as temporary_path:
        result.save(temporary_path, format="PNG", optimize=True, compress_level=6)
    return {
        "format": "PNG",
        "width": result.width,
        "height": result.height,
        "model": model_name,
        "metadata_removed": True,
        "provider": "CPUExecutionProvider",
    }
