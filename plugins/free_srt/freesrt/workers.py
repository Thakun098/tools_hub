"""Background worker implementations for downloads, transcription, and rendering.

Workers receive the top-level app module as ``services``.  This keeps runtime
paths and test overrides dynamic while separating process orchestration from the
portable Flask entry point.
"""

import hashlib
import os
import shutil
import tempfile
from .compute import is_gpu_error


def download_model_worker(services, filename):
    job = services.downloads[filename]
    destination = os.path.join(services.MODEL_FOLDER, filename)
    temporary = destination + ".tmp"
    response = None
    try:
        response = services.requests.get(services.MODELS_INFO[filename]["url"], stream=True, timeout=(10, 30))
        response.raise_for_status()
        with services.state_lock:
            job["_response"] = response
            job["total_bytes"] = int(response.headers.get("content-length", 0))
        downloaded = 0
        with open(temporary, "wb") as model_file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                services.check_cancelled(job)
                if chunk:
                    model_file.write(chunk)
                    downloaded += len(chunk)
                    with services.state_lock:
                        job["bytes_downloaded"] = downloaded
                        total = job["total_bytes"]
                        job["progress"] = int(downloaded * 100 / total) if total else 0
        with services.state_lock:
            services.check_cancelled(job)
            os.replace(temporary, destination)
            job.update(status="completed", progress=100)
    except services.JobCancelled:
        services.safe_remove(temporary)
        with services.state_lock:
            job.update(status="cancelled", progress=0, error=None)
    except Exception as error:
        services.safe_remove(temporary)
        with services.state_lock:
            if job["_cancel_event"].is_set():
                job.update(status="cancelled", progress=0, error=None)
            else:
                job.update(status="failed", error=str(error))
    finally:
        if response is not None:
            response.close()
        with services.state_lock:
            job["_response"] = None


def probe_gpu_backend(services, backend):
    runtime = services.installed_gpu_runtime(backend)
    if not runtime:
        return False, "ยังไม่ได้ติดตั้ง GPU runtime"
    executable = runtime["executable"]
    try:
        result = services.subprocess.run(
            [executable, "-h"], stdout=services.subprocess.PIPE,
            stderr=services.subprocess.PIPE, env=services.runtime_environment(executable),
            cwd=os.path.dirname(executable) or None, timeout=15, check=False,
        )
    except (OSError, services.subprocess.SubprocessError) as error:
        return False, str(error)
    output = b""
    for value in (result.stderr, result.stdout):
        if isinstance(value, bytes):
            output += value
        elif value:
            output += str(value).encode("utf-8", errors="ignore")
    detail = output.decode("utf-8", errors="ignore").strip()
    if result.returncode != 0:
        return False, detail[-500:] or f"process returned {result.returncode}"
    normalized = detail.lower()
    backend_markers = {
        "cuda": ("loaded cuda backend", "ggml_cuda", "cuda devices"),
        "vulkan": ("ggml_vulkan: found", "loaded vulkan backend", "vulkan devices"),
    }
    if any(marker in normalized for marker in backend_markers.get(backend, ())):
        return True, None
    backend_name = "NVIDIA CUDA" if backend == "cuda" else "Vulkan"
    return False, f"เปิด {backend_name} runtime ได้ แต่ไม่พบอุปกรณ์หรือ driver ที่พร้อมใช้งาน"


def download_gpu_worker(services, backend):
    job = services.gpu_downloads[backend]
    info = services.GPU_BACKENDS_INFO.get(backend)
    response = None
    archive_path = None
    staging = None
    try:
        if not info:
            raise ValueError("ไม่รองรับ GPU backend ที่เลือก")
        if not info.get("url"):
            raise RuntimeError("ยังไม่ได้ตั้งค่า URL ของ GPU runtime สำหรับรุ่นนี้")
        version_root = os.path.join(services.GPU_RUNTIME_FOLDER, backend, info["version"])
        os.makedirs(os.path.dirname(version_root), exist_ok=True)
        if services.installed_gpu_runtime(backend):
            with services.state_lock:
                job.update(status="completed", progress=100, error=None)
            return
        archive_path = os.path.join(os.path.dirname(version_root), f"{info['version']}.zip.tmp")
        response = services.requests.get(info["url"], stream=True, timeout=(10, 60))
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        with services.state_lock:
            job["_response"] = response
            job["total_bytes"] = total
        downloaded = 0
        with open(archive_path, "wb") as archive:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                services.check_cancelled(job)
                if chunk:
                    archive.write(chunk)
                    downloaded += len(chunk)
                    with services.state_lock:
                        job["bytes_downloaded"] = downloaded
                        job["progress"] = int(downloaded * 100 / total) if total else 0
        expected_hash = str(info.get("sha256") or "").lower()
        if expected_hash:
            digest = hashlib.sha256()
            with open(archive_path, "rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest().lower() != expected_hash:
                raise RuntimeError("ตรวจสอบ checksum ของ GPU runtime ไม่ผ่าน")
        staging = tempfile.mkdtemp(prefix=".gpu-runtime-", dir=os.path.dirname(version_root))
        services.extract_runtime_archive(archive_path, backend, staging)
        with services.state_lock:
            services.check_cancelled(job)
            if os.path.exists(version_root):
                shutil.rmtree(version_root)
            os.replace(staging, version_root)
            staging = None
            job.update(status="completed", progress=100, error=None)
    except services.JobCancelled:
        with services.state_lock:
            job.update(status="cancelled", progress=0, error=None)
    except Exception as error:
        with services.state_lock:
            if job["_cancel_event"].is_set():
                job.update(status="cancelled", progress=0, error=None)
            else:
                job.update(status="failed", error=str(error))
    finally:
        if response is not None:
            response.close()
        services.safe_remove(archive_path)
        if staging:
            shutil.rmtree(staging, ignore_errors=True)
        with services.state_lock:
            job["_response"] = None

def set_active_process(services, job, process):
    with services.state_lock:
        job["_process"] = process
    if job["_cancel_event"].is_set():
        services.terminate_process_tree(process)
        raise services.JobCancelled()


def run_ffmpeg_conversion(services, input_path, output_path, task_id):
    job = services.transcriptions[task_id]
    services.check_cancelled(job)
    duration = max(float(job.get("_duration_seconds") or 0), 0.001)
    with services.state_lock:
        services.begin_timed_stage(job, "converting")
        job["progress"] = 0
        job["logs"].append("กำลังแปลงเสียงเป็น WAV 16 kHz mono ด้วย FFmpeg...")
    command = [
        services.FFMPEG_EXE, "-y", "-hide_banner", "-loglevel", "error", "-i", input_path,
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        "-progress", "pipe:1", "-nostats", output_path,
    ]
    process = services.subprocess.Popen(
        command, stdout=services.subprocess.PIPE, stderr=services.subprocess.STDOUT, text=True,
        encoding="utf-8", errors="ignore", env=services.runtime_environment(services.FFMPEG_EXE),
        cwd=os.path.dirname(services.FFMPEG_EXE) or None, **services.process_options(),
    )
    services.set_active_process(job, process)
    try:
        progress_lines = iter(process.stdout or [])
    except TypeError:
        progress_lines = iter(())
    for raw_line in progress_lines:
        services.check_cancelled(job)
        line = raw_line.strip()
        if line.startswith("out_time_ms="):
            try:
                converted_seconds = int(line.split("=", 1)[1]) / 1_000_000
                fraction = min(1, converted_seconds / duration)
                with services.state_lock:
                    job["progress"] = min(14, max(0, int(fraction * 15)))
                    services.update_eta(job, fraction)
            except ValueError:
                pass
    return_code = process.wait()
    with services.state_lock:
        job["_process"] = None
    services.check_cancelled(job)
    if return_code != 0:
        raise RuntimeError("FFmpeg ไม่สามารถแปลงไฟล์นี้ได้ กรุณาตรวจว่าไฟล์มีแทร็กเสียง")
    with services.state_lock:
        job["progress"] = 15
        job["eta_seconds"] = None
        job["logs"].append("FFmpeg แปลงไฟล์เสร็จแล้ว")


def parse_whisper_progress(services, line, job):
    raw_percent = None
    if "progress =" in line:
        value = line.split("progress =", 1)[1].strip().split("%", 1)[0]
        if value.isdigit():
            raw_percent = int(value)
    if raw_percent is None:
        for word in line.split():
            value = word.rstrip("%")
            if word.endswith("%") and value.isdigit():
                raw_percent = int(value)
                break
    if raw_percent is not None:
        fraction = min(1, max(0, raw_percent) / 100)
        job["progress"] = min(95, 15 + int(fraction * 80))
        services.update_eta(job, fraction)


# STATUS_ILLEGAL_INSTRUCTION on Windows (0xC000001D = 3221225501) as unsigned 32-bit integer.
# Occurs when ggml-cpu-cascadelake/skylakex/icelake/cannonlake DLLs execute AVX-512
# instructions on CPUs or environments that do not support the instruction set.
# Python subprocess may return the unsigned value (3221225501) on Windows or the
# signed two's-complement value (-1073741795) on POSIX-emulated environments.
_STATUS_ILLEGAL_INSTRUCTION = 0xC000001D  # 3221225501 unsigned


def _relative_to(base, path):
    """Return path relative to base if possible, otherwise return path unchanged."""
    try:
        return os.path.relpath(path, base)
    except ValueError:
        # relpath raises ValueError on Windows when paths are on different drives.
        return path


def _run_whisper_process(services, job, wav_path, model_path, output_base, language, threads, task_id, backend):
    runtime = None
    if backend == "cpu":
        executable = services.WHISPER_EXE
    else:
        runtime = services.installed_gpu_runtime(backend)
        if not runtime:
            raise RuntimeError(f"GPU backend {backend} ยังไม่พร้อมใช้งาน")
        executable = runtime["executable"]

    # Run whisper from APP_DIR so that model/wav/output paths passed in argv
    # are short relative ASCII-only strings, avoiding ANSI code-page mangling
    # of Thai or other non-ASCII characters that appear in the installation
    # directory name on the user's machine.
    app_dir = services.APP_DIR
    rel_model = _relative_to(app_dir, model_path)
    rel_wav = _relative_to(app_dir, wav_path)
    rel_output_base = _relative_to(app_dir, output_base)

    command = [
        executable, "-m", rel_model, "-f", rel_wav, "-osrt", "-of", rel_output_base,
        "-l", language, "-t", str(threads), "-pp", "--max-len", "35", "--split-on-word",
    ]
    if backend == "cpu":
        command.append("--no-gpu")
    initial_prompt = services.build_initial_prompt()
    if initial_prompt:
        command.extend(["--prompt", initial_prompt])
    label = "CPU" if backend == "cpu" else ("NVIDIA CUDA" if backend == "cuda" else "Vulkan")
    with services.state_lock:
        services.begin_timed_stage(job, "transcribing")
        job["progress"] = 15
        job["compute_backend"] = backend
        job["logs"].append(f"กำลังถอดเสียงด้วย {label}...")
    try:
        process = services.subprocess.Popen(
            command, stdout=services.subprocess.PIPE, stderr=services.subprocess.STDOUT, text=True,
            encoding="utf-8", errors="ignore", env=services.runtime_environment(executable),
            cwd=app_dir, **services.process_options(),
        )
    except OSError as error:
        if backend != "cpu":
            raise RuntimeError(f"GPU backend {backend} เปิดใช้งานไม่ได้: {error}") from error
        raise RuntimeError(f"เปิด whisper.cpp ไม่ได้: {error}") from error
    services.set_active_process(job, process)
    output_lines = []
    try:
        for raw_line in process.stdout or []:
            services.check_cancelled(job)
            line = raw_line.strip()
            if line:
                output_lines.append(line)
                with services.state_lock:
                    services.append_public_log(job, line)
                    services.parse_whisper_progress(line, job)
        return_code = process.wait()
    finally:
        with services.state_lock:
            job["_process"] = None
    services.check_cancelled(job)
    if return_code != 0:
        # Detect STATUS_ILLEGAL_INSTRUCTION: ggml loaded an AVX-512 CPU backend DLL
        # (cascadelake / skylakex / icelake / cannonlake) on a CPU that does not
        # support those instructions.  Return code is the unsigned 32-bit value of
        # 0xC000001D on Windows, or -1073741795 as a signed integer.
        unsigned_code = return_code & 0xFFFFFFFF
        if unsigned_code == _STATUS_ILLEGAL_INSTRUCTION or return_code == _STATUS_ILLEGAL_INSTRUCTION:
            raise RuntimeError(
                "whisper.cpp หยุดทำงานเพราะ CPU ของเครื่องนี้ไม่รองรับชุดคำสั่ง AVX-512 "
                "ที่ใช้ใน ggml CPU backend \n"
                "วิธีแก้ไข: ลบไฟล์ ggml-cpu-cascadelake.dll, ggml-cpu-skylakex.dll, "
                "ggml-cpu-icelake.dll และ ggml-cpu-cannonlake.dll "
                "ออกจากโฟลเดอร์ bin/Release แล้วลองใหม่อีกครั้ง"
            )
        # Build a useful error summary.
        # whisper.cpp exits with code 2 for BOTH argument errors AND "input file not found".
        # When a file is missing it prints the error on lines 2-3 then dumps the full --help
        # (73+ lines).  Taking only the tail [-500:] hides the real error and shows only the
        # VAD help section.  Instead: extract explicit "error:" lines first, then fall back to
        # the first few lines of output so the real message is always visible.
        error_lines = [l for l in output_lines if l.lower().startswith("error:")]
        if error_lines:
            detail = "\n".join(error_lines)
        else:
            # No explicit error: lines – show head + tail of output.
            head = output_lines[:5]
            tail = output_lines[-5:] if len(output_lines) > 10 else []
            detail = "\n".join(head + (["..."] if tail else []) + tail)
        if backend != "cpu":
            raise RuntimeError(f"GPU backend {backend} ล้มเหลว: {detail or 'process returned ' + str(return_code)}")
        raise RuntimeError(f"whisper.cpp หยุดทำงานด้วยรหัส {return_code}: {detail or 'ไม่มีข้อมูลเพิ่มเติม'}")


def run_whisper_transcription(services, wav_path, model_path, output_base, language, threads, task_id):
    job = services.transcriptions[task_id]
    services.check_cancelled(job)
    backend = job.get("_compute_backend", "cpu")
    try:
        _run_whisper_process(
            services, job, wav_path, model_path, output_base, language, threads, task_id, backend,
        )
    except services.JobCancelled:
        raise
    except Exception as error:
        if backend == "cpu" or not is_gpu_error(error):
            raise
        services.safe_remove(output_base + ".srt")
        with services.state_lock:
            services.check_cancelled(job)
            job["_compute_backend"] = "cpu"
            job["compute_backend"] = "cpu"
            job["used_cpu_fallback"] = True
            job["fallback_reason"] = "GPU ใช้งานไม่ได้ จึงกลับไปใช้ CPU"
            services.append_public_log(job, error)
            job["logs"].append("กำลังลองใหม่ด้วย CPU...")
        _run_whisper_process(
            services, job, wav_path, model_path, output_base, language, threads, task_id, "cpu",
        )

def transcription_worker(services, task_id, input_path, model_filename, language, threads, owns_input=True):
    job = services.transcriptions[task_id]
    wav_path = os.path.join(services.UPLOAD_FOLDER, f"{task_id}.wav")
    output_base = os.path.join(services.OUTPUT_FOLDER, task_id)
    srt_path = output_base + ".srt"
    try:
        services.run_ffmpeg_conversion(input_path, wav_path, task_id)
        services.run_whisper_transcription(
            wav_path, os.path.join(services.MODEL_FOLDER, model_filename),
            output_base, language, threads, task_id,
        )
        if not os.path.exists(srt_path) and job.get("_compute_backend") != "cpu":
            with services.state_lock:
                services.check_cancelled(job)
                job["_compute_backend"] = "cpu"
                job["compute_backend"] = "cpu"
                job["used_cpu_fallback"] = True
                job["fallback_reason"] = "GPU ไม่สร้างไฟล์ SRT จึงกลับไปใช้ CPU"
                job["logs"].append("GPU ไม่ได้สร้างไฟล์ SRT กำลังลองใหม่ด้วย CPU...")
            services.run_whisper_transcription(
                wav_path, os.path.join(services.MODEL_FOLDER, model_filename),
                output_base, language, threads, task_id,
            )
        with services.state_lock:
            services.check_cancelled(job)
            if not os.path.exists(srt_path):
                raise RuntimeError("ถอดเสียงเสร็จแล้วแต่ไม่พบไฟล์ SRT")
            with open(srt_path, "r", encoding="utf-8-sig") as generated_srt:
                generated_content = generated_srt.read()
            try:
                generated_cues = services.parse_srt(generated_content)
            except ValueError as validation_error:
                if "must end after it starts" not in str(validation_error):
                    raise
                generated_cues = services.parse_srt(generated_content, repair_invalid_ranges=True)
                job["logs"].append("Repaired zero-duration timestamp from Whisper before segmentation")
            raw_original = services.serialize_srt(generated_cues)
            services.write_srt_atomic(
                os.path.join(services.OUTPUT_FOLDER, f"{task_id}.original.srt"),
                raw_original,
            )
            segmentation = services.segment_subtitles(generated_cues, language=language)
            if not segmentation.cues:
                raise RuntimeError("Subtitle segmentation produced no cues")
            job["segmentation_issues"] = segmentation.issues
            for issue in segmentation.issues:
                job["logs"].append(
                    f"{issue['code']}: cue {issue['cue_index'] + 1} — {issue['message']}"
                )
            services.write_srt_atomic(srt_path, services.serialize_srt(segmentation.cues))
            job.update(status="completed", progress=100, eta_seconds=0, srt_filename=f"{task_id}.srt")
    except services.JobCancelled:
        services.safe_remove(srt_path)
        with services.state_lock:
            job.update(status="cancelled", error=None, srt_filename=None)
            job["logs"].append("ยกเลิกงานและลบไฟล์ชั่วคราวแล้ว")
    except Exception as error:
        services.safe_remove(srt_path)
        with services.state_lock:
            if job["_cancel_event"].is_set():
                job.update(status="cancelled", error=None, srt_filename=None)
                job["logs"].append("ยกเลิกงานและลบไฟล์ชั่วคราวแล้ว")
            else:
                safe_error = services.redact_diagnostic(error, job)
                job.update(status="failed", error=safe_error, srt_filename=None)
                services.append_public_log(job, f"ERROR: {error}")
    finally:
        services.terminate_process_tree(job.get("_process"))
        with services.state_lock:
            job["_process"] = None
        if owns_input:
            services.safe_remove(input_path)
        services.safe_remove(wav_path)


def video_render_worker(services, render_id, task_id, input_path, owns_input, font_key, font_size, outline_width=2, background=True, shadow_depth=0, position="bottom", margin_v=48):
    job = services.video_renders[render_id]
    output_path = os.path.join(services.OUTPUT_FOLDER, f"{render_id}.mp4")
    temporary_path = os.path.join(services.OUTPUT_FOLDER, f"{render_id}.tmp.mp4")
    subtitle_path = job.get("_subtitle_path")
    try:
        services.check_cancelled(job)
        capacity_estimate = job.get("_capacity_estimate")
        if capacity_estimate is None:
            raise services.RenderCapacityError(
                "render_capacity_unknown", "Render capacity was not admitted before execution.",
            )
        services.ensure_render_capacity(services.OUTPUT_FOLDER, capacity_estimate)
        subtitle_filename = os.path.basename(subtitle_path or services.transcriptions[task_id]["srt_filename"])
        subtitle_filter = services.build_subtitle_filter(
            subtitle_filename, font_key, font_size, outline_width,
            background, shadow_depth, position, margin_v,
        )
        duration = max(float(capacity_estimate.duration_seconds), 0.001)
        with services.state_lock:
            services.check_cancelled(job)
            services.begin_timed_stage(job, "rendering")
            job["logs"].append("กำลังสร้างวิดีโอ MP4 และฝังคำบรรยายด้วย FFmpeg...")
        command = [
            services.FFMPEG_EXE, "-y", "-hide_banner", "-loglevel", "error", "-i", input_path,
            "-vf", subtitle_filter, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            "-progress", "pipe:1", "-nostats", temporary_path,
        ]
        process = services.subprocess.Popen(
            command, stdout=services.subprocess.PIPE, stderr=services.subprocess.STDOUT, text=True,
            encoding="utf-8", errors="ignore", env=services.runtime_environment(services.FFMPEG_EXE),
            cwd=services.OUTPUT_FOLDER, **services.process_options(),
        )
        services.set_active_process(job, process)
        for raw_line in process.stdout or []:
            services.check_cancelled(job)
            services.ensure_render_emergency_capacity(
                services.OUTPUT_FOLDER, capacity_estimate.emergency_floor_bytes,
            )
            line = raw_line.strip()
            if line.startswith("out_time_ms="):
                try:
                    elapsed_seconds = int(line.split("=", 1)[1]) / 1_000_000
                    with services.state_lock:
                        fraction = min(1, max(0, elapsed_seconds / duration))
                        job["progress"] = min(99, max(0, int(fraction * 100)))
                        services.update_eta(job, fraction)
                except ValueError:
                    pass
            elif line and not line.startswith(("frame=", "fps=", "stream_", "bitrate=", "total_size=", "out_time_", "dup_frames=", "drop_frames=", "speed=", "progress=")):
                with services.state_lock:
                    services.append_public_log(job, line)
        return_code = process.wait()
        with services.state_lock:
            job["_process"] = None
            services.check_cancelled(job)
            if return_code != 0 or not os.path.exists(temporary_path):
                raise RuntimeError("FFmpeg ไม่สามารถสร้างวิดีโอพร้อมซับได้")
            os.replace(temporary_path, output_path)
            job.update(status="completed", progress=100, eta_seconds=0, video_filename=f"{render_id}.mp4")
            job["logs"].append("สร้างวิดีโอพร้อมซับเสร็จแล้ว")
    except services.JobCancelled:
        services.safe_remove(temporary_path)
        with services.state_lock:
            job.update(status="cancelled", error=None, video_filename=None)
            job["logs"].append("ยกเลิกการสร้างวิดีโอและลบไฟล์ชั่วคราวแล้ว")
    except Exception as error:
        services.safe_remove(temporary_path)
        with services.state_lock:
            if job["_cancel_event"].is_set():
                job.update(status="cancelled", error=None, video_filename=None)
                job["logs"].append("ยกเลิกการสร้างวิดีโอและลบไฟล์ชั่วคราวแล้ว")
            else:
                safe_error = services.redact_diagnostic(error, job)
                job.update(status="failed", error=safe_error, video_filename=None)
                services.append_public_log(job, f"ERROR: {error}")
    finally:
        services.terminate_process_tree(job.get("_process"))
        with services.state_lock:
            job["_process"] = None
        if owns_input:
            services.safe_remove(input_path)
        if subtitle_path:
            services.safe_remove(subtitle_path)
        services.safe_remove(temporary_path)
