"""Flask routes for Image Universal Tools."""

import os
from urllib.parse import urlsplit

from flask import jsonify, render_template, request, send_file

from .validation import ValidationError


def _json_error(message, status=400):
    return jsonify(error=str(message)), status


def attach_routes(blueprint, runtime):
    @blueprint.after_request
    def add_browser_security_headers(response):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    @blueprint.before_request
    def protect_local_mutations():
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return None
        if request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            return _json_error("ไม่อนุญาตคำขอจากเว็บไซต์ภายนอก", 403)
        origin = request.headers.get("Origin")
        if not origin:
            return None
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != request.host.lower():
            return _json_error("ไม่อนุญาตคำขอจากเว็บไซต์ภายนอก", 403)
        return None

    @blueprint.get("/")
    def index():
        return render_template("image_universal_tools/index.html", base_url=runtime.config.url_prefix)

    @blueprint.get("/api/capabilities")
    def capabilities():
        return jsonify(
            formats=["PNG", "JPEG", "WebP", "BMP", "TIFF"],
            max_pixels=50_000_000,
            max_upload_bytes=200 * 1024 * 1024,
            cpu_only=True,
            metadata_removed=True,
            tiff_first_frame_only=True,
            output_root=runtime.config.output_root,
        )

    @blueprint.post("/api/uploads")
    def upload_files():
        files = request.files.getlist("files")
        if not files or len(files) > 100:
            return _json_error("เลือกไฟล์ 1 ถึง 100 ไฟล์ต่อครั้ง")
        records = []
        try:
            for storage in files:
                records.append(runtime.uploads.save(storage))
        except (ValidationError, OSError) as error:
            for record in records:
                runtime.uploads.delete(record)
            return _json_error(error)
        return jsonify(
            uploads=[
                {
                    "id": record.id,
                    "filename": record.original_name,
                    "size": record.size,
                }
                for record in records
            ]
        ), 201

    @blueprint.get("/api/jobs")
    def list_jobs():
        jobs = runtime.jobs.list()
        for job in jobs:
            if job["output_ready"]:
                job["output_url"] = f"{runtime.config.url_prefix}/api/jobs/{job['id']}/output"
        return jsonify(jobs=jobs)

    @blueprint.post("/api/uploads/discard")
    def discard_uploads():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _json_error("request body ต้องเป็น JSON object")
        try:
            discarded = runtime.uploads.discard(payload.get("upload_ids"))
        except ValidationError as error:
            return _json_error(error)
        return jsonify(discarded=discarded)

    @blueprint.post("/api/jobs")
    def create_jobs():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _json_error("request body ต้องเป็น JSON object")
        try:
            jobs = runtime.jobs.submit_many(
                payload.get("upload_ids"),
                payload.get("operation"),
                payload.get("settings", {}),
            )
        except (ValidationError, OSError) as error:
            return _json_error(error)
        return jsonify(jobs=jobs), 201

    @blueprint.post("/api/jobs/<job_id>/cancel")
    def cancel_job(job_id):
        try:
            return jsonify(job=runtime.jobs.cancel(job_id))
        except KeyError:
            return _json_error("ไม่พบงาน", 404)

    @blueprint.post("/api/jobs/cancel-all")
    def cancel_all_jobs():
        return jsonify(jobs=runtime.jobs.cancel_all())

    @blueprint.get("/api/jobs/<job_id>/output")
    def download_output(job_id):
        try:
            job = runtime.jobs.get(job_id)
        except KeyError:
            return _json_error("ไม่พบงาน", 404)
        if job.status != "completed" or not os.path.isfile(job.output_path):
            return _json_error("output ยังไม่พร้อม", 409)
        return send_file(job.output_path, as_attachment=True, download_name=os.path.basename(job.output_path))

    @blueprint.get("/api/models")
    def list_models():
        return jsonify(models=runtime.models.list_models())

    @blueprint.post("/api/models/<model_id>/download")
    def download_model(model_id):
        try:
            runtime.models.start(model_id)
        except KeyError:
            return _json_error("ไม่พบโมเดล", 404)
        return jsonify(status="accepted"), 202

    @blueprint.post("/api/models/<model_id>/cancel")
    def cancel_model_download(model_id):
        try:
            runtime.models.cancel(model_id)
        except KeyError:
            return _json_error("ไม่พบโมเดล", 404)
        return jsonify(status="cancelling")

    @blueprint.post("/api/models/<model_id>/verify")
    def verify_model(model_id):
        try:
            valid = runtime.models.verify(model_id)
        except KeyError:
            return _json_error("ไม่พบโมเดล", 404)
        return jsonify(valid=valid)

    @blueprint.get("/api/health")
    def health():
        return jsonify(status="ok", engine_command=os.path.basename(runtime.jobs.engine_runner.command()[0]))
