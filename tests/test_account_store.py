import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import account_store, db


class TestAccountStoreTokens(unittest.TestCase):
    def test_rejects_refresh_token_reused_by_another_account(self):
        tmp = tempfile.mkdtemp()
        try:
            db_path = str(Path(tmp) / "accounts.db")
            with patch.object(account_store, "_DB_PATH", db_path), patch.object(db, "DB_PATH", db_path):
                account_store.upsert_account(
                    account_id="account-a",
                    email="a@example.com",
                    refresh_token="refresh-a",
                    access_token="access-a",
                )

                with self.assertRaisesRegex(ValueError, "already assigned"):
                    account_store.upsert_account(
                        account_id="account-b",
                        email="b@example.com",
                        refresh_token="refresh-a",
                        access_token="access-b",
                    )

                self.assertIsNone(account_store.get_account_by_id("account-b"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_allows_refresh_token_update_for_same_account(self):
        tmp = tempfile.mkdtemp()
        try:
            db_path = str(Path(tmp) / "accounts.db")
            with patch.object(account_store, "_DB_PATH", db_path), patch.object(db, "DB_PATH", db_path):
                account_store.upsert_account(
                    account_id="account-a",
                    email="a@example.com",
                    refresh_token="refresh-a",
                    access_token="access-a",
                )
                account_store.upsert_account(
                    account_id="account-a",
                    email="a@example.com",
                    refresh_token="refresh-b",
                    access_token="access-b",
                )

                account = account_store.get_account_by_id("account-a")
                self.assertEqual(account["refresh_token"], "refresh-b")
                self.assertEqual(account["access_token"], "access-b")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_stores_and_updates_account_profile_name_and_picture(self):
        tmp = tempfile.mkdtemp()
        try:
            db_path = str(Path(tmp) / "accounts.db")
            with patch.object(account_store, "_DB_PATH", db_path), patch.object(db, "DB_PATH", db_path):
                account_store.upsert_account(
                    account_id="acc-profile",
                    email="profile@example.com",
                    refresh_token="refresh-prof",
                    name="Test User",
                    picture="https://example.com/photo.jpg",
                )
                account = account_store.get_account_by_id("acc-profile")
                self.assertEqual(account["name"], "Test User")
                self.assertEqual(account["picture"], "https://example.com/photo.jpg")

                account_store.update_account_profile(
                    "acc-profile",
                    name="Updated User",
                    picture="https://example.com/new_photo.jpg",
                )
                account = account_store.get_account_by_id("acc-profile")
                self.assertEqual(account["name"], "Updated User")
                self.assertEqual(account["picture"], "https://example.com/new_photo.jpg")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sync_accounts_from_pool_manifest_prunes_duplicates(self):
        import json

        tmp = tempfile.mkdtemp()
        try:
            db_path = str(Path(tmp) / "accounts.db")
            pool_dir = Path(tmp) / "pool"
            pool_dir.mkdir()
            acc1_dir = pool_dir / "accounts" / "acc-1"
            acc2_dir = pool_dir / "accounts" / "acc-2"
            acc1_dir.mkdir(parents=True)
            acc2_dir.mkdir(parents=True)

            # Both share the same refresh_token
            creds = {"refresh_token": "shared-refresh-token", "access_token": "tok"}
            (acc1_dir / "oauth_creds.json").write_text(json.dumps(creds), encoding="utf-8")
            (acc2_dir / "oauth_creds.json").write_text(json.dumps(creds), encoding="utf-8")

            manifest = {
                "accounts": [
                    {"id": "acc-1", "email": "user@example.com"},
                    {"id": "acc-2", "email": "user@example.com"},
                ]
            }
            manifest_file = pool_dir / "accounts.json"
            manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

            with patch.object(account_store, "_DB_PATH", db_path), patch.object(db, "DB_PATH", db_path):
                count = account_store.sync_accounts_from_pool_manifest(str(pool_dir))
                self.assertEqual(count, 1)

                # acc-1 is kept, acc-2 duplicate is pruned from manifest and disk
                self.assertIsNotNone(account_store.get_account_by_id("acc-1"))
                self.assertIsNone(account_store.get_account_by_id("acc-2"))

                updated_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                self.assertEqual(len(updated_manifest["accounts"]), 1)
                self.assertEqual(updated_manifest["accounts"][0]["id"], "acc-1")
                self.assertFalse(acc2_dir.exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
