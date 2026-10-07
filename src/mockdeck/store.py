"""DataStore — In-memory REST resource manager with atomic disk persistence."""

from __future__ import annotations
import copy
import json
import os
import tempfile
import threading
import uuid
from typing import Any


class DataStore:
    def __init__(
        self,
        filepath: str | None = None,
        initial_data: dict[str, Any] | None = None,
        read_only: bool = False,
        no_save: bool = False,
    ) -> None:
        self.filepath = filepath
        self.read_only = read_only
        self.no_save = no_save
        self._lock = threading.Lock()
        self._data: dict[str, list[dict[str, Any]]] = {}

        if initial_data is not None:
            self._data = copy.deepcopy(initial_data)
        elif self.filepath and os.path.exists(self.filepath):
            with open(self.filepath, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    self._data = loaded
                else:
                    self._data = {}

    def get_resources(self) -> dict[str, int]:
        """Returns map of resource names and item counts."""
        with self._lock:
            resources: dict[str, int] = {}
            for key, val in self._data.items():
                if isinstance(val, list):
                    resources[key] = len(val)
            return resources

    def get_collection(self, resource: str) -> list[dict[str, Any]] | None:
        """Returns entire collection or None if not registered."""
        with self._lock:
            if resource not in self._data or not isinstance(self._data[resource], list):
                return None
            return copy.deepcopy(self._data[resource])

    def query_collection(
        self,
        resource: str,
        params: dict[str, list[str]],
    ) -> tuple[list[dict[str, Any]] | None, dict[str, int]]:
        """Filters, sorts, searches, and paginates a collection."""
        with self._lock:
            if resource not in self._data or not isinstance(self._data[resource], list):
                return None, {}

            items = copy.deepcopy(self._data[resource])

        # 1. Exact field filtering (exclude reserved keywords)
        reserved_keys = {"_sort", "_order", "_page", "_limit", "q"}
        for key, vals in params.items():
            if key in reserved_keys:
                continue
            lower_vals = [v.lower() for v in vals]
            items = [
                item
                for item in items
                if isinstance(item, dict) and str(item.get(key, "")).lower() in lower_vals
            ]

        # 2. Full-text search via 'q' parameter
        if "q" in params and params["q"]:
            search_term = params["q"][0].lower()
            filtered: list[dict[str, Any]] = []
            for item in items:
                matched = False
                for v in item.values():
                    if isinstance(v, (str, int, float, bool)) and search_term in str(v).lower():
                        matched = True
                        break
                if matched:
                    filtered.append(item)
            items = filtered

        total_count = len(items)
        metadata: dict[str, int] = {"X-Total-Count": total_count}

        # 3. Sorting via '_sort' and '_order'
        if "_sort" in params and params["_sort"]:
            sort_field = params["_sort"][0]
            order = params.get("_order", ["asc"])[0].lower()
            reverse = order == "desc"

            def sort_key(item: dict[str, Any]) -> Any:
                val = item.get(sort_field)
                return "" if val is None else val

            try:
                items.sort(key=sort_key, reverse=reverse)
            except TypeError:
                items.sort(key=lambda item: str(sort_key(item)), reverse=reverse)

        # 4. Pagination via '_page' and '_limit'
        if "_page" in params or "_limit" in params:
            try:
                page = max(1, int(params.get("_page", ["1"])[0]))
            except ValueError:
                page = 1

            try:
                limit = max(1, int(params.get("_limit", ["10"])[0]))
            except ValueError:
                limit = 10

            import math
            total_pages = max(1, math.ceil(total_count / limit))
            start_idx = (page - 1) * limit
            items = items[start_idx : start_idx + limit]

            metadata["X-Page"] = page
            metadata["X-Total-Pages"] = total_pages

        return items, metadata

    def get_item(self, resource: str, item_id: str | int) -> dict[str, Any] | None:
        """Finds a single item by id."""
        with self._lock:
            items = self._data.get(resource)
            if not isinstance(items, list):
                return None
            str_id = str(item_id)
            for item in items:
                if isinstance(item, dict) and str(item.get("id")) == str_id:
                    return copy.deepcopy(item)
            return None

    def create_item(self, resource: str, item: dict[str, Any]) -> dict[str, Any]:
        """Adds a new item to resource, auto-generating id if missing."""
        if self.read_only:
            raise PermissionError("Server is in read-only mode")

        with self._lock:
            if resource not in self._data or not isinstance(self._data[resource], list):
                self._data[resource] = []

            collection = self._data[resource]
            new_item = copy.deepcopy(item)

            if "id" not in new_item or new_item["id"] is None:
                new_item["id"] = self._generate_id(collection)

            collection.append(new_item)
            self._save_locked()
            return copy.deepcopy(new_item)

    def update_item(
        self,
        resource: str,
        item_id: str | int,
        new_data: dict[str, Any],
        partial: bool = False,
    ) -> dict[str, Any] | None:
        """Replaces (PUT) or merges (PATCH) an existing item."""
        if self.read_only:
            raise PermissionError("Server is in read-only mode")

        with self._lock:
            items = self._data.get(resource)
            if not isinstance(items, list):
                return None

            str_id = str(item_id)
            for idx, existing in enumerate(items):
                if isinstance(existing, dict) and str(existing.get("id")) == str_id:
                    orig_id = existing.get("id")
                    if partial:
                        updated = copy.deepcopy(existing)
                        updated.update(new_data)
                    else:
                        updated = copy.deepcopy(new_data)
                    if "id" not in new_data or new_data["id"] is None:
                        updated["id"] = orig_id
                    items[idx] = updated
                    self._save_locked()
                    return copy.deepcopy(updated)
            return None

    def delete_item(self, resource: str, item_id: str | int) -> bool:
        """Removes an item from resource."""
        if self.read_only:
            raise PermissionError("Server is in read-only mode")

        with self._lock:
            items = self._data.get(resource)
            if not isinstance(items, list):
                return False

            str_id = str(item_id)
            for idx, existing in enumerate(items):
                if isinstance(existing, dict) and str(existing.get("id")) == str_id:
                    items.pop(idx)
                    self._save_locked()
                    return True
            return False

    def save(self) -> None:
        """Flushes in-memory data to disk atomically."""
        with self._lock:
            self._save_locked()

    def _save_locked(self) -> None:
        if self.read_only or self.no_save or not self.filepath:
            return

        dir_name = os.path.dirname(os.path.abspath(self.filepath))
        os.makedirs(dir_name, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".mockdeck_tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, self.filepath)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    def _generate_id(self, collection: list[dict[str, Any]]) -> int | str:
        int_ids = [
            item["id"]
            for item in collection
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        ]
        if int_ids:
            return max(int_ids) + 1
        if len(collection) == 0:
            return 1
        return str(uuid.uuid4())
