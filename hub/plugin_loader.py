"""Validated, namespaced plugin discovery and registration."""

from dataclasses import dataclass
import importlib.util
import json
import os
import re
import sys
import traceback
import types

from flask import Blueprint, Flask


PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PACKAGE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MODULE_RE = re.compile(r"^(?:__init__|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)$")
PLUGIN_ADAPTER_VERSION = "1.0.0"
REQUIRED_FIELDS = {"id", "name", "version", "adapter_version", "url_prefix", "entry_point", "python_package"}


@dataclass(frozen=True)
class PluginRegistration:
    """A side-effect-free plugin registration prepared for an atomic commit."""

    blueprint: Blueprint
    runtime: object = None



def _plugin_error(plugin, message):
    plugin["_loaded"] = False
    plugin["_error"] = str(message)
    return plugin


def validate_manifest(manifest, plugin_dir):
    missing = sorted(REQUIRED_FIELDS - set(manifest))
    if missing:
        raise ValueError(f"manifest missing fields: {', '.join(missing)}")
    plugin_id = manifest["id"]
    package = manifest["python_package"]
    prefix = manifest["url_prefix"]
    adapter_version = manifest["adapter_version"]
    if not isinstance(plugin_id, str) or not PLUGIN_ID_RE.fullmatch(plugin_id):
        raise ValueError("plugin id must match [a-z][a-z0-9_]*")
    if not isinstance(package, str) or not PACKAGE_RE.fullmatch(package):
        raise ValueError("python_package must be a single valid Python identifier")
    if adapter_version != PLUGIN_ADAPTER_VERSION:
        raise ValueError(f"unsupported adapter_version: {adapter_version}")
    if not isinstance(prefix, str) or not prefix.startswith("/") or prefix == "/" or prefix.endswith("/"):
        raise ValueError("url_prefix must start with '/', must not be '/', and must not end with '/'")
    if ".." in prefix or "//" in prefix:
        raise ValueError("url_prefix contains an unsafe path segment")
    entry_point = manifest["entry_point"]
    if not isinstance(entry_point, str) or entry_point.count(":") != 1:
        raise ValueError("entry_point must use module:function syntax")
    module_name, function_name = entry_point.split(":")
    if not MODULE_RE.fullmatch(module_name) or not function_name.isidentifier():
        raise ValueError("entry_point must name a safe Python module and function")
    package_init = os.path.join(plugin_dir, package, "__init__.py")
    if not os.path.isfile(package_init):
        raise ValueError(f"python package is missing: {package}")
    return manifest


def discover_plugins(plugin_roots):
    """Discover manifests from ordered roots without importing plugin code."""
    if isinstance(plugin_roots, (str, os.PathLike)):
        plugin_roots = [plugin_roots]
    plugins = []
    for root in plugin_roots:
        if not root or not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            plugin_dir = os.path.abspath(os.path.join(root, entry))
            manifest_path = os.path.join(plugin_dir, "plugin.json")
            if not os.path.isdir(plugin_dir) or not os.path.isfile(manifest_path):
                continue
            manifest = {"id": entry, "name": entry, "version": "0.0.0"}
            try:
                with open(manifest_path, "r", encoding="utf-8") as manifest_file:
                    loaded_manifest = json.load(manifest_file)
                if not isinstance(loaded_manifest, dict):
                    raise ValueError("manifest root must be a JSON object")
                manifest = loaded_manifest
                manifest["_dir"] = plugin_dir
                manifest["_loaded"] = False
                manifest["_error"] = None
                validate_manifest(manifest, plugin_dir)
            except (ValueError, json.JSONDecodeError, OSError) as error:
                manifest["_dir"] = plugin_dir
                _plugin_error(manifest, error)
            plugins.append(manifest)
    return plugins


def _ensure_adapter_namespace():
    namespace = sys.modules.get("toolshub_plugins")
    if namespace is None:
        namespace = types.ModuleType("toolshub_plugins")
        namespace.__path__ = []
        sys.modules["toolshub_plugins"] = namespace


def _canonical_module_origin(module):
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, (str, os.PathLike)):
        return None
    origin = os.fspath(origin)
    if origin.lower().endswith((".pyc", ".pyo")):
        try:
            origin = importlib.util.source_from_cache(origin)
        except ValueError:
            pass
    return os.path.normcase(os.path.realpath(origin))


def _origin_is_within(origin, directory):
    if origin is None:
        return False
    directory = os.path.normcase(os.path.realpath(directory))
    try:
        return os.path.commonpath([origin, directory]) == directory
    except ValueError:
        return False


def _validate_cached_package_origins(package_name, plugin_dir, package_init):
    expected_init = os.path.normcase(os.path.realpath(package_init))
    for module_name, module in list(sys.modules.items()):
        if module_name != package_name and not module_name.startswith(package_name + "."):
            continue
        origin = _canonical_module_origin(module)
        valid = origin == expected_init if module_name == package_name else _origin_is_within(origin, plugin_dir)
        if not valid:
            raise ImportError(f"python package origin mismatch: {module_name}")


def _load_package(plugin):
    package_name = plugin["python_package"]
    package_dir = os.path.join(plugin["_dir"], package_name)
    package_init = os.path.join(package_dir, "__init__.py")
    _validate_cached_package_origins(package_name, plugin["_dir"], package_init)
    if package_name in sys.modules:
        return sys.modules[package_name]
    spec = importlib.util.spec_from_file_location(
        package_name,
        package_init,
        submodule_search_locations=[package_dir],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(package_name, None)
        raise
    return module


def _preflight_blueprint(app, plugin, blueprint):
    """Exercise all deferred Blueprint callbacks without mutating the real app."""
    if blueprint.name in app.blueprints:
        raise ValueError(f"duplicate blueprint name: {blueprint.name}")
    probe = Flask(f"toolshub_preflight_{plugin['id']}", static_folder=None)
    probe.config.update(app.config)
    probe.register_blueprint(blueprint, url_prefix=plugin["url_prefix"])




def load_plugin(app, plugin, hub_paths):
    validate_manifest(plugin, plugin["_dir"])
    _ensure_adapter_namespace()
    before_modules = set(sys.modules)
    adapter_name = f"toolshub_plugins.{plugin['id']}"
    try:
        _load_package(plugin)
        module_file, function_name = plugin["entry_point"].split(":")
        module_path = os.path.join(
            plugin["_dir"],
            "__init__.py" if module_file == "__init__" else module_file.replace(".", os.sep) + ".py",
        )
        if not os.path.isfile(module_path):
            raise ValueError("plugin entry point file is missing")
        spec = importlib.util.spec_from_file_location(adapter_name, module_path)
        adapter = importlib.util.module_from_spec(spec)
        sys.modules[adapter_name] = adapter
        spec.loader.exec_module(adapter)
        register = getattr(adapter, function_name)
        registration = register(plugin["_dir"], plugin, hub_paths)
        if not isinstance(registration, PluginRegistration):
            raise TypeError("plugin entry point must return PluginRegistration")
        if not isinstance(registration.blueprint, Blueprint):
            raise TypeError("plugin registration blueprint must be a Flask Blueprint")
        _preflight_blueprint(app, plugin, registration.blueprint)
        app.register_blueprint(registration.blueprint, url_prefix=plugin["url_prefix"])
        if registration.runtime is not None:
            app.extensions.setdefault("plugin_runtimes", {})[plugin["id"]] = registration.runtime
        plugin["_loaded"] = True
        plugin["_error"] = None
    except Exception:
        for name in set(sys.modules) - before_modules:
            if name == adapter_name or name == plugin.get("python_package") or name.startswith(plugin.get("python_package", "") + "."):
                sys.modules.pop(name, None)
        raise


def _reject_duplicate_contracts(plugins):
    """Mark every member of a manifest conflict before any routes are committed."""
    owners = {"id": {}, "python_package": {}, "url_prefix": {}}
    for plugin in plugins:
        if plugin.get("_error"):
            continue
        for field, values in owners.items():
            value = plugin.get(field)
            first = values.get(value)
            if first is None:
                values[value] = plugin
                continue
            message = f"duplicate plugin {field}: {value}"
            _plugin_error(first, message)
            _plugin_error(plugin, message)


def load_all_plugins(app, plugins, hub_paths):
    _reject_duplicate_contracts(plugins)
    for plugin in plugins:
        if plugin.get("_error"):
            continue
        try:
            load_plugin(app, plugin, hub_paths)
            print(f"[hub] Loaded plugin: {plugin['name']} v{plugin['version']} at {plugin['url_prefix']}")
        except Exception as error:
            _plugin_error(plugin, error)
            print(f"[hub] ERROR loading plugin '{plugin['id']}': {error}")
            traceback.print_exc()
