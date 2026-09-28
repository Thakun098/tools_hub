"""Shared input validation for the Hub adapter."""

import re


ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
OUTPUT_FORMATS = {"PNG", "JPEG", "WEBP", "BMP", "TIFF"}
ALPHA_FORMATS = {"PNG", "WEBP", "TIFF"}
OPERATIONS = {"convert", "remove_background"}
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class ValidationError(ValueError):
    pass


def validate_operation(value):
    if value not in OPERATIONS:
        raise ValidationError("ไม่รู้จักประเภทงาน")
    return value


def validate_conversion_settings(settings):
    output_format = str(settings.get("format", "PNG")).upper()
    if output_format == "JPG":
        output_format = "JPEG"
    if output_format not in OUTPUT_FORMATS:
        raise ValidationError("format ปลายทางไม่รองรับ")
    try:
        quality = int(settings.get("quality", 90))
    except (TypeError, ValueError) as error:
        raise ValidationError("quality ต้องเป็นตัวเลข") from error
    if not 1 <= quality <= 100:
        raise ValidationError("quality ต้องอยู่ระหว่าง 1 ถึง 100")
    background = settings.get("background", "transparent")
    if output_format not in ALPHA_FORMATS:
        if not isinstance(background, str) or not HEX_COLOR_RE.fullmatch(background):
            raise ValidationError(f"{output_format} ไม่รองรับ transparency กรุณาเลือกสีพื้นหลัง")
    elif background != "transparent" and (
        not isinstance(background, str) or not HEX_COLOR_RE.fullmatch(background)
    ):
        raise ValidationError("สีพื้นหลังไม่ถูกต้อง")
    return {
        "format": output_format,
        "quality": quality,
        "background": background,
    }


def output_extension(operation, settings):
    if operation == "remove_background":
        return ".png"
    return {
        "PNG": ".png",
        "JPEG": ".jpg",
        "WEBP": ".webp",
        "BMP": ".bmp",
        "TIFF": ".tiff",
    }[settings["format"]]
