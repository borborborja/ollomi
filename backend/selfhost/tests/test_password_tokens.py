"""Migration tests for the password reset token table."""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def _config(database_url):
    cfg = Config("backend/selfhost/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def test_password_reset_migration_creates_and_drops_table(tmp_path, monkeypatch):
    database_url = "sqlite:///" + str(tmp_path / "migration.sqlite")
    monkeypatch.setenv("OLLOMI_DATABASE_URL", database_url)
    from selfhost.db import engine

    engine.cache_clear()
    cfg = _config(database_url)

    command.upgrade(cfg, "head")

    engine_test = create_engine(database_url)
    inspector = inspect(engine_test)
    assert "password_resets" in inspector.get_table_names()

    uniques = {tuple(sorted(u["column_names"])) for u in inspector.get_unique_constraints("password_resets")}
    assert ("token_hash",) in uniques

    indexes = {idx["name"]: idx for idx in inspector.get_indexes("password_resets")}
    indexed_columns = {tuple(sorted(idx["column_names"])) for idx in indexes.values()}
    assert ("user_id",) in indexed_columns
    assert ("expires_at",) in indexed_columns

    command.downgrade(cfg, "0002")
    inspector = inspect(engine_test)
    assert "password_resets" not in inspector.get_table_names()

    # Downgrade on a database without the table must not raise (checkfirst).
    command.downgrade(cfg, "0002")
    engine_test.dispose()
    engine.cache_clear()
