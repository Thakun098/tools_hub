"""Sequential, failure-isolated image processing queue."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid

from .validation import (
    ValidationError,
    output_extension,
    validate_conversion_settings,
    validate_operation,
)
from .engine_service import EngineService


TERMINAL_STATES = {"completed", "failed", "cancelled"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safe_stem(filename):
    stem = Path(os.path.basename(filename)).stem.strip()
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", stem).strip(" .-")
    return (stem[:80] or "image")


@dataclass
class Job:
    id: str
    upload: object
    operation: str
    settings: dict
    output_path: str
    status: str = "queued"
    progress: int = 0
    error: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    process: object = field(default=None, repr=False)

    def public(self):
        return {
            "id": self.id,
            "filename": self.upload.original_name,
            "operation": self.operation,
            "settings": dict(self.settings),
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "output_name": os.path.basename(self.output_path) if self.status == "completed" else None,
            "output_ready": self.status == "completed" and os.path.isfile(self.output_path),
        }


class JobManager:
    def __init__(self, upload_store, model_catalog, model_downloads, model_root, output_root, runtime_root, engine_runner):
        self.upload_store = upload_store
        self.model_catalog = model_catalog
        self.model_downloads = model_downloads
        self.model_root = os.path.abspath(model_root)
        self.output_root = os.path.abspath(output_root)
        self.runtime_root = os.path.abspath(runtime_root)
        self.engine_runner = engine_runner
        self.engine_service = EngineService(engine_runner)
        self._jobs = {}
        self._order = []
        self._queue = []
        self._reserved_outputs = set()
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._worker_thread = None
        self._stopping = False

    def _start_worker_locked(self):
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._worker_thread = threading.Thread(
            target=self._worker,
            name="image-universal-tools-queue",
            daemon=True,
        )
        self._worker_thread.start()

    def _model_for_job(self, model_id):
        try:
            model = self.model_catalog.get(model_id)
        except KeyError as error:
            raise ValidationError("ไม่พบโมเดลที่เลือก") from error
        if not self.model_downloads.is_verified(model["id"]):
            raise ValidationError("กรุณาดาวน์โหลดโมเดลที่เลือกก่อนเริ่มงาน")
        return model

    def _reserve_output_locked(self, filename, operation, settings):
        postfix = "-no-bg" if operation == "remove_background" else "-converted"
        extension = output_extension(operation, settings)
        base = _safe_stem(filename) + postfix
        index = 1
        while True:
            suffix = "" if index == 1 else f"-{index}"
            candidate = os.path.abspath(os.path.join(self.output_root, base + suffix + extension))
            if os.path.commonpath([candidate, self.output_root]) != self.output_root:
                raise ValidationError("ชื่อ output ไม่ปลอดภัย")
            normalized = os.path.normcase(candidate)
            if normalized not in self._reserved_outputs and not os.path.exists(candidate):
                self._reserved_outputs.add(normalized)
                return candidate
            index += 1

    def submit_many(self, upload_ids, operation, settings):
        operation = validate_operation(operation)
        if not isinstance(upload_ids, list) or not upload_ids or len(upload_ids) > 100:
            raise ValidationError("เลือกไฟล์ 1 ถึง 100 ไฟล์ต่อครั้ง")
        if len(set(upload_ids)) != len(upload_ids):
            raise ValidationError("มี upload id ซ้ำกัน")
        normalized_settings = dict(settings or {})
        model = None
        if operation == "convert":
            normalized_settings = validate_conversion_settings(normalized_settings)
        else:
            model = self._model_for_job(normalized_settings.get("model_id", "balanced-isnet"))
            normalized_settings = {
                "model_id": model["id"],
                "model_name": model["engine_name"],
            }

        claimed = []
        try:
            for upload_id in upload_ids:
                claimed.append(self.upload_store.claim(upload_id))
        except Exception:
            for record in claimed:
                self.upload_store.restore(record)
            raise

        jobs = []
        reserved_paths = []
        try:
            with self._condition:
                for record in claimed:
                    output_path = self._reserve_output_locked(record.original_name, operation, normalized_settings)
                    reserved_paths.append(output_path)
                    job = Job(
                        id=uuid.uuid4().hex,
                        upload=record,
                        operation=operation,
                        settings=dict(normalized_settings),
                        output_path=output_path,
                    )
                    jobs.append(job)
                self._start_worker_locked()
                for job in jobs:
                    self._jobs[job.id] = job
                    self._order.append(job.id)
                    self._queue.append(job.id)
                self._condition.notify_all()
        except Exception:
            with self._condition:
                job_ids = {job.id for job in jobs}
                for job_id in job_ids:
                    self._jobs.pop(job_id, None)
                self._order = [job_id for job_id in self._order if job_id not in job_ids]
                self._queue = [job_id for job_id in self._queue if job_id not in job_ids]
                for output_path in reserved_paths:
                    self._reserved_outputs.discard(os.path.normcase(os.path.abspath(output_path)))
            for record in claimed:
                self.upload_store.restore(record)
            raise
        return [job.public() for job in jobs]

    def list(self):
        with self._lock:
            return [self._jobs[job_id].public() for job_id in reversed(self._order)]

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job

    def cancel(self, job_id):
        with self._condition:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status in TERMINAL_STATES:
                return job.public()
            job.cancel_event.set()
            if job.status == "queued":
                job.status = "cancelled"
                job.progress = 0
                job.updated_at = _now()
                if job_id in self._queue:
                    self._queue.remove(job_id)
                self.upload_store.delete(job.upload)
                self._release_output(job.output_path)
            process = job.process
        if process is not None and process.poll() is None:
            process.terminate()
        return job.public()

    def cancel_all(self):
        with self._lock:
            ids = [job_id for job_id in self._order if self._jobs[job_id].status not in TERMINAL_STATES]
        return [self.cancel(job_id) for job_id in ids]

    def _release_output(self, path):
        with self._lock:
            self._reserved_outputs.discard(os.path.normcase(os.path.abspath(path)))

    def _set(self, job, **values):
        with self._lock:
            for key, value in values.items():
                setattr(job, key, value)
            job.updated_at = _now()

    def _worker(self):
        while True:
            with self._condition:
                while not self._queue and not self._stopping:
                    self._condition.wait()
                if self._stopping:
                    return
                job_id = self._queue.pop(0)
                job = self._jobs[job_id]
                if job.status == "cancelled":
                    continue
                self._set(job, status="running", progress=15)
            self._run_job(job)

    def _run_job(self, job):
        request_path = os.path.join(self.runtime_root, f"job-{job.id}.json")
        request_payload = {
            "input_path": job.upload.path,
            "output_path": job.output_path,
            "operation": job.operation,
            "settings": job.settings,
            "model_root": self.model_root,
            "max_pixels": 50_000_000,
        }
        if job.operation == "remove_background":
            model = self.model_catalog.get(job.settings["model_id"])
            request_payload["model"] = {
                "file_name": model["file_name"],
                "size_bytes": model["size_bytes"],
                "checksum": model["checksum"],
            }
        try:
            with open(request_path, "x", encoding="utf-8") as target:
                json.dump(request_payload, target, ensure_ascii=False)
            response = self.engine_service.process_request(
                request_path,
                job.cancel_event,
                lambda process: self._set(job, process=process, progress=35),
            )
            if not response.get("ok") or not os.path.isfile(job.output_path):
                raise RuntimeError(str(response.get("error") or "ไม่พบไฟล์ output"))
            self._set(job, status="completed", progress=100, error=None, process=None)
        except InterruptedError as error:
            self._set(job, status="cancelled", progress=0, error=str(error), process=None)
            try:
                os.remove(job.output_path)
            except FileNotFoundError:
                pass
        except Exception as error:
            self._set(job, status="failed", progress=0, error=str(error), process=None)
            try:
                os.remove(job.output_path)
            except FileNotFoundError:
                pass
        finally:
            self.upload_store.delete(job.upload)
            self._release_output(job.output_path)
            try:
                os.remove(request_path)
            except FileNotFoundError:
                pass

    def shutdown(self):
        self.cancel_all()
        self.engine_service.stop()
        with self._condition:
            self._stopping = True
            self._condition.notify_all()
