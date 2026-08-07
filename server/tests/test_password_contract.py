import os
from unittest import TestCase

from pydantic import ValidationError


os.environ.setdefault("DEV_MODE", "true")

from core.config import Settings
from routers.users import UpdateMeRequest


GENERATED_PASSWORD = "0123456789abcdef" * 4


class PasswordContractTests(TestCase):
    def test_update_username_preserves_format_contract(self):
        for username in ("user", "renamed_operator", "中文用户"):
            with self.subTest(username=username):
                self.assertEqual(UpdateMeRequest(username=username).username, username)

        for username in ("abc", "a" * 17, "bad name", "bad!"):
            with self.subTest(username=username), self.assertRaisesRegex(
                ValidationError, "Username format is incorrect"
            ):
                UpdateMeRequest(username=username)

    def test_update_password_accepts_generated_and_boundary_lengths(self):
        for password in ("a" * 8, GENERATED_PASSWORD, "z" * 128):
            with self.subTest(length=len(password)):
                self.assertEqual(UpdateMeRequest(password=password).password, password)

    def test_update_password_rejects_unsafe_lengths_and_whitespace(self):
        for password in ("", "a" * 7, "a" * 129, "safe passphrase", " " * 8):
            with self.subTest(password=repr(password)), self.assertRaises(
                ValidationError
            ):
                UpdateMeRequest(password=password)

    def test_production_accepts_generated_admin_password_but_rejects_weak_one(self):
        production = {
            "DEV_MODE": False,
            "DOMAIN_NAME": "example.com",
            "EMAIL_ADDRESS": "ops@example.com",
            "MONGODB_USERNAME": "hyac-root",
            "MONGODB_PASSWORD": "mongo-production-password",
            "S3_ACCESS_KEY": "production-access-key",
            "S3_SECRET_KEY": "production-secret-key",
            "SECRET_KEY": "production-jwt-secret-with-at-least-32-characters",
            "DEFAULT_ADMIN_USER": "admin",
            "DEFAULT_ADMIN_PASSWORD": GENERATED_PASSWORD,
            "APP_IMAGE_TAG": "release-password-contract",
        }

        self.assertEqual(
            Settings(**production).DEFAULT_ADMIN_PASSWORD,
            GENERATED_PASSWORD,
        )
        production["DEFAULT_ADMIN_PASSWORD"] = "admin123"
        with self.assertRaises(ValidationError):
            Settings(**production)
