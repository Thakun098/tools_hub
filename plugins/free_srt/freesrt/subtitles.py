"""SRT parsing, normalization, and atomic persistence."""

import os
import re


SRT_TIMESTAMP_RE = re.compile(
    r"^(\d{2,}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+"
    r"(\d{2,}):(\d{2}):(\d{2}),(\d{3})$"
)


def timestamp_to_ms(parts):
    hours, minutes, seconds, millis = (int(value) for value in parts)
    if minutes > 59 or seconds > 59:
        raise ValueError("Invalid SRT timestamp")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def ms_to_timestamp(value):
    value = max(0, int(value))
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def parse_srt(content, repair_invalid_ranges=False):
    blocks = re.split(r"\n\s*\n", content.replace("\r\n", "\n").strip()) if content.strip() else []
    cues = []
    for position, block in enumerate(blocks, 1):
        lines = block.splitlines()
        if len(lines) < 3:
            raise ValueError(f"Subtitle block {position} is incomplete")
        try:
            int(lines[0].strip())
        except ValueError as error:
            raise ValueError(f"Subtitle block {position} has an invalid number") from error
        match = SRT_TIMESTAMP_RE.match(lines[1].strip())
        if not match:
            raise ValueError(f"Subtitle block {position} has an invalid timestamp")
        start_ms = timestamp_to_ms(match.groups()[:4])
        end_ms = timestamp_to_ms(match.groups()[4:])
        if end_ms <= start_ms:
            if repair_invalid_ranges:
                end_ms = start_ms + 500
            else:
                raise ValueError(f"Subtitle block {position} must end after it starts")
        text = "\n".join(lines[2:]).strip()
        if not text:
            raise ValueError(f"Subtitle block {position} has no text")
        cues.append({"start_ms": start_ms, "end_ms": end_ms, "text": text})
    if not cues:
        raise ValueError("SRT content is empty")
    return cues


def serialize_srt(cues):
    return "\n\n".join(
        f"{index}\n{ms_to_timestamp(cue['start_ms'])} --> {ms_to_timestamp(cue['end_ms'])}\n{cue['text'].strip()}"
        for index, cue in enumerate(cues, 1)
    ) + "\n"


def serialize_txt(cues):
    """Return plain text with one normalized subtitle cue per line."""
    return "\n".join(
        " ".join(cue["text"].split())
        for cue in cues
    ) + "\n"


def write_srt_atomic(path, content):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as destination:
        destination.write(content)
    os.replace(temporary, path)

