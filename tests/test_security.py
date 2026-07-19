import base64
import time
import unittest

try:
    from app.core.config import settings
    from app.core.security import TokenError, create_access_token, decode_access_token
except ModuleNotFoundError as error:
    if error.name == "pydantic_settings":
        raise unittest.SkipTest("当前解释器未安装项目依赖 pydantic-settings")
    raise


class JwtTests(unittest.TestCase):
    def setUp(self):
        self.original_secret = settings.JWT_SECRET_KEY
        self.original_expiry = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        settings.JWT_SECRET_KEY = "test-secret-key-that-is-longer-than-thirty-two-characters"
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60

    def tearDown(self):
        settings.JWT_SECRET_KEY = self.original_secret
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = self.original_expiry

    def test_token_round_trip(self):
        token = create_access_token(user_id=2, tenant_id=7, role="customer")
        claims = decode_access_token(token)
        self.assertEqual(claims.user_id, 2)
        self.assertEqual(claims.tenant_id, 7)
        self.assertEqual(claims.role, "customer")

    def test_tampered_token_is_rejected(self):
        token = create_access_token(user_id=2, tenant_id=7, role="customer")
        header, payload, signature = token.split(".")
        raw_signature = bytearray(
            base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        )
        raw_signature[0] ^= 1
        tampered_signature = base64.urlsafe_b64encode(raw_signature).rstrip(b"=").decode()
        with self.assertRaises(TokenError):
            decode_access_token(f"{header}.{payload}.{tampered_signature}")

    def test_expired_token_is_rejected(self):
        settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 0
        token = create_access_token(user_id=2, tenant_id=7, role="customer")
        time.sleep(0.01)
        with self.assertRaises(TokenError):
            decode_access_token(token)


if __name__ == "__main__":
    unittest.main()
