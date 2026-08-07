import os
import tempfile
import unittest

from hub.app import HubPaths, PROJECT_ROOT, create_app


class HubIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        paths = HubPaths(
            resource_root=PROJECT_ROOT,
            runtime_root=self.temp.name,
            bundled_plugins=os.path.join(PROJECT_ROOT, "plugins"),
            external_plugins=os.path.join(self.temp.name, "external_plugins"),
        )
        self.app = create_app({"TESTING": True, "HUB_PATHS": paths})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_dashboard_manifest_health_and_prefixed_assets(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        plugins = self.client.get("/api/hub/plugins").get_json()
        free_srt = next(plugin for plugin in plugins if plugin["id"] == "free_srt")
        self.assertTrue(free_srt["loaded"])
        self.assertEqual(free_srt["url_prefix"], "/srt")
        health = self.client.get("/api/hub/health").get_json()
        self.assertIn("free_srt", health["loaded_plugin_ids"])
        self.assertEqual(self.client.get("/srt/").status_code, 200)
        self.assertEqual(self.client.get("/srt/api/models").status_code, 200)
        self.assertEqual(self.client.get("/srt/static/app.js").status_code, 200)
        self.assertEqual(self.client.get("/srt/static/styles.css").status_code, 200)
        self.assertEqual(self.client.get("/api/models").status_code, 404)
        page = self.client.get("/srt/").get_data(as_text=True)
        self.assertIn('data-base-url="/srt"', page)
        self.assertIn('src="static/app.js"', page)

    def test_preferences_glossary_and_backup_round_trips(self):
        response = self.client.put("/srt/api/preferences", json={"theme": "dark"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/srt/api/preferences").get_json()["theme"], "dark")

        entries = [{"from": "teh", "to": "the"}]
        response = self.client.put("/srt/api/glossary", json={"entries": entries})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/srt/api/glossary").get_json()["entries"], entries)

        content = "1\n00:00:00,000 --> 00:00:01,000\nhello\n"
        response = self.client.put(
            "/srt/api/editor-backup",
            json={"content": content, "input_name": "test", "dirty": True},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.get("/srt/api/editor-backup").get_json()["available"])
        self.assertEqual(self.client.delete("/srt/api/editor-backup").status_code, 200)
        self.assertFalse(self.client.get("/srt/api/editor-backup").get_json()["available"])


if __name__ == "__main__":
    unittest.main()
