"""Conservative, output-volume-aware capacity policy for video rendering."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import shutil


MIB = 1024 * 1024
DEFAULT_SAFETY_MARGIN_BYTES = 512 * MIB
DEFAULT_EMERGENCY_FLOOR_BYTES = 256 * MIB
SOURCE_SIZE_MULTIPLIER = 2.0


class RenderCapacityError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RenderCapacityEstimate:
    source_bytes: int
    duration_seconds: float
    width: int
    height: int
    estimated_output_bytes: int
    safety_margin_bytes: int
    emergency_floor_bytes: int
    required_free_bytes: int
    method: str

    def public_state(self):
        return asdict(self)


def _video_bitrate_bits_per_second(width, height):
    pixels = width * height
    if pixels <= 0:
        raise RenderCapacityError("render_capacity_unknown", "Video dimensions are unavailable.")
    if pixels <= 1280 * 720:
        return 5_000_000
    if pixels <= 1920 * 1080:
        return 9_000_000
    if pixels <= 3840 * 2160:
        return 20_000_000
    return 32_000_000


def estimate_render_capacity(
    source_bytes,
    duration_seconds,
    width,
    height,
    safety_margin_bytes=DEFAULT_SAFETY_MARGIN_BYTES,
    emergency_floor_bytes=DEFAULT_EMERGENCY_FLOOR_BYTES,
):
    try:
        source_bytes = int(source_bytes)
        duration_seconds = float(duration_seconds)
        width = int(width)
        height = int(height)
    except (TypeError, ValueError) as error:
        raise RenderCapacityError("render_capacity_unknown", "Video size metadata is invalid.") from error
    if source_bytes < 0 or duration_seconds <= 0 or width <= 0 or height <= 0:
        raise RenderCapacityError("render_capacity_unknown", "Video duration and dimensions are required.")
    video_bitrate = _video_bitrate_bits_per_second(width, height)
    audio_bitrate = 192_000
    duration_estimate = int(duration_seconds * (video_bitrate + audio_bitrate) / 8 * 1.20)
    source_estimate = int(source_bytes * SOURCE_SIZE_MULTIPLIER)
    estimated_output = max(duration_estimate, source_estimate, MIB)
    required_free = estimated_output + int(safety_margin_bytes) + int(emergency_floor_bytes)
    return RenderCapacityEstimate(
        source_bytes=source_bytes,
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        estimated_output_bytes=estimated_output,
        safety_margin_bytes=int(safety_margin_bytes),
        emergency_floor_bytes=int(emergency_floor_bytes),
        required_free_bytes=required_free,
        method="max(source_x2,resolution_duration_bitrate)+margin+emergency_floor",
    )


def ensure_render_capacity(output_folder, estimate, disk_usage=None):
    usage = disk_usage or shutil.disk_usage
    free_bytes = int(usage(output_folder).free)
    if free_bytes < estimate.required_free_bytes:
        raise RenderCapacityError(
            "render_capacity_insufficient",
            "Not enough free space on the output drive for a safe video render.",
        )
    return free_bytes


def ensure_render_emergency_capacity(
    output_folder,
    emergency_floor_bytes=DEFAULT_EMERGENCY_FLOOR_BYTES,
    disk_usage=None,
):
    usage = disk_usage or shutil.disk_usage
    free_bytes = int(usage(output_folder).free)
    if free_bytes < int(emergency_floor_bytes):
        raise RenderCapacityError(
            "render_disk_critical",
            "Video rendering stopped because output-drive free space reached the safety floor.",
        )
    return free_bytes