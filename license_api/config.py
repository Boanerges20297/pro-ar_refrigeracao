import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
KEYS_DIR = BASE_DIR / "keys"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return f"postgresql+psycopg://{url[len('postgres://') :]}"

    if url.startswith("postgresql://") and "+psycopg" not in url:
        return f"postgresql+psycopg://{url[len('postgresql://') :]}"

    return url


@dataclass(frozen=True)
class Settings:
    app_name: str = os.environ.get("LICENSE_API_NAME", "BTA License API")
    api_token: str = os.environ.get("LICENSE_API_TOKEN", "change-me")
    database_url: str = _normalize_database_url(os.environ.get(
        "LICENSE_API_DATABASE_URL",
        f"sqlite:///{(DATA_DIR / 'license_api.db').as_posix()}"
    ))
    database_sslmode: str | None = os.environ.get("LICENSE_API_DATABASE_SSLMODE") or None
    private_key_path: Path = Path(os.environ.get("LICENSE_PRIVATE_KEY_PATH", KEYS_DIR / "ed25519_private.pem"))
    public_key_path: Path = Path(os.environ.get("LICENSE_PUBLIC_KEY_PATH", KEYS_DIR / "ed25519_public.pem"))
    private_key_pem: str | None = os.environ.get("LICENSE_PRIVATE_KEY_PEM") or None
    public_key_pem: str | None = os.environ.get("LICENSE_PUBLIC_KEY_PEM") or None
    allow_perpetual_licenses: bool = _env_bool("LICENSE_ALLOW_PERPETUAL", True)
    auto_create_schema: bool = _env_bool("LICENSE_API_AUTO_CREATE_SCHEMA", True)


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
KEYS_DIR.mkdir(parents=True, exist_ok=True)
