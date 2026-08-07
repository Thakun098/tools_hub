import importlib.util
import json
import os
import sys
import tempfile
import unittest
import types

from flask import Flask

from hub.app import HubPaths
from hub.plugin_loader import discover_plugins, load_all_plugins


class PluginIsolationTest(unittest.TestCase):
    def _write_plugin(self, root, folder, plugin_id, package, prefix):
        plugin_dir = os.path.join(root, folder)
        package_dir = os.path.join(plugin_dir, package)
        os.makedirs(package_dir)
        with open(os.path.join(package_dir, "__init__.py"), "w", encoding="utf-8") as file:
            file.write("VALUE = 'isolated'\n")
        with open(os.path.join(plugin_dir, "__init__.py"), "w", encoding="utf-8") as file:
            file.write(
                "from flask import Blueprint\n"
                "from hub.plugin_loader import PluginRegistration\n"
                "def register(plugin_dir, manifest, hub_paths):\n"
                "    bp = Blueprint(manifest['id'], __name__)\n"
                "    bp.add_url_rule('/', 'index', lambda: manifest['id'])\n"
                "    return PluginRegistration(blueprint=bp)\n"
            )
        manifest = {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "adapter_version": "1.0.0",
            "url_prefix": prefix,
            "entry_point": "__init__:register",
            "python_package": package,
        }
        with open(os.path.join(plugin_dir, "plugin.json"), "w", encoding="utf-8") as file:
            json.dump(manifest, file)

    def test_loader_does_not_change_sys_path_and_namespaces_modules(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_plugin(root, "one", "one", "fake_one_package", "/one")
            self._write_plugin(root, "two", "two", "fake_two_package", "/two")
            paths = HubPaths(root, root, root, os.path.join(root, "external"))
            plugins = discover_plugins(root)
            before = list(sys.path)
            app = Flask(__name__)
            load_all_plugins(app, plugins, paths)
            self.assertEqual(before, sys.path)
            self.assertTrue(all(plugin["_loaded"] for plugin in plugins))
            self.assertIn("fake_one_package", sys.modules)
            self.assertIn("fake_two_package", sys.modules)
            self.assertEqual(app.test_client().get("/one/").get_data(as_text=True), "one")
            self.assertEqual(app.test_client().get("/two/").get_data(as_text=True), "two")

    def test_duplicate_prefix_rejects_all_conflicts_before_registration(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_plugin(root, "one", "one", "fake_dup_one", "/same")
            self._write_plugin(root, "two", "two", "fake_dup_two", "/same")
            plugins = discover_plugins(root)
            app = Flask(__name__)
            paths = HubPaths(root, root, root, os.path.join(root, "external"))
            load_all_plugins(app, plugins, paths)
            self.assertFalse(plugins[0]["_loaded"])
            self.assertFalse(plugins[1]["_loaded"])
            self.assertIn("duplicate", plugins[0]["_error"])
            self.assertIn("duplicate", plugins[1]["_error"])
            rules = [rule.rule for rule in app.url_map.iter_rules()]
            self.assertEqual(rules.count("/same/"), 0)

    def test_malformed_manifest_does_not_mutate_previous_plugin(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_plugin(root, "a_good", "good", "good_package", "/good")
            bad_dir = os.path.join(root, "b_bad")
            os.makedirs(bad_dir)
            with open(os.path.join(bad_dir, "plugin.json"), "w", encoding="utf-8") as file:
                file.write("{broken")

            plugins = discover_plugins(root)

            self.assertEqual(len(plugins), 2)
            self.assertIsNot(plugins[0], plugins[1])
            self.assertEqual(plugins[0]["id"], "good")
            self.assertEqual(plugins[0]["_dir"], os.path.join(root, "a_good"))
            self.assertIsNone(plugins[0]["_error"])
            self.assertEqual(plugins[1]["id"], "b_bad")
            self.assertEqual(plugins[1]["_dir"], bad_dir)
            self.assertIsNotNone(plugins[1]["_error"])

    def test_unsafe_entry_point_is_rejected_during_discovery(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_plugin(root, "probe", "probe", "safe_package", "/probe")
            manifest_path = os.path.join(root, "probe", "plugin.json")
            with open(manifest_path, "r", encoding="utf-8") as file:
                manifest = json.load(file)
            manifest["entry_point"] = "..outside:register"
            with open(manifest_path, "w", encoding="utf-8") as file:
                json.dump(manifest, file)

            plugins = discover_plugins(root)

            self.assertEqual(len(plugins), 1)
            self.assertFalse(plugins[0]["_loaded"])
            self.assertIn("safe Python module", plugins[0]["_error"])

    def test_blueprint_registration_failure_leaves_no_partial_route(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_plugin(root, "broken", "broken", "broken_package", "/broken")
            adapter_path = os.path.join(root, "broken", "__init__.py")
            with open(adapter_path, "w", encoding="utf-8") as file:
                file.write(
                    "from flask import Blueprint\n"
                    "from hub.plugin_loader import PluginRegistration\n"
                    "def register(plugin_dir, manifest, hub_paths):\n"
                    "    bp = Blueprint('broken', __name__)\n"
                    "    bp.add_url_rule('/', 'index', lambda: 'leaked')\n"
                    "    def fail_during_registration(state):\n"
                    "        raise RuntimeError('during blueprint registration')\n"
                    "    bp.record(fail_during_registration)\n"
                    "    return PluginRegistration(blueprint=bp)\n"
                )

            plugins = discover_plugins(root)
            app = Flask(__name__)
            paths = HubPaths(root, root, root, os.path.join(root, "external"))
            load_all_plugins(app, plugins, paths)

            self.assertFalse(plugins[0]["_loaded"])
            self.assertIn("during blueprint registration", plugins[0]["_error"])
            self.assertEqual(app.test_client().get("/broken/").status_code, 404)

    def test_cached_package_from_wrong_origin_is_rejected_without_replacement(self):
        with tempfile.TemporaryDirectory() as root:
            package = "wrong_origin_package"
            self._write_plugin(root, "probe", "probe", package, "/probe")
            cached = types.ModuleType(package)
            cached.__file__ = os.path.join(root, "elsewhere", "__init__.py")
            sys.modules[package] = cached
            try:
                plugins = discover_plugins(root)
                app = Flask(__name__)
                paths = HubPaths(root, root, root, os.path.join(root, "external"))
                load_all_plugins(app, plugins, paths)

                self.assertFalse(plugins[0]["_loaded"])
                self.assertIn("origin mismatch", plugins[0]["_error"])
                self.assertIs(sys.modules[package], cached)
                self.assertEqual(app.test_client().get("/probe/").status_code, 404)
            finally:
                sys.modules.pop(package, None)

    def test_cached_bytecode_origin_for_declared_package_is_reused(self):
        with tempfile.TemporaryDirectory() as root:
            package = "matching_origin_package"
            self._write_plugin(root, "probe", "probe", package, "/probe")
            source = os.path.join(root, "probe", package, "__init__.py")
            cached = types.ModuleType(package)
            cached.__file__ = importlib.util.cache_from_source(source)
            sys.modules[package] = cached
            try:
                plugins = discover_plugins(root)
                app = Flask(__name__)
                paths = HubPaths(root, root, root, os.path.join(root, "external"))
                load_all_plugins(app, plugins, paths)

                self.assertTrue(plugins[0]["_loaded"])
                self.assertIs(sys.modules[package], cached)
                self.assertEqual(app.test_client().get("/probe/").status_code, 200)
            finally:
                sys.modules.pop(package, None)

    def test_cached_submodule_from_wrong_origin_is_rejected_before_package_load(self):
        with tempfile.TemporaryDirectory() as root:
            package = "wrong_submodule_package"
            self._write_plugin(root, "probe", "probe", package, "/probe")
            submodule_name = package + ".helper"
            cached = types.ModuleType(submodule_name)
            cached.__file__ = os.path.join(root, "elsewhere", "helper.py")
            sys.modules[submodule_name] = cached
            try:
                plugins = discover_plugins(root)
                app = Flask(__name__)
                paths = HubPaths(root, root, root, os.path.join(root, "external"))
                load_all_plugins(app, plugins, paths)

                self.assertFalse(plugins[0]["_loaded"])
                self.assertIn(submodule_name, plugins[0]["_error"])
                self.assertIs(sys.modules[submodule_name], cached)
                self.assertNotIn(package, sys.modules)
                self.assertEqual(app.test_client().get("/probe/").status_code, 404)
            finally:
                sys.modules.pop(submodule_name, None)
                sys.modules.pop(package, None)

    def test_cached_submodule_inside_plugin_directory_is_reused(self):
        with tempfile.TemporaryDirectory() as root:
            package = "alternate_source_package"
            self._write_plugin(root, "probe", "probe", package, "/probe")
            alternate_dir = os.path.join(root, "probe", "legacy")
            os.makedirs(alternate_dir)
            submodule_name = package + ".helper"
            cached = types.ModuleType(submodule_name)
            cached.__file__ = os.path.join(alternate_dir, "helper.py")
            sys.modules[submodule_name] = cached
            try:
                plugins = discover_plugins(root)
                app = Flask(__name__)
                paths = HubPaths(root, root, root, os.path.join(root, "external"))
                load_all_plugins(app, plugins, paths)

                self.assertTrue(plugins[0]["_loaded"])
                self.assertIs(sys.modules[submodule_name], cached)
                self.assertEqual(app.test_client().get("/probe/").status_code, 200)
            finally:
                sys.modules.pop(submodule_name, None)
                sys.modules.pop(package, None)

    def test_unsupported_adapter_version_is_rejected_during_discovery(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_plugin(root, "future", "future", "future_package", "/future")
            manifest_path = os.path.join(root, "future", "plugin.json")
            with open(manifest_path, "r", encoding="utf-8") as file:
                manifest = json.load(file)
            manifest["adapter_version"] = "2.0.0"
            with open(manifest_path, "w", encoding="utf-8") as file:
                json.dump(manifest, file)

            plugins = discover_plugins(root)

            self.assertEqual(len(plugins), 1)
            self.assertFalse(plugins[0]["_loaded"])
            self.assertIn("unsupported adapter_version", plugins[0]["_error"])


if __name__ == "__main__":
    unittest.main()
