# mockdeck Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and package `mockdeck`, a zero-config Python CLI tool that serves instant mock REST APIs from JSON files with CRUD, filtering, pagination, chaos simulation, and Rich terminal output.

**Architecture:** A lightweight, thread-safe in-memory `DataStore` manages JSON collections and handles queries/mutations with atomic disk flushes. Python's standard library `ThreadingHTTPServer` dispatches requests through middleware (CORS, latency jitter, chaos fault injection) to resource handlers, while `rich` formats console startup tables and live HTTP logs.

**Tech Stack:** Python 3.10+, `http.server.ThreadingHTTPServer`, `rich>=13.0.0`, standard library (`argparse`, `json`, `urllib.request`, `unittest`).

**Spec:** `docs/superpowers/specs/2026-10-05-mockdeck-design.md`

## Global Constraints

- **Python Version Floor:** Python 3.10+.
- **Zero Heavy Web Frameworks:** Must run using Python's standard library `http.server` without external network runtimes (no uvicorn, starlette, flask, fastapi).
- **Single Runtime Dependency:** The only external runtime dependency is `rich>=13.0.0`.
- **Test Framework:** Python's built-in `unittest` runner (`python -m unittest discover -s tests`).
- **Atomic File Persistence:** Disk saves must write to a `.tmp` file first and use `os.replace` to prevent corrupted data files.

## Review Focus

1. **Auto ID Assignment:** When `POST /resource` receives a payload without an `id`, it auto-generates the next sequential integer `max(ids) + 1` (or UUID if existing IDs are strings).
2. **Invalid JSON Body:** If `POST`, `PUT`, or `PATCH` receives malformed JSON, return `400 Bad Request` with `{"error": "Invalid JSON body"}`.
3. **Read-Only Enforcement:** When `--read-only` is active, all mutating operations (`POST`, `PUT`, `PATCH`, `DELETE`) return `403 Forbidden` with `{"error": "Server is in read-only mode"}`.
4. **Non-Existent Resources:** Requests to an unmapped collection (`GET /unknown_collection`) return `404 Not Found` with `{"error": "Resource 'unknown_collection' not found"}`.
5. **Port In Use Graceful Error:** When socket binding encounters `OSError` (`EADDRINUSE` / `10048`), catch it and output a clean recommendation rather than crashing with an unhandled traceback.

---

### Task 1: Project Scaffolding & Packaging

**Files:**
- Create: `pyproject.toml`
- Create: `src/mockdeck/__init__.py`
- Test: `tests/__init__.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces: Package `mockdeck` version `0.1.0` importable via standard python path.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
import unittest

class TestSmoke(unittest.TestCase):
    def test_import_mockdeck(self):
        import mockdeck
        self.assertEqual(mockdeck.__version__, "0.1.0")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_smoke.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'mockdeck'`

- [ ] **Step 3: Create `pyproject.toml` and `src/mockdeck/__init__.py`**

Define package configuration in `pyproject.toml` with `dependencies = ["rich>=13.0.0"]` and CLI entry point `[project.scripts] mockdeck = "mockdeck.cli:main"`. Set `__version__ = "0.1.0"` in `src/mockdeck/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_smoke.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/mockdeck/__init__.py tests/__init__.py tests/test_smoke.py
git commit -m "chore: scaffold project packaging and package metadata"
```

---

### Task 2: DataStore Core & CRUD Operations

**Files:**
- Create: `src/mockdeck/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: Built-in `json`, `os`, `copy`, `threading`.
- Produces: `DataStore(filepath: str | None, read_only: bool = False, no_save: bool = False)`
  - `store.get_resources() -> dict[str, int]` (resource names and item counts)
  - `store.get_collection(resource: str) -> list[dict] | None`
  - `store.get_item(resource: str, item_id: str | int) -> dict | None`
  - `store.create_item(resource: str, item: dict) -> dict`
  - `store.update_item(resource: str, item_id: str | int, new_data: dict, partial: bool = False) -> dict | None`
  - `store.delete_item(resource: str, item_id: str | int) -> bool`
  - `store.save()` (flushes to disk atomically)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store.py
import unittest
import tempfile
import os
import json
from mockdeck.store import DataStore

class TestDataStoreCore(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
        data = {
            "users": [
                {"id": 1, "name": "Alice", "role": "admin"},
                {"id": 2, "name": "Bob", "role": "user"}
            ]
        }
        json.dump(data, self.temp_file)
        self.temp_file.close()
        self.store = DataStore(filepath=self.temp_file.name)

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def test_get_collection(self):
        users = self.store.get_collection("users")
        self.assertEqual(len(users), 2)
        self.assertIsNone(self.store.get_collection("unknown"))

    def test_get_item(self):
        user = self.store.get_item("users", 1)
        self.assertIsNotNone(user)
        self.assertEqual(user["name"], "Alice")
        self.assertIsNone(self.store.get_item("users", 99))

    def test_create_item_auto_id(self):
        new_user = self.store.create_item("users", {"name": "Charlie", "role": "user"})
        self.assertEqual(new_user["id"], 3)
        self.assertEqual(len(self.store.get_collection("users")), 3)

    def test_update_item_full_and_partial(self):
        # Full replacement (PUT)
        updated = self.store.update_item("users", 2, {"name": "Robert"}, partial=False)
        self.assertEqual(updated, {"id": 2, "name": "Robert"})
        
        # Partial update (PATCH)
        patched = self.store.update_item("users", 1, {"name": "Alicia"}, partial=True)
        self.assertEqual(patched["name"], "Alicia")
        self.assertEqual(patched["role"], "admin")

    def test_delete_item(self):
        deleted = self.store.delete_item("users", 1)
        self.assertTrue(deleted)
        self.assertIsNone(self.store.get_item("users", 1))
        self.assertFalse(self.store.delete_item("users", 99))

    def test_atomic_persistence(self):
        self.store.create_item("users", {"name": "Eve"})
        with open(self.temp_file.name, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        self.assertEqual(len(disk_data["users"]), 3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_store.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'mockdeck.store'`

- [ ] **Step 3: Implement `DataStore` in `src/mockdeck/store.py`**

Implement thread-safe in-memory operations with `threading.Lock()`. Handle ID generation by checking existing integer IDs (defaulting to `max(ids) + 1`) or generating UUID4 hex strings if existing IDs are strings. Implement `save()` using atomic temp file replacement (`tempfile.NamedTemporaryFile` + `os.replace`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_store.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mockdeck/store.py tests/test_store.py
git commit -m "feat: implement DataStore core CRUD and atomic persistence"
```

---

### Task 3: DataStore Query Engine (Filtering, Sorting, Pagination, Search)

**Files:**
- Modify: `src/mockdeck/store.py`
- Modify: `tests/test_store.py`

**Interfaces:**
- Consumes: `DataStore` from Task 2.
- Produces: `store.query_collection(resource: str, params: dict[str, list[str]]) -> tuple[list[dict], dict[str, int]]`
  - Returns `(paginated_items, metadata_headers)`
  - Metadata includes: `X-Total-Count`, `X-Page`, `X-Total-Pages`

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_store.py
    def test_query_filter_exact(self):
        items, meta = self.store.query_collection("users", {"role": ["admin"]})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Alice")
        self.assertEqual(meta["X-Total-Count"], 1)

    def test_query_sorting(self):
        items_asc, _ = self.store.query_collection("users", {"_sort": ["name"], "_order": ["asc"]})
        self.assertEqual([i["name"] for i in items_asc], ["Alice", "Bob"])

        items_desc, _ = self.store.query_collection("users", {"_sort": ["name"], "_order": ["desc"]})
        self.assertEqual([i["name"] for i in items_desc], ["Bob", "Alice"])

    def test_query_pagination(self):
        # Seed extra items
        for i in range(3, 11):
            self.store.create_item("users", {"name": f"User {i}", "role": "user"})
        
        items, meta = self.store.query_collection("users", {"_page": ["2"], "_limit": ["3"]})
        self.assertEqual(len(items), 3)
        self.assertEqual(meta["X-Total-Count"], 10)
        self.assertEqual(meta["X-Page"], 2)
        self.assertEqual(meta["X-Total-Pages"], 4)

    def test_query_full_text_search(self):
        items, _ = self.store.query_collection("users", {"q": ["lic"]})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Alice")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_store.py`
Expected: FAIL with `AttributeError: 'DataStore' object has no attribute 'query_collection'`

- [ ] **Step 3: Implement `query_collection` in `src/mockdeck/store.py`**

Add filtering for normal keys, sorting by `_sort` with `_order` (`asc`/`desc`), pagination math (`_page`, `_limit`), and substring search `q` checking all string values in item. Return matching slice and headers dictionary.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_store.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mockdeck/store.py tests/test_store.py
git commit -m "feat: implement query engine with filtering, sorting, pagination, and text search"
```

---

### Task 4: HTTP Server, REST Router & Middleware

**Files:**
- Create: `src/mockdeck/server.py`
- Create: `tests/test_server.py`

**Interfaces:**
- Consumes: `DataStore` from Task 2 & 3.
- Produces: `create_server(store: DataStore, host: str = "127.0.0.1", port: int = 8000, delay: str | int = 0, chaos: float = 0.0, on_request = None) -> ThreadingHTTPServer`
  - REST handler supporting `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`.
  - Injects CORS headers on every response.
  - Implements delay simulation (fixed or range jitter).
  - Implements chaos failure injection (returns 500 when triggered).
  - Handles 400 (bad json), 403 (read-only), 404 (not found).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server.py
import unittest
import threading
import json
import urllib.request
import urllib.error
import tempfile
import os
from mockdeck.store import DataStore
from mockdeck.server import create_server

class TestMockServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
        json.dump({"items": [{"id": 1, "title": "Item 1"}]}, cls.temp_file)
        cls.temp_file.close()

        cls.store = DataStore(filepath=cls.temp_file.name)
        cls.server = create_server(cls.store, host="127.0.0.1", port=0)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        if os.path.exists(cls.temp_file.name):
            os.remove(cls.temp_file.name)

    def test_get_collection_and_cors(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/items")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            data = json.loads(resp.read().decode())
            self.assertEqual(len(data), 1)

    def test_post_item_and_auto_id(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/items",
            data=json.dumps({"title": "Item 2"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 201)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["id"], 2)
            self.assertEqual(data["title"], "Item 2")

    def test_options_cors_preflight(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/items", method="OPTIONS")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 204)
            self.assertIn("GET", resp.headers.get("Access-Control-Allow-Methods", ""))

    def test_not_found(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/unknown")
        self.assertEqual(ctx.exception.code, 404)

    def test_bad_json_payload(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/items",
            data=b"not-a-json",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_server.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'mockdeck.server'`

- [ ] **Step 3: Implement `create_server` & `MockRequestHandler` in `src/mockdeck/server.py`**

Subclass `http.server.BaseHTTPRequestHandler` with URL parser (`urllib.parse`), request dispatcher, delay parser/sleep, chaos threshold checker, JSON response helper, and thread-safe request lifecycle handling.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_server.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mockdeck/server.py tests/test_server.py
git commit -m "feat: implement HTTP server, REST router, CORS, and simulation middleware"
```

---

### Task 5: Rich Terminal UI & Traffic Logger

**Files:**
- Create: `src/mockdeck/tui.py`
- Modify: `src/mockdeck/server.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: `rich.console.Console`, `rich.table.Table`, `rich.panel.Panel`.
- Produces:
  - `print_startup_banner(host: str, port: int, resources: dict[str, int], delay: str | int, chaos: float, read_only: bool)`
  - `log_request(method: str, path: str, status: int, duration_ms: float, client_ip: str)`

- [ ] **Step 1: Write test for logger hook invocation**

```python
# Add to tests/test_server.py
    def test_request_logger_hook(self):
        logged_calls = []
        def on_req(method, path, status, duration_ms, client_ip):
            logged_calls.append((method, path, status))

        server = create_server(self.store, host="127.0.0.1", port=0, on_request=on_req)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/items")
            self.assertEqual(len(logged_calls), 1)
            self.assertEqual(logged_calls[0][0], "GET")
            self.assertEqual(logged_calls[0][2], 200)
        finally:
            server.shutdown()
            server.server_close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_server.py`
Expected: FAIL or passes if `on_request` parameter already stubbed.

- [ ] **Step 3: Implement `tui.py` with Rich components**

Implement `print_startup_banner` displaying title, server address, configuration table, and resource endpoints table. Implement `log_request` printing timestamped badge-colored status lines (`GET` in cyan, `POST` in green, `2xx` in green, `4xx` in yellow, `5xx` in red, with execution time in ms).

- [ ] **Step 4: Run tests to verify everything passes**

Run: `python -m unittest discover -s tests`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mockdeck/tui.py src/mockdeck/server.py tests/test_server.py
git commit -m "feat: implement Rich terminal startup dashboard and live traffic logger"
```

---

### Task 6: CLI Interface, `init` Generator & Error Handling

**Files:**
- Create: `src/mockdeck/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `cli.py` orchestrates `store.py`, `server.py`, and `tui.py`.
- Produces: `main(args: list[str] | None = None) -> int`
  - `mockdeck init [FILE]`
  - `mockdeck serve [FILE] [--port] [--host] [--delay] [--chaos] [--read-only] [--no-save] [--quiet]`

- [ ] **Step 1: Write CLI command tests**

```python
# tests/test_cli.py
import unittest
import tempfile
import os
import json
from mockdeck.cli import main

class TestCLI(unittest.TestCase):
    def test_cli_init_generates_valid_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "test_db.json")
            ret = main(["init", target])
            self.assertEqual(ret, 0)
            self.assertTrue(os.path.exists(target))
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("users", data)
            self.assertIn("posts", data)
            self.assertIn("products", data)

    def test_cli_init_does_not_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "test_db.json")
            with open(target, "w", encoding="utf-8") as f:
                f.write('{"custom": []}')
            ret = main(["init", target])
            self.assertEqual(ret, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_cli.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'mockdeck.cli'`

- [ ] **Step 3: Implement `cli.py`**

Parse arguments with `argparse`. Handle `init` by writing starter dataset. Handle `serve` by catching `FileNotFoundError`, `json.JSONDecodeError`, and `OSError` (port conflicts) with formatted user advice.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mockdeck/cli.py tests/test_cli.py
git commit -m "feat: implement CLI commands init, serve, and error handling"
```

---

### Task 7: Documentation, Example Dataset & Final Validation

**Files:**
- Create: `README.md`
- Create: `.gitignore`
- Modify: `tests/test_server.py`

**Interfaces:**
- Produces: Full documentation, GitHub repo presentation with usage badges, quickstart guide, and end-to-end regression validation.

- [ ] **Step 1: Write `.gitignore` and `README.md`**

Include installation instructions, quickstart guide (`mockdeck init`, `mockdeck serve`), query parameter reference (`_sort`, `_page`, `_limit`, `q`), chaos options, and example `curl` commands.

- [ ] **Step 2: Run full test suite**

Run: `python -m unittest discover -s tests -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add README.md .gitignore docs/
git commit -m "docs: add comprehensive README with quickstart and API reference"
```
