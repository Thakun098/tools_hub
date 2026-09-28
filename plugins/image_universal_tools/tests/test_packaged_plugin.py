import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
import zipfile

from PIL import Image


def _json_request(url, method="GET", payload=None, headers=None, timeout=5):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = dict(headers or {})
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.load(response)


class PackagedImagePluginTest(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("TOOLSHUB_EXE") and os.environ.get("IMAGE_PLUGIN_ARCHIVE"),
        "set TOOLSHUB_EXE and IMAGE_PLUGIN_ARCHIVE to run packaged plugin smoke",
    )
    def test_packaged_hub_loads_plugin_and_converts_image(self):
        source_exe = Path(os.environ["TOOLSHUB_EXE"]).resolve()
        archive_path = Path(os.environ["IMAGE_PLUGIN_ARCHIVE"]).resolve()
        self.assertTrue(source_exe.is_file())
        self.assertTrue(archive_path.is_file())
        with tempfile.TemporaryDirectory(prefix="toolshub-packaged-image-") as temp:
            app_dir = Path(temp) / "ToolsHub"
            shutil.copytree(source_exe.parent, app_dir)
            plugins_dir = app_dir / "plugins"
            if plugins_dir.exists():
                shutil.rmtree(plugins_dir)
            plugins_dir.mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(plugins_dir)
            executable = app_dir / source_exe.name
            engine = plugins_dir / "image_universal_tools" / "runtime" / "image-engine.exe"
            self.assertTrue(engine.is_file())

            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            environment = os.environ.copy()
            environment.update(PORT=str(port), TOOLS_HUB_NO_BROWSER="1", PYTHONUTF8="1")
            process = subprocess.Popen(
                [str(executable)],
                cwd=app_dir,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                origin = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 35
                health = None
                while time.monotonic() < deadline:
                    try:
                        _, health = _json_request(origin + "/api/hub/health", timeout=1)
                        break
                    except Exception:
                        if process.poll() is not None:
                            self.fail(f"ToolsHub exited early with code {process.returncode}")
                        time.sleep(.2)
                self.assertIsNotNone(health, "packaged Hub did not become healthy")
                self.assertIn("image_universal_tools", health["loaded_plugin_ids"])
                for path in ("/image-tools/", "/image-tools/api/models", "/image-tools/static/app.js"):
                    with urllib.request.urlopen(origin + path, timeout=5) as response:
                        self.assertEqual(response.status, 200, path)

                image_bytes = io.BytesIO()
                Image.new("RGBA", (30, 20), (30, 90, 210, 130)).save(image_bytes, format="PNG")
                boundary = "----ToolsHub" + uuid.uuid4().hex
                body = (
                    f"--{boundary}\r\n"
                    'Content-Disposition: form-data; name="files"; filename="packaged.png"\r\n'
                    "Content-Type: image/png\r\n\r\n"
                ).encode("ascii") + image_bytes.getvalue() + f"\r\n--{boundary}--\r\n".encode("ascii")
                upload_request = urllib.request.Request(
                    origin + "/image-tools/api/uploads",
                    data=body,
                    method="POST",
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                )
                with urllib.request.urlopen(upload_request, timeout=10) as response:
                    upload_id = json.load(response)["uploads"][0]["id"]
                _, created = _json_request(
                    origin + "/image-tools/api/jobs",
                    method="POST",
                    payload={
                        "upload_ids": [upload_id],
                        "operation": "convert",
                        "settings": {"format": "WEBP", "quality": 80, "background": "transparent"},
                    },
                )
                self.assertEqual(len(created["jobs"]), 1)
                deadline = time.monotonic() + 90
                job = None
                while time.monotonic() < deadline:
                    _, jobs = _json_request(origin + "/image-tools/api/jobs")
                    job = jobs["jobs"][0]
                    if job["status"] in {"completed", "failed", "cancelled"}:
                        break
                    time.sleep(.25)
                self.assertEqual(job["status"], "completed", job.get("error"))
                with urllib.request.urlopen(origin + job["output_url"], timeout=10) as response:
                    output = response.read()
                with Image.open(io.BytesIO(output)) as converted:
                    self.assertEqual(converted.format, "WEBP")
                    self.assertEqual(converted.size, (30, 20))
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                unlock_probe = engine.with_suffix(".unlock-probe")
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    try:
                        os.replace(engine, unlock_probe)
                        os.replace(unlock_probe, engine)
                        break
                    except PermissionError:
                        time.sleep(.1)
                else:
                    self.fail("persistent image engine did not exit with packaged Hub")


if __name__ == "__main__":
    unittest.main()
