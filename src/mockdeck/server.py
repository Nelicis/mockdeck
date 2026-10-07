"""HTTP Server & REST Request Router with CORS and Simulation Middleware."""

from __future__ import annotations
import json
import random
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from mockdeck.store import DataStore


def _parse_delay(delay_spec: str | int | float) -> tuple[float, float]:
    """Parses delay string or number into (min_seconds, max_seconds)."""
    if isinstance(delay_spec, (int, float)):
        sec = max(0.0, float(delay_spec) / 1000.0)
        return sec, sec

    spec = str(delay_spec).strip()
    if not spec:
        return 0.0, 0.0

    if "-" in spec:
        parts = spec.split("-", 1)
        try:
            min_ms = float(parts[0])
            max_ms = float(parts[1])
            return max(0.0, min_ms / 1000.0), max(0.0, max_ms / 1000.0)
        except ValueError:
            return 0.0, 0.0
    else:
        try:
            ms = float(spec)
            sec = max(0.0, ms / 1000.0)
            return sec, sec
        except ValueError:
            return 0.0, 0.0


class MockRequestHandler(BaseHTTPRequestHandler):
    server: MockServer

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress default stdlib stderr logging
        pass

    def _apply_middleware(self) -> bool:
        """Applies latency and chaos fault injection. Returns False if aborted by chaos."""
        min_sec, max_sec = self.server.delay_range
        if max_sec > 0:
            delay = random.uniform(min_sec, max_sec) if max_sec > min_sec else min_sec
            time.sleep(delay)

        if self.server.chaos > 0 and random.random() < self.server.chaos:
            self._send_json(500, {
                "error": "Chaos Monkey: Simulated Internal Server Error",
                "status": 500
            })
            return False
        return True

    def _read_json_body(self) -> tuple[bool, Any]:
        """Reads request body and parses JSON. Returns (success, data_or_error_msg)."""
        raw_header = self.headers.get("Content-Length", 0)
        try:
            content_len = int(raw_header)
        except (ValueError, TypeError):
            return False, "Invalid Content-Length header"

        if content_len == 0:
            return True, {}
        try:
            raw = self.rfile.read(content_len).decode("utf-8")
            return True, json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False, "Invalid JSON body"

    def _send_json(
        self,
        status: int,
        data: Any = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        body_bytes = b""
        if data is not None:
            body_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")

        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        if data is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body_bytes)))

        if headers:
            for k, v in headers.items():
                self.send_header(k, str(v))
            expose = ", ".join(headers.keys())
            self.send_header("Access-Control-Expose-Headers", expose)

        self.end_headers()
        if body_bytes:
            self.wfile.write(body_bytes)

        duration_ms = (time.perf_counter() - self._start_time) * 1000
        if self.server.on_request:
            client_ip = self.client_address[0] if self.client_address else "127.0.0.1"
            self.server.on_request(self.command, self.path, status, duration_ms, client_ip)

    def do_OPTIONS(self) -> None:
        self._start_time = time.perf_counter()
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        duration_ms = (time.perf_counter() - self._start_time) * 1000
        if self.server.on_request:
            client_ip = self.client_address[0] if self.client_address else "127.0.0.1"
            self.server.on_request("OPTIONS", self.path, 204, duration_ms, client_ip)

    def do_GET(self) -> None:
        self._start_time = time.perf_counter()
        if not self._apply_middleware():
            return

        parsed = urllib.parse.urlparse(self.path)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        params = urllib.parse.parse_qs(parsed.query)

        if len(parts) == 0:
            # Root index: return resource overview
            resources = self.server.store.get_resources()
            self._send_json(200, {
                "message": "mockdeck server running",
                "resources": resources
            })
            return

        resource = parts[0]
        if len(parts) == 1:
            items, meta = self.server.store.query_collection(resource, params)
            if items is None:
                self._send_json(404, {"error": f"Resource '{resource}' not found"})
                return
            self._send_json(200, items, headers=meta)
            return

        if len(parts) == 2:
            item_id = parts[1]
            item = self.server.store.get_item(resource, item_id)
            if item is None:
                self._send_json(404, {"error": f"Item '{item_id}' not found in '{resource}'"})
                return
            self._send_json(200, item)
            return

        self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        self._start_time = time.perf_counter()
        if not self._apply_middleware():
            return

        parsed = urllib.parse.urlparse(self.path)
        parts = [p for p in parsed.path.strip("/").split("/") if p]

        if len(parts) != 1:
            self._send_json(404, {"error": "Endpoint not found"})
            return

        resource = parts[0]
        success, body = self._read_json_body()
        if not success or not isinstance(body, dict):
            msg = body if isinstance(body, str) else "Invalid JSON body"
            self._send_json(400, {"error": msg})
            return

        try:
            created = self.server.store.create_item(resource, body)
            self._send_json(201, created)
        except PermissionError as e:
            self._send_json(403, {"error": str(e)})

    def do_PUT(self) -> None:
        self._start_time = time.perf_counter()
        if not self._apply_middleware():
            return

        parsed = urllib.parse.urlparse(self.path)
        parts = [p for p in parsed.path.strip("/").split("/") if p]

        if len(parts) != 2:
            self._send_json(404, {"error": "Endpoint not found"})
            return

        resource, item_id = parts[0], parts[1]
        success, body = self._read_json_body()
        if not success or not isinstance(body, dict):
            msg = body if isinstance(body, str) else "Invalid JSON body"
            self._send_json(400, {"error": msg})
            return

        try:
            updated = self.server.store.update_item(resource, item_id, body, partial=False)
            if updated is None:
                self._send_json(404, {"error": f"Item '{item_id}' not found in '{resource}'"})
                return
            self._send_json(200, updated)
        except PermissionError as e:
            self._send_json(403, {"error": str(e)})

    def do_PATCH(self) -> None:
        self._start_time = time.perf_counter()
        if not self._apply_middleware():
            return

        parsed = urllib.parse.urlparse(self.path)
        parts = [p for p in parsed.path.strip("/").split("/") if p]

        if len(parts) != 2:
            self._send_json(404, {"error": "Endpoint not found"})
            return

        resource, item_id = parts[0], parts[1]
        success, body = self._read_json_body()
        if not success or not isinstance(body, dict):
            msg = body if isinstance(body, str) else "Invalid JSON body"
            self._send_json(400, {"error": msg})
            return

        try:
            updated = self.server.store.update_item(resource, item_id, body, partial=True)
            if updated is None:
                self._send_json(404, {"error": f"Item '{item_id}' not found in '{resource}'"})
                return
            self._send_json(200, updated)
        except PermissionError as e:
            self._send_json(403, {"error": str(e)})

    def do_DELETE(self) -> None:
        self._start_time = time.perf_counter()
        if not self._apply_middleware():
            return

        parsed = urllib.parse.urlparse(self.path)
        parts = [p for p in parsed.path.strip("/").split("/") if p]

        if len(parts) != 2:
            self._send_json(404, {"error": "Endpoint not found"})
            return

        resource, item_id = parts[0], parts[1]
        try:
            deleted = self.server.store.delete_item(resource, item_id)
            if not deleted:
                self._send_json(404, {"error": f"Item '{item_id}' not found in '{resource}'"})
                return
            self._send_json(204)
        except PermissionError as e:
            self._send_json(403, {"error": str(e)})


class MockServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[BaseHTTPRequestHandler],
        store: DataStore,
        delay: str | int | float = 0,
        chaos: float = 0.0,
        on_request: Callable[[str, str, int, float, str], None] | None = None,
    ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.store = store
        self.delay_range = _parse_delay(delay)
        self.chaos = max(0.0, min(1.0, float(chaos)))
        self.on_request = on_request


def create_server(
    store: DataStore,
    host: str = "127.0.0.1",
    port: int = 8000,
    delay: str | int | float = 0,
    chaos: float = 0.0,
    on_request: Callable[[str, str, int, float, str], None] | None = None,
) -> MockServer:
    """Creates a ThreadingHTTPServer configured with mockdeck REST routing."""
    return MockServer(
        (host, port),
        MockRequestHandler,
        store=store,
        delay=delay,
        chaos=chaos,
        on_request=on_request,
    )
