"""Routes for local video preview and subtitle rendering."""

import os
import shutil
import threading
import uuid

from flask import jsonify, request, send_file
from werkzeug.exceptions import BadRequest, ClientDisconnected


def register_video_routes(app, services):
    @app.route("/api/video-options")
    def video_options():
        return jsonify(
            default_font=services.DEFAULT_SUBTITLE_FONT,
            default_font_size=36,
            default_style={"outline_width": 2, "background": True, "shadow_depth": 0, "position": "bottom", "margin_v": 48},
            fonts=[{"key": key, **value} for key, value in services.SUBTITLE_FONTS.items()],
        )

    @app.route("/api/media/<task_id>")
    def preview_source_media(task_id):
        with services.state_lock:
            job = services.transcriptions.get(task_id)
            source_path = job.get("_source_path") if job and job.get("status") == "completed" else None
            has_video = bool(job and job.get("has_video"))
        if not source_path or not has_video or not os.path.isfile(source_path):
            return jsonify(error="ไม่พบวิดีโอต้นฉบับสำหรับพรีวิว"), 404
        return send_file(source_path, conditional=True)

    @app.route("/api/video-render/<task_id>/reservations", methods=["POST"])
    def reserve_video_render(task_id):
        with services.state_lock:
            task = services.transcriptions.get(task_id)
            if not task or task.get("status") != "completed" or not task.get("srt_filename"):
                return jsonify(error="Subtitle job is not ready for rendering."), 404
            if not task.get("has_video"):
                return jsonify(error="This job has no video track."), 400
            services.expire_reservations(services.video_renders)
            if services.has_active_render() or services.has_active_transcription():
                return jsonify(error="Another processing job is active.", code="render_busy"), 409
            render_id = services.reserve_job(
                services.video_renders, services.state_lock, "video_render", parent_task_id=task_id,
            )
        return jsonify(render_id=render_id, status="reserved"), 201

    @app.route("/api/video-render/<task_id>", methods=["POST"])
    def start_video_render(task_id):
        render_id = request.args.get("render_id") or request.headers.get("X-FreeSRT-Job-ID")
        try:
            job = services.claim_reservation(
                services.video_renders, services.state_lock, render_id, "video_render",
                parent_task_id=task_id,
            )
        except services.ReservationError as error:
            return jsonify(error={"code": error.code, "message": str(error)}), error.http_status

        source_path = None
        owns_input = False
        subtitle_path = os.path.join(services.OUTPUT_FOLDER, f"{render_id}.render.srt")

        def fail_prestart(message, code="render_preflight_failed", http_status=400):
            if owns_input:
                services.safe_remove(source_path)
            services.safe_remove(subtitle_path)
            safe_message = services.redact_diagnostic(message, job)
            services.finish_prestart(job, services.state_lock, "failed", safe_message)
            return jsonify(error=safe_message, code=code, render_id=render_id), http_status

        def cancel_disconnected_request():
            if owns_input:
                services.safe_remove(source_path)
            services.safe_remove(subtitle_path)
            services.finish_prestart(job, services.state_lock, "cancelled")
            return jsonify(render_id=render_id, status="cancelled"), 409

        try:
            services.check_cancelled(job)
            with services.state_lock:
                task = services.transcriptions.get(task_id)
                if not task or task.get("status") != "completed" or not task.get("srt_filename"):
                    return fail_prestart("Subtitle job is not ready for rendering.", "task_not_ready", 404)
                if not task.get("has_video"):
                    return fail_prestart("This job has no video track.", "video_required")
                if services.has_active_render(exclude_id=render_id) or services.has_active_transcription():
                    return fail_prestart("Another processing job is active.", "render_busy", 409)
            try:
                services.ensure_upload_capacity(request.content_length)
            except ValueError as error:
                return fail_prestart(error, "upload_too_large", 413)

            form, files = services.read_request_form_files(request)
            font_key = form.get("font", services.DEFAULT_SUBTITLE_FONT)
            try:
                style_options = services.normalize_subtitle_style(
                    font_key, form.get("font_size", 36), form.get("outline_width", 2),
                    form.get("background", "true"), form.get("shadow_depth", 0),
                    form.get("position", "bottom"), form.get("margin_v", 48),
                )
                services.build_subtitle_filter("preview.srt", **style_options)
            except ValueError as error:
                return fail_prestart(error, "invalid_subtitle_style")

            uploaded_file = files.get("file")
            with services.state_lock:
                source_path = task.get("_source_path")
                input_name = task.get("input_name") or "video"
                owns_input = bool(uploaded_file and uploaded_file.filename)
                if owns_input:
                    extension = services.safe_media_extension(uploaded_file.filename)
                    source_path = os.path.join(services.UPLOAD_FOLDER, f"{render_id}_render_input{extension}")
                    input_name = uploaded_file.filename
                if not source_path:
                    return fail_prestart("Select the source video again before rendering.", "source_required")
                job.update(
                    font=font_key, font_size=style_options["font_size"],
                    outline_width=style_options["outline_width"], background=style_options["background"],
                    shadow_depth=style_options["shadow_depth"], position=style_options["position"],
                    margin_v=style_options["margin_v"], _source_path=source_path,
                    _owns_input=owns_input, _subtitle_path=subtitle_path,
                    _download_name=f"{os.path.splitext(os.path.basename(input_name))[0]}_subtitled.mp4",
                    _private_paths=[] if owns_input else [source_path],
                    task_id=task_id, video_filename=None,
                )

            if owns_input:
                services.save_upload_cancellable(
                    uploaded_file, source_path, job, services.JobCancelled,
                )
            services.check_cancelled(job)
            services.set_prestart_status(job, services.state_lock, "preflighting")
            shutil.copyfile(
                os.path.join(services.OUTPUT_FOLDER, task["srt_filename"]), subtitle_path,
            )
            services.check_cancelled(job)
            media_info = services.probe_media(source_path, job=job)
            if not media_info["has_video"]:
                return fail_prestart("The selected file has no video track.", "video_required")
            estimate = services.estimate_render_capacity(
                os.path.getsize(source_path), media_info.get("duration_seconds"),
                media_info.get("width"), media_info.get("height"),
            )
            services.ensure_render_capacity(services.OUTPUT_FOLDER, estimate)
            with services.state_lock:
                job["_capacity_estimate"] = estimate
                job["capacity"] = estimate.public_state()
            services.runtime_preflight(job=job)
            services.check_cancelled(job)
            with services.state_lock:
                job["status"] = "queued"
                job["logs"].append("Video render queued")
            threading.Thread(
                target=services.video_render_worker,
                args=(render_id, task_id, source_path, owns_input), kwargs=style_options, daemon=True,
            ).start()
            return jsonify(render_id=render_id, status="queued")
        except services.JobCancelled:
            if owns_input:
                services.safe_remove(source_path)
            services.safe_remove(subtitle_path)
            services.finish_prestart(job, services.state_lock, "cancelled")
            return jsonify(render_id=render_id, status="cancelled"), 409
        except ClientDisconnected:
            return cancel_disconnected_request()
        except BadRequest as error:
            return fail_prestart(error, "request_parse_failed", 400)
        except services.RenderCapacityError as error:
            http_status = 507 if error.code == "render_capacity_insufficient" else 400
            return fail_prestart(error, error.code, http_status)
        except (OSError, ValueError, RuntimeError) as error:
            return fail_prestart(error)
    @app.route("/api/video-render/status/<render_id>")
    def get_video_render_status(render_id):
        with services.state_lock:
            job = services.video_renders.get(render_id)
            return (jsonify(services.public_state(job)), 200) if job else (jsonify(error="Render job not found"), 404)

    @app.route("/api/video-render/<render_id>/cancel", methods=["POST"])
    def cancel_video_render(render_id):
        job, process = services.request_cancel(
            services.video_renders, services.state_lock, render_id,
        )
        if not job:
            return jsonify(error="Render job not found"), 404
        services.terminate_process_tree(process)
        status = job.get("status")
        message = "Cancellation requested" if status == "cancelling" else "Render job is not active"
        return jsonify(status=status, message=message)
    def get_completed_render(render_id):
        with services.state_lock:
            job = services.video_renders.get(render_id)
            if not job or job.get("status") != "completed" or not job.get("video_filename"):
                return None, None
            path = os.path.join(services.OUTPUT_FOLDER, job["video_filename"])
            return job, path

    @app.route("/api/video-render/<render_id>/preview")
    def preview_rendered_video(render_id):
        job, path = get_completed_render(render_id)
        if not job or not os.path.isfile(path):
            return jsonify(error="ไม่พบวิดีโอผลลัพธ์"), 404
        return send_file(path, conditional=True, mimetype="video/mp4")

    @app.route("/api/video-render/<render_id>/download")
    def download_rendered_video(render_id):
        job, path = get_completed_render(render_id)
        if not job or not os.path.isfile(path):
            return jsonify(error="ไม่พบวิดีโอผลลัพธ์"), 404
        return send_file(path, as_attachment=True, download_name=job["_download_name"], mimetype="video/mp4")
