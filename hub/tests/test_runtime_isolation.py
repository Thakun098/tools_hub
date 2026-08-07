import os
import tempfile
import unittest

from hub.app import HubPaths, PROJECT_ROOT, create_app


class RuntimeIsolationTest(unittest.TestCase):
    def _create(self, runtime_root):
        paths = HubPaths(
            PROJECT_ROOT,
            runtime_root,
            os.path.join(PROJECT_ROOT, "plugins"),
            os.path.join(runtime_root, "external_plugins"),
        )
        return create_app({"TESTING": True, "HUB_PATHS": paths})

    def test_apps_do_not_share_state_or_writable_roots(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            app_one = self._create(first)
            app_two = self._create(second)
            runtime_one = app_one.extensions["plugin_runtimes"]["free_srt"]
            runtime_two = app_two.extensions["plugin_runtimes"]["free_srt"]
            self.assertIsNot(runtime_one, runtime_two)
            self.assertIsNot(runtime_one.transcriptions, runtime_two.transcriptions)
            self.assertIsNot(runtime_one.state_lock, runtime_two.state_lock)
            self.assertNotEqual(runtime_one.DATA_FOLDER, runtime_two.DATA_FOLDER)
            runtime_one.transcriptions["only-one"] = {"status": "completed"}
            self.assertNotIn("only-one", runtime_two.transcriptions)


if __name__ == "__main__":
    unittest.main()
