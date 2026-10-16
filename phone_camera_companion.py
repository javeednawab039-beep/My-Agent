"""Local-only HTTPS and authenticated WebRTC signaling for the phone camera."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import time
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import websockets
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


HTTPS_PORT = 8443
WSS_PORT = 8444
CODE_TTL_SECONDS = 300
SESSION_TTL_SECONDS = 8 * 60 * 60
MAX_SIGNAL_BYTES = 64 * 1024
MAX_ACTIVE_SESSIONS = 32
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
PHONE_PAGE_PATH = Path(__file__).resolve().parent / "phone_camera.html"
PHONE_ORIGIN = ""
CA_CERT_PATH = Path()


def select_lan_ipv4() -> str:
    """Return the private IPv4 address selected for the default route."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        address = ipaddress.ip_address(probe.getsockname()[0])
    finally:
        probe.close()
    if not address.is_private or address.is_loopback or address.is_link_local:
        raise RuntimeError(
            "No private LAN IPv4 interface was selected. Connect the desktop and phone "
            "to the same Wi-Fi network and try again."
        )
    return str(address)


def certificate_directory() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "JarvisPhoneCamera" / "certificates"


def _write_private_key(key: ec.EllipticCurvePrivateKey, path: Path) -> None:
    path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))


def _public_key_bytes(key: Any) -> bytes:
    return key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def ensure_local_certificates(lan_ip: str, directory: Path | None = None) -> tuple[Path, Path, Path]:
    """Create a local root CA and an IP-SAN TLS certificate without exporting keys."""
    destination = directory or certificate_directory()
    destination.mkdir(parents=True, exist_ok=True)
    ca_key_path = destination / "phone-camera-ca.key"
    ca_cert_path = destination / "phone-camera-ca.crt"
    server_key_path = destination / "phone-camera-server.key"
    server_cert_path = destination / "phone-camera-server.crt"
    ip_address = ipaddress.ip_address(lan_ip)

    now = datetime.now(timezone.utc)
    try:
        ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
        constraints = ca_cert.extensions.get_extension_for_class(x509.BasicConstraints).value
        if (
            not isinstance(ca_key, ec.EllipticCurvePrivateKey)
            or _public_key_bytes(ca_key.public_key()) != _public_key_bytes(ca_cert.public_key())
            or not constraints.ca
            or ca_cert.issuer != ca_cert.subject
            or ca_cert.not_valid_after_utc <= now + timedelta(days=1)
        ):
            raise ValueError("Invalid local CA material")
        ca_cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
        ca_cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)
    except (OSError, ValueError, TypeError, x509.ExtensionNotFound):
        ca_key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Jarvis Phone Camera Local CA")])
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ), critical=True)
            .sign(ca_key, hashes.SHA256())
        )
        leaf_key = ec.generate_private_key(ec.SECP256R1())
        leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Jarvis Phone Camera {lan_ip}")])
        leaf_cert = (
            x509.CertificateBuilder()
            .subject_name(leaf_name)
            .issuer_name(ca_cert.subject)
            .public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        _write_private_key(ca_key, ca_key_path)
        ca_cert_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

    valid_leaf = False
    try:
        leaf_key = serialization.load_pem_private_key(server_key_path.read_bytes(), password=None)
        leaf_cert = x509.load_pem_x509_certificate(server_cert_path.read_bytes())
        names = leaf_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        valid_leaf = (
            isinstance(leaf_key, ec.EllipticCurvePrivateKey)
            and _public_key_bytes(leaf_key.public_key()) == _public_key_bytes(leaf_cert.public_key())
            and leaf_cert.issuer == ca_cert.subject
            and ip_address in names.get_values_for_type(x509.IPAddress)
            and leaf_cert.not_valid_after_utc > now + timedelta(days=1)
            and leaf_cert.extensions.get_extension_for_class(
                x509.AuthorityKeyIdentifier
            ).value.key_identifier == ca_cert.extensions.get_extension_for_class(
                x509.SubjectKeyIdentifier
            ).value.digest
        )
    except (OSError, ValueError, TypeError, x509.ExtensionNotFound):
        valid_leaf = False

    if not valid_leaf:
        leaf_key = ec.generate_private_key(ec.SECP256R1())
        leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Jarvis Phone Camera {lan_ip}")])
        leaf_cert = (
            x509.CertificateBuilder()
            .subject_name(leaf_name)
            .issuer_name(ca_cert.subject)
            .public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        _write_private_key(leaf_key, server_key_path)
        server_cert_path.write_bytes(leaf_cert.public_bytes(serialization.Encoding.PEM))
    return ca_cert_path, server_cert_path, server_key_path


def create_tls_context(cert_path: Path, key_path: Path) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return context


@dataclass
class PairingSession:
    code: str
    desktop: Any
    desktop_token: str
    created_at: float
    code_expires_at: float
    expires_at: float
    mobile: Any | None = None
    mobile_token: str | None = None


class PairingBroker:
    """Single-use, short-code pairing and bounded WebRTC message relay."""

    def __init__(self) -> None:
        self.sessions: dict[str, PairingSession] = {}
        self.attempts: dict[str, deque[float]] = defaultdict(deque)

    def _allow_attempt(self, address: str, limit: int = 12) -> bool:
        now = time.monotonic()
        if address not in self.attempts and len(self.attempts) >= 1024:
            for stale_address, stale_history in tuple(self.attempts.items()):
                while stale_history and now - stale_history[0] > 60:
                    stale_history.popleft()
                if not stale_history:
                    self.attempts.pop(stale_address, None)
                if len(self.attempts) < 1024:
                    break
            if len(self.attempts) >= 1024:
                return False
        history = self.attempts[address]
        while history and now - history[0] > 60:
            history.popleft()
        if len(history) >= limit:
            return False
        history.append(now)
        return True

    def _expire_sessions(self) -> None:
        now = time.monotonic()
        for code, session in tuple(self.sessions.items()):
            if session.expires_at <= now or (session.mobile is None and session.code_expires_at <= now):
                del self.sessions[code]

    def _new_code(self) -> str:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
            if code not in self.sessions:
                return code

    async def handle(self, websocket: Any) -> None:
        peer = websocket.remote_address
        address = str(peer[0]) if peer else "unknown"
        session: PairingSession | None = None
        rate_history: deque[float] = deque()
        origin = websocket.request.headers.get("Origin")
        is_desktop = origin in {
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        }
        is_mobile = bool(PHONE_ORIGIN and origin == PHONE_ORIGIN)
        if not (is_desktop or is_mobile):
            await websocket.close(code=1008, reason="Origin not permitted")
            return

        self._expire_sessions()
        try:
            first = await asyncio.wait_for(websocket.recv(), timeout=10)
            if not isinstance(first, str) or len(first.encode("utf-8")) > MAX_SIGNAL_BYTES:
                await websocket.close(code=1009, reason="Message too large")
                return
            request = json.loads(first)
            if not isinstance(request, dict):
                raise ValueError("Invalid request")
            if request.get("type") == "create" and is_desktop:
                if not self._allow_attempt(address):
                    await websocket.close(code=1013, reason="Too many pairing requests")
                    return
                if len(self.sessions) >= MAX_ACTIVE_SESSIONS:
                    await websocket.close(code=1013, reason="Too many active sessions")
                    return
                code = self._new_code()
                now = time.monotonic()
                session = PairingSession(
                    code=code,
                    desktop=websocket,
                    desktop_token=secrets.token_urlsafe(32),
                    created_at=now,
                    code_expires_at=now + CODE_TTL_SECONDS,
                    expires_at=now + SESSION_TTL_SECONDS,
                )
                self.sessions[code] = session
                await websocket.send(json.dumps({
                    "type": "paired",
                    "role": "desktop",
                    "code": code,
                    "token": session.desktop_token,
                    "expiresIn": CODE_TTL_SECONDS,
                }))
                while True:
                    timeout = session.expires_at - time.monotonic()
                    if session.mobile is None:
                        timeout = min(timeout, session.code_expires_at - time.monotonic())
                    if timeout <= 0:
                        await websocket.close(code=1008, reason="Pairing expired")
                        return
                    try:
                        raw = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                    except asyncio.TimeoutError:
                        await websocket.close(code=1008, reason="Pairing expired")
                        return
                    if not self._allow_message(rate_history):
                        await websocket.close(code=1013, reason="Signaling rate limit exceeded")
                        return
                    await self._desktop_message(session, raw)
            if request.get("type") == "join" and is_mobile:
                if not self._allow_attempt(address, limit=8):
                    await websocket.close(code=1013, reason="Too many pairing attempts")
                    return
                code = request.get("code")
                if not isinstance(code, str) or len(code) != 8:
                    await websocket.close(code=1008, reason="Invalid pairing code")
                    return
                session = self.sessions.get(code.upper())
                if (
                    session is None or session.mobile is not None
                    or session.code_expires_at <= time.monotonic()
                    or session.expires_at <= time.monotonic()
                ):
                    await websocket.close(code=1008, reason="Pairing code expired or already used")
                    return
                session.mobile = websocket
                session.mobile_token = secrets.token_urlsafe(32)
                await websocket.send(json.dumps({
                    "type": "paired",
                    "role": "mobile",
                    "token": session.mobile_token,
                    "expiresIn": max(0, int(session.expires_at - time.monotonic())),
                }))
                await session.desktop.send(json.dumps({"type": "peer_joined"}))
                while True:
                    timeout = session.expires_at - time.monotonic()
                    if timeout <= 0:
                        await websocket.close(code=1008, reason="Pairing expired")
                        return
                    try:
                        raw = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                    except asyncio.TimeoutError:
                        await websocket.close(code=1008, reason="Pairing expired")
                        return
                    if not self._allow_message(rate_history):
                        await websocket.close(code=1013, reason="Signaling rate limit exceeded")
                        return
                    await self._mobile_message(session, raw)
            await websocket.close(code=1008, reason="Invalid pairing operation")
        except (asyncio.TimeoutError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
            await websocket.close(code=1008, reason="Invalid pairing request")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if session is not None:
                await self._close_session(session, notify=True)
            self._expire_sessions()

    @staticmethod
    def _allow_message(history: deque[float]) -> bool:
        now = time.monotonic()
        while history and now - history[0] > 60:
            history.popleft()
        if len(history) >= 120:
            return False
        history.append(now)
        return True

    async def _read_authenticated(self, raw: Any, expected_token: str) -> dict[str, Any] | None:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_SIGNAL_BYTES:
            return None
        try:
            message = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(message, dict) or not secrets.compare_digest(
            str(message.get("token", "")), expected_token
        ):
            return None
        if message.get("type") not in {"offer", "answer", "ice", "disconnect"}:
            return None
        if message["type"] != "disconnect" and not isinstance(message.get("data"), dict):
            return None
        return message

    async def _desktop_message(self, session: PairingSession, raw: Any) -> None:
        message = await self._read_authenticated(raw, session.desktop_token)
        if message is None:
            await session.desktop.close(code=1008, reason="Invalid signaling message")
            return
        if message["type"] == "disconnect":
            await self._close_session(session, notify=True)
            return
        if session.mobile is None:
            return
        if message["type"] == "answer":
            await session.desktop.close(code=1008, reason="Desktop cannot send answers")
            return
        await session.mobile.send(json.dumps({"type": message["type"], "data": message.get("data")}))

    async def _mobile_message(self, session: PairingSession, raw: Any) -> None:
        message = await self._read_authenticated(raw, session.mobile_token or "")
        if message is None:
            if session.mobile:
                await session.mobile.close(code=1008, reason="Invalid signaling message")
            return
        if message["type"] == "disconnect":
            await self._close_session(session, notify=True)
            return
        if message["type"] == "offer":
            mobile = session.mobile
            if mobile is not None:
                await mobile.close(code=1008, reason="Mobile cannot send offers")
            return
        await session.desktop.send(json.dumps({"type": message["type"], "data": message.get("data")}))

    async def _close_session(self, session: PairingSession, notify: bool) -> None:
        self.sessions.pop(session.code, None)
        if notify:
            for peer in (session.desktop, session.mobile):
                if peer is not None:
                    try:
                        await peer.send(json.dumps({"type": "peer_left"}))
                    except websockets.exceptions.ConnectionClosed:
                        pass
        for peer in (session.desktop, session.mobile):
            if peer is not None:
                try:
                    await peer.close(code=1000, reason="Session ended")
                except websockets.exceptions.ConnectionClosed:
                    pass


class PhonePageHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        route = urlsplit(self.path).path
        if route == "/phone":
            try:
                page = PHONE_PAGE_PATH.read_bytes()
            except OSError:
                self.send_error(500)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; media-src 'self' blob:; connect-src 'self' wss:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
            self.send_header("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(page)
            return
        if route == "/phone-camera-ca.crt":
            try:
                certificate = CA_CERT_PATH.read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/pkix-cert")
            self.send_header("Content-Disposition", 'attachment; filename="phone-camera-ca.crt"')
            self.send_header("Content-Length", str(len(certificate)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(certificate)
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        print(f"Phone companion: {format % args}")


def make_companion_tls_context(lan_ip: str) -> ssl.SSLContext:
    ca_path, cert_path, key_path = ensure_local_certificates(lan_ip)
    global CA_CERT_PATH, PHONE_ORIGIN
    CA_CERT_PATH = ca_path
    PHONE_ORIGIN = f"https://{lan_ip}:{HTTPS_PORT}"
    return create_tls_context(cert_path, key_path)


def substitute_phone_origin(page: bytes) -> bytes:
    """Fill the desktop's runtime-only companion URL placeholder."""
    if not PHONE_ORIGIN:
        return page
    return page.replace(b"__JARVIS_PHONE_ORIGIN__", PHONE_ORIGIN.encode("ascii"))
