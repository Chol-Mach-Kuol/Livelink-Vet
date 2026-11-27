"""Bring any database to the latest schema with Alembic.

Handles every starting point automatically:
- empty database             -> run all migrations
- v0.1 database (no Alembic)  -> mark as 0001, then upgrade
- database already at v0.2 schema but untracked (made by create_all) -> mark as head
- tracked database            -> upgrade to head
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.core.database import engine

ROOT = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.attributes["configure_logger"] = False  # keep the app's/uvicorn's logging intact
    return cfg


def upgrade_db() -> None:
    cfg = alembic_config()
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "alembic_version" not in tables and "users" in tables:
        columns = {c["name"] for c in insp.get_columns("disease_reports")}
        command.stamp(cfg, "head" if "triage" in columns else "0001")
    command.upgrade(cfg, "head")
