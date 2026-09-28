"""Static-image conversion with metadata stripping."""

from PIL import Image, ImageColor

from .image_policy import load_image
from .output_paths import AtomicOutput


SUPPORTED_OUTPUTS = {"PNG", "JPEG", "WEBP", "BMP", "TIFF"}
ALPHA_OUTPUTS = {"PNG", "WEBP", "TIFF"}


def _flatten(image, color):
    rgba = image.convert("RGBA")
    background = ImageColor.getrgb(color)
    canvas = Image.new("RGB", rgba.size, background)
    canvas.paste(rgba, mask=rgba.getchannel("A"))
    return canvas


def convert_image(input_path, output_path, settings, max_pixels):
    output_format = str(settings.get("format", "PNG")).upper()
    if output_format == "JPG":
        output_format = "JPEG"
    if output_format not in SUPPORTED_OUTPUTS:
        raise ValueError("format ปลายทางไม่รองรับ")
    quality = int(settings.get("quality", 90))
    if not 1 <= quality <= 100:
        raise ValueError("quality ต้องอยู่ระหว่าง 1 ถึง 100")
    background = settings.get("background", "transparent")

    loaded = load_image(input_path, max_pixels=max_pixels)
    image = loaded.image
    if output_format not in ALPHA_OUTPUTS:
        if background == "transparent":
            raise ValueError(f"{output_format} ไม่รองรับ transparency")
        image = _flatten(image, background)
    elif background != "transparent" and loaded.had_alpha:
        image = _flatten(image, background)
    elif loaded.had_alpha:
        image = image.convert("RGBA")
    else:
        image = image.convert("RGB")

    save_options = {}
    if output_format == "PNG":
        save_options.update(optimize=True, compress_level=6)
    elif output_format == "JPEG":
        save_options.update(quality=quality, optimize=True, progressive=True, subsampling=0)
    elif output_format == "WEBP":
        save_options.update(quality=quality, method=5)
    elif output_format == "TIFF":
        save_options.update(compression="tiff_deflate")

    with AtomicOutput(output_path) as temporary_path:
        image.save(temporary_path, format=output_format, **save_options)
    return {
        "format": output_format,
        "width": image.width,
        "height": image.height,
        "source_format": loaded.source_format,
        "metadata_removed": True,
    }
