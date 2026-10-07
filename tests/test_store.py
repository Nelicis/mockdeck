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

    def test_query_unknown_collection(self):
        items, meta = self.store.query_collection("unknown", {})
        self.assertIsNone(items)
        self.assertEqual(meta, {})

    def test_query_filter_absent_field(self):
        # Create an item without the 'role' field
        self.store.create_item("users", {"name": "NoRoleUser"})
        # Querying for empty role should not match the user who doesn't even have a 'role' key
        items, _ = self.store.query_collection("users", {"role": [""]})
        self.assertEqual(len(items), 0)

        # Querying for role="none" should not match None
        items_none, _ = self.store.query_collection("users", {"role": ["none"]})
        self.assertEqual(len(items_none), 0)

if __name__ == "__main__":
    unittest.main()
