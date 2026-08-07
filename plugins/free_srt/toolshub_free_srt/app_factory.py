"""Factory helpers used by the Tools Hub adapter."""

import importlib.util
import os
import sys
import uuid


def build_runtime_config(**values):
    resource_root = os.path.abspath(values["resource_root"])
    return {
        "APP_DIR": os.path.abspath(values["data_root"]),
        "RESOURCE_DIR": resource_root,
        "DATA_FOLDER": os.path.abspath(values["data_root"]),
        "MODEL_FOLDER": os.path.abspath(values["model_root"]),
        "GPU_RUNTIME_FOLDER": os.path.abspath(values["runtime_root"]),
        "UPLOAD_FOLDER": os.path.abspath(values["upload_root"]),
        "OUTPUT_FOLDER": os.path.abspath(values["output_root"]),
        "URL_PREFIX": str(values.get("url_prefix", "")).rstrip("/"),
    }


def create_runtime_context(config):
    """Load app.py under an isolated module name and inject its path config."""
    plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(plugin_dir, "app.py")
    module_name = f"toolshub_plugins.free_srt.runtime_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, app_path)
    module = importlib.util.module_from_spec(spec)
    module._FREESRT_BOOT_CONFIG = dict(config)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def register_routes(target, runtime):
    runtime.register_routes(target, runtime, runtime.URL_PREFIX)
