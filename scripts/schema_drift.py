"""Compare the schema Alembic produces against the schema the ORM models declare.

Two sources of truth for one database is how `generation_assets` ended up carrying a
foreign key in Postgres that SQLAlchemy knew nothing about. The damage surfaced far from
the cause: `Base.metadata.drop_all` sorted the tables by the relationships declared on
the models, dropped `generation_jobs` while a dependent table still referenced it, and
130 tests died on `DependentObjectsStillExistError`.

Run standalone for a readable report:

    python scripts/schema_drift.py

The same comparison runs as an assertion in tests/test_schema_drift.py.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from kelbet.db.base import Base
from kelbet.db.models import *  # noqa: F401,F403  (registers every table on Base.metadata)

ALEMBIC_DB = "kelbet_drift_alembic"
MODELS_DB = "kelbet_drift_models"

Column = tuple[str, str]
ForeignKeyRef = tuple[str, str, str, str]


def database_url() -> str:
    return os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://kelbet:kelbet@localhost:5433/kelbet_test",
    )


@dataclass(frozen=True)
class Snapshot:
    """What one database actually contains, reduced to the parts worth comparing."""

    tables: frozenset[str]
    columns: frozenset[Column]
    nullable: dict[Column, bool]
    foreign_keys: frozenset[ForeignKeyRef]


@dataclass
class Drift:
    """Everything the two schemas disagree about."""

    missing_tables: list[str] = field(default_factory=list)
    extra_tables: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    nullability: list[str] = field(default_factory=list)
    missing_foreign_keys: list[str] = field(default_factory=list)
    extra_foreign_keys: list[str] = field(default_factory=list)

    _LABELS = {
        "missing_tables": "tables in Alembic but not in the models",
        "extra_tables": "tables in the models but not in Alembic",
        "missing_columns": "columns in Alembic but not in the models",
        "extra_columns": "columns in the models but not in Alembic",
        "nullability": "columns whose nullability disagrees",
        "missing_foreign_keys": "foreign keys in Alembic but not in the models",
        "extra_foreign_keys": "foreign keys in the models but not in Alembic",
    }

    def is_clean(self) -> bool:
        return not any(getattr(self, name) for name in self._LABELS)

    def report(self) -> str:
        if self.is_clean():
            return "no drift: Alembic and the models agree"
        lines: list[str] = []
        for name, label in self._LABELS.items():
            items: list[str] = getattr(self, name)
            if items:
                lines.append(f"{label} ({len(items)}):")
                lines.extend(f"  - {item}" for item in sorted(items))
        return "\n".join(lines)


_COLUMNS = text("""
    SELECT c.table_name, c.column_name, c.is_nullable
    FROM information_schema.columns c
    JOIN information_schema.tables t
      ON t.table_schema = c.table_schema AND t.table_name = c.table_name
    WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
""")

# Constraint names come from a naming convention and can legitimately differ between the
# two sides, so foreign keys are compared by what they point at, never by what they are
# called. Composite keys are matched column by column via the ordinality join.
_FOREIGN_KEYS = text("""
    SELECT src.relname      AS src_table,
           src_col.attname  AS src_column,
           tgt.relname      AS tgt_table,
           tgt_col.attname  AS tgt_column
    FROM pg_constraint c
    JOIN pg_class src ON src.oid = c.conrelid
    JOIN pg_class tgt ON tgt.oid = c.confrelid
    JOIN pg_namespace ns ON ns.oid = src.relnamespace
    JOIN unnest(c.conkey)  WITH ORDINALITY AS sk(attnum, ord) ON TRUE
    JOIN unnest(c.confkey) WITH ORDINALITY AS tk(attnum, ord) ON tk.ord = sk.ord
    JOIN pg_attribute src_col ON src_col.attrelid = c.conrelid AND src_col.attnum = sk.attnum
    JOIN pg_attribute tgt_col ON tgt_col.attrelid = c.confrelid AND tgt_col.attnum = tk.attnum
    WHERE c.contype = 'f' AND ns.nspname = 'public'
""")


async def _snapshot(conn: AsyncConnection) -> Snapshot:
    nullable: dict[Column, bool] = {}
    tables: set[str] = set()
    for table, column, is_nullable in (await conn.execute(_COLUMNS)).all():
        if table == "alembic_version":
            continue
        tables.add(table)
        nullable[(table, column)] = is_nullable == "YES"

    foreign_keys = {
        (src_table, src_column, tgt_table, tgt_column)
        for src_table, src_column, tgt_table, tgt_column in (
            await conn.execute(_FOREIGN_KEYS)
        ).all()
        if src_table in tables
    }
    return Snapshot(
        tables=frozenset(tables),
        columns=frozenset(nullable),
        nullable=nullable,
        foreign_keys=frozenset(foreign_keys),
    )


def compare(alembic: Snapshot, models: Snapshot) -> Drift:
    """Diff two snapshots, reporting only differences inside tables both sides have.

    Restricting column and foreign-key comparison to shared tables keeps the report
    honest: a table missing entirely from one side would otherwise be reported once as a
    missing table and again as every one of its columns.
    """
    shared = alembic.tables & models.tables

    def fk_label(fk: ForeignKeyRef) -> str:
        src_table, src_column, tgt_table, tgt_column = fk
        return f"{src_table}.{src_column} -> {tgt_table}.{tgt_column}"

    return Drift(
        missing_tables=sorted(alembic.tables - models.tables),
        extra_tables=sorted(models.tables - alembic.tables),
        missing_columns=sorted(
            f"{table}.{column}"
            for table, column in alembic.columns - models.columns
            if table in shared
        ),
        extra_columns=sorted(
            f"{table}.{column}"
            for table, column in models.columns - alembic.columns
            if table in shared
        ),
        nullability=sorted(
            f"{table}.{column}: alembic nullable={alembic.nullable[(table, column)]}, "
            f"models nullable={models.nullable[(table, column)]}"
            for table, column in alembic.columns & models.columns
            if table in shared
            and alembic.nullable[(table, column)] != models.nullable[(table, column)]
        ),
        missing_foreign_keys=sorted(
            fk_label(fk) for fk in alembic.foreign_keys - models.foreign_keys if fk[0] in shared
        ),
        extra_foreign_keys=sorted(
            fk_label(fk) for fk in models.foreign_keys - alembic.foreign_keys if fk[0] in shared
        ),
    )


def _swap_database(url: str, database: str) -> str:
    """Point a SQLAlchemy URL at a different database, leaving credentials intact."""
    base, _, _ = url.rpartition("/")
    return f"{base}/{database}"


async def _admin_execute(statements: list[str]) -> None:
    """Run CREATE/DROP DATABASE, which Postgres refuses inside a transaction."""
    engine = create_async_engine(
        _swap_database(database_url(), "postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with engine.connect() as conn:
            for statement in statements:
                await conn.execute(text(statement))
    finally:
        await engine.dispose()


def _run_alembic(url: str) -> None:
    """Run `alembic upgrade head` against an explicit database URL."""
    result = subprocess.run(  # noqa: S603
        ["alembic", "upgrade", "head"],  # noqa: S607
        env={**os.environ, "DATABASE_URL": url, "TEST_DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")


async def _snapshot_database(url: str) -> Snapshot:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return await _snapshot(conn)
    finally:
        await engine.dispose()


async def _build_models_database(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


async def detect_drift() -> Drift:
    """Build one database from the migrations and one from the models, then diff them.

    Both are scratch databases created and dropped here, so the comparison never touches
    the database the tests themselves use.
    """
    alembic_url = _swap_database(database_url(), ALEMBIC_DB)
    models_url = _swap_database(database_url(), MODELS_DB)
    drop = [f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)' for name in (ALEMBIC_DB, MODELS_DB)]
    create = [f'CREATE DATABASE "{name}"' for name in (ALEMBIC_DB, MODELS_DB)]

    await _admin_execute(drop + create)
    try:
        _run_alembic(alembic_url)
        await _build_models_database(models_url)
        return compare(
            await _snapshot_database(alembic_url),
            await _snapshot_database(models_url),
        )
    finally:
        await _admin_execute(drop)


def main() -> int:
    drift = asyncio.run(detect_drift())
    print(drift.report())
    return 0 if drift.is_clean() else 1


if __name__ == "__main__":
    raise SystemExit(main())
