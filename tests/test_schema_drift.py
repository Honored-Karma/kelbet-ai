"""The migrations and the ORM models must describe the same database.

This guard exists because they silently stopped agreeing. Migration 0006 added a foreign
key from `generation_assets.generation_id` to `generation_jobs.id`, the model never learned
about it, and the consequence surfaced nowhere near the cause: the test fixture's
`drop_all` ordered those two tables wrongly and 130 unrelated tests failed on
`DependentObjectsStillExistError`. Nothing compared the two schemas, so the drift was free
to sit in the repository.

The fixture now drops the whole schema, which makes the suite immune to that ordering
question. That immunity is exactly why this test is needed: with the symptom gone, nothing
else would ever notice the models and migrations disagreeing again.
"""

import pytest
from scripts.schema_drift import (
    InsufficientPrivilege,
    Snapshot,
    compare,
    detect_drift,
    preflight,
)


def _snapshot(*, on_delete: str = "SET NULL", nullable: bool = True) -> Snapshot:
    columns = frozenset({("generation_assets", "generation_id")})
    return Snapshot(
        tables=frozenset({"generation_assets", "generation_jobs"}),
        columns=columns,
        nullable=dict.fromkeys(columns, nullable),
        foreign_keys=frozenset(
            {
                (
                    "generation_assets",
                    "generation_id",
                    "generation_jobs",
                    "id",
                    on_delete,
                    "NO ACTION",
                )
            }
        ),
    )


def test_identical_schemas_report_no_drift() -> None:
    assert compare(_snapshot(), _snapshot()).is_clean()


def test_a_foreign_key_present_on_only_one_side_is_reported() -> None:
    """The original bug in one line: the migration has the key, the model does not."""
    models = Snapshot(
        tables=_snapshot().tables,
        columns=_snapshot().columns,
        nullable=_snapshot().nullable,
        foreign_keys=frozenset(),
    )
    drift = compare(_snapshot(), models)

    assert not drift.is_clean()
    assert drift.missing_foreign_keys == [
        "generation_assets.generation_id -> generation_jobs.id "
        "(ON DELETE SET NULL, ON UPDATE NO ACTION)"
    ]


def test_a_differing_on_delete_action_is_reported() -> None:
    """Same relationship, different behaviour on deletion. `CASCADE` where the migration
    says `SET NULL` silently deletes rows the database was supposed to keep, so comparing
    only the target column would let a data-loss change through as 'clean'."""
    drift = compare(_snapshot(on_delete="SET NULL"), _snapshot(on_delete="CASCADE"))

    assert not drift.is_clean()
    assert any("SET NULL" in item for item in drift.missing_foreign_keys)
    assert any("CASCADE" in item for item in drift.extra_foreign_keys)


def test_a_differing_nullability_is_reported() -> None:
    drift = compare(_snapshot(nullable=True), _snapshot(nullable=False))

    assert not drift.is_clean()
    assert drift.nullability == [
        "generation_assets.generation_id: alembic nullable=True, models nullable=False"
    ]


async def test_migrations_and_models_describe_the_same_schema() -> None:
    try:
        await preflight()
    except InsufficientPrivilege as exc:
        # The comparison needs two scratch databases. A least-privilege CI role or a
        # managed Postgres user may not be allowed to create them, and that must not take
        # the rest of the suite down with it.
        pytest.skip(str(exc))

    drift = await detect_drift()
    assert drift.is_clean(), (
        "the migrations and the ORM models disagree about the schema.\n\n"
        f"{drift.report()}\n\n"
        "Fix whichever side is wrong. A foreign key missing from a model is not cosmetic: "
        "SQLAlchemy uses it to order DDL, and its ON DELETE action decides whether rows "
        "are cascaded, nulled, or the delete is refused."
    )
