# Tools Hub plugin contract

A plugin is a directory containing `plugin.json`, an adapter entry-point file, and the Python package named by `python_package`.

## Atomic registration

The entry point must not receive or mutate the Hub Flask app. It builds a Blueprint and returns a `PluginRegistration`:

```python
from flask import Blueprint
from hub.plugin_loader import PluginRegistration


def register(plugin_dir, manifest, hub_paths):
    blueprint = Blueprint(manifest["id"], __name__)
    blueprint.add_url_rule("/", "index", lambda: manifest["name"])
    return PluginRegistration(blueprint=blueprint)
```

The loader preflights the Blueprint on a temporary Flask app, then registers it on the real app using the manifest's `url_prefix`. If construction or preflight fails, the real app receives no routes. Plugins must keep Blueprint registration callbacks deterministic and must not reach the Hub app through globals.

Blueprint deferred callbacks run once during preflight and once during the real commit. They must only declare Flask registrations and must not start processes, write files, or mutate external state.

A plugin with runtime state may return it as `PluginRegistration(blueprint=blueprint, runtime=runtime)`. The loader publishes that state under `app.extensions["plugin_runtimes"][plugin_id]` only after route registration succeeds.

## Required manifest fields

- `id`: lowercase identifier matching `[a-z][a-z0-9_]*`
- `name`
- `version`
- `adapter_version`: must equal the Hub plugin API version `1.0.0`
- `url_prefix`: non-root prefix such as `/example`, without a trailing slash
- `entry_point`: `module:function`, normally `__init__:register`
- `python_package`: a single globally unique Python package name

Plugin IDs, package names, and URL prefixes must be unique across all discovered roots. Every member of a duplicate group is rejected before any plugin route is registered.

If the declared package or one of its submodules already exists in `sys.modules`, the top-level package must originate from its declared `__init__.py` and every submodule must remain under `plugin_dir`. A collision is rejected without removing or replacing the cached module.

Use `hub_paths.plugin_data(id)`, `plugin_models(id)`, `plugin_runtimes(id)`, `plugin_uploads(id)`, and `plugin_outputs(id)` for writable files. Bundled plugin resources under `plugin_dir` must be treated as read-only.


## Monorepo distribution

The repository keeps every plugin source tree under `plugins/<plugin_id>`, but the portable Tools Hub build contains only the Hub core. Each plugin is a separate download artifact and must set `bundled` to `false`.

A plugin manifest declares:

- `distribution.include`: allow-listed files or glob patterns relative to the plugin directory
- `distribution.external_files`: build-time files supplied by environment variable and mapped to an archive-relative target

Build one plugin from the repository root:

```powershell
python -m hub.plugin_package plugins/free_srt --output-dir dist/plugins
```

The generated ZIP has one top-level directory named after the plugin ID. Install it by extracting the ZIP into the portable Hub's `plugins` directory:

```text
ToolsHub/
  ToolsHub.exe
  plugins/
    free_srt/
      plugin.json
      __init__.py
      ...
```

Plugin archives must contain immutable code/resources only. Models, uploads, outputs, preferences, glossary data, caches, virtual environments, and build directories must never be included. Third-party Python dependencies must live inside the plugin's unique package namespace and use relative imports; the Hub does not add plugin directories to `sys.path`.
