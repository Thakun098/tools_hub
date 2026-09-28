"""Request protocol for the isolated engine."""

import os

from .background import remove_background
from .converter import convert_image
from .image_policy import DEFAULT_MAX_PIXELS


def process_request(payload):
    if not isinstance(payload, dict):
        raise ValueError("request ต้องเป็น object")
    input_path = os.path.abspath(str(payload.get("input_path", "")))
    output_path = os.path.abspath(str(payload.get("output_path", "")))
    if not input_path or not os.path.isfile(input_path):
        raise ValueError("ไม่พบไฟล์ input")
    if input_path == output_path:
        raise ValueError("ห้ามเขียนทับไฟล์ต้นฉบับ")
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("settings ต้องเป็น object")
    max_pixels = min(int(payload.get("max_pixels", DEFAULT_MAX_PIXELS)), DEFAULT_MAX_PIXELS)
    operation = payload.get("operation")
    if operation == "convert":
        details = convert_image(input_path, output_path, settings, max_pixels)
    elif operation == "remove_background":
        model_root = os.path.abspath(str(payload.get("model_root", "")))
        if not os.path.isdir(model_root):
            raise ValueError("ไม่พบโฟลเดอร์โมเดล")
        details = remove_background(input_path, output_path, settings, model_root, payload.get("model"), max_pixels)
    else:
        raise ValueError("ไม่รู้จักประเภทงาน")
    return {"ok": True, "details": details}
