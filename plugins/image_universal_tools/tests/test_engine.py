import io
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

from PIL import Image


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from image_engine.converter import convert_image
from image_engine.background import _SESSION_CACHE, _build_offline_session, _verify_local_model
from image_engine.image_policy import ImagePolicyError, load_image


class ConversionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        image = Image.new("RGBA", (48, 32), (200, 30, 60, 128))
        exif = Image.Exif()
        exif[270] = "private description"
        image.save(self.source, exif=exif)

    def tearDown(self):
        _SESSION_CACHE.clear()
        self.temp.cleanup()

    def test_conversion_matrix_and_metadata_removal(self):
        cases = [
            ("PNG", ".png", "transparent"),
            ("JPEG", ".jpg", "#ffffff"),
            ("WEBP", ".webp", "transparent"),
            ("BMP", ".bmp", "#ffffff"),
            ("TIFF", ".tiff", "transparent"),
        ]
        for output_format, suffix, background in cases:
            with self.subTest(output_format=output_format):
                output = self.root / f"result-{output_format}{suffix}"
                details = convert_image(
                    str(self.source),
                    str(output),
                    {"format": output_format, "quality": 88, "background": background},
                    50_000_000,
                )
                self.assertTrue(output.is_file())
                self.assertTrue(details["metadata_removed"])
                with Image.open(output) as converted:
                    self.assertEqual(converted.size, (48, 32))
                    private_metadata = converted.getexif()
                    self.assertNotIn(270, private_metadata)
                    self.assertNotIn(274, private_metadata)

    def test_jpeg_requires_background_color(self):
        with self.assertRaisesRegex(ValueError, "transparency"):
            convert_image(
                str(self.source),
                str(self.root / "result.jpg"),
                {"format": "JPEG", "quality": 90, "background": "transparent"},
                50_000_000,
            )

    def test_existing_output_is_not_overwritten(self):
        output = self.root / "result.png"
        output.write_bytes(b"original")
        with self.assertRaises(FileExistsError):
            convert_image(
                str(self.source),
                str(output),
                {"format": "PNG", "quality": 90, "background": "transparent"},
                50_000_000,
            )
        self.assertEqual(output.read_bytes(), b"original")

    def test_exif_orientation_is_applied(self):
        source = self.root / "oriented.jpg"
        image = Image.new("RGB", (20, 10), "red")
        exif = Image.Exif()
        exif[274] = 6
        image.save(source, exif=exif)
        loaded = load_image(str(source))
        self.assertEqual(loaded.image.size, (10, 20))

    def test_pixel_limit_rejects_image(self):
        with self.assertRaises(ImagePolicyError):
            load_image(str(self.source), max_pixels=100)

    def test_background_model_integrity_gate_rejects_same_size_corruption(self):
        model_path = self.root / "model.onnx"
        model_path.write_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "checksum"):
            _verify_local_model(
                str(self.root),
                {
                    "file_name": "model.onnx",
                    "size_bytes": 5,
                    "checksum": "md5:00000000000000000000000000000000",
                },
            )

    def test_background_session_cannot_use_rembg_network_downloader(self):
        model_path = self.root / "model.onnx"
        model_path.write_bytes(b"verified")
        fake_pooch = types.ModuleType("pooch")
        original_retrieve = mock.Mock(side_effect=AssertionError("network downloader must not run"))
        fake_pooch.retrieve = original_retrieve
        fake_rembg = types.ModuleType("rembg")

        def fake_new_session(_model_name, providers):
            self.assertEqual(providers, ["CPUExecutionProvider"])
            return fake_pooch.retrieve(
                "https://blocked.invalid/model.onnx",
                "sha256:ignored",
                fname="model.onnx",
                path=str(self.root),
            )

        fake_rembg.new_session = fake_new_session
        with mock.patch.dict(sys.modules, {"pooch": fake_pooch, "rembg": fake_rembg}):
            session = _build_offline_session("test-model", str(model_path))
        self.assertEqual(session, os.path.normcase(os.path.abspath(model_path)))
        self.assertIs(fake_pooch.retrieve, original_retrieve)
        original_retrieve.assert_not_called()

    def test_background_session_is_reused_for_unchanged_model(self):
        model_path = self.root / "model.onnx"
        model_path.write_bytes(b"verified")
        fake_pooch = types.ModuleType("pooch")
        fake_pooch.retrieve = mock.Mock()
        fake_rembg = types.ModuleType("rembg")
        created_session = object()
        fake_rembg.new_session = mock.Mock(return_value=created_session)
        with mock.patch.dict(sys.modules, {"pooch": fake_pooch, "rembg": fake_rembg}):
            first = _build_offline_session("test-model", str(model_path))
            second = _build_offline_session("test-model", str(model_path))
        self.assertIs(first, created_session)
        self.assertIs(second, created_session)
        fake_rembg.new_session.assert_called_once()

    def test_tiff_uses_first_frame(self):
        source = self.root / "multi.tiff"
        first = Image.new("RGB", (12, 8), "red")
        second = Image.new("RGB", (20, 16), "blue")
        first.save(source, save_all=True, append_images=[second])
        output = self.root / "first.png"
        convert_image(str(source), str(output), {"format": "PNG", "quality": 90, "background": "transparent"}, 50_000_000)
        with Image.open(output) as converted:
            self.assertEqual(converted.size, (12, 8))


if __name__ == "__main__":
    unittest.main()
