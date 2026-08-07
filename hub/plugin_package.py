"""Build deterministic, separately downloadable Tools Hub plugin archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import zipfile

from hub.plugin_loader import validate_manifest


class PluginPackageError(ValueError):
    pass


def _safe_relative(value, label):
    normalized = str(value).replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:/", normalized)
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise PluginPackageError(f"{label} must be a safe relative path: {value}")
    return path


def _path_under(root, candidate):
    root = root.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise PluginPackageError(f"distribution source escapes plugin directory: {candidate}") from error
    return candidate


def _load_distribution(plugin_dir):
    manifest_path = plugin_dir / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PluginPackageError(f"cannot read plugin manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise PluginPackageError("plugin manifest root must be a JSON object")
    validate_manifest(manifest, str(plugin_dir))
    distribution = manifest.get("distribution")
    if not isinstance(distribution, dict):
        raise PluginPackageError("plugin manifest must define a distribution object")
    includes = distribution.get("include")
    if not isinstance(includes, list) or not includes:
        raise PluginPackageError("distribution.include must be a non-empty list")
    external_files = distribution.get("external_files", [])
    if not isinstance(external_files, list):
        raise PluginPackageError("distribution.external_files must be a list")
    return manifest, includes, external_files


def _collect_sources(plugin_dir, includes, external_files, environ):
    selected = {}
    normalized_targets = {}

    def add_source(target, source):
        normalized = target.casefold()
        existing = normalized_targets.get(normalized)
        if existing is not None:
            raise PluginPackageError(f"duplicate distribution target: {target} conflicts with {existing}")
        normalized_targets[normalized] = target
        selected[target] = source

    for raw_pattern in includes:
        pattern = _safe_relative(raw_pattern, "distribution include pattern").as_posix()
        matches = []
        for candidate in plugin_dir.glob(pattern):
            if candidate.is_file():
                candidate = _path_under(plugin_dir, candidate)
                relative = candidate.relative_to(plugin_dir).as_posix()
                matches.append((relative, candidate))
        if not matches:
            raise PluginPackageError(f"distribution include matched no files: {raw_pattern}")
        for relative, candidate in matches:
            if relative not in selected:
                add_source(relative, candidate)

    for item in external_files:
        if not isinstance(item, dict):
            raise PluginPackageError("external file entries must be objects")
        environment = item.get("environment")
        target = _safe_relative(item.get("target", ""), "external file target").as_posix()
        if not isinstance(environment, str) or not environment:
            raise PluginPackageError("external file environment must be a non-empty string")
        source_value = environ.get(environment)
        if not source_value:
            raise PluginPackageError(f"required environment variable is missing: {environment}")
        source = Path(source_value).resolve()
        if not source.is_file():
            raise PluginPackageError(f"external file does not exist for {environment}")
        add_source(target, source)
    return selected


def _write_entry(archive, name, source):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_plugin_archive(plugin_dir, output_dir, environ=None):
    plugin_dir = Path(plugin_dir).resolve()
    output_dir = Path(output_dir).resolve()
    if not plugin_dir.is_dir():
        raise PluginPackageError(f"plugin directory does not exist: {plugin_dir}")
    try:
        output_dir.relative_to(plugin_dir)
    except ValueError:
        pass
    else:
        raise PluginPackageError("output directory must be outside the plugin directory")
    manifest, includes, external_files = _load_distribution(plugin_dir)
    sources = _collect_sources(plugin_dir, includes, external_files, dict(os.environ if environ is None else environ))
    plugin_id = manifest["id"]
    version = re.sub(r"[^A-Za-z0-9._-]+", "_", str(manifest["version"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"toolshub-plugin-{plugin_id}-{version}.zip"
    temporary_path = archive_path.with_suffix(archive_path.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temporary_path, "w") as archive:
            for relative, source in sorted(sources.items()):
                _write_entry(archive, f"{plugin_id}/{relative}", source)
        os.replace(temporary_path, archive_path)
    except Exception:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return archive_path


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Build a separately downloadable Tools Hub plugin ZIP")
    parser.add_argument("plugin_dir")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    try:
        archive = build_plugin_archive(args.plugin_dir, args.output_dir)
    except (OSError, PluginPackageError) as error:
        parser.error(str(error))
    print(archive)
    print(f"sha256={sha256_file(archive)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
