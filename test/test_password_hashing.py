import hashlib
import unittest

from core.passwords import hash_password, password_needs_rehash, verify_password


class PasswordHashingTests(unittest.TestCase):
    def test_hash_password_uses_salted_pbkdf2_not_legacy_md5(self):
        password = "secure_password_123"

        hashed = hash_password(password)

        self.assertTrue(hashed.startswith("pbkdf2_sha256$"))
        self.assertNotEqual(hashed, hashlib.md5(password.encode("utf-8")).hexdigest())
        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("wrong_password", hashed))
        self.assertFalse(password_needs_rehash(hashed))

    def test_verify_password_accepts_legacy_md5_for_migration_only(self):
        password = "legacy_password"
        legacy_hash = hashlib.md5(password.encode("utf-8")).hexdigest()

        self.assertTrue(verify_password(password, legacy_hash))
        self.assertTrue(password_needs_rehash(legacy_hash))


if __name__ == "__main__":
    unittest.main()
