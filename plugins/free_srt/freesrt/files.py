"""Small, framework-independent filesystem and serialization helpers."""

import json
import os
import re

from .diagnostics import redact_public_value


def read_json_object(path, default=None):
    fallback = {} if default is None else default
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8-sig") as source:
            value = json.load(source)
        return value if isinstance(value, dict) else fallback
    except (OSError, json.JSONDecodeError):
        return fallback


def atomic_write_json(path, value):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as destination:
        json.dump(value, destination, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def safe_media_extension(filename):
    extension = os.path.splitext(filename or "")[1]
    return extension if re.fullmatch(r"\.[A-Za-z0-9]{1,10}", extension) else ".media"


def public_state(job):
    public = {key: value for key, value in job.items() if not key.startswith("_")}
    return redact_public_value(public, job)
