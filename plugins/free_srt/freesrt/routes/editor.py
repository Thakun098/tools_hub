"""Routes for preferences, recovery data, glossary, and SRT editing."""

import io
import json
import os
import threading
import uuid

from flask import jsonify, request, send_file, send_from_directory


def register_editor_routes(app, services):
    """Register editor routes using the app module as a compatibility facade."""

    @app.route("/api/preferences", methods=["GET", "PUT"])
    def preferences():
        if request.method == "GET":
            return jsonify(services.read_json_object(services.PREFERENCES_PATH))
        try:
            current = services.read_json_object(services.PREFERENCES_PATH)
            normalized = services.normalize_preferences(request.get_json(silent=True) or {}, current)
            services.atomic_write_json(services.PREFERENCES_PATH, normalized)
            return jsonify(normalized)
        except (ValueError, OSError) as error:
            return jsonify(error=str(error)), 400

    @app.route("/api/editor-backup", methods=["GET", "PUT", "DELETE"])
    def editor_backup():
        if request.method == "GET":
            backup = services.read_json_object(services.EDITOR_BACKUP_PATH)
            if not backup:
                return jsonify(available=False)
            return jsonify(
                available=True, saved_at=backup.get("saved_at"), input_name=backup.get("input_name"),
                cue_count=backup.get("cue_count"), dirty=backup.get("dirty", True),
            )
        if request.method == "DELETE":
            services.safe_remove(services.EDITOR_BACKUP_PATH)
            services.safe_remove(services.EDITOR_BACKUP_PATH + ".tmp")
            return jsonify(available=False)
        try:
            backup = services.normalize_editor_backup(request.get_json(silent=True) or {})
            services.atomic_write_json(services.EDITOR_BACKUP_PATH, backup)
            return jsonify(
                saved_at=backup["saved_at"], input_name=backup["input_name"],
                cue_count=backup["cue_count"],
            )
        except (ValueError, OSError) as error:
            return jsonify(error=str(error)), 400

    @app.route("/api/editor-backup/restore", methods=["POST"])
    def restore_editor_backup():
        backup = services.read_json_object(services.EDITOR_BACKUP_PATH)
        if not backup:
            return jsonify(error="ไม่พบคำบรรยายสำรอง"), 404
        try:
            cues = services.parse_srt(str(backup.get("content", "")))
            content = services.serialize_srt(cues)
            task_id = str(uuid.uuid4())
            current_path = os.path.join(services.OUTPUT_FOLDER, f"{task_id}.srt")
            original_path = os.path.join(services.OUTPUT_FOLDER, f"{task_id}.original.srt")
            services.write_srt_atomic(current_path, content)
            services.write_srt_atomic(original_path, content)
            with services.state_lock:
                services.transcriptions[task_id] = {
                    "status": "completed", "progress": 100, "eta_seconds": 0, "logs": ["กู้คืนคำบรรยายจากข้อมูลสำรองแล้ว"],
                    "srt_filename": f"{task_id}.srt", "error": None, "has_video": False,
                    "input_name": backup.get("input_name") or "Recovered subtitle",
                    "_duration_seconds": max(cues[-1]["end_ms"] / 1000, 0.001),
                    "_source_path": None, "_owns_input": False,
                    "_cancel_event": threading.Event(), "_process": None,
                }
            return jsonify(
                task_id=task_id, has_video=False, input_name=backup.get("input_name"),
                subtitle_style=backup.get("subtitle_style"), dirty=backup.get("dirty", True),
            )
        except (ValueError, OSError) as error:
            return jsonify(error=str(error)), 400

    @app.route("/api/glossary/export")
    def export_glossary():
        payload = json.dumps({"entries": services.read_glossary()}, ensure_ascii=False, indent=2).encode("utf-8")
        return send_file(
            io.BytesIO(payload), as_attachment=True, download_name="free-srt-glossary.json",
            mimetype="application/json",
        )

    @app.route("/api/glossary", methods=["GET", "PUT"])
    def glossary():
        if request.method == "GET":
            return jsonify(entries=services.read_glossary())
        try:
            entries = services.validate_glossary((request.json or {}).get("entries"))
            services.save_glossary(entries)
            return jsonify(entries=entries, message="Glossary saved")
        except (ValueError, OSError) as error:
            return jsonify(error=str(error)), 400

    @app.route("/api/subtitles/<task_id>", methods=["GET", "PUT"])
    def subtitles(task_id):
        with services.state_lock:
            job = services.transcriptions.get(task_id)
            if not job or job["status"] != "completed" or not job["srt_filename"]:
                return jsonify(error="Completed task not found"), 404
            current_path = os.path.join(services.OUTPUT_FOLDER, job["srt_filename"])
            original_path = os.path.join(services.OUTPUT_FOLDER, f"{task_id}.original.srt")
        if request.method == "GET":
            try:
                with open(current_path, "r", encoding="utf-8-sig") as current_file:
                    current = current_file.read()
                with open(original_path if os.path.exists(original_path) else current_path, "r", encoding="utf-8-sig") as original_file:
                    original = original_file.read()
                return jsonify(content=current, original_content=original)
            except OSError as error:
                return jsonify(error=str(error)), 500
        try:
            content = (request.json or {}).get("content", "")
            normalized = services.serialize_srt(services.parse_srt(content))
            if not os.path.exists(original_path):
                with open(current_path, "r", encoding="utf-8-sig") as current_file:
                    original_content = services.serialize_srt(services.parse_srt(current_file.read()))
                services.write_srt_atomic(original_path, original_content)
            services.write_srt_atomic(current_path, normalized)
            return jsonify(content=normalized, message="Subtitles saved")
        except (ValueError, OSError) as error:
            services.safe_remove(current_path + ".tmp")
            return jsonify(error=str(error)), 400

    @app.route("/api/subtitles/<task_id>/reset", methods=["POST"])
    def reset_subtitles(task_id):
        with services.state_lock:
            job = services.transcriptions.get(task_id)
            if not job or job["status"] != "completed":
                return jsonify(error="Completed task not found"), 404
            current_path = os.path.join(services.OUTPUT_FOLDER, job["srt_filename"])
            original_path = os.path.join(services.OUTPUT_FOLDER, f"{task_id}.original.srt")
        if not os.path.exists(original_path):
            return jsonify(error="Original subtitles not found"), 404
        try:
            with open(original_path, "r", encoding="utf-8-sig") as original_file:
                normalized = services.serialize_srt(services.parse_srt(original_file.read()))
            services.write_srt_atomic(current_path, normalized)
            return jsonify(content=normalized, message="Original restored")
        except ValueError as error:
            services.safe_remove(current_path + ".tmp")
            return jsonify(error=str(error)), 400
        except OSError as error:
            services.safe_remove(current_path + ".tmp")
            return jsonify(error=str(error)), 500

    @app.route("/api/download/<task_id>")
    def download_srt(task_id):
        with services.state_lock:
            job = services.transcriptions.get(task_id)
            if not job or job["status"] != "completed" or not job["srt_filename"]:
                return jsonify(error="Result file not found or transcription not completed"), 404
            filename = job["srt_filename"]
        if not os.path.exists(os.path.join(services.OUTPUT_FOLDER, filename)):
            return jsonify(error="SRT file does not exist on disk"), 404
        return send_from_directory(services.OUTPUT_FOLDER, filename, as_attachment=True, download_name="transcription.srt")

    @app.route("/api/download/<task_id>/txt")
    def download_txt(task_id):
        with services.state_lock:
            job = services.transcriptions.get(task_id)
            if not job or job["status"] != "completed" or not job["srt_filename"]:
                return jsonify(error="Result file not found or transcription not completed"), 404
            path = os.path.join(services.OUTPUT_FOLDER, job["srt_filename"])
        if not os.path.exists(path):
            return jsonify(error="SRT file does not exist on disk"), 404
        try:
            with open(path, "r", encoding="utf-8-sig") as subtitle_file:
                cues = services.parse_srt(subtitle_file.read())
            payload = services.serialize_txt(cues).encode("utf-8-sig")
            return send_file(
                io.BytesIO(payload),
                as_attachment=True,
                download_name="transcription.txt",
                mimetype="text/plain; charset=utf-8",
            )
        except (ValueError, OSError) as error:
            return jsonify(error=f"Failed to export TXT: {error}"), 500

    @app.route("/api/preview/<task_id>")
    def preview_srt(task_id):
        with services.state_lock:
            job = services.transcriptions.get(task_id)
            if not job or job["status"] != "completed" or not job["srt_filename"]:
                return jsonify(error="Result file not found or transcription not completed"), 404
            path = os.path.join(services.OUTPUT_FOLDER, job["srt_filename"])
        if not os.path.exists(path):
            return jsonify(error="SRT file does not exist on disk"), 404
        try:
            with open(path, "r", encoding="utf-8") as subtitle_file:
                return jsonify(content=subtitle_file.read())
        except OSError as error:
            return jsonify(error=f"Failed to read SRT: {error}"), 500
