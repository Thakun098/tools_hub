import io
import os
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import Mock, patch

from werkzeug.exceptions import BadRequest, ClientDisconnected

import app
from freesrt.runtime_policy import RuntimePolicyError, is_allowed_cpu_release_binary


class FakeResponse:
    headers = {"content-length": "6"}

    def __init__(self, cancel_event=None):
        self.cancel_event = cancel_event
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield b"abc"
        if self.cancel_event:
            self.cancel_event.set()
        yield b"def"

    def close(self):
        self.closed = True


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.uploads = os.path.join(self.temp.name, "uploads")
        self.models = os.path.join(self.temp.name, "models")
        self.outputs = os.path.join(self.temp.name, "outputs")
        self.data = os.path.join(self.temp.name, "data")
        self.gpu_runtimes = os.path.join(self.temp.name, "gpu-runtimes")
        for folder in (self.uploads, self.models, self.outputs, self.data, self.gpu_runtimes):
            os.makedirs(folder)
        self.original_paths = app.UPLOAD_FOLDER, app.MODEL_FOLDER, app.OUTPUT_FOLDER, app.DATA_FOLDER, app.GLOSSARY_PATH, app.PREFERENCES_PATH, app.EDITOR_BACKUP_PATH, app.GPU_RUNTIME_FOLDER
        app.UPLOAD_FOLDER, app.MODEL_FOLDER, app.OUTPUT_FOLDER = self.uploads, self.models, self.outputs
        app.DATA_FOLDER, app.GLOSSARY_PATH = self.data, os.path.join(self.data, "glossary.json")
        app.PREFERENCES_PATH = os.path.join(self.data, "preferences.json")
        app.EDITOR_BACKUP_PATH = os.path.join(self.data, "editor-backup.json")
        app.GPU_RUNTIME_FOLDER = self.gpu_runtimes
        app.downloads.clear()
        app.gpu_downloads.clear()
        app.transcriptions.clear()
        app.video_renders.clear()
        app.local_selections.clear()
        app.app.config.update(TESTING=True)
        self.client = app.app.test_client()

    def reserve_transcription(self):
        response = self.client.post("/api/transcribe/reservations")
        self.assertEqual(response.status_code, 201)
        return response.get_json()["task_id"]

    def reserve_render(self, task_id="video-task"):
        response = self.client.post(f"/api/video-render/{task_id}/reservations")
        self.assertEqual(response.status_code, 201)
        return response.get_json()["render_id"]
    def tearDown(self):
        app.UPLOAD_FOLDER, app.MODEL_FOLDER, app.OUTPUT_FOLDER, app.DATA_FOLDER, app.GLOSSARY_PATH, app.PREFERENCES_PATH, app.EDITOR_BACKUP_PATH, app.GPU_RUNTIME_FOLDER = self.original_paths
        app.downloads.clear()
        app.gpu_downloads.clear()
        app.transcriptions.clear()
        app.video_renders.clear()
        app.local_selections.clear()
        self.temp.cleanup()

    def test_models_include_plain_language_metadata(self):
        response = self.client.get("/api/models")
        self.assertEqual(response.status_code, 200)
        model = response.get_json()[0]
        for key in ("description", "speed", "accuracy", "recommended_for", "memory_hint", "badge"):
            self.assertTrue(model[key])

    def test_compute_backend_status_separates_hardware_from_runtime(self):
        with patch("app.detect_gpu_vendors", return_value=["nvidia"]):
            response = self.client.get("/api/compute/backends")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        cuda = next(item for item in data["backends"] if item["id"] == "cuda")
        self.assertTrue(data["hardware"]["gpu_detected"])
        self.assertEqual(data["recommended_backend"], "cuda")
        self.assertFalse(cuda["installed"])
        self.assertTrue(cuda["download_available"])
        self.assertIn("266 MB", cuda["download_size"])
        self.assertIn("whisper.cpp", cuda["download_source"])
    def test_public_status_never_serializes_internal_objects(self):
        app.downloads["ggml-base.bin"] = {
            "status": "downloading", "progress": 12, "error": None,
            "_cancel_event": threading.Event(), "_response": object(),
        }
        data = self.client.get("/api/models/download-status").get_json()["ggml-base.bin"]
        self.assertEqual(data["progress"], 12)
        self.assertNotIn("_cancel_event", data)
        self.assertNotIn("_response", data)

    def test_cancel_model_download_is_idempotent(self):
        event = threading.Event()
        response = Mock()
        app.downloads["ggml-base.bin"] = {
            "status": "downloading", "progress": 30, "error": None,
            "_cancel_event": event, "_response": response,
        }
        first = self.client.post("/api/models/ggml-base.bin/cancel")
        second = self.client.post("/api/models/ggml-base.bin/cancel")
        self.assertEqual(first.get_json()["status"], "cancelling")
        self.assertEqual(second.get_json()["status"], "cancelling")
        self.assertTrue(event.is_set())
        self.assertGreaterEqual(response.close.call_count, 1)

    def test_cancelled_download_removes_partial_file(self):
        event = threading.Event()
        app.downloads["ggml-base.bin"] = {
            "status": "downloading", "progress": 0, "bytes_downloaded": 0,
            "total_bytes": 0, "error": None, "_cancel_event": event, "_response": None,
        }
        fake = FakeResponse(event)
        with patch("app.requests.get", return_value=fake):
            app.download_model_worker("ggml-base.bin")
        self.assertEqual(app.downloads["ggml-base.bin"]["status"], "cancelled")
        self.assertFalse(os.path.exists(os.path.join(self.models, "ggml-base.bin.tmp")))
        self.assertFalse(os.path.exists(os.path.join(self.models, "ggml-base.bin")))
        self.assertTrue(fake.closed)

    def test_cuda_probe_rejects_cpu_only_help_output(self):
        runtime = {"executable": os.path.join(self.gpu_runtimes, "cuda", "whisper-cli.exe")}
        result = Mock(returncode=0, stdout=b"", stderr=b"load_backend: loaded CPU backend")
        with patch("app.installed_gpu_runtime", return_value=runtime), patch("app.subprocess.run", return_value=result):
            available, error = app.probe_gpu_backend("cuda")
        self.assertFalse(available)
        self.assertIn("ไม่พบอุปกรณ์", error)

    def test_gpu_probe_requires_backend_device_marker(self):
        runtime = {"executable": os.path.join(self.gpu_runtimes, "vulkan", "whisper-cli.exe")}
        result = Mock(returncode=0, stdout=b"", stderr=b"ggml_vulkan: Found 1 Vulkan devices")
        with patch("app.installed_gpu_runtime", return_value=runtime), patch("app.subprocess.run", return_value=result):
            available, error = app.probe_gpu_backend("vulkan")
        self.assertTrue(available)
        self.assertIsNone(error)
    def test_cancelled_gpu_download_stays_cancelled_after_stream_error(self):
        event = threading.Event()
        app.gpu_downloads["cuda"] = {
            "status": "downloading", "progress": 0, "bytes_downloaded": 0,
            "total_bytes": 0, "error": None, "_cancel_event": event, "_response": None,
        }
        response = Mock(headers={"content-length": "10"})
        response.raise_for_status.return_value = None

        def interrupted_stream(chunk_size):
            event.set()
            raise OSError("connection closed during cancellation")
            yield b""

        response.iter_content.side_effect = interrupted_stream
        info = {**app.GPU_BACKENDS_INFO["cuda"], "url": "https://example.invalid/cuda.zip", "sha256": ""}
        with patch.dict(app.GPU_BACKENDS_INFO, {"cuda": info}), patch("app.requests.get", return_value=response):
            app.download_gpu_worker("cuda")
        self.assertEqual(app.gpu_downloads["cuda"]["status"], "cancelled")
        self.assertIsNone(app.gpu_downloads["cuda"]["error"])

    def test_gpu_download_replaces_incomplete_runtime_directory(self):
        version = app.GPU_BACKENDS_INFO["cuda"]["version"]
        version_root = Path(self.gpu_runtimes, "cuda", version)
        version_root.mkdir(parents=True)
        Path(version_root, "stale.txt").write_text("broken", encoding="utf-8")
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as archive:
            archive.writestr("whisper-cli.exe", b"runtime")
            archive.writestr("ggml-cuda.dll", b"cuda")
            archive.writestr("ggml-cpu-cascadelake.dll", b"forbidden")
            archive.writestr("bench.exe", b"extra")
            archive.writestr("README.txt", b"extra")
        payload = archive_buffer.getvalue()
        response = Mock(headers={"content-length": str(len(payload))})
        response.raise_for_status.return_value = None
        response.iter_content.return_value = [payload]
        app.gpu_downloads["cuda"] = {
            "status": "downloading", "progress": 0, "bytes_downloaded": 0,
            "total_bytes": 0, "error": None, "_cancel_event": threading.Event(), "_response": None,
        }
        info = {**app.GPU_BACKENDS_INFO["cuda"], "url": "https://example.invalid/cuda.zip", "sha256": ""}
        with patch.dict(app.GPU_BACKENDS_INFO, {"cuda": info}), patch("app.requests.get", return_value=response):
            app.download_gpu_worker("cuda")
        self.assertEqual(app.gpu_downloads["cuda"]["status"], "completed")
        self.assertTrue(Path(version_root, "whisper-cli.exe").exists())
        self.assertTrue(Path(version_root, "ggml-cuda.dll").exists())
        self.assertFalse(Path(version_root, "ggml-cpu-cascadelake.dll").exists())
        self.assertFalse(Path(version_root, "bench.exe").exists())
        self.assertFalse(Path(version_root, "README.txt").exists())
        self.assertFalse(Path(version_root, "stale.txt").exists())

    def test_cancel_transcription_sets_event_and_terminates_process(self):
        event = threading.Event()
        process = Mock()
        app.transcriptions["task-1"] = {
            "status": "transcribing", "progress": 25, "logs": [], "error": None,
            "srt_filename": None, "_cancel_event": event, "_process": process,
        }
        with patch("app.terminate_process_tree") as terminate:
            response = self.client.post("/api/transcribe/task-1/cancel")
        self.assertEqual(response.get_json()["status"], "cancelling")
        self.assertTrue(event.is_set())
        terminate.assert_called_once_with(process)

    def test_completed_task_is_not_cancelled(self):
        app.transcriptions["done"] = {
            "status": "completed", "progress": 100, "logs": [], "error": None,
            "srt_filename": "done.srt", "_cancel_event": threading.Event(), "_process": None,
        }
        response = self.client.post("/api/transcribe/done/cancel")
        self.assertEqual(response.get_json()["status"], "completed")
        self.assertFalse(app.transcriptions["done"]["_cancel_event"].is_set())

    def test_cancelled_worker_cleans_input_wav_and_partial_srt(self):
        task_id = "cleanup"
        input_path = os.path.join(self.uploads, "input.mp3")
        wav_path = os.path.join(self.uploads, f"{task_id}.wav")
        srt_path = os.path.join(self.outputs, f"{task_id}.srt")
        for path in (input_path, wav_path, srt_path):
            with open(path, "wb") as handle:
                handle.write(b"partial")
        event = threading.Event()
        app.transcriptions[task_id] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "srt_filename": None, "_cancel_event": event, "_process": None,
        }
        def cancel_during_conversion(*args):
            event.set()
            raise app.JobCancelled()
        with patch("app.run_ffmpeg_conversion", side_effect=cancel_during_conversion):
            app.transcription_worker(task_id, input_path, "ggml-base.bin", "auto", 2)
        self.assertEqual(app.transcriptions[task_id]["status"], "cancelled")
        for path in (input_path, wav_path, srt_path):
            self.assertFalse(os.path.exists(path))

    def test_start_transcription_validates_model_and_creates_queued_job(self):
        model_path = os.path.join(self.models, "ggml-base.bin")
        Path(model_path).write_bytes(b"model")
        task_id = self.reserve_transcription()
        with patch("app.runtime_preflight"), patch("app.probe_media", return_value={"has_video": False, "duration_seconds": 30}), patch("app.threading.Thread") as thread:
            response = self.client.post(
                f"/api/transcribe?task_id={task_id}",
                data={"file": (io.BytesIO(b"audio"), "audio.mp3"), "model": "ggml-base.bin", "threads": "2"},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["task_id"], task_id)
        self.assertEqual(app.transcriptions[task_id]["status"], "queued")
        thread.return_value.start.assert_called_once()

    def test_local_selection_is_opaque_and_preflight_does_not_expose_path(self):
        source = os.path.join(self.temp.name, "outside.mp4")
        Path(source).write_bytes(b"media")
        with patch("app.select_local_media_file", return_value=source), patch("app.probe_media", return_value={"duration_seconds": 60, "estimated_wav_bytes": 1, "recommended_free_bytes": 2, "upload_free_bytes": 3, "output_free_bytes": 3}):
            response = self.client.post("/api/local-selection")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("selection_id", payload)
        self.assertEqual(payload["name"], "outside.mp4")
        self.assertNotIn("path", payload)
        self.assertNotIn(source, response.get_data(as_text=True))

    @unittest.skipUnless(os.name == "nt", "Windows native dialog structure")
    def test_windows_file_dialog_casts_writable_buffer_to_lpwstr(self):
        import ctypes
        from ctypes import wintypes
        dialog, file_buffer, dialog_type = app.build_windows_open_file_dialog(ctypes, wintypes)
        self.assertEqual(dialog.lStructSize, ctypes.sizeof(dialog_type))
        self.assertEqual(dialog.nMaxFile, len(file_buffer))
        self.assertEqual(file_buffer.value, "")
        self.assertEqual(dialog.lpstrTitle, "เลือกไฟล์เสียงหรือวิดีโอ")

    def test_local_input_is_never_removed_by_worker_cleanup(self):
        task_id = "local-cleanup"
        input_path = os.path.join(self.temp.name, "source.mp4")
        wav_path = os.path.join(self.uploads, f"{task_id}.wav")
        Path(input_path).write_bytes(b"original")
        Path(wav_path).write_bytes(b"wav")
        event = threading.Event()
        app.transcriptions[task_id] = {"status": "queued", "progress": 0, "logs": [], "error": None, "srt_filename": None, "_cancel_event": event, "_process": None}
        with patch("app.run_ffmpeg_conversion", side_effect=app.JobCancelled()):
            app.transcription_worker(task_id, input_path, "ggml-base.bin", "auto", 2, owns_input=False)
        self.assertTrue(os.path.exists(input_path))
        self.assertFalse(os.path.exists(wav_path))

    def test_active_transcription_rejects_second_reservation(self):
        app.transcriptions["active"] = {"status": "transcribing", "progress": 10, "logs": [], "error": None, "srt_filename": None, "_cancel_event": threading.Event(), "_process": None}
        response = self.client.post("/api/transcribe/reservations")
        self.assertEqual(response.status_code, 409)

    def test_srt_round_trip_preserves_multiline_text(self):
        source = "1\n00:00:01,000 --> 00:00:03,250\nสวัสดีครับ\nบรรทัดที่สอง\n\n2\n00:00:04,000 --> 00:00:05,000\nOpenAI\n"
        cues = app.parse_srt(source)
        self.assertEqual(cues[0]["start_ms"], 1000)
        self.assertEqual(cues[0]["text"], "สวัสดีครับ\nบรรทัดที่สอง")
        self.assertEqual(app.parse_srt(app.serialize_srt(cues)), cues)

    def test_srt_rejects_invalid_time_range(self):
        with self.assertRaisesRegex(ValueError, "end after"):
            app.parse_srt("1\n00:00:03,000 --> 00:00:02,000\nผิดเวลา\n")

    def test_glossary_persists_and_builds_next_job_prompt(self):
        response = self.client.put("/api/glossary", json={"entries": [
            {"from": "พรีเมียโปร", "to": "Premiere Pro"},
            {"from": "โอเพ่นเอไอ", "to": "OpenAI"},
        ]})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(os.path.exists(app.GLOSSARY_PATH))
        entries = self.client.get("/api/glossary").get_json()["entries"]
        self.assertEqual(entries[0]["to"], "Premiere Pro")
        self.assertEqual(app.build_initial_prompt(), "Premiere Pro, OpenAI")

    def test_glossary_allows_empty_replacement_as_deletion_rule(self):
        response = self.client.put("/api/glossary", json={"entries": [
            {"from": "คร", "to": ""},
            {"from": "เอสอาร์ที", "to": "SRT"},
        ]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["entries"][0], {"from": "คร", "to": ""})
        self.assertEqual(app.build_initial_prompt(), "SRT")

    def test_glossary_rejects_duplicate_terms(self):
        response = self.client.put("/api/glossary", json={"entries": [
            {"from": "Whisper", "to": "Whisper"},
            {"from": "whisper", "to": "whisper.cpp"},
        ]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Duplicate", response.get_json()["error"])

    def test_glossary_export_returns_portable_json(self):
        self.client.put("/api/glossary", json={"entries": [{"from": "เอสอาร์ที", "to": "SRT"}]})
        response = self.client.get("/api/glossary/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertIn("SRT", response.get_data(as_text=True))

    def test_preferences_persist_validated_values(self):
        payload = {
            "model": "ggml-base.bin", "language": "th", "threads": 6, "theme": "dark",
            "subtitle_style": {
                "font": "leelawadee-ui", "font_size": 36.5, "outline_width": 2.25,
                "background": True, "shadow_depth": 1.5, "position": "bottom", "margin_v": 48.5,
            },
        }
        response = self.client.put("/api/preferences", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/preferences").get_json()["threads"], 6)
        self.assertEqual(self.client.get("/api/preferences").get_json()["subtitle_style"]["font_size"], 36.5)
        self.assertTrue(os.path.exists(app.PREFERENCES_PATH))

    def test_editor_backup_restores_validated_subtitles(self):
        content = "1\n00:00:01,000 --> 00:00:03,000\nข้อความสำรอง\n"
        saved = self.client.put("/api/editor-backup", json={
            "content": content, "input_name": "งานที่ยังไม่เสร็จ.mp4", "dirty": True,
            "subtitle_style": {"font": "leelawadee-ui", "font_size": 36},
        })
        self.assertEqual(saved.status_code, 200)
        metadata = self.client.get("/api/editor-backup").get_json()
        self.assertTrue(metadata["available"])
        self.assertEqual(metadata["cue_count"], 1)
        restored = self.client.post("/api/editor-backup/restore")
        self.assertEqual(restored.status_code, 200)
        task_id = restored.get_json()["task_id"]
        self.assertEqual(app.transcriptions[task_id]["status"], "completed")
        self.assertFalse(app.transcriptions[task_id]["has_video"])
        subtitle = self.client.get(f"/api/subtitles/{task_id}").get_json()["content"]
        self.assertIn("ข้อความสำรอง", subtitle)

    def test_eta_is_smoothed_and_internal_clock_is_private(self):
        job = {"_stage_started_at": 10, "_eta_smoothed": None, "eta_seconds": None}
        with patch("app.time.monotonic", return_value=20):
            app.update_eta(job, 0.25)
        self.assertEqual(job["eta_seconds"], 30)
        self.assertNotIn("_stage_started_at", app.public_state(job))
    def test_whisper_progress_maps_to_transcription_stage_and_eta(self):
        job = {"_stage_started_at": 10, "_eta_smoothed": None, "eta_seconds": None, "progress": 15}
        with patch("app.time.monotonic", return_value=20):
            app.parse_whisper_progress("whisper_print_progress_callback: progress = 25%", job)
        self.assertEqual(job["progress"], 35)
        self.assertEqual(job["eta_seconds"], 30)
    def seed_completed_subtitles(self, task_id="editor"):
        current = os.path.join(self.outputs, f"{task_id}.srt")
        original = os.path.join(self.outputs, f"{task_id}.original.srt")
        content = "1\n00:00:01,000 --> 00:00:03,000\nข้อความเดิม\n"
        for path in (current, original):
            with open(path, "w", encoding="utf-8") as subtitle:
                subtitle.write(content)
        app.transcriptions[task_id] = {
            "status": "completed", "progress": 100, "logs": [], "error": None,
            "srt_filename": f"{task_id}.srt", "_cancel_event": threading.Event(), "_process": None,
        }
        return current, original, content

    def test_editor_save_preserves_original_and_reset_restores_it(self):
        current, original, initial = self.seed_completed_subtitles()
        edited = "1\n00:00:01,000 --> 00:00:03,500\nข้อความที่แก้แล้ว\n"
        saved = self.client.put("/api/subtitles/editor", json={"content": edited})
        self.assertEqual(saved.status_code, 200)
        self.assertIn("ข้อความที่แก้แล้ว", Path(current).read_text(encoding="utf-8-sig"))
        self.assertEqual(Path(original).read_text(encoding="utf-8-sig"), initial)
        reset = self.client.post("/api/subtitles/editor/reset")
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(Path(current).read_text(encoding="utf-8-sig"), initial)

    def test_editor_rejects_invalid_srt_without_overwriting_file(self):
        current, _, initial = self.seed_completed_subtitles("invalid")
        response = self.client.put("/api/subtitles/invalid", json={"content": "not srt"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Path(current).read_text(encoding="utf-8-sig"), initial)

    def test_editor_reset_rejects_invalid_original_without_overwriting_current(self):
        current, original, initial = self.seed_completed_subtitles("invalid-reset")
        Path(original).write_text("not srt", encoding="utf-8")
        response = self.client.post("/api/subtitles/invalid-reset/reset")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Path(current).read_text(encoding="utf-8-sig"), initial)
        self.assertFalse(Path(current + ".tmp").exists())

    def test_editor_reset_uses_atomic_srt_writer(self):
        current, _, _ = self.seed_completed_subtitles("atomic-reset")
        with patch("app.write_srt_atomic", wraps=app.write_srt_atomic) as atomic_write:
            response = self.client.post("/api/subtitles/atomic-reset/reset")
        self.assertEqual(response.status_code, 200)
        atomic_write.assert_called_once()
        self.assertEqual(atomic_write.call_args.args[0], current)

    def test_transcription_rejects_request_larger_than_available_space_before_parsing(self):
        task_id = self.reserve_transcription()
        disk = Mock(free=1024)
        with patch("app.shutil.disk_usage", return_value=disk):
            response = self.client.post(
                f"/api/transcribe?task_id={task_id}",
                data={"file": (io.BytesIO(b"x" * 2048), "large.mp4")},
            )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json()["code"], "upload_too_large")
        self.assertEqual(os.listdir(self.uploads), [])
        self.assertEqual(app.transcriptions[task_id]["status"], "failed")

    def test_failed_upload_save_removes_partial_file_and_marks_job_failed(self):
        Path(self.models, "ggml-base.bin").write_bytes(b"model")
        task_id = self.reserve_transcription()

        def fail_after_partial_save(file_storage, destination, *_):
            Path(destination).write_bytes(b"partial")
            raise OSError("disk full")

        with patch("app.save_upload_cancellable", side_effect=fail_after_partial_save):
            response = self.client.post(
                f"/api/transcribe?task_id={task_id}",
                data={"file": (io.BytesIO(b"media"), "broken.mp4"), "model": "ggml-base.bin"},
            )
        self.assertEqual(response.status_code, 507)
        self.assertEqual(response.get_json()["code"], "upload_failed")
        self.assertEqual(os.listdir(self.uploads), [])
        self.assertEqual(app.transcriptions[task_id]["status"], "failed")

    def test_glossary_renderer_uses_dom_value_properties_not_html_interpolation(self):
        source = Path(app.SOURCE_DIR, "static", "app.js").read_text(encoding="utf-8")
        renderer = source.split("function renderGlossary()", 1)[1].split("function openGlossary()", 1)[0]
        self.assertNotIn("innerHTML", renderer)
        self.assertIn(".value=String(", renderer)
        self.assertIn("document.createElement('input')", renderer)

    def test_portable_build_uses_shared_runtime_binary_policy(self):
        spec = Path(app.SOURCE_DIR, "FreeSRT.spec").read_text(encoding="utf-8")
        build = Path(app.SOURCE_DIR, "build_portable.ps1").read_text(encoding="utf-8")
        policy_source = Path(app.SOURCE_DIR, "freesrt", "runtime_policy.py").read_text(encoding="utf-8")
        selected = {
            path.name
            for path in Path(app.SOURCE_DIR, "bin", "Release").iterdir()
            if path.is_file() and is_allowed_cpu_release_binary(path)
        }
        self.assertEqual(
            selected,
            {
                "whisper-cli.exe", "whisper.dll", "ggml.dll", "ggml-base.dll",
                "ggml-cpu-x64.dll", "ggml-cpu-sse42.dll", "ggml-cpu-sandybridge.dll",
                "ggml-cpu-haswell.dll", "ggml-cpu-alderlake.dll",
            },
        )
        for variant in ("cascadelake", "skylakex", "icelake", "cannonlake"):
            self.assertIn(variant, policy_source)
        self.assertIn("from freesrt.runtime_policy import is_allowed_cpu_release_binary", spec)
        self.assertIn("-m freesrt.runtime_policy validate-portable", build)
        self.assertIn("-m freesrt.runtime_policy extract-runtime", build)
        self.assertNotIn("Test-ForbiddenCpuDll", build)
    def test_txt_export_uses_latest_edited_subtitles_without_timestamps(self):
        self.seed_completed_subtitles("txt-export")
        edited = (
            "1\n00:00:01,000 --> 00:00:03,500\nFirst line\nsecond line\n\n"
            "2\n00:00:04,000 --> 00:00:05,000\nข้อความล่าสุด\n"
        )
        saved = self.client.put("/api/subtitles/txt-export", json={"content": edited})
        self.assertEqual(saved.status_code, 200)

        exported = self.client.get("/api/download/txt-export/txt")

        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.mimetype, "text/plain")
        self.assertIn("attachment", exported.headers["Content-Disposition"])
        self.assertIn("transcription.txt", exported.headers["Content-Disposition"])
        self.assertEqual(
            exported.data.decode("utf-8-sig"),
            "First line second line\nข้อความล่าสุด\n",
        )
        self.assertNotIn("-->", exported.data.decode("utf-8-sig"))

    def test_txt_export_rejects_unknown_or_incomplete_task(self):
        response = self.client.get("/api/download/missing/txt")
        self.assertEqual(response.status_code, 404)

    def test_whisper_uses_long_prompt_flag_from_glossary(self):
        app.transcriptions["prompt"] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "srt_filename": None, "_cancel_event": threading.Event(), "_process": None,
        }
        process = Mock(stdout=[])
        process.wait.return_value = 0
        with patch("app.build_initial_prompt", return_value="Premiere Pro, OpenAI"), patch("app.subprocess.Popen", return_value=process) as popen:
            app.run_whisper_transcription("audio.wav", "model.bin", "out", "th", 4, "prompt")
        command = popen.call_args.args[0]
        self.assertIn("--prompt", command)
        self.assertEqual(command[command.index("--prompt") + 1], "Premiere Pro, OpenAI")
        self.assertNotIn("-p", command)
        self.assertIn("--no-gpu", command)

    def test_successful_worker_keeps_original_srt_for_reset(self):
        task_id = "original-copy"
        input_path = os.path.join(self.uploads, "input.mp3")
        Path(input_path).write_bytes(b"audio")
        app.transcriptions[task_id] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "srt_filename": None, "_cancel_event": threading.Event(), "_process": None,
        }
        def fake_whisper(wav, model, output_base, language, threads, job_id):
            Path(output_base + ".srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nสวัสดี\n", encoding="utf-8"
            )
        with patch("app.run_ffmpeg_conversion"), patch("app.run_whisper_transcription", side_effect=fake_whisper):
            app.transcription_worker(task_id, input_path, "ggml-base.bin", "th", 2)
        self.assertEqual(app.transcriptions[task_id]["status"], "completed")
        self.assertTrue(Path(self.outputs, f"{task_id}.original.srt").exists())
    def test_diagnostics_reports_runtime_paths(self):
        response = self.client.get("/api/diagnostics")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("path", payload["ffmpeg"])
        self.assertIn("exists", payload["whisper"])
        self.assertIn("exists", payload["ffprobe"])
        self.assertIn("writable", payload)
    def test_ffmpeg_uses_configured_bundled_executable(self):
        app.transcriptions["ffmpeg-path"] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "srt_filename": None, "_cancel_event": threading.Event(), "_process": None,
        }
        process = Mock()
        process.wait.return_value = 0
        with patch("app.FFMPEG_EXE", r"C:\portable\_internal\bin\ffmpeg.exe"), patch("app.runtime_environment", return_value={}), patch("app.subprocess.Popen", return_value=process) as popen:
            app.run_ffmpeg_conversion("input.mp4", "output.wav", "ffmpeg-path")
        command = popen.call_args.args[0]
        self.assertEqual(command[0], r"C:\portable\_internal\bin\ffmpeg.exe")
        self.assertNotEqual(command[0], "ffmpeg")

    def test_probe_media_parses_ffprobe_json(self):
        source = os.path.join(self.uploads, "probe.wav")
        Path(source).write_bytes(b"wave")
        result = Mock(
            returncode=0,
            stdout='{"format":{"duration":"2.5"},"streams":[{"codec_type":"audio"}]}',
            stderr="",
        )
        with patch("app.subprocess.run", return_value=result), patch("app.runtime_environment", return_value={}):
            metadata = app.probe_media(source)
        self.assertEqual(metadata["duration_seconds"], 2.5)
        self.assertFalse(metadata["has_video"])
        self.assertEqual(metadata["estimated_wav_bytes"], int(2.5 * app.WAV_BYTES_PER_SECOND))

    def test_whisper_zero_duration_cue_is_repaired(self):
        source = "1\n00:00:10,000 --> 00:00:10,000\nคำบรรยายช่วงสั้น\n"
        with self.assertRaisesRegex(ValueError, "end after"):
            app.parse_srt(source)
        cues = app.parse_srt(source, repair_invalid_ranges=True)
        self.assertEqual(cues[0]["start_ms"], 10000)
        self.assertEqual(cues[0]["end_ms"], 10500)
        self.assertEqual(app.parse_srt(app.serialize_srt(cues)), cues)

    def test_video_options_default_to_leelawadee_and_allow_multiple_fonts(self):
        response = self.client.get("/api/video-options")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["default_font"], "leelawadee-ui")
        self.assertEqual(payload["default_style"]["outline_width"], 2)
        self.assertTrue(payload["default_style"]["background"])
        self.assertEqual(payload["default_style"]["position"], "bottom")
        self.assertEqual(payload["fonts"][0]["family"], "Leelawadee UI")
        self.assertGreaterEqual(len(payload["fonts"]), 4)

    def test_subtitle_filter_uses_whitelisted_font_and_rejects_unknown_font(self):
        subtitle_filter = app.build_subtitle_filter("task.srt", "leelawadee-ui", 36)
        self.assertIn("FontName=Leelawadee UI", subtitle_filter)
        self.assertIn("FontSize=36", subtitle_filter)
        with self.assertRaisesRegex(ValueError, "ฟอนต์"):
            app.build_subtitle_filter("task.srt", "not-installed", 36)

    def test_subtitle_filter_supports_outline_background_shadow_and_position(self):
        subtitle_filter = app.build_subtitle_filter(
            "task.srt", "leelawadee-ui", 42, outline_width=4, background=True,
            shadow_depth=3, position="top", margin_v=80,
        )
        self.assertIn("Outline=4", subtitle_filter)
        self.assertIn("BorderStyle=3", subtitle_filter)
        self.assertIn("BackColour=&H4D000000", subtitle_filter)
        self.assertIn("Shadow=3", subtitle_filter)
        self.assertIn("Alignment=6", subtitle_filter)
        self.assertIn("MarginV=80", subtitle_filter)
        with self.assertRaisesRegex(ValueError, "เส้นขอบ"):
            app.build_subtitle_filter("task.srt", "leelawadee-ui", 36, outline_width=7)
        with self.assertRaisesRegex(ValueError, "ตำแหน่ง"):
            app.build_subtitle_filter("task.srt", "leelawadee-ui", 36, position="outside")

    def test_subtitle_filter_preserves_decimal_style_precision(self):
        subtitle_filter = app.build_subtitle_filter(
            "task.srt", "leelawadee-ui", 36.5, outline_width=2.25,
            background=False, shadow_depth=1.75, margin_v=48.5,
        )
        self.assertIn("FontSize=36.5", subtitle_filter)
        self.assertIn("Outline=2.25", subtitle_filter)
        self.assertIn("Shadow=1.75", subtitle_filter)
        self.assertIn("MarginV=48.5", subtitle_filter)

    def seed_video_task(self, task_id="video-task", source_path=None):
        Path(self.outputs, f"{task_id}.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nสวัสดี\n", encoding="utf-8"
        )
        app.transcriptions[task_id] = {
            "status": "completed", "progress": 100, "logs": [], "error": None,
            "srt_filename": f"{task_id}.srt", "input_name": "clip.mp4", "has_video": True,
            "_duration_seconds": 1, "_source_path": source_path,
            "_cancel_event": threading.Event(), "_process": None,
        }

    def test_local_media_preview_uses_private_source_without_serializing_path(self):
        source = os.path.join(self.temp.name, "private-source.mp4")
        Path(source).write_bytes(b"video-bytes")
        self.seed_video_task(source_path=source)
        status = self.client.get("/api/transcribe/status/video-task")
        self.assertNotIn(source, status.get_data(as_text=True))
        preview = self.client.get("/api/media/video-task")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data, b"video-bytes")
        preview.close()

    def test_start_local_video_render_creates_queued_job(self):
        source = os.path.join(self.temp.name, "source.mp4")
        Path(source).write_bytes(b"video")
        self.seed_video_task(source_path=source)
        media = {"has_video": True, "duration_seconds": 1, "width": 640, "height": 480}
        render_id = self.reserve_render()
        with patch("app.probe_media", return_value=media), patch("app.runtime_preflight"), patch("app.threading.Thread") as thread:
            response = self.client.post(f"/api/video-render/video-task?render_id={render_id}", data={
                "font": "leelawadee-ui", "font_size": "36.5", "outline_width": "4.25",
                "background": "false", "shadow_depth": "2.5", "position": "middle", "margin_v": "64.5",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["render_id"], render_id)
        self.assertEqual(app.video_renders[render_id]["status"], "queued")
        self.assertEqual(app.video_renders[render_id]["font"], "leelawadee-ui")
        self.assertEqual(app.video_renders[render_id]["font_size"], 36.5)
        self.assertEqual(app.video_renders[render_id]["outline_width"], 4.25)
        self.assertEqual(app.video_renders[render_id]["shadow_depth"], 2.5)
        self.assertFalse(app.video_renders[render_id]["background"])
        self.assertEqual(app.video_renders[render_id]["margin_v"], 64.5)
        self.assertEqual(app.video_renders[render_id]["position"], "middle")
        thread.return_value.start.assert_called_once()

    def test_video_render_status_hides_internal_source_and_cancel_is_idempotent(self):
        event = threading.Event()
        source = os.path.join(self.temp.name, "source.mp4")
        app.video_renders["render"] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "video_filename": None, "_cancel_event": event, "_process": None,
            "_source_path": source, "_owns_input": False,
        }
        first = self.client.post("/api/video-render/render/cancel")
        second = self.client.post("/api/video-render/render/cancel")
        self.assertEqual(first.get_json()["status"], "cancelling")
        self.assertEqual(second.get_json()["status"], "cancelling")
        self.assertTrue(event.is_set())
        status = self.client.get("/api/video-render/status/render")
        self.assertNotIn("_source_path", status.get_json())
        self.assertNotIn(source, status.get_data(as_text=True))

    def test_completed_video_render_is_not_changed_by_late_cancel(self):
        event = threading.Event()
        app.video_renders["done-render"] = {
            "status": "completed", "progress": 100, "logs": [], "error": None,
            "video_filename": "done-render.mp4", "_cancel_event": event, "_process": None,
        }
        response = self.client.post("/api/video-render/done-render/cancel")
        self.assertEqual(response.get_json()["status"], "completed")
        self.assertFalse(event.is_set())

    def test_cancelled_video_worker_cleans_uploaded_input_and_partial_output(self):
        source = os.path.join(self.uploads, "render-input.mp4")
        Path(source).write_bytes(b"source")
        self.seed_video_task()
        event = threading.Event()
        event.set()
        app.video_renders["cancel-render"] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "video_filename": None, "_cancel_event": event, "_process": None,
        }
        Path(self.outputs, "cancel-render.tmp.mp4").write_bytes(b"partial")
        app.video_render_worker("cancel-render", "video-task", source, True, "leelawadee-ui", 36)
        self.assertEqual(app.video_renders["cancel-render"]["status"], "cancelled")
        self.assertFalse(os.path.exists(source))
        self.assertFalse(Path(self.outputs, "cancel-render.tmp.mp4").exists())
    def test_whisper_invoked_from_app_dir_with_relative_paths(self):
        """Whisper must run from APP_DIR with relative paths so non-ASCII install
        directories (e.g. Thai folder names) do not corrupt argv on Windows."""
        task_id = "relpath-test"
        app.transcriptions[task_id] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "srt_filename": None, "_cancel_event": threading.Event(), "_process": None,
            "_compute_backend": "cpu",
        }
        process = Mock(stdout=[])
        process.wait.return_value = 0
        # Patch APP_DIR to the temp directory so that model/wav/output paths
        # (which live under temp) are on the same drive and relpath succeeds.
        with patch("app.APP_DIR", self.temp.name), \
             patch("app.subprocess.Popen", return_value=process) as popen, \
             patch("app.runtime_environment", return_value={}), \
             patch("app.build_initial_prompt", return_value=""):
            app.run_whisper_transcription(
                os.path.join(self.uploads, f"{task_id}.wav"),
                os.path.join(self.models, "ggml-base.bin"),
                os.path.join(self.outputs, task_id),
                "th", 4, task_id,
            )
        call_kwargs = popen.call_args
        # cwd must be the patched APP_DIR
        actual_cwd = call_kwargs.kwargs.get("cwd") or call_kwargs[1].get("cwd")
        self.assertEqual(actual_cwd, self.temp.name)
        command = call_kwargs.args[0]
        # -m, -f, and -of arguments must be relative (no drive letter prefix)
        model_arg = command[command.index("-m") + 1]
        wav_arg = command[command.index("-f") + 1]
        of_arg = command[command.index("-of") + 1]
        self.assertFalse(os.path.isabs(model_arg), f"-m arg should be relative, got: {model_arg}")
        self.assertFalse(os.path.isabs(wav_arg), f"-f arg should be relative, got: {wav_arg}")
        self.assertFalse(os.path.isabs(of_arg), f"-of arg should be relative, got: {of_arg}")

    def test_illegal_instruction_exit_code_raises_avx512_message(self):
        """Exit code 3221226505 (0xC000001D STATUS_ILLEGAL_INSTRUCTION) must be
        detected and produce a clear Thai error message about AVX-512."""
        task_id = "avx512-crash"
        app.transcriptions[task_id] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "srt_filename": None, "_cancel_event": threading.Event(), "_process": None,
            "_compute_backend": "cpu",
        }
        process = Mock(stdout=[])
        # 3221225501 = 0xC000001D as unsigned 32-bit integer
        process.wait.return_value = 0xC000001D  # 3221225501
        with patch("app.subprocess.Popen", return_value=process), \
             patch("app.runtime_environment", return_value={}), \
             patch("app.build_initial_prompt", return_value=""):
            with self.assertRaises(RuntimeError) as ctx:
                app.run_whisper_transcription(
                    os.path.join(self.uploads, f"{task_id}.wav"),
                    os.path.join(self.models, "ggml-base.bin"),
                    os.path.join(self.outputs, task_id),
                    "th", 4, task_id,
                )
        self.assertIn("AVX-512", str(ctx.exception))
        self.assertIn("cascadelake", str(ctx.exception))

    def test_illegal_instruction_signed_exit_code_also_detected(self):
        """Signed -1073741795 (same bits as 0xC000001D) must also be detected."""
        task_id = "avx512-signed"
        app.transcriptions[task_id] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "srt_filename": None, "_cancel_event": threading.Event(), "_process": None,
            "_compute_backend": "cpu",
        }
        process = Mock(stdout=[])
        # 0xC000001D as signed 32-bit two's complement = -(2**32 - 0xC000001D) = -1073741795
        # Verify: (-1073741795) & 0xFFFFFFFF == 0xC000001D
        process.wait.return_value = -(2**32 - 0xC000001D)  # -1073741795
        with patch("app.subprocess.Popen", return_value=process), \
             patch("app.runtime_environment", return_value={}), \
             patch("app.build_initial_prompt", return_value=""):
            with self.assertRaises(RuntimeError) as ctx:
                app.run_whisper_transcription(
                    os.path.join(self.uploads, f"{task_id}.wav"),
                    os.path.join(self.models, "ggml-base.bin"),
                    os.path.join(self.outputs, task_id),
                    "th", 4, task_id,
                )
        self.assertIn("AVX-512", str(ctx.exception))


    def test_unreserved_start_routes_return_migration_error(self):
        transcription = self.client.post("/api/transcribe", data={})
        self.assertEqual(transcription.status_code, 428)
        self.assertEqual(transcription.get_json()["error"]["code"], "reservation_required")
        self.seed_video_task()
        render = self.client.post("/api/video-render/video-task", data={})
        self.assertEqual(render.status_code, 428)
        self.assertEqual(render.get_json()["error"]["code"], "reservation_required")

    def test_reserved_transcription_can_be_cancelled_before_start_idempotently(self):
        task_id = self.reserve_transcription()
        first = self.client.post(f"/api/transcribe/{task_id}/cancel")
        second = self.client.post(f"/api/transcribe/{task_id}/cancel")
        self.assertEqual(first.get_json()["status"], "cancelled")
        self.assertEqual(second.get_json()["status"], "cancelled")
        status = self.client.get(f"/api/transcribe/status/{task_id}")
        self.assertEqual(status.get_json()["status"], "cancelled")
        self.assertNotIn("_cancel_event", status.get_json())
        start = self.client.post(f"/api/transcribe?task_id={task_id}", data={})
        self.assertEqual(start.status_code, 409)
        self.assertEqual(start.get_json()["error"]["code"], "reservation_cancelled")

    def test_claimed_reservation_cannot_be_reused(self):
        task_id = self.reserve_transcription()
        first = self.client.post(f"/api/transcribe?task_id={task_id}", data={})
        self.assertEqual(first.status_code, 413)
        second = self.client.post(f"/api/transcribe?task_id={task_id}", data={})
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.get_json()["error"]["code"], "reservation_claimed")

    def test_cancel_during_upload_cleans_partial_input(self):
        Path(self.models, "ggml-base.bin").write_bytes(b"model")
        task_id = self.reserve_transcription()

        def cancel_upload(file_storage, destination, job, cancelled_error):
            Path(destination).write_bytes(b"partial")
            job["_cancel_event"].set()
            raise cancelled_error()

        with patch("app.save_upload_cancellable", side_effect=cancel_upload):
            response = self.client.post(
                f"/api/transcribe?task_id={task_id}",
                data={"file": (io.BytesIO(b"media"), "clip.mp4"), "model": "ggml-base.bin"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(app.transcriptions[task_id]["status"], "cancelled")
        self.assertEqual(os.listdir(self.uploads), [])

    def test_client_disconnect_terminalizes_transcription_across_cancel_orderings(self):
        for cancel_during_parse in (False, True):
            with self.subTest(cancel_during_parse=cancel_during_parse):
                task_id = self.reserve_transcription()

                def disconnect(_request):
                    if cancel_during_parse:
                        app.request_cancel(app.transcriptions, app.state_lock, task_id)
                    raise ClientDisconnected()

                with patch("app.read_request_form_files", side_effect=disconnect), \
                     patch("app.threading.Thread") as worker:
                    response = self.client.post(
                        f"/api/transcribe?task_id={task_id}",
                        data={"placeholder": "body"}, content_type="multipart/form-data",
                    )
                self.assertEqual(response.status_code, 409)
                self.assertEqual(app.transcriptions[task_id]["status"], "cancelled")
                worker.assert_not_called()
                late_cancel = self.client.post(f"/api/transcribe/{task_id}/cancel")
                self.assertEqual(late_cancel.get_json()["status"], "cancelled")
                replacement = self.reserve_transcription()
                self.client.post(f"/api/transcribe/{replacement}/cancel")
                self.assertEqual(os.listdir(self.uploads), [])

    def test_client_disconnect_terminalizes_render_and_preserves_local_source(self):
        source = os.path.join(self.temp.name, "user-owned-source.mp4")
        Path(source).write_bytes(b"video")
        self.seed_video_task(source_path=source)
        for cancel_during_parse in (False, True):
            with self.subTest(cancel_during_parse=cancel_during_parse):
                render_id = self.reserve_render()

                def disconnect(_request):
                    if cancel_during_parse:
                        app.request_cancel(app.video_renders, app.state_lock, render_id)
                    raise ClientDisconnected()

                with patch("app.read_request_form_files", side_effect=disconnect), \
                     patch("app.threading.Thread") as worker:
                    response = self.client.post(
                        f"/api/video-render/video-task?render_id={render_id}",
                        data={"placeholder": "body"}, content_type="multipart/form-data",
                    )
                self.assertEqual(response.status_code, 409)
                self.assertEqual(app.video_renders[render_id]["status"], "cancelled")
                worker.assert_not_called()
                self.assertTrue(Path(source).exists())
                self.assertFalse(Path(self.outputs, f"{render_id}.render.srt").exists())
                late_cancel = self.client.post(f"/api/video-render/{render_id}/cancel")
                self.assertEqual(late_cancel.get_json()["status"], "cancelled")

    def test_malformed_multipart_terminalizes_claimed_job_as_failed(self):
        task_id = self.reserve_transcription()
        with patch("app.read_request_form_files", side_effect=BadRequest("malformed multipart")):
            response = self.client.post(
                f"/api/transcribe?task_id={task_id}",
                data={"placeholder": "body"}, content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "request_parse_failed")
        self.assertEqual(app.transcriptions[task_id]["status"], "failed")
        replacement = self.reserve_transcription()
        self.client.post(f"/api/transcribe/{replacement}/cancel")
    def test_reserved_render_can_be_cancelled_before_start(self):
        self.seed_video_task()
        render_id = self.reserve_render()
        response = self.client.post(f"/api/video-render/{render_id}/cancel")
        self.assertEqual(response.get_json()["status"], "cancelled")
        self.assertTrue(app.video_renders[render_id]["_cancel_event"].is_set())
        start = self.client.post(f"/api/video-render/video-task?render_id={render_id}", data={})
        self.assertEqual(start.status_code, 409)

    def test_cancellable_probe_terminates_process_tree(self):
        task_id = self.reserve_transcription()
        job = app.transcriptions[task_id]
        process = Mock()

        def interrupt_probe(timeout):
            job["_cancel_event"].set()
            raise app.subprocess.TimeoutExpired(["probe"], timeout)

        process.communicate.side_effect = interrupt_probe
        with patch("app.subprocess.Popen", return_value=process), patch("app.terminate_process_tree") as terminate:
            with self.assertRaises(app.JobCancelled):
                app.run_cancellable_probe(["probe"], "probe", None, 1, job=job)
        terminate.assert_called_once_with(process)
        self.assertIsNone(job["_process"])

    def test_public_state_redacts_private_path_variants_recursively(self):
        secret = r"C:\Users\Private Person\Videos\clip.mp4"
        job = {
            "status": "failed",
            "error": f"cannot open {secret}",
            "logs": ["C:/USERS/PRIVATE PERSON/VIDEOS/CLIP.MP4: access denied"],
            "detail": {"nested": secret.replace("\\", "\\\\")},
            "_private_paths": [secret],
            "_cancel_event": threading.Event(),
        }
        public = app.public_state(job)
        serialized = str(public).casefold()
        self.assertNotIn("private person", serialized)
        self.assertNotIn("clip.mp4", serialized)
        self.assertIn("[private source]", serialized)
        self.assertNotIn("_private_paths", public)

    def test_preflight_error_response_redacts_local_source_path(self):
        source = os.path.join(self.temp.name, "private", "source.mp4")
        Path(source).parent.mkdir()
        Path(source).write_bytes(b"video")
        Path(self.models, "ggml-base.bin").write_bytes(b"model")
        selection_id = "private-selection"
        app.local_selections[selection_id] = {
            "path": source,
            "expires_at": app.time.monotonic() + 60,
        }
        task_id = self.reserve_transcription()
        with patch("app.probe_media", side_effect=ValueError(f"ffprobe failed for {source}")):
            response = self.client.post(
                f"/api/transcribe?task_id={task_id}",
                data={"selection_id": selection_id, "model": "ggml-base.bin"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(source.casefold(), response.get_data(as_text=True).casefold())
        self.assertNotIn(source.casefold(), str(app.public_state(app.transcriptions[task_id])).casefold())
        self.assertTrue(Path(source).exists())

    def test_render_worker_redacts_ffmpeg_output_with_private_source(self):
        source = os.path.join(self.temp.name, "Private Source", "movie.mp4")
        Path(source).parent.mkdir()
        Path(source).write_bytes(b"video")
        self.seed_video_task(source_path=source)
        subtitle_path = os.path.join(self.outputs, "private-render.render.srt")
        Path(subtitle_path).write_text("1\n00:00:00,000 --> 00:00:01,000\nText\n", encoding="utf-8")
        app.video_renders["private-render"] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "video_filename": None, "_cancel_event": threading.Event(), "_process": None,
            "_source_path": source, "_owns_input": False, "_subtitle_path": subtitle_path,
            "_private_paths": [source],
            "_capacity_estimate": app.estimate_render_capacity(len(b"video"), 1, 640, 480),
        }
        process = Mock(stdout=[f"{source}: access denied"])
        process.wait.return_value = 1
        with patch("app.subprocess.Popen", return_value=process), patch("app.runtime_environment", return_value={}):
            app.video_render_worker(
                "private-render", "video-task", source, False, "leelawadee-ui", 36,
            )
        public = app.public_state(app.video_renders["private-render"])
        serialized = str(public).casefold()
        self.assertEqual(public["status"], "failed")
        self.assertNotIn(source.casefold(), serialized)
        self.assertIn("[private source]", serialized)
        self.assertTrue(Path(source).exists())

    def test_render_capacity_estimate_is_conservative_and_fails_closed(self):
        estimate = app.estimate_render_capacity(100 * 1024 * 1024, 120, 1920, 1080)
        self.assertGreaterEqual(estimate.estimated_output_bytes, 200 * 1024 * 1024)
        self.assertEqual(
            estimate.required_free_bytes,
            estimate.estimated_output_bytes + estimate.safety_margin_bytes + estimate.emergency_floor_bytes,
        )
        with self.assertRaisesRegex(app.RenderCapacityError, "duration and dimensions"):
            app.estimate_render_capacity(1, 60, 0, 1080)

    def test_render_capacity_checks_output_volume(self):
        estimate = app.estimate_render_capacity(1024, 10, 640, 480)
        usage = Mock(return_value=Mock(free=estimate.required_free_bytes - 1))
        with self.assertRaises(app.RenderCapacityError) as error:
            app.ensure_render_capacity(self.outputs, estimate, disk_usage=usage)
        self.assertEqual(error.exception.code, "render_capacity_insufficient")
        usage.assert_called_once_with(self.outputs)

    def test_local_render_rejects_insufficient_output_capacity(self):
        source = os.path.join(self.temp.name, "large-source.mp4")
        Path(source).write_bytes(b"video")
        self.seed_video_task(source_path=source)
        render_id = self.reserve_render()
        media = {"has_video": True, "duration_seconds": 3600, "width": 3840, "height": 2160}
        free = 700 * 1024 * 1024
        with patch("app.probe_media", return_value=media), patch("app.shutil.disk_usage", return_value=Mock(free=free)):
            response = self.client.post(
                f"/api/video-render/video-task?render_id={render_id}",
                data={"font": "leelawadee-ui"},
            )
        self.assertEqual(response.status_code, 507)
        self.assertEqual(response.get_json()["code"], "render_capacity_insufficient")
        self.assertEqual(app.video_renders[render_id]["status"], "failed")
        self.assertTrue(Path(source).exists())

    def test_render_with_unknown_dimensions_fails_closed(self):
        source = os.path.join(self.temp.name, "unknown-size.mp4")
        Path(source).write_bytes(b"video")
        self.seed_video_task(source_path=source)
        render_id = self.reserve_render()
        media = {"has_video": True, "duration_seconds": 10, "width": 0, "height": 0}
        with patch("app.probe_media", return_value=media):
            response = self.client.post(
                f"/api/video-render/video-task?render_id={render_id}", data={"font": "leelawadee-ui"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "render_capacity_unknown")

    def test_render_emergency_floor_terminates_and_cleans_partials(self):
        source = os.path.join(self.uploads, "emergency.mp4")
        Path(source).write_bytes(b"video")
        self.seed_video_task()
        render_id = "emergency-render"
        subtitle = os.path.join(self.outputs, f"{render_id}.render.srt")
        temporary = os.path.join(self.outputs, f"{render_id}.tmp.mp4")
        Path(subtitle).write_text("1\n00:00:00,000 --> 00:00:01,000\nText\n", encoding="utf-8")
        Path(temporary).write_bytes(b"partial")
        estimate = app.estimate_render_capacity(len(b"video"), 1, 640, 480)
        app.video_renders[render_id] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "video_filename": None, "_cancel_event": threading.Event(), "_process": None,
            "_subtitle_path": subtitle, "_capacity_estimate": estimate, "_private_paths": [],
        }
        process = Mock(stdout=["out_time_ms=1000"])
        critical = app.RenderCapacityError("render_disk_critical", "critical disk floor")
        with patch("app.ensure_render_capacity"), patch("app.ensure_render_emergency_capacity", side_effect=critical), patch("app.subprocess.Popen", return_value=process), patch("app.runtime_environment", return_value={}), patch("app.terminate_process_tree") as terminate:
            app.video_render_worker(
                render_id, "video-task", source, True, "leelawadee-ui", 36,
            )
        self.assertEqual(app.video_renders[render_id]["status"], "failed")
        self.assertIn("critical disk floor", app.video_renders[render_id]["error"])
        terminate.assert_called_once_with(process)
        self.assertFalse(Path(source).exists())
        self.assertFalse(Path(subtitle).exists())
        self.assertFalse(Path(temporary).exists())

    def test_runtime_policy_extracts_only_approved_members(self):
        archive_path = os.path.join(self.temp.name, "cuda.zip")
        destination = os.path.join(self.temp.name, "runtime-stage")
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("bin/whisper-cli.exe", b"exe")
            archive.writestr("bin/ggml-cuda.dll", b"cuda")
            archive.writestr("bin/cublas64_11.dll", b"cuda dependency")
            archive.writestr("bin/ggml-cpu-cascadelake.dll", b"avx512")
            archive.writestr("bin/bench.exe", b"tool")
            archive.writestr("README.txt", b"docs")
            archive.writestr("parakeet.dll", b"unused")
        app.extract_runtime_archive(archive_path, "cuda", destination)
        self.assertEqual(
            {path.name for path in Path(destination).iterdir()},
            {"whisper-cli.exe", "ggml-cuda.dll", "cublas64_11.dll"},
        )

    def test_runtime_policy_rejects_unsafe_duplicate_and_incomplete_archives(self):
        unsafe = os.path.join(self.temp.name, "unsafe.zip")
        with zipfile.ZipFile(unsafe, "w") as archive:
            archive.writestr("../whisper-cli.exe", b"exe")
            archive.writestr("ggml-cuda.dll", b"cuda")
        with self.assertRaises(RuntimePolicyError):
            app.extract_runtime_archive(unsafe, "cuda", os.path.join(self.temp.name, "unsafe-stage"))

        duplicate = os.path.join(self.temp.name, "duplicate.zip")
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr("a/whisper-cli.exe", b"one")
            archive.writestr("b/WHISPER-CLI.EXE", b"two")
            archive.writestr("ggml-cuda.dll", b"cuda")
        with self.assertRaisesRegex(RuntimePolicyError, "duplicate"):
            app.extract_runtime_archive(duplicate, "cuda", os.path.join(self.temp.name, "duplicate-stage"))

        incomplete = os.path.join(self.temp.name, "incomplete.zip")
        with zipfile.ZipFile(incomplete, "w") as archive:
            archive.writestr("whisper-cli.exe", b"exe")
            archive.writestr("ggml.dll", b"cpu only")
        with self.assertRaisesRegex(RuntimePolicyError, "accelerator DLL"):
            app.extract_runtime_archive(incomplete, "vulkan", os.path.join(self.temp.name, "incomplete-stage"))

    def test_runtime_policy_rejects_arbitrary_dll_without_promotion(self):
        for backend, marker in (("cuda", "ggml-cuda.dll"), ("vulkan", "ggml-vulkan.dll")):
            with self.subTest(backend=backend, layout="archive"):
                archive_path = os.path.join(self.temp.name, f"{backend}-unreviewed.zip")
                destination = os.path.join(self.temp.name, f"{backend}-unreviewed-stage")
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr("bin/whisper-cli.exe", b"exe")
                    archive.writestr(f"bin/{marker}", b"accelerator")
                    archive.writestr("bin/unreviewed-plugin.dll", b"unreviewed")
                with self.assertRaisesRegex(RuntimePolicyError, "outside GPU runtime policy"):
                    app.extract_runtime_archive(archive_path, backend, destination)
                self.assertEqual(list(Path(destination).iterdir()), [])

            with self.subTest(backend=backend, layout="staged"):
                stage = Path(self.temp.name, f"{backend}-unreviewed-tree")
                stage.mkdir()
                Path(stage, "whisper-cli.exe").write_bytes(b"exe")
                Path(stage, marker).write_bytes(b"accelerator")
                Path(stage, "unreviewed-plugin.dll").write_bytes(b"unreviewed")
                with self.assertRaisesRegex(RuntimePolicyError, "outside GPU runtime policy"):
                    app.validate_staged_runtime(stage, backend)
    def test_runtime_policy_rejects_forbidden_staged_tree(self):
        stage = Path(self.temp.name, "invalid-stage")
        stage.mkdir()
        Path(stage, "whisper-cli.exe").write_bytes(b"exe")
        Path(stage, "ggml-vulkan.dll").write_bytes(b"vulkan")
        Path(stage, "ggml-cpu-icelake.dll").write_bytes(b"avx512")
        with self.assertRaisesRegex(RuntimePolicyError, "AVX-512"):
            app.validate_staged_runtime(stage, "vulkan")
        executable_stage = Path(self.temp.name, "invalid-executable-stage")
        executable_stage.mkdir()
        Path(executable_stage, "whisper-cli.exe").write_bytes(b"exe")
        Path(executable_stage, "ggml-vulkan.dll").write_bytes(b"vulkan")
        Path(executable_stage, "other.exe").write_bytes(b"tool")
        with self.assertRaisesRegex(RuntimePolicyError, "Unexpected executable"):
            app.validate_staged_runtime(executable_stage, "vulkan")

    def test_portable_build_is_staged_and_recoverable(self):
        build = Path(app.SOURCE_DIR, "build_portable.ps1").read_text(encoding="utf-8")
        helpers = Path(app.SOURCE_DIR, "build_portable_helpers.ps1").read_text(encoding="utf-8")
        recovery_test = Path(app.SOURCE_DIR, "scratch", "test_build_portable_recovery.ps1").read_text(encoding="utf-8")
        self.assertIn("build\\portable-staging", build)
        self.assertIn("build\\portable-recovery", build)
        self.assertIn("--distpath $stageDist", build)
        self.assertIn("Copy-PortableUserData", build)
        self.assertIn("Assert-PortableArchiveExcludesUserData", build)
        self.assertIn("Restore-PortableUserData", build)
        self.assertIn("Invoke-PortablePromotion", build)
        self.assertLess(build.index("Compress-Archive"), build.index("Restore-PortableUserData"))
        self.assertNotIn("$preservedData", build)
        self.assertNotIn("Remove-Item", build)
        self.assertIn("Assert-PathWithin", helpers)
        self.assertIn("failed-promotion", helpers)
        self.assertIn("after-old-dist-move", helpers)
        self.assertIn("FAULT_POINTS=8", recovery_test)

    def test_expired_and_mismatched_reservations_are_rejected(self):
        task_id = self.reserve_transcription()
        app.transcriptions[task_id]["_reservation_expires_at"] = 0
        expired = self.client.post(f"/api/transcribe?task_id={task_id}", data={})
        self.assertEqual(expired.status_code, 409)
        self.assertEqual(expired.get_json()["error"]["code"], "reservation_expired")

        self.seed_video_task()
        render_id = self.reserve_render()
        mismatch = self.client.post(f"/api/video-render/other-task?render_id={render_id}", data={})
        self.assertEqual(mismatch.status_code, 409)
        self.assertEqual(mismatch.get_json()["error"]["code"], "reservation_mismatch")

    def test_process_registration_closes_cancel_race(self):
        event = threading.Event()
        event.set()
        job = {"status": "cancelling", "_cancel_event": event, "_process": None}
        process = Mock()
        with patch("app.terminate_process_tree") as terminate:
            with self.assertRaises(app.JobCancelled):
                app.set_active_process(job, process)
        terminate.assert_called_once_with(process)

if __name__ == "__main__":
    unittest.main()












