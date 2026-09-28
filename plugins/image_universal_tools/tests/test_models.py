import hashlib
from pathlib import Path
import sys
import tempfile
import time
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from toolshub_image_universal_tools.model_downloads import ModelDownloadManager


class FakeCatalog:
    def __init__(self, model):
        self.model = model

    def get(self, model_id):
        if model_id != self.model["id"]:
            raise KeyError(model_id)
        return dict(self.model)

    def all(self):
        return [dict(self.model)]

    @staticmethod
    def model_path(root, model):
        return str(Path(root) / model["file_name"])


class ModelDownloadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.onnx"
        self.source.write_bytes(b"model-payload" * 1000)
        payload = self.source.read_bytes()
        self.model = {
            "id": "test-model",
            "file_name": "installed.onnx",
            "size_bytes": len(payload),
            "checksum": f"md5:{hashlib.md5(payload).hexdigest()}",
            "url": self.source.as_uri(),
            "tier": "Test",
        }
        self.destination = self.root / "models"
        self.destination.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def _wait(self, manager):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = manager.list_models()[0]
            if state["download_status"] != "downloading":
                return state
            time.sleep(.02)
        self.fail("model download did not finish")

    def test_atomic_verified_download(self):
        manager = ModelDownloadManager(FakeCatalog(self.model), str(self.destination))
        manager.start("test-model")
        state = self._wait(manager)
        self.assertEqual(state["download_status"], "completed")
        self.assertTrue(state["installed"])
        self.assertTrue(manager.verify("test-model"))
        self.assertFalse((self.destination / "installed.onnx.part").exists())

    def test_bad_checksum_never_installs(self):
        model = dict(self.model, checksum="md5:" + "0" * 32)
        manager = ModelDownloadManager(FakeCatalog(model), str(self.destination))
        manager.start("test-model")
        state = self._wait(manager)
        self.assertEqual(state["download_status"], "failed")
        self.assertFalse(state["installed"])
        self.assertFalse((self.destination / "installed.onnx").exists())


if __name__ == "__main__":
    unittest.main()
