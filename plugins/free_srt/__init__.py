"""FreeSRT adapter for Tools Hub."""

import os

from flask import Blueprint

from hub.plugin_loader import PluginRegistration

from toolshub_free_srt.app_factory import (
    build_runtime_config,
    create_runtime_context,
    register_routes,
)


def register(plugin_dir, manifest, hub_paths):
    runtime_config = build_runtime_config(
        resource_root=plugin_dir,
        data_root=hub_paths.plugin_data(manifest["id"]),
        model_root=hub_paths.plugin_models(manifest["id"]),
        runtime_root=hub_paths.plugin_runtimes(manifest["id"]),
        upload_root=hub_paths.plugin_uploads(manifest["id"]),
        output_root=hub_paths.plugin_outputs(manifest["id"]),
        url_prefix=manifest["url_prefix"],
    )
    runtime = create_runtime_context(runtime_config)
    blueprint = Blueprint(
        "free_srt_plugin",
        __name__,
        template_folder=os.path.join(runtime.RESOURCE_DIR, "templates"),
        static_folder=os.path.join(runtime.RESOURCE_DIR, "static"),
        static_url_path="/static",
    )
    register_routes(blueprint, runtime)
    return PluginRegistration(blueprint=blueprint, runtime=runtime)
