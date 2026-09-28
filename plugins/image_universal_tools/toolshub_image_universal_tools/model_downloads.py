"""Explicit, cancellable and checksum-verified model downloads."""

import hashlib
import os
import ssl
import threading
import urllib.request


class ModelDownloadManager:
    def __init__(self, catalog, model_root):
        self.catalog = catalog
        self.model_root = os.path.abspath(model_root)
        self._states = {}
        self._cancel_events = {}
        self._verification_cache = {}
        self._lock = threading.RLock()

    @staticmethod
    def _checksum_parts(value):
        algorithm, expected = value.split(":", 1)
        if algorithm not in {"md5", "sha256"}:
            raise ValueError("unsupported checksum algorithm")
        return algorithm, expected.lower()

    def _fingerprint(self, path):
        try:
            stat = os.stat(path)
            return stat.st_size, stat.st_mtime_ns
        except OSError:
            return None

    def _verify_model(self, model, *, force=False, remove_invalid=False):
        path = self.catalog.model_path(self.model_root, model)
        fingerprint = self._fingerprint(path)
        if fingerprint is None:
            return False
        with self._lock:
            cached = self._verification_cache.get(model["id"])
        if not force and cached and cached[0] == fingerprint:
            return cached[1]
        valid = fingerprint[0] == int(model["size_bytes"])
        if valid:
            algorithm, expected = self._checksum_parts(model["checksum"])
            digest = hashlib.new(algorithm)
            with open(path, "rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            valid = digest.hexdigest().lower() == expected
        with self._lock:
            self._verification_cache[model["id"]] = (fingerprint, valid)
        if not valid and remove_invalid:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            with self._lock:
                self._verification_cache.pop(model["id"], None)
        return valid

    def _installed(self, model):
        return self._verify_model(model)

    def is_verified(self, model_id):
        return self._verify_model(self.catalog.get(model_id))

    def list_models(self):
        result = []
        with self._lock:
            states = {key: dict(value) for key, value in self._states.items()}
        for model in self.catalog.all():
            public = {key: value for key, value in model.items() if key not in {"url", "checksum"}}
            state = states.get(model["id"], {})
            public.update(
                installed=self._installed(model),
                download_status=state.get("status", "idle"),
                downloaded_bytes=state.get("downloaded_bytes", 0),
                error=state.get("error"),
            )
            result.append(public)
        return result

    def start(self, model_id):
        model = self.catalog.get(model_id)
        if self._installed(model):
            return
        with self._lock:
            state = self._states.get(model_id)
            if state and state.get("status") == "downloading":
                return
            cancel_event = threading.Event()
            self._cancel_events[model_id] = cancel_event
            self._states[model_id] = {
                "status": "downloading",
                "downloaded_bytes": 0,
                "error": None,
            }
        thread = threading.Thread(
            target=self._download,
            args=(model, cancel_event),
            name=f"image-model-{model_id}",
            daemon=True,
        )
        thread.start()

    def cancel(self, model_id):
        self.catalog.get(model_id)
        with self._lock:
            event = self._cancel_events.get(model_id)
        if event is not None:
            event.set()

    def verify(self, model_id):
        model = self.catalog.get(model_id)
        return self._verify_model(model, force=True, remove_invalid=True)

    def _set_state(self, model_id, **values):
        with self._lock:
            self._states.setdefault(model_id, {}).update(values)

    def _download(self, model, cancel_event):
        model_id = model["id"]
        final_path = self.catalog.model_path(self.model_root, model)
        part_path = final_path + ".part"
        algorithm, expected = self._checksum_parts(model["checksum"])
        digest = hashlib.new(algorithm)
        downloaded = 0
        try:
            os.makedirs(self.model_root, exist_ok=True)
            request = urllib.request.Request(
                model["url"],
                headers={"User-Agent": "ToolsHub-ImageUniversalTools/0.1"},
            )
            with urllib.request.urlopen(request, timeout=30, context=ssl.create_default_context()) as response:
                with open(part_path, "wb") as target:
                    while True:
                        if cancel_event.is_set():
                            raise InterruptedError("ยกเลิกการดาวน์โหลดแล้ว")
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        target.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        if downloaded > int(model["size_bytes"]):
                            raise ValueError("ขนาดไฟล์โมเดลเกิน catalog")
                        self._set_state(model_id, downloaded_bytes=downloaded)
            if downloaded != int(model["size_bytes"]):
                raise ValueError("ขนาดไฟล์โมเดลไม่ตรงกับ catalog")
            if digest.hexdigest().lower() != expected:
                raise ValueError("checksum ของโมเดลไม่ถูกต้อง")
            os.replace(part_path, final_path)
            fingerprint = self._fingerprint(final_path)
            with self._lock:
                self._verification_cache[model_id] = (fingerprint, True)
            self._set_state(model_id, status="completed", downloaded_bytes=downloaded, error=None)
        except InterruptedError as error:
            self._set_state(model_id, status="cancelled", error=str(error))
        except Exception as error:
            self._set_state(model_id, status="failed", error=str(error))
        finally:
            try:
                os.remove(part_path)
            except FileNotFoundError:
                pass
            with self._lock:
                self._cancel_events.pop(model_id, None)
