"""Routes for model management, media selection, and transcription jobs."""

import os
import threading
import time
import uuid

from flask import jsonify, render_template, request
from werkzeug.exceptions import BadRequest, ClientDisconnected


def register_transcription_routes(app, services):
    @app.route("/")
    def index():
        return render_template("index.html", base_url=getattr(services, "URL_PREFIX", ""))

    @app.route("/api/compute/backends")
    def get_compute_backends():
        return jsonify(services.compute_backend_status())

    @app.route("/api/compute/backends/<backend>/download", methods=["POST"])
    def start_gpu_download(backend):
        if backend not in services.GPU_BACKENDS_INFO:
            return jsonify(error="ไม่รองรับ GPU backend ที่เลือก"), 400
        info = services.GPU_BACKENDS_INFO[backend]
        if not info.get("url"):
            return jsonify(error="ยังไม่ได้เปิดให้ดาวน์โหลด GPU runtime รุ่นนี้"), 503
        with services.state_lock:
            existing = services.gpu_downloads.get(backend)
            if existing and existing["status"] in {"downloading", "cancelling"}:
                return jsonify(status=existing["status"])
            services.gpu_downloads[backend] = {
                "status": "downloading", "progress": 0, "bytes_downloaded": 0,
                "total_bytes": 0, "error": None, "_cancel_event": threading.Event(), "_response": None,
            }
        threading.Thread(target=services.download_gpu_worker, args=(backend,), daemon=True).start()
        return jsonify(status="downloading", backend=backend)

    @app.route("/api/compute/backends/<backend>/probe", methods=["POST"])
    def probe_gpu_download(backend):
        if backend not in services.GPU_BACKENDS_INFO:
            return jsonify(error="ไม่รองรับ GPU backend ที่เลือก"), 400
        available, error = services.probe_gpu_backend(backend)
        return jsonify(backend=backend, available=available, error=error)
    @app.route("/api/compute/backends/<backend>/cancel", methods=["POST"])
    def cancel_gpu_download(backend):
        if backend not in services.GPU_BACKENDS_INFO:
            return jsonify(error="ไม่รองรับ GPU backend ที่เลือก"), 400
        with services.state_lock:
            job = services.gpu_downloads.get(backend)
            if not job:
                return jsonify(status="not_downloaded")
            if job["status"] not in {"downloading", "cancelling"}:
                return jsonify(status=job["status"])
            job["status"] = "cancelling"
            job["_cancel_event"].set()
            response = job.get("_response")
        if response is not None:
            response.close()
        return jsonify(status="cancelling")

    @app.route("/api/compute/backends/download-status")
    def get_gpu_download_status():
        with services.state_lock:
            return jsonify({name: services.public_state(job) for name, job in services.gpu_downloads.items()})
    @app.route("/api/models")
    def get_models():
        result = []
        with services.state_lock:
            for filename, info in services.MODELS_INFO.items():
                model_job = services.downloads.get(filename)
                exists = os.path.exists(os.path.join(services.MODEL_FOLDER, filename))
                status, progress = ("downloaded", 100) if exists else ("not_downloaded", 0)
                if not exists and model_job:
                    status, progress = model_job["status"], model_job["progress"]
                result.append({**info, "filename": filename, "status": status, "progress": progress})
        return jsonify(result)

    @app.route("/api/models/download", methods=["POST"])
    def start_model_download():
        filename = (request.json or {}).get("filename")
        if filename not in services.MODELS_INFO:
            return jsonify(error="Invalid model filename"), 400
        if os.path.exists(os.path.join(services.MODEL_FOLDER, filename)):
            return jsonify(message="Model already downloaded", status="downloaded")
        with services.state_lock:
            existing = services.downloads.get(filename)
            if existing and existing["status"] in {"downloading", "cancelling"}:
                return jsonify(message="Download already in progress", status=existing["status"])
            services.downloads[filename] = {
                "status": "downloading", "progress": 0, "bytes_downloaded": 0,
                "total_bytes": 0, "error": None, "_cancel_event": threading.Event(), "_response": None,
            }
        threading.Thread(target=services.download_model_worker, args=(filename,), daemon=True).start()
        return jsonify(message="Download started", status="downloading")

    @app.route("/api/models/<filename>/cancel", methods=["POST"])
    def cancel_model_download(filename):
        if filename not in services.MODELS_INFO:
            return jsonify(error="Invalid model filename"), 400
        with services.state_lock:
            job = services.downloads.get(filename)
            if not job:
                return jsonify(status="not_downloaded", message="No active download")
            if job["status"] not in {"downloading", "cancelling"}:
                return jsonify(status=job["status"], message="Download is not active")
            job["status"] = "cancelling"
            job["_cancel_event"].set()
            response = job.get("_response")
        if response is not None:
            response.close()
        return jsonify(status="cancelling", message="Cancellation requested")

    @app.route("/api/models/download-status")
    def get_download_status():
        with services.state_lock:
            return jsonify({name: services.public_state(job) for name, job in services.downloads.items()})

    @app.route("/api/local-selection", methods=["POST"])
    def choose_local_media():
        try:
            selected_path = services.select_local_media_file()
        except RuntimeError as error:
            return jsonify(error=str(error)), 500
        if not selected_path:
            return jsonify(cancelled=True)
        try:
            metadata = services.probe_media(selected_path)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        selection_id = str(uuid.uuid4())
        with services.state_lock:
            services.cleanup_expired_selections()
            services.local_selections[selection_id] = {
                "path": selected_path,
                "expires_at": time.monotonic() + services.LOCAL_SELECTION_TTL_SECONDS,
            }
        return jsonify(
            selection_id=selection_id, name=os.path.basename(selected_path),
            size=os.path.getsize(selected_path), preflight=metadata,
        )

    @app.route("/api/local-selection/<selection_id>/preflight")
    def preflight_local_selection(selection_id):
        with services.state_lock:
            services.cleanup_expired_selections()
            selection = services.local_selections.get(selection_id)
        if not selection:
            return jsonify(error="การเลือกไฟล์หมดอายุแล้ว กรุณาเลือกใหม่"), 404
        try:
            return jsonify(services.probe_media(selection["path"]))
        except ValueError as error:
            return jsonify(error=str(error)), 400

    @app.route("/api/transcribe/reservations", methods=["POST"])
    def reserve_transcription():
        with services.state_lock:
            services.expire_reservations(services.transcriptions)
            services.expire_reservations(services.video_renders)
            if services.has_active_transcription() or services.has_active_render():
                return jsonify(error="Another processing job is active.", code="transcription_busy"), 409
            task_id = services.reserve_job(services.transcriptions, services.state_lock, "transcription")
        return jsonify(task_id=task_id, status="reserved"), 201

    @app.route("/api/transcribe", methods=["POST"])
    def start_transcription():
        task_id = request.args.get("task_id") or request.headers.get("X-FreeSRT-Job-ID")
        try:
            job = services.claim_reservation(
                services.transcriptions, services.state_lock, task_id, "transcription",
            )
        except services.ReservationError as error:
            return jsonify(error={"code": error.code, "message": str(error)}), error.http_status

        input_path = None
        owns_input = False

        def fail_prestart(message, code="preflight_failed", http_status=400):
            if owns_input:
                services.safe_remove(input_path)
            safe_message = services.redact_diagnostic(message, job)
            services.finish_prestart(job, services.state_lock, "failed", safe_message)
            return jsonify(error=safe_message, code=code, task_id=task_id), http_status

        def cancel_disconnected_request():
            if owns_input:
                services.safe_remove(input_path)
            services.finish_prestart(job, services.state_lock, "cancelled")
            return jsonify(task_id=task_id, status="cancelled"), 409

        try:
            services.check_cancelled(job)
            with services.state_lock:
                services.expire_reservations(services.video_renders)
                if services.has_active_transcription(exclude_id=task_id) or services.has_active_render():
                    return fail_prestart("Another processing job is active.", "transcription_busy", 409)
            try:
                services.ensure_upload_capacity(request.content_length)
            except ValueError as error:
                return fail_prestart(error, "upload_too_large", 413)

            form, files = services.read_request_form_files(request)
            selection_id = form.get("selection_id")
            uploaded_file = files.get("file")
            if bool(selection_id) == bool(uploaded_file and uploaded_file.filename):
                return fail_prestart("Choose exactly one input source.", "invalid_source")

            display_name = None
            with services.state_lock:
                services.cleanup_expired_selections()
                if selection_id:
                    selection = services.local_selections.pop(selection_id, None)
                    if not selection:
                        return fail_prestart("Local file selection expired.", "selection_expired", 404)
                    input_path = selection["path"]
                    display_name = os.path.basename(input_path)
                elif uploaded_file and uploaded_file.filename:
                    extension = services.safe_media_extension(uploaded_file.filename)
                    input_path = os.path.join(services.UPLOAD_FOLDER, f"{task_id}_orig{extension}")
                    owns_input = True
                    display_name = uploaded_file.filename
                else:
                    return fail_prestart("No input file was selected.", "invalid_source")
                job.update(
                    _source_path=input_path if not owns_input else None,
                    _owns_input=owns_input,
                    _private_paths=[input_path] if not owns_input else [],
                )

            if owns_input:
                try:
                    services.save_upload_cancellable(
                        uploaded_file, input_path, job, services.JobCancelled,
                    )
                except OSError as error:
                    return fail_prestart(error, "upload_failed", 507)

            services.check_cancelled(job)
            services.set_prestart_status(job, services.state_lock, "preflighting")
            media_info = services.probe_media(input_path, job=job)
            services.runtime_preflight(job=job)
            services.check_cancelled(job)

            model = form.get("model", "ggml-large-v3-turbo.bin")
            language = form.get("language", "auto")
            try:
                compute_mode = services.normalize_compute_mode(form.get("compute_mode", "cpu"))
                gpu_backend = services.normalize_gpu_backend(form.get("gpu_backend", "auto"))
            except ValueError as error:
                return fail_prestart(error, "invalid_compute")
            if model not in services.MODELS_INFO or not os.path.exists(os.path.join(services.MODEL_FOLDER, model)):
                return fail_prestart("The selected model is not ready.", "model_not_ready")
            try:
                threads = int(form.get("threads") or os.cpu_count() or 4)
            except ValueError:
                return fail_prestart("CPU threads must be a number.", "invalid_threads")
            threads = max(1, min(64, threads))
            selected_backend = services.resolve_compute_backend(compute_mode, gpu_backend)
            with services.state_lock:
                services.check_cancelled(job)
                job.update(
                    status="queued", progress=0, eta_seconds=None, logs=["Job queued"],
                    input_name=display_name, has_video=media_info["has_video"],
                    _duration_seconds=media_info["duration_seconds"], compute_mode=compute_mode,
                    gpu_backend=gpu_backend, compute_backend=selected_backend,
                    used_cpu_fallback=False, fallback_reason=None, _compute_backend=selected_backend,
                )
            threading.Thread(
                target=services.transcription_worker,
                args=(task_id, input_path, model, language, threads, owns_input), daemon=True,
            ).start()
            return jsonify(task_id=task_id, status="queued")
        except services.JobCancelled:
            if owns_input:
                services.safe_remove(input_path)
            services.finish_prestart(job, services.state_lock, "cancelled")
            return jsonify(task_id=task_id, status="cancelled"), 409
        except ClientDisconnected:
            return cancel_disconnected_request()
        except BadRequest as error:
            return fail_prestart(error, "request_parse_failed", 400)
        except (ValueError, RuntimeError) as error:
            return fail_prestart(error)
    @app.route("/api/transcribe/<task_id>/cancel", methods=["POST"])
    def cancel_transcription(task_id):
        job, process = services.request_cancel(
            services.transcriptions, services.state_lock, task_id,
        )
        if not job:
            return jsonify(error="Task not found"), 404
        services.terminate_process_tree(process)
        status = job.get("status")
        message = "Cancellation requested" if status == "cancelling" else "Task is not active"
        return jsonify(status=status, message=message)
    @app.route("/api/transcribe/status/<task_id>")
    def get_transcription_status(task_id):
        with services.state_lock:
            job = services.transcriptions.get(task_id)
            return (jsonify(services.public_state(job)), 200) if job else (jsonify(error="Task not found"), 404)

    @app.route("/api/diagnostics")
    def diagnostics():
        return jsonify(
            frozen=bool(getattr(services.sys, "frozen", False)), app_dir=services.APP_DIR, resource_dir=services.RESOURCE_DIR,
            ffmpeg={"path": services.FFMPEG_EXE, "exists": os.path.isfile(services.FFMPEG_EXE)},
            ffprobe={"path": services.FFPROBE_EXE, "exists": os.path.isfile(services.FFPROBE_EXE)},
            whisper={"path": services.WHISPER_EXE, "exists": os.path.isfile(services.WHISPER_EXE)},
            compute=services.compute_backend_status(),
            model_dir={"path": services.MODEL_FOLDER, "exists": os.path.isdir(services.MODEL_FOLDER)},
            writable={
                "uploads": os.access(services.UPLOAD_FOLDER, os.W_OK),
                "outputs": os.access(services.OUTPUT_FOLDER, os.W_OK),
                "data": os.access(services.DATA_FOLDER, os.W_OK),
            },
        )
