import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from license_api.config import settings


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _canonical_json(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def ensure_keypair() -> tuple[Path, Path]:
    private_path = settings.private_key_path
    public_path = settings.public_key_path

    if private_path.exists() and public_path.exists():
        return private_path, public_path

    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_path, public_path


def load_private_key() -> Ed25519PrivateKey:
    ensure_keypair()
    return serialization.load_pem_private_key(settings.private_key_path.read_bytes(), password=None)


def load_public_key() -> Ed25519PublicKey:
    ensure_keypair()
    return serialization.load_pem_public_key(settings.public_key_path.read_bytes())


def sign_payload(payload: dict) -> str:
    private_key = load_private_key()
    message = _canonical_json(payload)
    signature = private_key.sign(message)
    return f"{_b64url_encode(message)}.{_b64url_encode(signature)}"


def verify_token(token: str) -> dict:
    message_b64, signature_b64 = token.split(".", 1)
    message = _b64url_decode(message_b64)
    signature = _b64url_decode(signature_b64)

    public_key = load_public_key()
    public_key.verify(signature, message)
    return json.loads(message.decode("utf-8"))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
