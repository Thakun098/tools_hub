import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import app


class SegmentationIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.uploads = os.path.join(self.temp.name, "uploads")
        self.models = os.path.join(self.temp.name, "models")
        self.outputs = os.path.join(self.temp.name, "outputs")
        self.data = os.path.join(self.temp.name, "data")
        for folder in (self.uploads, self.models, self.outputs, self.data):
            os.makedirs(folder)
        self.original_paths = (
            app.UPLOAD_FOLDER, app.MODEL_FOLDER, app.OUTPUT_FOLDER, app.DATA_FOLDER,
            app.GLOSSARY_PATH, app.PREFERENCES_PATH, app.EDITOR_BACKUP_PATH,
        )
        app.UPLOAD_FOLDER, app.MODEL_FOLDER, app.OUTPUT_FOLDER = self.uploads, self.models, self.outputs
        app.DATA_FOLDER = self.data
        app.GLOSSARY_PATH = os.path.join(self.data, "glossary.json")
        app.PREFERENCES_PATH = os.path.join(self.data, "preferences.json")
        app.EDITOR_BACKUP_PATH = os.path.join(self.data, "editor-backup.json")
        app.transcriptions.clear()

    def tearDown(self):
        (
            app.UPLOAD_FOLDER, app.MODEL_FOLDER, app.OUTPUT_FOLDER, app.DATA_FOLDER,
            app.GLOSSARY_PATH, app.PREFERENCES_PATH, app.EDITOR_BACKUP_PATH,
        ) = self.original_paths
        app.transcriptions.clear()
        self.temp.cleanup()

    def _job(self, task_id):
        app.transcriptions[task_id] = {
            "status": "queued", "progress": 0, "logs": [], "error": None,
            "srt_filename": None, "_cancel_event": threading.Event(), "_process": None,
            "_compute_backend": "cpu",
        }

    def test_whisper_command_has_segmenting_hints(self):
        task_id = "segment-flags"
        self._job(task_id)
        process = Mock(stdout=[])
        process.wait.return_value = 0
        with patch("app.subprocess.Popen", return_value=process) as popen, \
             patch("app.runtime_environment", return_value={}), \
             patch("app.build_initial_prompt", return_value=""):
            app.run_whisper_transcription("audio.wav", "model.bin", "out", "en", 4, task_id)
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("--max-len") + 1], "35")
        self.assertIn("--split-on-word", command)

    def test_worker_keeps_raw_original_and_writes_segmented_working_srt(self):
        task_id = "segment-worker"
        self._job(task_id)
        input_path = os.path.join(self.uploads, "input.wav")
        Path(input_path).write_bytes(b"audio")
        source = "This generated subtitle is intentionally long enough to require deterministic segmentation into multiple readable events."

        def fake_whisper(_wav, _model, output_base, _language, _threads, _job_id):
            Path(output_base + ".srt").write_text(
                f"1\n00:00:00,000 --> 00:00:10,000\n{source}\n", encoding="utf-8"
            )

        with patch("app.run_ffmpeg_conversion"), patch("app.run_whisper_transcription", side_effect=fake_whisper):
            app.transcription_worker(task_id, input_path, "ggml-base.bin", "en", 2)

        self.assertEqual(app.transcriptions[task_id]["status"], "completed")
        original = app.parse_srt(Path(self.outputs, f"{task_id}.original.srt").read_text(encoding="utf-8"))
        working = app.parse_srt(Path(self.outputs, f"{task_id}.srt").read_text(encoding="utf-8"))
        self.assertEqual(len(original), 1)
        self.assertGreater(len(working), 1)
        self.assertEqual("".join("".join(cue["text"].split()) for cue in working), "".join(source.split()))
        self.assertTrue(all("..." not in cue["text"] for cue in working))
        self.assertTrue(app.transcriptions[task_id]["segmentation_issues"])


if __name__ == "__main__":
    unittest.main()
