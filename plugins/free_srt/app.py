import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import requests
from flask import Flask

from toolshub_free_srt import workers as worker_services
from toolshub_free_srt.capacity import (
    RenderCapacityError,
    ensure_render_capacity,
    ensure_render_emergency_capacity,
    estimate_render_capacity,
)
from toolshub_free_srt.compute import GPU_BACKENDS_INFO
from toolshub_free_srt.compute import detect_gpu_vendors, installed_runtime, normalize_compute_mode, normalize_gpu_backend, recommended_backend
from toolshub_free_srt.diagnostics import append_public_log, redact_diagnostic, register_private_value
from toolshub_free_srt.files import atomic_write_json, public_state, read_json_object, safe_media_extension, safe_remove
from toolshub_free_srt.jobs import (
    ReservationError,
    claim_reservation,
    expire_reservations,
    finish_prestart,
    read_request_form_files,
    request_cancel,
    reserve_job,
    save_upload_cancellable,
    set_prestart_status,
)
from toolshub_free_srt.glossary import build_initial_prompt as build_prompt_from_entries
from toolshub_free_srt.glossary import validate_glossary
from toolshub_free_srt.model_catalog import MODELS_INFO
from toolshub_free_srt.runtime_policy import extract_runtime_archive, select_runtime_members, validate_staged_runtime
from toolshub_free_srt.settings import normalize_editor_backup as normalize_backup_payload
from toolshub_free_srt.settings import normalize_preferences as normalize_preferences_payload
from toolshub_free_srt.segmentation import SegmentationConfig, segment_cues as segment_subtitle_cues
from toolshub_free_srt.subtitle_style import (
    DEFAULT_SUBTITLE_FONT,
    SUBTITLE_FONTS,
    build_subtitle_filter,
    format_ass_number,
    normalize_subtitle_style,
)
from toolshub_free_srt.subtitles import (
    SRT_TIMESTAMP_RE,
    ms_to_timestamp,
    parse_srt,
    serialize_srt,
    serialize_txt,
    timestamp_to_ms,
    write_srt_atomic,
)

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
_BOOT_CONFIG = dict(globals().get("_FREESRT_BOOT_CONFIG", {}))
_DEFAULT_APP_DIR = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else SOURCE_DIR
APP_DIR = os.path.abspath(_BOOT_CONFIG.get("APP_DIR", _DEFAULT_APP_DIR))
RESOURCE_DIR = os.path.abspath(_BOOT_CONFIG.get("RESOURCE_DIR", getattr(sys, "_MEIPASS", SOURCE_DIR)))
URL_PREFIX = str(_BOOT_CONFIG.get("URL_PREFIX", "")).rstrip("/")
UPLOAD_FOLDER = os.path.abspath(_BOOT_CONFIG.get("UPLOAD_FOLDER", os.path.join(APP_DIR, "uploads")))
MODEL_FOLDER = os.path.abspath(_BOOT_CONFIG.get("MODEL_FOLDER", os.path.join(APP_DIR, "models")))
OUTPUT_FOLDER = os.path.abspath(_BOOT_CONFIG.get("OUTPUT_FOLDER", os.path.join(APP_DIR, "outputs")))
DATA_FOLDER = os.path.abspath(_BOOT_CONFIG.get("DATA_FOLDER", os.path.join(APP_DIR, "data")))
GLOSSARY_PATH = os.path.join(DATA_FOLDER, "glossary.json")
PREFERENCES_PATH = os.path.join(DATA_FOLDER, "preferences.json")
EDITOR_BACKUP_PATH = os.path.join(DATA_FOLDER, "editor-backup.json")
WHISPER_EXE = os.environ.get("WHISPER_EXE", os.path.join(RESOURCE_DIR, "bin", "Release", "whisper-cli.exe"))
CPU_WHISPER_EXE = WHISPER_EXE
GPU_RUNTIME_FOLDER = os.path.abspath(_BOOT_CONFIG.get("GPU_RUNTIME_FOLDER", os.path.join(APP_DIR, "gpu-runtimes")))
SEGMENTATION_CONFIG = SegmentationConfig()
_bundled_ffmpeg = os.path.join(RESOURCE_DIR, "bin", "ffmpeg.exe")
_bundled_ffprobe = os.path.join(RESOURCE_DIR, "bin", "ffprobe.exe")
_system_ffmpeg = shutil.which("ffmpeg")
FFMPEG_EXE = os.environ.get("FFMPEG_EXE", _bundled_ffmpeg if os.path.exists(_bundled_ffmpeg) else (_system_ffmpeg or "ffmpeg"))
FFPROBE_EXE = os.environ.get("FFPROBE_EXE", _bundled_ffprobe if os.path.exists(_bundled_ffprobe) else (shutil.which("ffprobe") or "ffprobe"))
for folder in (UPLOAD_FOLDER, MODEL_FOLDER, OUTPUT_FOLDER, DATA_FOLDER, GPU_RUNTIME_FOLDER):
    os.makedirs(folder, exist_ok=True)
_DLL_DIRECTORY_HANDLES = []

def runtime_environment(executable):
    environment = os.environ.copy()
    directories = []
    for candidate in (os.path.dirname(executable), os.path.dirname(FFMPEG_EXE), os.path.dirname(WHISPER_EXE)):
        if candidate and os.path.isdir(candidate) and candidate not in directories:
            directories.append(candidate)
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        for directory in directories:
            try:
                _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(directory))
            except OSError:
                pass
    if directories:
        environment["PATH"] = os.pathsep.join(directories + [environment.get("PATH", "")])
    return environment


def run_cancellable_probe(command, executable, cwd, timeout, job=None, text=False):
    """Run a short probe and expose its process to the job cancellation token."""

    if job is None:
        return subprocess.run(
            command, stdout=subprocess.PIPE if text else subprocess.DEVNULL,
            stderr=subprocess.PIPE, text=text, encoding="utf-8" if text else None,
            errors="ignore" if text else None, env=runtime_environment(executable),
            cwd=cwd, timeout=timeout, check=False,
        )
    check_cancelled(job)
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE if text else subprocess.DEVNULL,
        stderr=subprocess.PIPE, text=text, encoding="utf-8" if text else None,
        errors="ignore" if text else None, env=runtime_environment(executable),
        cwd=cwd, **process_options(),
    )
    with state_lock:
        job["_process"] = process
    deadline = time.monotonic() + timeout
    try:
        while True:
            check_cancelled(job)
            try:
                stdout, stderr = process.communicate(timeout=0.1)
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    terminate_process_tree(process)
                    raise
    except JobCancelled:
        terminate_process_tree(process)
        raise
    finally:
        with state_lock:
            if job.get("_process") is process:
                job["_process"] = None


def runtime_preflight(whisper_exe=None, job=None):
    whisper_exe = whisper_exe or WHISPER_EXE
    # whisper-cli.exe is probed with cwd=APP_DIR so the -h check mirrors the
    # exact environment used during transcription (relative paths, APP_DIR cwd).
    checks = (
        (FFMPEG_EXE, "FFmpeg", ["-version"], os.path.dirname(FFMPEG_EXE) or None),
        (FFPROBE_EXE, "ffprobe", ["-version"], os.path.dirname(FFPROBE_EXE) or None),
        (whisper_exe, "whisper.cpp", ["-h"], APP_DIR),
    )
    for executable, label, arguments, cwd in checks:
        if not os.path.isfile(executable):
            raise RuntimeError(f"ไม่พบ {label} ใน portable package: {executable}")
        try:
            result = run_cancellable_probe(
                [executable, *arguments], executable, cwd, 15, job=job, text=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError(f"เปิด {label} ไม่ได้ ({executable}): {error}") from error
        if result.returncode != 0:
            detail = (result.stderr or b"").decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"เปิด {label} ไม่ได้ ({executable}): {detail or 'process returned an error'}")

downloads = {}
gpu_downloads = {}
transcriptions = {}
video_renders = {}
local_selections = {}
state_lock = threading.RLock()
LOCAL_SELECTION_TTL_SECONDS = 15 * 60
WAV_BYTES_PER_SECOND = 16_000 * 2
PREFLIGHT_MARGIN_BYTES = 512 * 1024 * 1024
MEDIA_FILETYPES = [("ไฟล์สื่อ", "*.mp4 *.mov *.mkv *.avi *.webm *.mp3 *.wav *.m4a *.aac *.flac *.ogg"), ("ทุกไฟล์", "*.*")]
class JobCancelled(Exception):
    pass

def read_glossary():
    return read_json_object(GLOSSARY_PATH, {"entries": []}).get("entries", [])

def save_glossary(entries):
    atomic_write_json(GLOSSARY_PATH, {"entries": entries})

def build_initial_prompt():
    return build_prompt_from_entries(read_glossary())

def update_eta(job, fraction):
    fraction = max(0.0, min(1.0, float(fraction)))
    started = job.get("_stage_started_at")
    elapsed = time.monotonic() - started if started else 0
    if elapsed < 2 or fraction < 0.02 or fraction >= 1:
        job["eta_seconds"] = None
        return
    estimate = max(0, elapsed * (1 - fraction) / fraction)
    previous = job.get("_eta_smoothed")
    smoothed = estimate if previous is None else previous * 0.72 + estimate * 0.28
    job["_eta_smoothed"] = smoothed
    job["eta_seconds"] = int(round(smoothed))

def begin_timed_stage(job, status):
    job["status"] = status
    job["eta_seconds"] = None
    job["_eta_smoothed"] = None
    job["_stage_started_at"] = time.monotonic()

def cleanup_expired_selections():
    now = time.monotonic()
    for selection_id, selection in list(local_selections.items()):
        if selection["expires_at"] <= now:
            local_selections.pop(selection_id, None)

def ensure_upload_capacity(content_length):
    if content_length is None:
        raise ValueError("ไม่สามารถตรวจสอบขนาดไฟล์อัปโหลดได้ กรุณาลองเลือกไฟล์ใหม่")
    try:
        content_length = int(content_length)
    except (TypeError, ValueError) as error:
        raise ValueError("ขนาดไฟล์อัปโหลดไม่ถูกต้อง") from error
    if content_length < 0:
        raise ValueError("ขนาดไฟล์อัปโหลดไม่ถูกต้อง")

    upload_root = os.path.abspath(UPLOAD_FOLDER)
    temporary_root = os.path.abspath(tempfile.gettempdir())
    upload_free = shutil.disk_usage(upload_root).free
    temporary_free = shutil.disk_usage(temporary_root).free
    same_volume = os.path.splitdrive(upload_root)[0].casefold() == os.path.splitdrive(temporary_root)[0].casefold()
    if same_volume:
        enough_space = upload_free >= content_length * 2 + PREFLIGHT_MARGIN_BYTES
    else:
        enough_space = (
            upload_free >= content_length + PREFLIGHT_MARGIN_BYTES
            and temporary_free >= content_length + PREFLIGHT_MARGIN_BYTES
        )
    if not enough_space:
        raise ValueError("พื้นที่ว่างไม่พอสำหรับรับไฟล์นี้ กรุณาเพิ่มพื้นที่ว่างหรือใช้การเลือกไฟล์โดยตรง")

def has_active_transcription(exclude_id=None):
    active = {"reserved", "uploading", "preflighting", "starting", "queued", "converting", "transcribing", "cancelling"}
    return any(identifier != exclude_id and job["status"] in active for identifier, job in transcriptions.items())

def has_active_render(exclude_id=None):
    active = {"reserved", "uploading", "preflighting", "queued", "rendering", "cancelling"}
    return any(identifier != exclude_id and job["status"] in active for identifier, job in video_renders.items())

def build_windows_open_file_dialog(ctypes, wintypes):
    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [("lStructSize", wintypes.DWORD), ("hwndOwner", wintypes.HWND), ("hInstance", wintypes.HINSTANCE), ("lpstrFilter", wintypes.LPCWSTR), ("lpstrCustomFilter", wintypes.LPWSTR), ("nMaxCustFilter", wintypes.DWORD), ("nFilterIndex", wintypes.DWORD), ("lpstrFile", wintypes.LPWSTR), ("nMaxFile", wintypes.DWORD), ("lpstrFileTitle", wintypes.LPWSTR), ("nMaxFileTitle", wintypes.DWORD), ("lpstrInitialDir", wintypes.LPCWSTR), ("lpstrTitle", wintypes.LPCWSTR), ("Flags", wintypes.DWORD), ("nFileOffset", wintypes.WORD), ("nFileExtension", wintypes.WORD), ("lpstrDefExt", wintypes.LPCWSTR), ("lCustData", wintypes.LPARAM), ("lpfnHook", wintypes.LPVOID), ("lpTemplateName", wintypes.LPCWSTR), ("pvReserved", wintypes.LPVOID), ("dwReserved", wintypes.DWORD), ("FlagsEx", wintypes.DWORD)]
    file_buffer = ctypes.create_unicode_buffer(32768)
    filters = "ไฟล์สื่อ\0*.mp4;*.mov;*.mkv;*.avi;*.webm;*.mp3;*.wav;*.m4a;*.aac;*.flac;*.ogg\0ทุกไฟล์\0*.*\0\0"
    dialog = OPENFILENAMEW(
        lStructSize=ctypes.sizeof(OPENFILENAMEW),
        lpstrFilter=filters,
        lpstrFile=ctypes.cast(file_buffer, wintypes.LPWSTR),
        nMaxFile=len(file_buffer),
        lpstrTitle="เลือกไฟล์เสียงหรือวิดีโอ",
        Flags=0x00080000 | 0x00001000,
    )
    return dialog, file_buffer, OPENFILENAMEW

def select_local_media_file():
    if os.name != "nt":
        raise RuntimeError("การเลือกไฟล์โดยตรงรองรับเฉพาะ Windows portable mode")
    try:
        import ctypes
        from ctypes import wintypes
        dialog, file_buffer, dialog_type = build_windows_open_file_dialog(ctypes, wintypes)
        get_open_file_name = ctypes.windll.comdlg32.GetOpenFileNameW
        get_open_file_name.argtypes = [ctypes.POINTER(dialog_type)]
        get_open_file_name.restype = wintypes.BOOL
        if get_open_file_name(ctypes.byref(dialog)):
            return file_buffer.value
        extended_error = ctypes.windll.comdlg32.CommDlgExtendedError()
        if extended_error:
            raise OSError(f"Common Dialog error 0x{extended_error:04X}")
        return ""
    except Exception as error:
        raise RuntimeError(f"ไม่สามารถเปิดหน้าต่างเลือกไฟล์ของ Windows ได้: {error}") from error

def probe_media(path, job=None):
    if not os.path.isfile(path) or not os.access(path, os.R_OK):
        raise ValueError("ไม่พบไฟล์ต้นฉบับ หรือไม่สามารถอ่านไฟล์ได้แล้ว กรุณาเลือกใหม่")
    command = [FFPROBE_EXE, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", path]
    try:
        result = run_cancellable_probe(command, FFPROBE_EXE, os.path.dirname(FFPROBE_EXE) or None, 30, job=job, text=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"ตรวจไฟล์ด้วย ffprobe ไม่สำเร็จ: {error}") from error
    if result.returncode != 0:
        raise ValueError("ไม่สามารถอ่านข้อมูลไฟล์สื่อนี้ได้ กรุณาตรวจสอบไฟล์อีกครั้ง")
    try:
        metadata = json.loads(result.stdout or "{}")
        duration = float(metadata.get("format", {}).get("duration", 0))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("ไม่พบระยะเวลาที่ใช้ได้ในไฟล์สื่อนี้") from error
    streams = metadata.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    if duration <= 0 or not any(stream.get("codec_type") == "audio" for stream in streams):
        raise ValueError("ไฟล์นี้ไม่มีแทร็กเสียงที่ถอดได้")
    wav_bytes = int(duration * WAV_BYTES_PER_SECOND)
    required_bytes = wav_bytes + PREFLIGHT_MARGIN_BYTES
    upload_free = shutil.disk_usage(UPLOAD_FOLDER).free
    output_free = shutil.disk_usage(OUTPUT_FOLDER).free
    if upload_free < required_bytes or output_free < PREFLIGHT_MARGIN_BYTES:
        raise ValueError("พื้นที่ว่างไม่พอสำหรับสร้างไฟล์เสียงชั่วคราว กรุณาเพิ่มพื้นที่ว่างแล้วลองใหม่")
    return {"duration_seconds": round(duration, 1), "has_video": bool(video_stream), "width": int(video_stream.get("width") or 0), "height": int(video_stream.get("height") or 0), "estimated_wav_bytes": wav_bytes, "recommended_free_bytes": required_bytes, "upload_free_bytes": upload_free, "output_free_bytes": output_free}
def process_options():
    return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}

def terminate_process_tree(process):
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=3)
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
            process.wait(timeout=2)
        except (OSError, subprocess.SubprocessError):
            pass

def check_cancelled(job):
    if job["_cancel_event"].is_set():
        raise JobCancelled()

def download_model_worker(filename):
    return worker_services.download_model_worker(sys.modules[__name__], filename)

def download_gpu_worker(backend):
    return worker_services.download_gpu_worker(sys.modules[__name__], backend)

def installed_gpu_runtime(backend):
    return installed_runtime(os.path.dirname(GPU_RUNTIME_FOLDER), backend)

def probe_gpu_backend(backend):
    return worker_services.probe_gpu_backend(sys.modules[__name__], backend)

def compute_backend_status():
    vendors = detect_gpu_vendors()
    result = []
    for backend, info in GPU_BACKENDS_INFO.items():
        runtime = installed_gpu_runtime(backend)
        available, error = probe_gpu_backend(backend) if runtime else (False, None)
        download = gpu_downloads.get(backend) or {}
        result.append({
            "id": backend, "name": info["name"], "description": info["description"],
            "badge": info["badge"], "version": info["version"], "vendors": info["vendors"],
            "installed": bool(runtime), "available": bool(available), "error": error,
            "download_available": bool(info.get("url")),
            "download_size": info.get("size", ""),
            "download_source": info.get("source", ""),
            "download_status": download.get("status", "not_downloaded"),
            "download_progress": download.get("progress", 0),
            "download_error": download.get("error"),
        })
    return {"hardware": {"gpu_detected": bool(vendors), "vendors": vendors}, "recommended_backend": recommended_backend(vendors), "backends": result}

def resolve_compute_backend(mode="cpu", backend="auto"):
    mode = normalize_compute_mode(mode)
    backend = normalize_gpu_backend(backend)
    if mode == "cpu":
        return "cpu"
    candidates = [backend] if backend != "auto" else ["cuda", "vulkan"]
    for candidate in candidates:
        if installed_gpu_runtime(candidate) and probe_gpu_backend(candidate)[0]:
            return candidate
    return "cpu"
def set_active_process(job, process):
    return worker_services.set_active_process(sys.modules[__name__], job, process)

def run_ffmpeg_conversion(input_path, output_path, task_id):
    return worker_services.run_ffmpeg_conversion(sys.modules[__name__], input_path, output_path, task_id)

def parse_whisper_progress(line, job):
    return worker_services.parse_whisper_progress(sys.modules[__name__], line, job)

def segment_subtitles(cues, language=None):
    return segment_subtitle_cues(cues, SEGMENTATION_CONFIG, language=language)

def run_whisper_transcription(wav_path, model_path, output_base, language, threads, task_id):
    return worker_services.run_whisper_transcription(
        sys.modules[__name__], wav_path, model_path, output_base, language, threads, task_id
    )

def transcription_worker(task_id, input_path, model_filename, language, threads, owns_input=True):
    return worker_services.transcription_worker(
        sys.modules[__name__], task_id, input_path, model_filename, language, threads, owns_input
    )


def normalize_preferences(payload, existing=None):
    return normalize_preferences_payload(payload, MODELS_INFO, existing)

def normalize_editor_backup(payload):
    return normalize_backup_payload(payload, MODELS_INFO)
def video_render_worker(render_id, task_id, input_path, owns_input, font_key, font_size, outline_width=2, background=True, shadow_depth=0, position="bottom", margin_v=48):
    return worker_services.video_render_worker(
        sys.modules[__name__], render_id, task_id, input_path, owns_input, font_key, font_size,
        outline_width, background, shadow_depth, position, margin_v,
    )


from toolshub_free_srt.routes.transcription import register_transcription_routes
from toolshub_free_srt.routes.video import register_video_routes
from toolshub_free_srt.routes.editor import register_editor_routes


def register_routes(target, services, base_url=""):
    services.URL_PREFIX = str(base_url or "").rstrip("/")
    register_transcription_routes(target, services)
    register_video_routes(target, services)
    register_editor_routes(target, services)


def _build_current_app():
    flask_app = Flask(
        __name__,
        template_folder=os.path.join(RESOURCE_DIR, "templates"),
        static_folder=os.path.join(RESOURCE_DIR, "static"),
        static_url_path=(URL_PREFIX + "/static") if URL_PREFIX else "/static",
    )
    register_routes(flask_app, sys.modules[__name__], URL_PREFIX)
    flask_app.extensions["free_srt_runtime"] = sys.modules[__name__]
    return flask_app


def load_runtime(config=None):
    """Load an isolated copy of this module with instance-specific globals."""
    module_name = f"_free_srt_runtime_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, __file__)
    module = importlib.util.module_from_spec(spec)
    module._FREESRT_BOOT_CONFIG = dict(config or {})
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def create_app(config=None):
    """Create an isolated FreeSRT app while preserving the module-level app contract."""
    return load_runtime(config).app


app = _build_current_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)




























