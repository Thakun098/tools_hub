"""Tools Hub Flask application factory."""

from dataclasses import dataclass
import os
import sys

from flask import Flask, jsonify, render_template

from hub.plugin_loader import discover_plugins, load_all_plugins


SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SOURCE_DIR)


@dataclass(frozen=True)
class HubPaths:
    resource_root: str
    runtime_root: str
    bundled_plugins: str
    external_plugins: str

    def _under_runtime(self, category, plugin_id):
        path = os.path.abspath(os.path.join(self.runtime_root, category, plugin_id))
        os.makedirs(path, exist_ok=True)
        return path

    def plugin_data(self, plugin_id):
        return self._under_runtime(os.path.join("data", "plugins"), plugin_id)

    def plugin_models(self, plugin_id):
        return self._under_runtime("models", plugin_id)

    def plugin_runtimes(self, plugin_id):
        return self._under_runtime("runtimes", plugin_id)

    def plugin_uploads(self, plugin_id):
        return self._under_runtime("uploads", plugin_id)

    def plugin_outputs(self, plugin_id):
        return self._under_runtime("outputs", plugin_id)


def default_paths():
    frozen = bool(getattr(sys, "frozen", False))
    resource_root = os.path.abspath(getattr(sys, "_MEIPASS", PROJECT_ROOT))
    runtime_root = os.path.dirname(os.path.abspath(sys.executable)) if frozen else PROJECT_ROOT
    bundled_plugins = os.path.join(resource_root, "plugins")
    external_plugins = os.path.join(runtime_root, "plugins") if frozen else os.path.join(runtime_root, "external_plugins")
    if frozen:
        os.makedirs(external_plugins, exist_ok=True)
    return HubPaths(resource_root, runtime_root, bundled_plugins, external_plugins)


def create_app(config=None):
    config = dict(config or {})
    paths = config.pop("HUB_PATHS", default_paths())
    flask_app = Flask(
        __name__,
        template_folder=os.path.join(paths.resource_root, "hub", "templates"),
        static_folder=os.path.join(paths.resource_root, "hub", "static"),
    )
    flask_app.config.update(config)
    plugins = discover_plugins([paths.bundled_plugins, paths.external_plugins])
    load_all_plugins(flask_app, plugins, paths)
    flask_app.extensions["hub_paths"] = paths
    flask_app.extensions["hub_plugins"] = plugins

    @flask_app.route("/")
    def hub_dashboard():
        return render_template("hub.html")

    @flask_app.route("/api/hub/plugins")
    def hub_plugin_list():
        return jsonify([
            {
                "id": plugin.get("id"),
                "name": plugin.get("name", plugin.get("id", "unknown")),
                "description": plugin.get("description", ""),
                "icon": plugin.get("icon", "🔧"),
                "version": plugin.get("version", "0.0.0"),
                "url_prefix": plugin.get("url_prefix", "/"),
                "bundled": plugin.get("bundled", False),
                "loaded": plugin.get("_loaded", False),
                "error": plugin.get("_error"),
            }
            for plugin in plugins
        ])

    @flask_app.route("/api/hub/health")
    def hub_health():
        loaded = [plugin["id"] for plugin in plugins if plugin.get("_loaded")]
        return jsonify(status="ok", plugins_loaded=len(loaded), loaded_plugin_ids=loaded)

    return flask_app


app = create_app()
