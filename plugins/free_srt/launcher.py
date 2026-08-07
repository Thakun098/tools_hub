"""Launch Free SRT as a portable local application."""
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser


def write_startup_error():
    base = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(base, "portable_startup.log"), "a", encoding="utf-8") as log_file:
            log_file.write(traceback.format_exc())
            log_file.write("\n")
    except OSError:
        pass


def run_server(application, port):
    try:
        application.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
    except BaseException:
        write_startup_error()
        raise


def find_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_server(url, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                return True
        except Exception:
            time.sleep(0.15)
    return False


def main():
    port = int(os.environ.get("PORT", find_port()))
    os.environ["PORT"] = str(port)
    try:
        from app import app
        url = f"http://127.0.0.1:{port}/"
        server = threading.Thread(target=run_server, args=(app, port), daemon=True)
        server.start()
        if not wait_for_server(url):
            raise RuntimeError("Free SRT server did not start within the expected time")
        webbrowser.open(url)
        while server.is_alive():
            time.sleep(1)
    except BaseException:
        write_startup_error()
        raise


if __name__ == "__main__":
    main()
