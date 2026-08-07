"""Shared in-memory job reservation and cancellation helpers.

The application intentionally remains single-process. These helpers keep the
existing dictionary registries while making reservation and terminal-state
rules explicit.
"""

from __future__ import annotations

import threading
import time
import uuid


TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
RESERVATION_TTL_SECONDS = 5 * 60


class ReservationError(ValueError):
    """A stable API error raised while claiming a reservation."""

    def __init__(self, code, message, http_status=409):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def expire_reservations(registry, now=None):
    """Mark unclaimed expired reservations cancelled while retaining status."""

    current = time.monotonic() if now is None else now
    for job in registry.values():
        if (
            job.get("status") == "reserved"
            and not job.get("_claimed")
            and float(job.get("_reservation_expires_at") or 0) <= current
        ):
            job["_cancel_event"].set()
            job["_expired"] = True
            job.update(status="cancelled", error=None)


def reserve_job(registry, lock, kind, parent_task_id=None, ttl_seconds=RESERVATION_TTL_SECONDS):
    identifier = str(uuid.uuid4())
    with lock:
        expire_reservations(registry)
        registry[identifier] = {
            "id": identifier,
            "kind": kind,
            "status": "reserved",
            "progress": 0,
            "eta_seconds": None,
            "logs": [],
            "error": None,
            "_kind": kind,
            "_parent_task_id": parent_task_id,
            "_claimed": False,
            "_reservation_expires_at": time.monotonic() + ttl_seconds,
            "_cancel_event": threading.Event(),
            "_process": None,
            "_private_paths": [],
        }
    return identifier


def claim_reservation(registry, lock, identifier, kind, parent_task_id=None, initial_status="uploading"):
    if not identifier:
        raise ReservationError(
            "reservation_required",
            "Create a reservation before starting this job.",
            428,
        )
    with lock:
        expire_reservations(registry)
        job = registry.get(identifier)
        if not job:
            raise ReservationError("reservation_not_found", "Reservation not found.")
        if job.get("_kind") != kind or job.get("_parent_task_id") != parent_task_id:
            raise ReservationError("reservation_mismatch", "Reservation does not match this job.")
        if job.get("_expired"):
            raise ReservationError("reservation_expired", "Reservation expired.")
        if job.get("status") == "cancelled":
            raise ReservationError("reservation_cancelled", "Reservation was cancelled.")
        if job.get("status") != "reserved" or job.get("_claimed"):
            raise ReservationError("reservation_claimed", "Reservation was already claimed.")
        job["_claimed"] = True
        job["status"] = initial_status
        return job


def request_cancel(registry, lock, identifier):
    """Request cancellation and return ``(job, process)``."""

    with lock:
        job = registry.get(identifier)
        if not job:
            return None, None
        if job.get("status") in TERMINAL_STATUSES:
            return job, None
        job["_cancel_event"].set()
        process = job.get("_process")
        if job.get("status") == "reserved":
            job.update(status="cancelled", error=None)
        else:
            job["status"] = "cancelling"
        return job, process


def finish_prestart(job, lock, status, error=None):
    """Finalize request-side work without turning a late cancel into failure."""

    with lock:
        if job.get("status") in TERMINAL_STATUSES:
            return job.get("status")
        if job["_cancel_event"].is_set() or status == "cancelled":
            job.update(status="cancelled", error=None)
        else:
            job.update(status=status, error=error)
        job["_process"] = None
        return job.get("status")


def set_prestart_status(job, lock, status):
    with lock:
        if job.get("status") not in TERMINAL_STATUSES and not job["_cancel_event"].is_set():
            job["status"] = status


def read_request_form_files(http_request):
    """Parse multipart data once so routes can terminalize parser failures."""

    return http_request.form, http_request.files


def save_upload_cancellable(file_storage, destination, job, cancelled_error, chunk_size=1024 * 1024):
    """Copy a Werkzeug upload while checking the job token between chunks."""

    stream = file_storage.stream
    with open(destination, "wb") as output:
        while True:
            if job["_cancel_event"].is_set():
                raise cancelled_error()
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            output.write(chunk)
    if job["_cancel_event"].is_set():
        raise cancelled_error()