"""Immutable background-removal model catalog."""

import json
import os


class ModelCatalog:
    def __init__(self, catalog_path):
        with open(catalog_path, "r", encoding="utf-8") as source:
            payload = json.load(source)
        if payload.get("catalog_version") != 1 or not isinstance(payload.get("models"), list):
            raise ValueError("unsupported model catalog")
        self._models = {item["id"]: dict(item) for item in payload["models"]}

    def get(self, model_id):
        model = self._models.get(model_id)
        if model is None:
            raise KeyError(model_id)
        return dict(model)

    def all(self):
        return [dict(model) for model in self._models.values()]

    @staticmethod
    def model_path(model_root, model):
        return os.path.join(os.path.abspath(model_root), model["file_name"])
