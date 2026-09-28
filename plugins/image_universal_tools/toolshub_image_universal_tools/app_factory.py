"""Side-effect-light factory used by the Hub adapter."""

from dataclasses import dataclass
import os

from .jobs import JobManager
from .model_catalog import ModelCatalog
from .model_downloads import ModelDownloadManager
from .routes import attach_routes
from .runtime import EngineRunner, RuntimeConfig
from .uploads import UploadStore


@dataclass
class RuntimeContext:
    config: RuntimeConfig
    uploads: UploadStore
    models: ModelDownloadManager
    jobs: JobManager


def build_runtime_config(**values):
    return RuntimeConfig(**{key: os.path.abspath(value) if key != "url_prefix" else value for key, value in values.items()})


def create_runtime_context(config):
    for path in (
        config.data_root,
        config.model_root,
        config.runtime_root,
        config.upload_root,
        config.output_root,
    ):
        os.makedirs(path, exist_ok=True)
    catalog = ModelCatalog(os.path.join(config.resource_root, "model_catalog.json"))
    uploads = UploadStore(config.upload_root)
    models = ModelDownloadManager(catalog, config.model_root)
    jobs = JobManager(
        upload_store=uploads,
        model_catalog=catalog,
        model_downloads=models,
        model_root=config.model_root,
        output_root=config.output_root,
        runtime_root=config.runtime_root,
        engine_runner=EngineRunner(config.resource_root),
    )
    return RuntimeContext(config=config, uploads=uploads, models=models, jobs=jobs)


def register_routes(blueprint, runtime):
    attach_routes(blueprint, runtime)
