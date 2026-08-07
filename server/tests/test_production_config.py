import os
import tempfile
from pathlib import Path
from unittest import TestCase

from pydantic import ValidationError


os.environ.setdefault("DEV_MODE", "true")

from core.config import Settings


VALID_PRODUCTION = {
    "DEV_MODE": False,
    "DOMAIN_NAME": "example.com",
    "EMAIL_ADDRESS": "ops@example.com",
    "MONGODB_USERNAME": "hyac-root",
    "MONGODB_PASSWORD": "mongo-production-password",
    "S3_ACCESS_KEY": "production-access-key",
    "S3_SECRET_KEY": "production-secret-key",
    "SECRET_KEY": "production-jwt-secret-with-at-least-32-characters",
    "DEFAULT_ADMIN_USER": "admin",
    "DEFAULT_ADMIN_PASSWORD": "production-admin-password",
    "APP_IMAGE_TAG": "release-2026-08-06",
}


class ProductionConfigTests(TestCase):
    def test_production_requires_domain_and_acme_email(self):
        for field in ("DOMAIN_NAME", "EMAIL_ADDRESS"):
            values = dict(VALID_PRODUCTION)
            values[field] = None
            with self.subTest(field=field), self.assertRaises(ValidationError):
                Settings(**values)

    def test_complete_non_placeholder_production_config_is_accepted(self):
        settings = Settings(**VALID_PRODUCTION)
        self.assertFalse(settings.DEV_MODE)
        self.assertFalse(settings.CI_SMOKE_MODE)
        self.assertEqual("websecure", settings.RUNTIME_INGRESS_ENTRYPOINT)
        self.assertTrue(settings.RUNTIME_INGRESS_TLS)

    def test_production_rejects_plaintext_runtime_ingress_without_ci_smoke_gate(self):
        values = dict(
            VALID_PRODUCTION,
            RUNTIME_INGRESS_ENTRYPOINT="ci",
            RUNTIME_INGRESS_TLS=False,
        )

        with self.assertRaisesRegex(
            ValidationError, "Plaintext runtime ingress is restricted"
        ):
            Settings(**values)

    def test_ci_smoke_tls_ingress_is_restricted_to_disposable_domain(self):
        smoke_values = dict(
            VALID_PRODUCTION,
            CI_SMOKE_MODE=True,
            DOMAIN_NAME="ci.example.com",
            RUNTIME_INGRESS_ENTRYPOINT="ci",
            RUNTIME_INGRESS_TLS=True,
        )

        settings = Settings(**smoke_values)
        self.assertTrue(settings.CI_SMOKE_MODE)

        for domain in ("example.com", "production.example.com"):
            with self.subTest(domain=domain), self.assertRaisesRegex(
                ValidationError, "CI_SMOKE_MODE is restricted"
            ):
                Settings(**dict(smoke_values, DOMAIN_NAME=domain))

    def test_dev_mode_cannot_bypass_the_ci_plaintext_ingress_gate(self):
        with self.assertRaisesRegex(
            ValidationError, "Plaintext runtime ingress is restricted"
        ):
            Settings(
                DEV_MODE=True,
                RUNTIME_INGRESS_ENTRYPOINT="ci",
                RUNTIME_INGRESS_TLS=False,
            )

        with self.assertRaisesRegex(
            ValidationError, "CI_SMOKE_MODE requires DEV_MODE=false"
        ):
            Settings(
                DEV_MODE=True,
                CI_SMOKE_MODE=True,
                DOMAIN_NAME="ci.example.com",
                RUNTIME_INGRESS_ENTRYPOINT="ci",
                RUNTIME_INGRESS_TLS=False,
            )

    def test_ci_smoke_rejects_plaintext_even_on_the_disposable_domain(self):
        with self.assertRaisesRegex(
            ValidationError, "CI_SMOKE_MODE requires the isolated ci TLS ingress"
        ):
            Settings(
                **dict(
                    VALID_PRODUCTION,
                    CI_SMOKE_MODE=True,
                    DOMAIN_NAME="ci.example.com",
                    RUNTIME_INGRESS_ENTRYPOINT="ci",
                    RUNTIME_INGRESS_TLS=False,
                )
            )

    def test_production_rejects_weak_admin_passwords(self):
        for password in ("x", "1234567", "eight ch", "contains space"):
            with self.subTest(password=password), self.assertRaises(ValidationError):
                Settings(**dict(VALID_PRODUCTION, DEFAULT_ADMIN_PASSWORD=password))

        self.assertEqual(
            "abcdefgh",
            Settings(
                **dict(VALID_PRODUCTION, DEFAULT_ADMIN_PASSWORD="abcdefgh")
            ).DEFAULT_ADMIN_PASSWORD,
        )
        self.assertEqual(
            "a" * 128,
            Settings(
                **dict(VALID_PRODUCTION, DEFAULT_ADMIN_PASSWORD="a" * 128)
            ).DEFAULT_ADMIN_PASSWORD,
        )
        with self.assertRaises(ValidationError):
            Settings(
                **dict(VALID_PRODUCTION, DEFAULT_ADMIN_PASSWORD="a" * 129)
            )

    def test_production_rejects_short_infrastructure_secrets(self):
        for field, value in (
            ("MONGODB_PASSWORD", "x" * 11),
            ("S3_SECRET_KEY", "x" * 15),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                Settings(**dict(VALID_PRODUCTION, **{field: value}))

    def test_production_rejects_mutable_runtime_image_tag(self):
        for tag in (None, "", "latest", "LATEST"):
            with self.subTest(tag=tag), self.assertRaises(ValidationError):
                Settings(**dict(VALID_PRODUCTION, APP_IMAGE_TAG=tag))

    def test_production_rejects_example_domain_and_email_placeholders(self):
        for field, value in (
            ("DOMAIN_NAME", "your-domain.com"),
            ("EMAIL_ADDRESS", "xxxx@xxxx.com"),
        ):
            values = dict(VALID_PRODUCTION)
            values[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(
                ValidationError
            ):
                Settings(**values)

    def test_production_rejects_malformed_domain_names(self):
        for domain in (
            "localhost",
            "https://example.com",
            "example",
            "-bad.example.com",
            "bad_.example.com",
            "example..com",
            "example.com/path",
        ):
            values = dict(VALID_PRODUCTION, DOMAIN_NAME=domain)
            with self.subTest(domain=domain), self.assertRaises(ValidationError):
                Settings(**values)

    def test_production_rejects_malformed_acme_email_addresses(self):
        for email in (
            "ops",
            "ops@localhost",
            "@example.com",
            "ops @example.com",
            "ops@example",
            "ops@@example.com",
        ):
            values = dict(VALID_PRODUCTION, EMAIL_ADDRESS=email)
            with self.subTest(email=email), self.assertRaises(ValidationError):
                Settings(**values)

    def test_production_accepts_valid_subdomain_and_tagged_email(self):
        values = dict(
            VALID_PRODUCTION,
            DOMAIN_NAME="functions.example.co.uk",
            EMAIL_ADDRESS="ops+acme@example.co.uk",
        )

        settings = Settings(**values)

        self.assertEqual("functions.example.co.uk", settings.DOMAIN_NAME)
        self.assertEqual("ops+acme@example.co.uk", settings.EMAIL_ADDRESS)

    def test_dev_mount_is_stored_as_a_canonical_existing_directory(self):
        with tempfile.TemporaryDirectory() as root:
            app_dir = Path(root) / "app"
            app_dir.mkdir()
            noncanonical = app_dir / ".." / "app"

            settings = Settings(
                DEV_MODE=True,
                APP_CODE_PATH_ON_HOST=str(noncanonical),
            )

            self.assertEqual(str(app_dir.resolve()), settings.APP_CODE_PATH_ON_HOST)
