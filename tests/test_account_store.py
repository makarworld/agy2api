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


if __name__ == "__main__":
    unittest.main()
