"""Opaque, atomic upload storage."""

from dataclasses import dataclass
import os
from pathlib import Path
import threading
import uuid

from .validation import ALLOWED_EXTENSIONS, ValidationError


MAX_UPLOAD_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class UploadRecord:
    id: str
    original_name: str
    path: str
    size: int


class UploadStore:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self._records = {}
        self._lock = threading.RLock()

    def save(self, storage):
        original_name = os.path.basename(str(storage.filename or ""))
        suffix = Path(original_name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise ValidationError("รองรับเฉพาะ PNG, JPEG, WebP, BMP และ TIFF")
        upload_id = uuid.uuid4().hex
        final_path = os.path.join(self.root, upload_id + suffix)
        part_path = final_path + ".part"
        total = 0
        try:
            with open(part_path, "xb") as target:
                while True:
                    chunk = storage.stream.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise ValidationError("ไฟล์มีขนาดเกิน 200 MB")
                    target.write(chunk)
            if total == 0:
                raise ValidationError("ไฟล์ว่างเปล่า")
            os.replace(part_path, final_path)
        except Exception:
            try:
                os.remove(part_path)
            except FileNotFoundError:
                pass
            raise
        record = UploadRecord(upload_id, original_name, final_path, total)
        with self._lock:
            self._records[upload_id] = record
        return record

    def claim(self, upload_id):
        if not isinstance(upload_id, str):
            raise ValidationError("upload id ไม่ถูกต้อง")
        with self._lock:
            record = self._records.pop(upload_id, None)
        if record is None or not os.path.isfile(record.path):
            raise ValidationError("ไม่พบไฟล์อัปโหลดหรือไฟล์ถูกนำไปเข้าคิวแล้ว")
        return record

    def restore(self, record):
        if os.path.isfile(record.path):
            with self._lock:
                self._records[record.id] = record

    def discard(self, upload_ids):
        if not isinstance(upload_ids, list):
            raise ValidationError("upload ids ไม่ถูกต้อง")
        discarded = 0
        for upload_id in upload_ids:
            with self._lock:
                record = self._records.pop(upload_id, None)
            if record is None:
                continue
            try:
                os.remove(record.path)
            except FileNotFoundError:
                pass
            discarded += 1
        return discarded

    def delete(self, record):
        with self._lock:
            self._records.pop(record.id, None)
        try:
            os.remove(record.path)
        except FileNotFoundError:
            pass

    def close(self):
        with self._lock:
            records = list(self._records.values())
            self._records.clear()
        for record in records:
            try:
                os.remove(record.path)
            except FileNotFoundError:
                pass
