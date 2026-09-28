"""Atomic output helper."""

import os
import uuid


class AtomicOutput:
    def __init__(self, final_path):
        self.final_path = os.path.abspath(final_path)
        self.temporary_path = f"{self.final_path}.{uuid.uuid4().hex}.part"

    def __enter__(self):
        os.makedirs(os.path.dirname(self.final_path), exist_ok=True)
        if os.path.exists(self.final_path):
            raise FileExistsError("output มีอยู่แล้ว")
        return self.temporary_path

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            if os.path.exists(self.final_path):
                try:
                    os.remove(self.temporary_path)
                except FileNotFoundError:
                    pass
                raise FileExistsError("output มีอยู่แล้ว")
            os.replace(self.temporary_path, self.final_path)
            return False
        try:
            os.remove(self.temporary_path)
        except FileNotFoundError:
            pass
        return False
