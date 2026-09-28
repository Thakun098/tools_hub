"""Defensive decoding and color normalization policy."""

from dataclasses import dataclass
import warnings

from PIL import Image, ImageCms, ImageOps


ALLOWED_PIL_FORMATS = {"PNG", "JPEG", "WEBP", "BMP", "TIFF"}
DEFAULT_MAX_PIXELS = 50_000_000


class ImagePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedImage:
    image: Image.Image
    source_format: str
    width: int
    height: int
    had_alpha: bool


def _has_alpha(image):
    return image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def _to_srgb(image):
    had_alpha = _has_alpha(image)
    alpha = image.convert("RGBA").getchannel("A") if had_alpha else None
    rgb = image.convert("RGB")
    profile_bytes = image.info.get("icc_profile")
    if profile_bytes:
        try:
            source_profile = ImageCms.ImageCmsProfile(__import__("io").BytesIO(profile_bytes))
            target_profile = ImageCms.createProfile("sRGB")
            rgb = ImageCms.profileToProfile(rgb, source_profile, target_profile, outputMode="RGB")
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass
    if alpha is None:
        return rgb
    result = rgb.convert("RGBA")
    result.putalpha(alpha)
    return result


def load_image(path, max_pixels=DEFAULT_MAX_PIXELS):
    max_pixels = min(int(max_pixels), DEFAULT_MAX_PIXELS)
    if max_pixels <= 0:
        raise ImagePolicyError("pixel limit ไม่ถูกต้อง")
    old_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = max_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                source_format = (source.format or "").upper()
                if source_format not in ALLOWED_PIL_FORMATS:
                    raise ImagePolicyError("ชนิดข้อมูลภายในไฟล์ไม่รองรับ")
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise ImagePolicyError(f"ภาพต้องไม่เกิน {max_pixels:,} pixels")
                if source_format == "TIFF":
                    source.seek(0)
                source.load()
                oriented = ImageOps.exif_transpose(source)
                had_alpha = _has_alpha(oriented)
                normalized = _to_srgb(oriented)
                normalized.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ImagePolicyError(f"ภาพต้องไม่เกิน {max_pixels:,} pixels") from error
    except (OSError, SyntaxError) as error:
        raise ImagePolicyError("เปิดไฟล์ภาพไม่สำเร็จหรือไฟล์เสียหาย") from error
    finally:
        Image.MAX_IMAGE_PIXELS = old_limit
    return LoadedImage(normalized, source_format, width, height, had_alpha)
