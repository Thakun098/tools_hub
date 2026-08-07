"""Redact user-owned private values from diagnostics and public job state."""

from __future__ import annotations

import os
import re


REDACTION = "[private source]"


def register_private_value(job, value):
    if not value:
        return
    normalized = os.path.abspath(os.fspath(value))
    values = job.setdefault("_private_paths", [])
    if not any(os.path.normcase(existing) == os.path.normcase(normalized) for existing in values):
        values.append(normalized)


def _variants(value):
    original = os.fspath(value)
    normalized = os.path.normpath(original)
    candidates = {
        original,
        normalized,
        original.replace("\\", "/"),
        normalized.replace("\\", "/"),
        original.replace("\\", "\\\\"),
        normalized.replace("\\", "\\\\"),
    }
    return sorted((candidate for candidate in candidates if candidate), key=len, reverse=True)


def redact_diagnostic(value, job=None):
    text = str(value)
    private_values = (job or {}).get("_private_paths", [])
    for private in private_values:
        for variant in _variants(private):
            text = re.sub(re.escape(variant), REDACTION, text, flags=re.IGNORECASE)
    return text


def redact_public_value(value, job):
    if isinstance(value, str):
        return redact_diagnostic(value, job)
    if isinstance(value, dict):
        return {key: redact_public_value(item, job) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_public_value(item, job) for item in value]
    if isinstance(value, tuple):
        return [redact_public_value(item, job) for item in value]
    return value


def append_public_log(job, value):
    job.setdefault("logs", []).append(redact_diagnostic(value, job))