"""Migrations must build exactly the schema the models describe, from every starting point."""
import pytest
from alembic import command
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from app.core.database import Base, engine
from app.core.migrations import alembic_config, upgrade_db


@pytest.fixture
def empty_db():
    Base.metadata.drop_all(bind=engine)
    _drop_version_table()
    yield
    _drop_version_table()


def _drop_version_table():
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def _revision() -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def _assert_matches_models():
    # Raises if autogenerate finds any difference between models and database.
    command.check(alembic_config())


def test_fresh_database(empty_db):
    upgrade_db()
    assert _revision() == "0002"
    _assert_matches_models()


def test_v01_database_without_alembic(empty_db):
    command.upgrade(alembic_config(), "0001")
    _drop_version_table()  # as created by the original app, never tracked
    upgrade_db()
    assert _revision() == "0002"
    assert "triage" in {c["name"] for c in inspect(engine).get_columns("disease_reports")}
    _assert_matches_models()


def test_untracked_current_schema(empty_db):
    Base.metadata.create_all(bind=engine)
    upgrade_db()
    assert _revision() == "0002"


def test_downgrade_round_trip(empty_db):
    upgrade_db()
    command.downgrade(alembic_config(), "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(alembic_config(), "head")
    _assert_matches_models()
