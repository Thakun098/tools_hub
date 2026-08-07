"""Allow-listed subtitle appearance values shared by preview and rendering."""

import os
import re


DEFAULT_SUBTITLE_FONT = "leelawadee-ui"
SUBTITLE_FONTS = {
    "leelawadee-ui": {"label": "Leelawadee UI", "family": "Leelawadee UI", "css_stack": "'Leelawadee UI', Tahoma, sans-serif"},
    "tahoma": {"label": "Tahoma", "family": "Tahoma", "css_stack": "Tahoma, sans-serif"},
    "segoe-ui": {"label": "Segoe UI", "family": "Segoe UI", "css_stack": "'Segoe UI', sans-serif"},
    "arial": {"label": "Arial", "family": "Arial", "css_stack": "Arial, sans-serif"},
}


def normalize_subtitle_style(font_key, font_size, outline_width=2, background=True, shadow_depth=0, position="bottom", margin_v=48):
    if font_key not in SUBTITLE_FONTS:
        raise ValueError("ไม่รองรับฟอนต์คำบรรยายที่เลือก")
    try:
        font_size = round(float(font_size), 2)
        outline_width = round(float(outline_width), 2)
        shadow_depth = round(float(shadow_depth), 2)
        margin_v = round(float(margin_v), 2)
    except (TypeError, ValueError) as error:
        raise ValueError("ค่ารูปแบบคำบรรยายต้องเป็นตัวเลข") from error
    if not 18 <= font_size <= 72:
        raise ValueError("ขนาดตัวอักษรต้องอยู่ระหว่าง 18 ถึง 72")
    if not 0 <= outline_width <= 6:
        raise ValueError("ความหนาเส้นขอบต้องอยู่ระหว่าง 0 ถึง 6")
    if not 0 <= shadow_depth <= 6:
        raise ValueError("ความลึกเงาต้องอยู่ระหว่าง 0 ถึง 6")
    if position not in {"top", "middle", "bottom"}:
        raise ValueError("ตำแหน่งคำบรรยายไม่ถูกต้อง")
    if not 0 <= margin_v <= 240:
        raise ValueError("ระยะห่างจากขอบต้องอยู่ระหว่าง 0 ถึง 240")
    if isinstance(background, str):
        background = background.strip().lower() in {"1", "true", "yes", "on"}
    else:
        background = bool(background)
    return {
        "font_key": font_key, "font_size": font_size, "outline_width": outline_width,
        "background": background, "shadow_depth": shadow_depth,
        "position": position, "margin_v": margin_v,
    }


def format_ass_number(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def build_subtitle_filter(srt_filename, font_key, font_size, outline_width=2, background=True, shadow_depth=0, position="bottom", margin_v=48):
    if os.path.basename(srt_filename) != srt_filename or not re.fullmatch(r"[A-Za-z0-9._-]+", srt_filename):
        raise ValueError("Invalid subtitle filename")
    options = normalize_subtitle_style(font_key, font_size, outline_width, background, shadow_depth, position, margin_v)
    font = SUBTITLE_FONTS[font_key]
    alignment = {"bottom": 2, "middle": 10, "top": 6}[options["position"]]
    border_style = 3 if options["background"] else 1
    back_colour = "&H4D000000" if options["background"] else "&H00000000"
    style = (
        f"FontName={font['family']},FontSize={format_ass_number(options['font_size'])},PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,BackColour={back_colour},BorderStyle={border_style},"
        f"Outline={format_ass_number(options['outline_width'])},Shadow={format_ass_number(options['shadow_depth'])},"
        f"Alignment={alignment},MarginV={format_ass_number(options['margin_v'])}"
    )
    return f"subtitles=filename='{srt_filename}':force_style='{style}'"
