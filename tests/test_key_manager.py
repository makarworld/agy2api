import os
import tempfile
import unittest

from app.core import key_manager, stats_store
from app.main import app
from fastapi import HTTPException
from fastapi.testclient import TestClient


class TestKeyManager(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._temp_dir.name, "test_stats.db")
        stats_store.init_db(self.db_path)
        key_manager.init_keys_db()
        self._env = os.environ.copy()
        os.environ["AGY_API_KEY"] = "master-secret-123"
        self.client = TestClient(app)

    def tearDown(self):
        self._temp_dir.cleanup()
        os.environ.clear()
        os.environ.update(self._env)

    def test_master_key_validation(self):
        info = key_manager.validate_and_consume_key("master-secret-123")
        self.assertTrue(info.is_master)
        self.assertTrue(info.is_active)
        self.assertEqual(info.name, "Master Key")

    def test_create_and_validate_key(self):
        info = key_manager.create_key(
            name="test-key",
            expires_in_days=7,
            daily_output_limit=1000,
        )
        self.assertTrue(info.key.startswith("sk-agy-"))
        self.assertFalse(info.is_master)
        self.assertEqual(info.name, "test-key")
        self.assertEqual(info.daily_output_limit, 1000)

        validated = key_manager.validate_and_consume_key(info.key)
        self.assertEqual(validated.key, info.key)
        self.assertEqual(validated.used_output_today, 0)

    def test_record_output_tokens_and_limit(self):
        info = key_manager.create_key(
            name="limited-key",
            daily_output_limit=500,
        )
        key_manager.record_key_output_tokens(info.key, 300)
        validated = key_manager.validate_and_consume_key(info.key)
        self.assertEqual(validated.used_output_today, 300)

        key_manager.record_key_output_tokens(info.key, 250)
        with self.assertRaises(HTTPException) as ctx:
            key_manager.validate_and_consume_key(info.key)
        self.assertEqual(ctx.exception.status_code, 429)

    def test_toggle_and_delete_key(self):
        info = key_manager.create_key(name="toggle-key")

        # Toggle off
        updated = key_manager.toggle_key(info.key, is_active=False)
        self.assertFalse(updated["is_active"])
        with self.assertRaises(HTTPException) as ctx:
            key_manager.validate_and_consume_key(info.key)
        self.assertEqual(ctx.exception.status_code, 401)

        # Toggle on
        updated = key_manager.toggle_key(info.key, is_active=True)
        self.assertTrue(updated["is_active"])
        validated = key_manager.validate_and_consume_key(info.key)
        self.assertTrue(validated.is_active)

        # Delete
        self.assertTrue(key_manager.delete_key(info.key))
        with self.assertRaises(HTTPException) as ctx:
            key_manager.validate_and_consume_key(info.key)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_admin_keys_api_endpoints(self):
        master_header = {"Authorization": "Bearer master-secret-123"}
        unauth_header = {"Authorization": "Bearer invalid-key"}

        # 1. Unauthorized / Forbidden
        resp = self.client.get("/v1/admin/keys")
        self.assertEqual(resp.status_code, 401)
        resp = self.client.get("/v1/admin/keys", headers=unauth_header)
        self.assertEqual(resp.status_code, 403)

        # 2. Create key
        resp = self.client.post(
            "/v1/admin/keys",
            json={"name": "agent-key", "daily_output_limit": 5000},
            headers=master_header,
        )
        self.assertEqual(resp.status_code, 200)
        created = resp.json()
        self.assertEqual(created["status"], "ok")
        key_str = created["key"]["key"]
        self.assertEqual(created["key"]["daily_output_limit"], 5000)

        # 3. List keys
        resp = self.client.get("/v1/admin/keys", headers=master_header)
        self.assertEqual(resp.status_code, 200)
        keys = resp.json()["keys"]
        self.assertTrue(any(k["key"] == key_str for k in keys))

        # 4. Patch (toggle status)
        resp = self.client.patch(
            f"/v1/admin/keys/{key_str}",
            json={"is_active": False},
            headers=master_header,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["key"]["is_active"])

        # 5. Delete key
        resp = self.client.delete(f"/v1/admin/keys/{key_str}", headers=master_header)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["deleted"], key_str)

        # 6. Verify deleted
        resp = self.client.get("/v1/admin/keys", headers=master_header)
        keys = resp.json()["keys"]
        self.assertFalse(any(k["key"] == key_str for k in keys))


if __name__ == "__main__":
    unittest.main()
