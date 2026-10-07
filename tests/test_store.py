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

    def test_get_resources(self):
        resources = self.store.get_resources()
        self.assertEqual(resources, {"users": 2})

    def test_get_collection(self):
        users = self.store.get_collection("users")
        self.assertEqual(len(users), 2)
        self.assertIsNone(self.store.get_collection("unknown"))

    def test_get_item(self):
        user = self.store.get_item("users", 1)
        self.assertIsNotNone(user)
        self.assertEqual(user["name"], "Alice")
        self.assertIsNone(self.store.get_item("users", 99))

    def test_get_item_string_id(self):
        self.store.create_item("users", {"id": "custom-uuid", "name": "Dave"})
        user = self.store.get_item("users", "custom-uuid")
        self.assertIsNotNone(user)
        self.assertEqual(user["name"], "Dave")

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

    def test_read_only_mode(self):
        ro_store = DataStore(filepath=self.temp_file.name, read_only=True)
        with self.assertRaises(PermissionError):
            ro_store.create_item("users", {"name": "Blocked"})

    def test_no_save_mode(self):
        ns_store = DataStore(filepath=self.temp_file.name, no_save=True)
        ns_store.create_item("users", {"name": "MemoryOnly"})
        with open(self.temp_file.name, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        self.assertEqual(len(disk_data["users"]), 2)

if __name__ == "__main__":
    unittest.main()
