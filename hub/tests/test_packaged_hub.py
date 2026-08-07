import json
import os
import socket
import subprocess
import time
import unittest
import urllib.request
import zipfile


class PackagedHubSmokeTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("TOOLSHUB_EXE"), "set TOOLSHUB_EXE to run packaged smoke")
    def test_packaged_hub_core_or_external_plugin(self):
        executable = os.path.abspath(os.environ["TOOLSHUB_EXE"])
        self.assertTrue(os.path.isfile(executable))
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        environment = os.environ.copy()
        plugin_archive = os.environ.get("TOOLSHUB_PLUGIN_ARCHIVE")
        if plugin_archive:
            plugins_dir = os.path.join(os.path.dirname(executable), "plugins")
            os.makedirs(plugins_dir, exist_ok=True)
            with zipfile.ZipFile(plugin_archive) as archive:
                archive.extractall(plugins_dir)

        environment.update(PORT=str(port), TOOLS_HUB_NO_BROWSER="1")
        process = subprocess.Popen(
            [executable],
            env=environment,
            cwd=os.path.dirname(executable),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.monotonic() + 30
            health = None
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/hub/health", timeout=1
                    ) as response:
                        health = json.load(response)
                    break
                except Exception:
                    if process.poll() is not None:
                        self.fail(f"ToolsHub exited early with code {process.returncode}")
                    time.sleep(0.2)
            self.assertIsNotNone(health, "ToolsHub did not become healthy")
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                self.assertEqual(response.status, 200)
            if plugin_archive:
                self.assertIn("free_srt", health["loaded_plugin_ids"])
                for path in ("/srt/", "/srt/api/models", "/srt/static/app.js"):
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
                        self.assertEqual(response.status, 200, path)
                external = os.path.join(os.path.dirname(executable), "plugins", "free_srt", "bin")
                self.assertTrue(os.path.isfile(os.path.join(external, "Release", "whisper-cli.exe")))
                self.assertTrue(os.path.isfile(os.path.join(external, "ffmpeg.exe")))
                self.assertTrue(os.path.isfile(os.path.join(external, "ffprobe.exe")))
            else:
                self.assertEqual(health["loaded_plugin_ids"], [])
                internal = os.path.join(os.path.dirname(executable), "_internal", "plugins", "free_srt")
                self.assertFalse(os.path.exists(internal))
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
