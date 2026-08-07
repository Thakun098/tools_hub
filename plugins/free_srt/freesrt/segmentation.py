"""Deterministic subtitle segmentation and line wrapping.

The module deliberately has no Flask, filesystem, or subprocess dependencies.  It
is the single source of truth for generated subtitles and editor-side tests.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
import unicodedata


SENTENCE_PUNCTUATION = frozenset(".!?。！？…")
PHRASE_PUNCTUATION = frozenset(",;:，；：、—–-…")
_VARIATION_SELECTORS = frozenset(chr(value) for value in range(0xFE00, 0xFE10))
_EMOJI_MODIFIERS = frozenset(chr(value) for value in range(0x1F3FB, 0x1F400))
_SPACING_MARKS = frozenset("\u0e33\u0eb3")


@dataclass(frozen=True)
class SegmentationConfig:
    """Default subtitle policy.

    Character limits are display-oriented grapheme units.  The ten-word value is
    intentionally only a diagnostic hint; it is never a hard constraint because
    Thai and other scripts do not reliably separate words with whitespace.
    """

    max_line_chars: int = 35
    max_lines: int = 2
    max_cue_chars: int = 70
    target_min_duration_ms: int = 2_000
    target_max_duration_ms: int = 5_000
    hard_max_duration_ms: int = 7_000
    min_duration_ms: int = 833
    max_chars_per_second: float = 20.0
    soft_word_limit: int = 10


@dataclass(frozen=True)
class SegmentationResult:
    cues: list[dict]
    issues: list[dict]


def normalize_text(text: str) -> str:
    """Collapse presentation whitespace without changing non-whitespace text."""

    return re.sub(r"\s+", " ", str(text or "").replace("\r\n", "\n")).strip()


def grapheme_units(text: str) -> list[str]:
    """Return a dependency-free approximation of Unicode grapheme clusters."""

    clusters: list[str] = []
    for char in text:
        if not clusters:
            clusters.append(char)
            continue
        previous = clusters[-1]
        category = unicodedata.category(char)
        if (
            category.startswith("M")
            or char in _VARIATION_SELECTORS
            or char in _EMOJI_MODIFIERS
            or char in _SPACING_MARKS
            or char == "\u200d"
            or previous.endswith("\u200d")
        ):
            clusters[-1] += char
        else:
            clusters.append(char)
    return clusters


def display_length(text: str) -> int:
    """Count non-whitespace grapheme units for cue reading limits."""

    return sum(not unit.isspace() for unit in grapheme_units(text))


def whitespace_word_count(text: str) -> int:
    return len(re.findall(r"\S+", normalize_text(text)))


def _visual_length(units: list[str]) -> int:
    return len(units)


def _boundary_score(units: list[str], index: int) -> int:
    """Score a boundary immediately before ``index``."""

    if index <= 0 or index > len(units):
        return -1
    previous = units[index - 1]
    if previous and previous[-1] in SENTENCE_PUNCTUATION:
        return 6
    if previous and previous[-1] in PHRASE_PUNCTUATION:
        return 5
    if previous.isspace():
        return 4
    return 1


def _choose_boundary(units: list[str], start: int, end: int, target: int) -> int:
    """Choose a natural boundary close to target, falling back to graphemes."""

    candidates = list(range(start + 1, end + 1))
    if not candidates:
        return start
    target = max(start + 1, min(target, end))
    search_radius = max(1, (end - start) // 4)
    nearby = [index for index in candidates if abs(index - target) <= search_radius]
    natural = [index for index in nearby if _boundary_score(units, index) > 1]
    pool = natural or nearby or candidates
    return max(
        pool,
        key=lambda index: (
            _boundary_score(units, index),
            -abs(index - target),
            index,
        ),
    )


def _trim_range(units: list[str], start: int, end: int) -> tuple[int, int]:
    while start < end and units[start].isspace():
        start += 1
    while end > start and units[end - 1].isspace():
        end -= 1
    return start, end


def wrap_text(text: str, config: SegmentationConfig | None = None) -> str:
    """Wrap one cue to at most two display-length lines."""

    config = config or SegmentationConfig()
    normalized = normalize_text(text)
    units = grapheme_units(normalized)
    if not units or config.max_lines <= 1:
        return normalized
    if _visual_length(units) <= config.max_line_chars:
        return normalized

    # The current policy has two lines.  Keep this generic enough to fail safely
    # if a future configuration asks for one line only.
    first_limit = min(config.max_line_chars, len(units) - 1)
    valid_boundaries = []
    for candidate in range(1, len(units)):
        left_start, left_end = _trim_range(units, 0, candidate)
        right_start, right_end = _trim_range(units, candidate, len(units))
        if (
            left_end > left_start
            and right_end > right_start
            and _visual_length(units[left_start:left_end]) <= config.max_line_chars
            and _visual_length(units[right_start:right_end]) <= config.max_line_chars
        ):
            valid_boundaries.append(candidate)
    boundary = (
        max(valid_boundaries, key=lambda index: (_boundary_score(units, index), -abs(index - first_limit), index))
        if valid_boundaries
        else _choose_boundary(units, 0, first_limit, first_limit)
    )
    left_start, left_end = _trim_range(units, 0, boundary)
    right_start, right_end = _trim_range(units, boundary, len(units))
    left = "".join(units[left_start:left_end])
    right = "".join(units[right_start:right_end])
    if not left or not right:
        return normalized

    # If the natural boundary leaves the second line too long, use a grapheme
    # boundary at the hard line limit.  A single very long word is allowed to be
    # cut at this final fallback; a grapheme cluster is never split.
    if _visual_length(grapheme_units(right)) > config.max_line_chars:
        boundary = min(config.max_line_chars, len(units) - 1)
        left_start, left_end = _trim_range(units, 0, boundary)
        right_start, right_end = _trim_range(units, boundary, len(units))
        left = "".join(units[left_start:left_end])
        right = "".join(units[right_start:right_end])
    return f"{left}\n{right}" if left and right else normalized


def _split_ranges(units: list[str], max_units: int) -> list[tuple[int, int]]:
    """Split units into non-empty ranges without exceeding the visual limit."""

    ranges: list[tuple[int, int]] = []
    start = 0
    while start < len(units):
        limit = start
        for index in range(start, len(units)):
            if index - start >= max_units:
                break
            limit = index + 1
        if limit >= len(units):
            end = len(units)
        else:
            end = _choose_boundary(units, start, max(start + 1, limit), limit)
            if end <= start:
                end = limit
        range_start, range_end = _trim_range(units, start, end)
        if range_start < range_end:
            ranges.append((range_start, range_end))
        start = end
        while start < len(units) and units[start].isspace():
            start += 1
    return ranges


def _balanced_ranges(units: list[str], count: int) -> list[tuple[int, int]]:
    """Create balanced text ranges, preferring punctuation/whitespace boundaries."""

    if count <= 1:
        return [(0, len(units))] if units else []
    count = min(count, len(units))
    ranges: list[tuple[int, int]] = []
    start = 0
    for part in range(1, count):
        target = round(len(units) * part / count)
        remaining_parts = count - part
        min_end = start + 1
        max_end = len(units) - remaining_parts
        end = _choose_boundary(units, min_end - 1, max_end, max(min_end, target))
        end = max(min_end, min(end, max_end))
        left_start, left_end = _trim_range(units, start, end)
        if left_start == left_end:
            end = min(max_end, start + 1)
            left_start, left_end = _trim_range(units, start, end)
        if left_start < left_end:
            ranges.append((left_start, left_end))
        start = end
        while start < len(units) and units[start].isspace():
            start += 1
    final_start, final_end = _trim_range(units, start, len(units))
    if final_start < final_end:
        ranges.append((final_start, final_end))
    return ranges


def _allocate_durations(total_ms: int, lengths: list[int], min_ms: int, max_ms: int) -> list[int]:
    if len(lengths) <= 1:
        return [max(1, total_ms)]
    count = len(lengths)
    total_ms = max(count, int(total_ms))
    lower = min_ms if total_ms >= count * min_ms else 1
    durations = [lower] * count
    remaining = total_ms - sum(durations)
    capacities = [max(0, max_ms - lower)] * count

    while remaining > 0:
        active = [index for index, capacity in enumerate(capacities) if capacity > 0]
        if not active:
            break
        weight_total = max(1, sum(lengths[index] for index in active))
        additions = [
            min(capacities[index], int(remaining * lengths[index] / weight_total))
            for index in active
        ]
        allocated = min(remaining, sum(additions))
        if allocated:
            excess = sum(additions) - allocated
            for position in range(len(additions) - 1, -1, -1):
                reduction = min(excess, additions[position])
                additions[position] -= reduction
                excess -= reduction
            for index, addition in zip(active, additions):
                durations[index] += addition
                capacities[index] -= addition
            remaining -= allocated
            continue
        for index in active:
            durations[index] += 1
            capacities[index] -= 1
            remaining -= 1
            if remaining == 0:
                break

    if remaining > 0:
        weight_total = max(1, sum(lengths))
        additions = [int(remaining * length / weight_total) for length in lengths]
        for index, addition in enumerate(additions):
            durations[index] += addition
        missing = remaining - sum(additions)
        for index in range(missing):
            durations[index % count] += 1
    return durations


def _issue(code: str, cue_index: int, message: str) -> dict:
    return {"code": code, "cue_index": cue_index, "message": message}


def segment_cue(cue: dict, config: SegmentationConfig | None = None, cue_index: int = 0) -> tuple[list[dict], list[dict]]:
    config = config or SegmentationConfig()
    source_text = str(cue.get("text", ""))
    text = normalize_text(source_text)
    units = grapheme_units(text)
    start_ms = int(cue.get("start_ms", 0))
    end_ms = int(cue.get("end_ms", start_ms + 1))
    duration_ms = max(1, end_ms - start_ms)
    char_count = display_length(text)
    visual_text = normalize_text(source_text.replace("\r\n", "").replace("\n", ""))
    visual_count = len(grapheme_units(visual_text))
    cue_visual_limit = max(1, min(config.max_cue_chars, config.max_line_chars * config.max_lines))
    issues: list[dict] = []
    if not text or not units:
        return [], [_issue("SEGMENTATION_UNRESOLVED", cue_index, "Cue has no text")]

    reading_speed = char_count / max(0.001, duration_ms / 1000)
    if reading_speed > config.max_chars_per_second:
        issues.append(_issue(
            "READING_SPEED_UNRESOLVED", cue_index, "Cue is too short for the configured reading-speed ceiling"
        ))

    requested = max(
        1,
        math.ceil(visual_count / cue_visual_limit),
        math.ceil(duration_ms / max(1, config.hard_max_duration_ms)),
    )
    non_space_units = max(1, sum(not unit.isspace() for unit in units))
    if requested > non_space_units:
        issues.append(_issue("SEGMENTATION_UNRESOLVED", cue_index, "Not enough text units for every requested fragment"))
        requested = non_space_units

    if requested == 1:
        wrapped = wrap_text(text, config)
        lines = wrapped.splitlines()
        if (
            len(lines) > config.max_lines
            or any(len(grapheme_units(line)) > config.max_line_chars for line in lines)
            or len(units) > cue_visual_limit
        ):
            issues.append(_issue("SEGMENTATION_UNRESOLVED", cue_index, "Cue remains longer than the hard character limit"))
        return [{"start_ms": start_ms, "end_ms": end_ms, "text": wrapped}], issues

    ranges = _balanced_ranges(units, requested)
    if len(ranges) < requested:
        issues.append(_issue("SEGMENTATION_UNRESOLVED", cue_index, "Could not find non-empty grapheme boundaries"))
    fragments = ["".join(units[left:right]).strip() for left, right in ranges]
    fragments = [fragment for fragment in fragments if fragment]
    if not fragments:
        return [], [_issue("SEGMENTATION_UNRESOLVED", cue_index, "No non-empty fragments were produced")]
    if "".join("".join(fragments).split()) != "".join(text.split()):
        issues.append(_issue("SEGMENTATION_TEXT_MISMATCH", cue_index, "Fragment text did not conserve the source text"))

    # A balanced duration split may leave a fragment over the hard character cap.
    # Apply a deterministic hard-cap pass and record the issue if it still cannot
    # satisfy every timing constraint.
    expanded: list[str] = []
    for fragment in fragments:
        fragment_units = grapheme_units(fragment)
        expanded.extend("".join(fragment_units[left:right]).strip() for left, right in _split_ranges(fragment_units, cue_visual_limit))
    fragments = [fragment for fragment in expanded if fragment]
    if duration_ms < len(fragments) * config.min_duration_ms:
        issues.append(_issue("MIN_DURATION_UNRESOLVED", cue_index, "Fragments cannot all reach the minimum duration"))
    lengths = [max(1, display_length(fragment)) for fragment in fragments]
    durations = _allocate_durations(
        duration_ms, lengths, config.min_duration_ms, config.hard_max_duration_ms
    )
    if any(duration > config.hard_max_duration_ms for duration in durations):
        issues.append(_issue(
            "SEGMENTATION_UNRESOLVED", cue_index, "Fragments cannot all stay below the hard duration limit"
        ))
    result: list[dict] = []
    cursor = start_ms
    for index, (fragment, fragment_duration) in enumerate(zip(fragments, durations)):
        fragment_start = cursor
        fragment_end = end_ms if index == len(fragments) - 1 else min(end_ms, cursor + fragment_duration)
        result.append({
            "start_ms": fragment_start,
            "end_ms": max(fragment_start + 1, fragment_end),
            "text": wrap_text(fragment, config),
        })
        cursor = fragment_end
    return result, issues


def segment_cues(cues: list[dict], config: SegmentationConfig | None = None, language: str | None = None) -> SegmentationResult:
    """Segment all cues while preserving order and reporting unresolved issues."""

    config = config or SegmentationConfig()
    result: list[dict] = []
    issues: list[dict] = []
    for index, cue in enumerate(cues):
        fragments, cue_issues = segment_cue(cue, config, index)
        result.extend(fragments)
        issues.extend(cue_issues)
        if language not in {"th", "ja", "zh", "ko"} and whitespace_word_count(cue.get("text", "")) > config.soft_word_limit:
            issues.append(_issue("SOFT_WORD_LIMIT", index, "Cue exceeds the soft whitespace word-count hint"))
    return SegmentationResult(result, issues)


__all__ = [
    "SegmentationConfig",
    "SegmentationResult",
    "display_length",
    "grapheme_units",
    "normalize_text",
    "segment_cue",
    "segment_cues",
    "whitespace_word_count",
    "wrap_text",
]
