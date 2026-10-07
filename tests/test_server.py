import unittest
import threading
import json
import urllib.request
import urllib.error
import tempfile
import os
import time
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
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["id"], 1)

    def test_get_single_item(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/items/1")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["title"], "Item 1")

    def test_post_item_and_auto_id(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/items",
            data=json.dumps({"title": "Item 2"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 201)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["id"], 2)
            self.assertEqual(data["title"], "Item 2")

    def test_put_item(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/items/1",
            data=json.dumps({"title": "Item 1 Replaced"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["title"], "Item 1 Replaced")

    def test_patch_item(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/items/1",
            data=json.dumps({"extra": "value"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PATCH"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["extra"], "value")
            self.assertEqual(data["id"], 1)

    def test_delete_item(self):
        # Create item to delete
        self.store.create_item("items", {"id": 999, "title": "To Delete"})
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/items/999", method="DELETE")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 204)

        # Verify it's deleted
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/items/999")
        self.assertEqual(ctx.exception.code, 404)

    def test_options_cors_preflight(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/items", method="OPTIONS")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 204)
            self.assertIn("GET", resp.headers.get("Access-Control-Allow-Methods", ""))
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")

    def test_not_found_collection(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/unknown_collection")
        self.assertEqual(ctx.exception.code, 404)
        err = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertIn("error", err)

    def test_bad_json_payload(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/items",
            data=b"not-a-valid-json",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)
        err = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual(err["error"], "Invalid JSON body")

    def test_read_only_server(self):
        ro_store = DataStore(filepath=None, initial_data={"items": [{"id": 1}]}, read_only=True)
        ro_server = create_server(ro_store, host="127.0.0.1", port=0)
        ro_port = ro_server.server_address[1]
        t = threading.Thread(target=ro_server.serve_forever, daemon=True)
        t.start()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{ro_port}/items",
                data=json.dumps({"name": "Forbidden"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 403)
        finally:
            ro_server.shutdown()
            ro_server.server_close()

    def test_delay_simulation(self):
        store = DataStore(filepath=None, initial_data={"items": [{"id": 1}]})
        server = create_server(store, host="127.0.0.1", port=0, delay=100)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            start = time.time()
            urllib.request.urlopen(f"http://127.0.0.1:{port}/items")
            elapsed_ms = (time.time() - start) * 1000
            self.assertGreaterEqual(elapsed_ms, 90)
        finally:
            server.shutdown()
            server.server_close()

    def test_chaos_fault_injection(self):
        store = DataStore(filepath=None, initial_data={"items": [{"id": 1}]})
        server = create_server(store, host="127.0.0.1", port=0, chaos=1.0)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/items")
            self.assertEqual(ctx.exception.code, 500)
            err = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertIn("Chaos Monkey", err["error"])
        finally:
            server.shutdown()
            server.server_close()

if __name__ == "__main__":
    unittest.main()
