import json
import shutil
import time
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import serialization

import phone_camera_companion as companion


class FakePeer:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True


class PairingBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_role_tokens_gate_relay_and_roles(self) -> None:
        broker = companion.PairingBroker()
        desktop = FakePeer()
        mobile = FakePeer()
        session = companion.PairingSession(
            code="ABCDEFGH",
            desktop=desktop,
            desktop_token="desktop-secret",
            created_at=time.monotonic(),
            code_expires_at=time.monotonic() + 300,
            expires_at=time.monotonic() + 600,
            mobile=mobile,
            mobile_token="mobile-secret",
        )

        await broker._desktop_message(session, json.dumps({
            "type": "ice",
            "token": "desktop-secret",
            "data": {"candidate": "host"},
        }))
        self.assertEqual(json.loads(mobile.sent[-1]), {
            "type": "ice",
            "data": {"candidate": "host"},
        })

        await broker._mobile_message(session, json.dumps({
            "type": "answer",
            "token": "mobile-secret",
            "data": {"type": "answer", "sdp": "local-only"},
        }))
        self.assertEqual(json.loads(desktop.sent[-1])["type"], "answer")

        await broker._desktop_message(session, json.dumps({
            "type": "offer",
            "token": "wrong-token",
            "data": {},
        }))
        self.assertTrue(desktop.closed)

    async def test_code_expiry_and_single_use_session_cleanup(self) -> None:
        broker = companion.PairingBroker()
        old = companion.PairingSession(
            code="ABCDEFGH",
            desktop=FakePeer(),
            desktop_token="token",
            created_at=time.monotonic() - 400,
            code_expires_at=time.monotonic() - 1,
            expires_at=time.monotonic() + 60,
        )
        broker.sessions[old.code] = old
        broker._expire_sessions()
        self.assertNotIn(old.code, broker.sessions)

        code = broker._new_code()
        self.assertEqual(len(code), 8)
        self.assertTrue(set(code).issubset(set(companion.CODE_ALPHABET)))

    async def test_message_size_and_token_validation(self) -> None:
        broker = companion.PairingBroker()
        self.assertIsNone(await broker._read_authenticated(
            "x" * (companion.MAX_SIGNAL_BYTES + 1), "token"
        ))
        self.assertIsNone(await broker._read_authenticated(
            '{"type":"ice","token":"other","data":{}}', "token"
        ))
        accepted = await broker._read_authenticated(
            '{"type":"ice","token":"token","data":{}}', "token"
        )
        self.assertEqual(accepted["type"], "ice")


class CertificateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = companion.certificate_directory() / "test-certificates"
        shutil.rmtree(self.directory, ignore_errors=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_local_ca_signs_ip_san_server_certificate(self) -> None:
        ca_path, cert_path, key_path = companion.ensure_local_certificates(
            "192.168.50.23", self.directory
        )
        ca = x509.load_pem_x509_certificate(ca_path.read_bytes())
        leaf = x509.load_pem_x509_certificate(cert_path.read_bytes())
        private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        subject_alt_names = leaf.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
        self.assertIn("192.168.50.23", [str(ip) for ip in subject_alt_names.get_values_for_type(x509.IPAddress)])
        self.assertEqual(leaf.issuer, ca.subject)
        self.assertEqual(
            companion._public_key_bytes(leaf.public_key()),
            companion._public_key_bytes(private_key.public_key()),
        )
        self.assertIsNotNone(companion.create_tls_context(cert_path, key_path))


if __name__ == "__main__":
    unittest.main()
