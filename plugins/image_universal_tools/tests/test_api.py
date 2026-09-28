import io
import os
from pathlib import Path
import tempfile
import time
import unittest

from PIL import Image

from hub.app import HubPaths, PROJECT_ROOT, create_app


def png_bytes(color=(40, 100, 220, 180)):
    output = io.BytesIO()
    image = Image.new("RGBA", (32, 24), color)
    exif = Image.Exif()
    exif[270] = "private"
    image.save(output, format="PNG", exif=exif)
    return output.getvalue()


class PluginApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        paths = HubPaths(
            resource_root=PROJECT_ROOT,
            runtime_root=str(root),
            bundled_plugins=os.path.join(PROJECT_ROOT, "plugins"),
            external_plugins=str(root / "external_plugins"),
        )
        self.app = create_app({"TESTING": True, "HUB_PATHS": paths})
        self.client = self.app.test_client()

    def tearDown(self):
        runtime = self.app.extensions.get("plugin_runtimes", {}).get("image_universal_tools")
        if runtime:
            runtime.jobs.shutdown()
            runtime.uploads.close()
        self.temp.cleanup()

    def _upload(self, content, filename):
        response = self.client.post(
            "/image-tools/api/uploads",
            data={"files": (io.BytesIO(content), filename)},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["uploads"][0]["id"]

    def _wait_jobs(self, count):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            jobs = self.client.get("/image-tools/api/jobs").get_json()["jobs"]
            if len(jobs) >= count and all(job["status"] in {"completed", "failed", "cancelled"} for job in jobs[:count]):
                return jobs
            time.sleep(.05)
        self.fail("jobs did not finish")

    def test_plugin_and_freesrt_have_hub_navigation(self):
        image_page = self.client.get("/image-tools/")
        self.assertEqual(image_page.status_code, 200)
        self.assertIn("กลับ Tools Hub".encode("utf-8"), image_page.data)
        self.assertIn("default-src 'self'", image_page.headers["Content-Security-Policy"])
        self.assertNotIn("<script>window.", image_page.get_data(as_text=True))
        srt_page = self.client.get("/srt/")
        self.assertEqual(srt_page.status_code, 200)
        self.assertIn("hub-back-link", srt_page.get_data(as_text=True))

    def test_cross_origin_upload_is_rejected(self):
        response = self.client.post(
            "/image-tools/api/uploads",
            data={"files": (io.BytesIO(png_bytes()), "external.png")},
            content_type="multipart/form-data",
            headers={"Origin": "https://malicious.example", "Sec-Fetch-Site": "cross-site"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("เว็บไซต์ภายนอก", response.get_json()["error"])

    def test_conversion_api_removes_metadata(self):
        upload_id = self._upload(png_bytes(), "ภาพตัวอย่าง.png")
        created = self.client.post(
            "/image-tools/api/jobs",
            json={
                "upload_ids": [upload_id],
                "operation": "convert",
                "settings": {"format": "WEBP", "quality": 82, "background": "transparent"},
            },
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        jobs = self._wait_jobs(1)
        self.assertEqual(jobs[0]["status"], "completed", jobs[0].get("error"))
        downloaded = self.client.get(jobs[0]["output_url"])
        self.assertEqual(downloaded.status_code, 200)
        with Image.open(io.BytesIO(downloaded.data)) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertFalse(image.getexif())
        downloaded.close()

    def test_corrupt_file_does_not_stop_next_job(self):
        corrupt_id = self._upload(b"not-an-image", "broken.png")
        valid_id = self._upload(png_bytes(), "valid.png")
        response = self.client.post(
            "/image-tools/api/jobs",
            json={
                "upload_ids": [corrupt_id, valid_id],
                "operation": "convert",
                "settings": {"format": "PNG", "quality": 90, "background": "transparent"},
            },
        )
        self.assertEqual(response.status_code, 201)
        jobs = self._wait_jobs(2)
        statuses = {job["filename"]: job["status"] for job in jobs[:2]}
        self.assertEqual(statuses["broken.png"], "failed")
        self.assertEqual(statuses["valid.png"], "completed")

    def test_batch_registration_rolls_back_every_job_and_upload(self):
        first_id = self._upload(png_bytes(), "first.png")
        second_id = self._upload(png_bytes(), "second.png")
        runtime = self.app.extensions["plugin_runtimes"]["image_universal_tools"]
        original_reserve = runtime.jobs._reserve_output_locked
        calls = 0

        def fail_on_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated reservation failure")
            return original_reserve(*args, **kwargs)

        runtime.jobs._reserve_output_locked = fail_on_second
        try:
            response = self.client.post(
                "/image-tools/api/jobs",
                json={
                    "upload_ids": [first_id, second_id],
                    "operation": "convert",
                    "settings": {"format": "PNG", "quality": 90, "background": "transparent"},
                },
            )
        finally:
            runtime.jobs._reserve_output_locked = original_reserve

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/image-tools/api/jobs").get_json()["jobs"], [])
        discarded = self.client.post(
            "/image-tools/api/uploads/discard",
            json={"upload_ids": [first_id, second_id]},
        )
        self.assertEqual(discarded.get_json()["discarded"], 2)
        self.assertFalse(runtime.jobs._reserved_outputs)

    def test_remove_background_requires_downloaded_model(self):
        upload_id = self._upload(png_bytes(), "subject.png")
        response = self.client.post(
            "/image-tools/api/jobs",
            json={
                "upload_ids": [upload_id],
                "operation": "remove_background",
                "settings": {"model_id": "fast-u2netp"},
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("ดาวน์โหลด", response.get_json()["error"])
        discarded = self.client.post("/image-tools/api/uploads/discard", json={"upload_ids": [upload_id]})
        self.assertEqual(discarded.get_json()["discarded"], 1)

    def test_same_size_corrupt_model_is_rejected_before_queueing(self):
        runtime = self.app.extensions["plugin_runtimes"]["image_universal_tools"]
        model = runtime.models.catalog.get("fast-u2netp")
        model_path = runtime.models.catalog.model_path(runtime.config.model_root, model)
        with open(model_path, "wb") as target:
            target.truncate(model["size_bytes"])
        upload_id = self._upload(png_bytes(), "subject.png")
        response = self.client.post(
            "/image-tools/api/jobs",
            json={
                "upload_ids": [upload_id],
                "operation": "remove_background",
                "settings": {"model_id": "fast-u2netp"},
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/image-tools/api/jobs").get_json()["jobs"], [])
        discarded = self.client.post("/image-tools/api/uploads/discard", json={"upload_ids": [upload_id]})
        self.assertEqual(discarded.get_json()["discarded"], 1)


if __name__ == "__main__":
    unittest.main()
