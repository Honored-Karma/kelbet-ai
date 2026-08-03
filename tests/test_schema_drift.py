"""The migrations and the ORM models must describe the same database.

This guard exists because they silently stopped agreeing. Migration 0006 added a
foreign key from `generation_assets.generation_id` to `generation_jobs.id`, the model
never learned about it, and the consequence surfaced nowhere near the cause: the test
fixture's `drop_all` sorted those two tables wrongly and 130 unrelated tests failed on
`DependentObjectsStillExistError`. Nothing in the suite compared the two schemas, so the
drift was free to sit in the repository.

The test builds one database from `alembic upgrade head` and one from
`Base.metadata.create_all`, then diffs tables, columns, nullability and foreign keys.
"""

from scripts.schema_drift import detect_drift


async def test_migrations_and_models_describe_the_same_schema() -> None:
    drift = await detect_drift()
    assert drift.is_clean(), (
        "the migrations and the ORM models disagree about the schema.\n\n"
        f"{drift.report()}\n\n"
        "Fix the side that is wrong. A foreign key missing from a model is not cosmetic: "
        "SQLAlchemy uses it to order DDL, so the omission breaks schema teardown."
    )
