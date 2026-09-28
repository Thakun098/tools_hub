"""Runtime paths and sidecar command selection."""

from dataclasses import dataclass
import json
import os
import shlex
import sys


@dataclass(frozen=True)
class RuntimeConfig:
    resource_root: str
    data_root: str
    model_root: str
    runtime_root: str
    upload_root: str
    output_root: str
    url_prefix: str


class EngineRunner:
    def __init__(self, resource_root):
        self.resource_root = os.path.abspath(resource_root)

    def command(self):
        override = os.environ.get("IMAGE_UNIVERSAL_ENGINE_COMMAND")
        if override:
            return shlex.split(override, posix=False)
        executable = os.path.join(self.resource_root, "runtime", "image-engine.exe")
        if os.path.isfile(executable):
            return [executable]
        local_python = os.path.join(self.resource_root, "venv", "Scripts", "python.exe")
        if os.path.isfile(local_python):
            return [local_python, "-m", "image_engine.cli"]
        return [sys.executable, "-m", "image_engine.cli"]

    def build_process_args(self, request_path):
        return [*self.command(), "process", "--request-file", request_path]

    def service_process_args(self):
        return [*self.command(), "serve"]

    def probe(self):
        return [*self.command(), "probe"]
