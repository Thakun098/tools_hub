"""JSON CLI for the image engine sidecar."""

import argparse
import json
import os
import sys

from . import __version__
from .protocol import process_request


MAX_REQUEST_BYTES = 64 * 1024


def _read_request(path):
    if os.path.getsize(path) > MAX_REQUEST_BYTES:
        raise ValueError("request file ใหญ่เกินกำหนด")
    with open(path, "r", encoding="utf-8") as source:
        return json.load(source)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Image Universal Tools CPU engine")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("probe")
    subparsers.add_parser("serve")
    process_parser = subparsers.add_parser("process")
    process_parser.add_argument("--request-file", required=True)
    args = parser.parse_args(argv)

    if args.command == "probe":
        from PIL import __version__ as pillow_version
        print(json.dumps({"ok": True, "version": __version__, "pillow": pillow_version, "cpu_only": True}))
        return 0
    if args.command == "serve":
        for request_path in sys.stdin:
            request_path = request_path.strip()
            if not request_path:
                continue
            try:
                response = process_request(_read_request(request_path))
            except Exception as error:
                response = {"ok": False, "error": str(error)}
            print(json.dumps(response, ensure_ascii=False), flush=True)
        return 0
    try:
        response = process_request(_read_request(args.request_file))
    except Exception as error:
        print(str(error), file=sys.stderr)
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
