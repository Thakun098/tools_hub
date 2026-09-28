import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from hub.plugin_loader import validate_manifest
from hub.plugin_package import build_plugin_archive


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class ManifestAndPackageTest(unittest.TestCase):
    def test_manifest_contract(self):
        manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
        validate_manifest(manifest, str(PLUGIN_ROOT))
        self.assertFalse(manifest["bundled"])
        self.assertEqual(manifest["python_package"], "toolshub_image_universal_tools")

    def test_archive_is_allowlisted_and_has_external_engine(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            engine = temp_path / "image-engine.exe"
            engine.write_bytes(b"engine-stub")
            archive = build_plugin_archive(
                PLUGIN_ROOT,
                temp_path / "dist",
                environ={"IMAGE_ENGINE_SOURCE": str(engine)},
            )
            with zipfile.ZipFile(archive) as source:
                names = set(source.namelist())
            self.assertIn("image_universal_tools/runtime/image-engine.exe", names)
            self.assertIn("image_universal_tools/plugin.json", names)
            self.assertFalse(any("/venv/" in name for name in names))
            self.assertFalse(any("/image_engine/" in name for name in names))


if __name__ == "__main__":
    unittest.main()
