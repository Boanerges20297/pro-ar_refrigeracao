"""Verify audit migration upgrade on a disposable local SQLite database."""
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine, inspect


def test_unknown_login_user_audit_migration_upgrade(tmp_path):
    target = Path(__file__).resolve().parents[1] / "migrations/versions/b6f3c91a2d08_nullable_audit_login_user.py"
    spec = importlib.util.spec_from_file_location("audit_revision_under_test", target)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    engine = create_engine(f"sqlite:///{tmp_path / 'audit-qa.db'}")
    metadata = MetaData()
    Table("user", metadata, Column("id", Integer, primary_key=True))
    Table("audit_log", metadata, Column("id", Integer, primary_key=True),
          Column("user_id", Integer, ForeignKey("user.id"), nullable=False),
          Column("action", String(100), nullable=False))
    metadata.create_all(engine)
    with engine.begin() as conn:
        before = {c["name"]: c for c in inspect(conn).get_columns("audit_log")}
        assert not before["user_id"]["nullable"]
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
        after = {c["name"]: c for c in inspect(conn).get_columns("audit_log")}
        assert after["user_id"]["nullable"]
        reflected = Table("audit_log", MetaData(), autoload_with=conn)
        conn.execute(reflected.insert().values(user_id=None, action="LOGIN"))
        assert conn.execute(reflected.select()).first().user_id is None
    engine.dispose()
