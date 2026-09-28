import os
from pathlib import Path
import sys
import threading
import time
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from toolshub_image_universal_tools.engine_service import EngineService


class FakeRunner:
    resource_root = os.getcwd()

    def service_process_args(self):
        script = (
            "import json,sys,time\n"
            "for line in sys.stdin:\n"
            " path=line.strip()\n"
            " if 'slow' in path: time.sleep(5)\n"
            " print(json.dumps({'ok': True, 'path': path}), flush=True)\n"
        )
        return [sys.executable, "-c", script]


class EngineServiceTest(unittest.TestCase):
    def test_cancelled_worker_is_replaced_for_next_request(self):
        service = EngineService(FakeRunner())
        cancel = threading.Event()
        timer = threading.Timer(0.15, cancel.set)
        timer.start()
        try:
            with self.assertRaises(InterruptedError):
                service.process_request("slow-request.json", cancel, lambda _process: None)
            started = time.monotonic()
            response = service.process_request("fast-request.json", threading.Event(), lambda _process: None)
            self.assertTrue(response["ok"])
            self.assertEqual(response["path"], "fast-request.json")
            self.assertLess(time.monotonic() - started, 2)
        finally:
            timer.cancel()
            service.stop()


if __name__ == "__main__":
    unittest.main()
