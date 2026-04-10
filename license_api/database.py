from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from license_api.config import settings


class Base(DeclarativeBase):
    pass


engine_kwargs = {
    "future": True,
    "pool_pre_ping": True,
}

if settings.database_url.startswith("postgresql") and settings.database_sslmode:
    engine_kwargs["connect_args"] = {"sslmode": settings.database_sslmode}

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
