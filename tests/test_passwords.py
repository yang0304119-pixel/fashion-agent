import unittest

from app.core.passwords import hash_password, verify_password


class PasswordTests(unittest.TestCase):
    def test_password_hash_round_trip(self):
        encoded = hash_password("StrongPassword123!")
        self.assertTrue(verify_password("StrongPassword123!", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))
        self.assertNotIn("StrongPassword123!", encoded)


if __name__ == "__main__":
    unittest.main()
