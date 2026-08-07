"""Validation for persisted UI preferences and crash-recovery data."""

import time

from .subtitle_style import DEFAULT_SUBTITLE_FONT, normalize_subtitle_style
from .compute import normalize_compute_mode, normalize_gpu_backend
from .subtitles import parse_srt, serialize_srt


def normalize_preferences(payload, models_info, existing=None):
    if not isinstance(payload, dict):
        raise ValueError("ข้อมูลการตั้งค่าไม่ถูกต้อง")
    result = dict(existing or {})
    if "compute_mode" in payload:
        result["compute_mode"] = normalize_compute_mode(payload["compute_mode"])
    if "gpu_backend" in payload:
        result["gpu_backend"] = normalize_gpu_backend(payload["gpu_backend"])
    if "gpu_prompt_dismissed" in payload:
        result["gpu_prompt_dismissed"] = bool(payload["gpu_prompt_dismissed"])
    if "model" in payload:
        model = str(payload["model"])
        if model not in models_info:
            raise ValueError("ไม่รองรับโมเดลที่เลือก")
        result["model"] = model
    if "language" in payload:
        language = str(payload["language"])
        if language not in {"auto", "th", "en", "ja", "zh", "ko"}:
            raise ValueError("ไม่รองรับภาษาที่เลือก")
        result["language"] = language
    if "threads" in payload:
        threads = payload["threads"]
        if threads in (None, ""):
            result["threads"] = None
        else:
            try:
                threads = int(threads)
            except (TypeError, ValueError) as error:
                raise ValueError("CPU threads ต้องเป็นตัวเลข") from error
            if not 1 <= threads <= 64:
                raise ValueError("CPU threads ต้องอยู่ระหว่าง 1 ถึง 64")
            result["threads"] = threads
    if "theme" in payload:
        theme = str(payload["theme"])
        if theme not in {"light", "dark"}:
            raise ValueError("ไม่รองรับธีมที่เลือก")
        result["theme"] = theme
    if "subtitle_style" in payload:
        style = payload["subtitle_style"]
        if not isinstance(style, dict):
            raise ValueError("รูปแบบคำบรรยายไม่ถูกต้อง")
        normalized = normalize_subtitle_style(
            style.get("font", DEFAULT_SUBTITLE_FONT), style.get("font_size", 36),
            style.get("outline_width", 2), style.get("background", True),
            style.get("shadow_depth", 0), style.get("position", "bottom"),
            style.get("margin_v", 48),
        )
        normalized["font"] = normalized.pop("font_key")
        result["subtitle_style"] = normalized
    return result


def normalize_editor_backup(payload, models_info, now=None):
    if not isinstance(payload, dict):
        raise ValueError("ข้อมูลสำรองไม่ถูกต้อง")
    content = str(payload.get("content", ""))
    if len(content.encode("utf-8")) > 5 * 1024 * 1024:
        raise ValueError("คำบรรยายมีขนาดใหญ่เกินไปสำหรับการสำรองอัตโนมัติ")
    cues = parse_srt(content)
    backup = {
        "version": 1,
        "saved_at": int(time.time() if now is None else now),
        "input_name": str(payload.get("input_name") or "Subtitle Editor")[:255],
        "content": serialize_srt(cues),
        "cue_count": len(cues),
        "dirty": bool(payload.get("dirty", True)),
    }
    style = payload.get("subtitle_style")
    if isinstance(style, dict):
        backup["subtitle_style"] = normalize_preferences(
            {"subtitle_style": style}, models_info
        ).get("subtitle_style")
    return backup
