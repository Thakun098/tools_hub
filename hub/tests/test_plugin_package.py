import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from hub.plugin_package import PluginPackageError, build_plugin_archive, sha256_file


class PluginPackageTest(unittest.TestCase):
    def _write_plugin(self, root, includes=None, external_files=None):
        plugin_dir = Path(root, "demo")
        package_dir = plugin_dir / "toolshub_demo"
        package_dir.mkdir(parents=True)
        (package_dir / "__init__.py").write_text("VALUE = 'demo'\n", encoding="utf-8")
        (plugin_dir / "__init__.py").write_text("# adapter\n", encoding="utf-8")
        (plugin_dir / "secret.txt").write_text("not packaged", encoding="utf-8")
        manifest = {
            "id": "demo",
            "adapter_version": "1.0.0",
            "name": "Demo",
            "version": "1.2.3",
            "url_prefix": "/demo",
            "entry_point": "__init__:register",
            "python_package": "toolshub_demo",
            "bundled": False,
            "distribution": {
                "include": includes or ["plugin.json", "__init__.py", "toolshub_demo/**/*.py"],
                "external_files": external_files or [],
            },
        }
        (plugin_dir / "plugin.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return plugin_dir

    def test_builds_deterministic_archive_with_plugin_root(self):
        with tempfile.TemporaryDirectory() as root:
            plugin_dir = self._write_plugin(root)
            output = Path(root, "dist")
            first = build_plugin_archive(plugin_dir, output, environ={})
            first_bytes = first.read_bytes()
            second = build_plugin_archive(plugin_dir, output, environ={})

            self.assertEqual(first, second)
            self.assertEqual(first_bytes, second.read_bytes())
            self.assertEqual(len(sha256_file(first)), 64)
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(
                    archive.namelist(),
                    [
                        "demo/__init__.py",
                        "demo/plugin.json",
                        "demo/toolshub_demo/__init__.py",
                    ],
                )
                self.assertNotIn("demo/secret.txt", archive.namelist())

    def test_external_file_is_mapped_to_declared_target(self):
        with tempfile.TemporaryDirectory() as root:
            external = Path(root, "runtime.exe")
            external.write_bytes(b"runtime")
            plugin_dir = self._write_plugin(
                root,
                external_files=[{"environment": "DEMO_RUNTIME", "target": "bin/runtime.exe"}],
            )
            archive_path = build_plugin_archive(
                plugin_dir,
                Path(root, "dist"),
                environ={"DEMO_RUNTIME": os.fspath(external)},
            )

            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(archive.read("demo/bin/runtime.exe"), b"runtime")

    def test_rejects_include_path_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            plugin_dir = self._write_plugin(root, includes=["../secret.txt"])
            with self.assertRaisesRegex(PluginPackageError, "safe relative path"):
                build_plugin_archive(plugin_dir, Path(root, "dist"), environ={})

    def test_rejects_missing_external_file_environment(self):
        with tempfile.TemporaryDirectory() as root:
            plugin_dir = self._write_plugin(
                root,
                external_files=[{"environment": "MISSING_RUNTIME", "target": "bin/runtime.exe"}],
            )
            with self.assertRaisesRegex(PluginPackageError, "MISSING_RUNTIME"):
                build_plugin_archive(plugin_dir, Path(root, "dist"), environ={})

    def test_rejects_case_insensitive_external_target_collision(self):
        with tempfile.TemporaryDirectory() as root:
            external = Path(root, "replacement.json")
            external.write_text("{}", encoding="utf-8")
            plugin_dir = self._write_plugin(
                root,
                external_files=[{"environment": "REPLACEMENT", "target": "PLUGIN.JSON"}],
            )
            with self.assertRaisesRegex(PluginPackageError, "duplicate distribution target"):
                build_plugin_archive(
                    plugin_dir,
                    Path(root, "dist"),
                    environ={"REPLACEMENT": os.fspath(external)},
                )

    def test_rejects_output_directory_inside_plugin(self):
        with tempfile.TemporaryDirectory() as root:
            plugin_dir = self._write_plugin(root)
            with self.assertRaisesRegex(PluginPackageError, "outside the plugin directory"):
                build_plugin_archive(plugin_dir, plugin_dir / "dist", environ={})

    def test_free_srt_is_external_and_has_distribution_metadata(self):
        project_root = Path(__file__).resolve().parents[2]
        manifest = json.loads(
            Path(project_root, "plugins", "free_srt", "plugin.json").read_text(encoding="utf-8")
        )
        self.assertFalse(manifest["bundled"])
        self.assertIn("distribution", manifest)
        self.assertEqual(
            {item["environment"] for item in manifest["distribution"]["external_files"]},
            {"FFMPEG_SOURCE", "FFPROBE_SOURCE"},
        )


if __name__ == "__main__":
    unittest.main()
