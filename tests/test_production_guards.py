"""Startup guards against the two defaults that destroy data in production.

Both defaults exist for a good reason — a laptop can run the whole stack with no S3
bucket and no Redis worker — and both are silent when they reach production. Nothing
logs an error while `STORAGE_BACKEND=memory` drops a paid generation on restart, so
the failure is only ever reported by the user who lost it.

These tests pin the guard in both directions: it must fire on production, and it must
stay out of the way everywhere else, or every developer and every test run would need
a bucket.
"""

from __future__ import annotations

import pytest

from kelbet.config import (
    PRODUCTION_ENVS,
    Settings,
    assert_production_ready,
    production_config_problems,
    runtime_config_summary,
)


def _production(**overrides: object) -> Settings:
    """A production configuration that is safe unless a test breaks it on purpose."""
    defaults: dict[str, object] = {
        "app_env": "production",
        "storage_backend": "s3",
        "generation_queue_backend": "arq",
        "webhook_secret": "a-real-secret",
        "cors_origins": "https://kelbet-ai.vercel.app,https://web.telegram.org",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_a_correctly_configured_production_starts() -> None:
    settings = _production()

    assert production_config_problems(settings) == []
    assert_production_ready(settings)


@pytest.mark.parametrize("app_env", sorted(PRODUCTION_ENVS))
def test_both_spellings_of_production_are_guarded(app_env: str) -> None:
    """`APP_ENV` is set by hand in a dashboard, so "prod" is as likely as
    "production" and must not be a way around the check."""
    settings = _production(app_env=app_env, storage_backend="memory")

    assert production_config_problems(settings)


@pytest.mark.parametrize("app_env", ["development", "test", "staging", "PRODUCTION_LIKE"])
def test_non_production_environments_keep_the_cheap_defaults(app_env: str) -> None:
    settings = Settings(
        app_env=app_env, storage_backend="memory", generation_queue_backend="inline"
    )

    assert production_config_problems(settings) == []
    assert_production_ready(settings)


def test_memory_storage_in_production_is_refused() -> None:
    """The failure this prevents: a restart erases generated media the user has
    already been charged credits for."""
    settings = _production(storage_backend="memory")

    problems = production_config_problems(settings)

    assert len(problems) == 1
    assert "STORAGE_BACKEND" in problems[0]
    with pytest.raises(RuntimeError, match="STORAGE_BACKEND"):
        assert_production_ready(settings)


def test_inline_queue_in_production_is_refused() -> None:
    """The failure this prevents: generation runs inside the HTTP request, so a
    video outlives the connection and the credits are spent on a lost result."""
    settings = _production(generation_queue_backend="inline")

    problems = production_config_problems(settings)

    assert len(problems) == 1
    assert "GENERATION_QUEUE_BACKEND" in problems[0]


def test_unauthenticated_provider_callbacks_are_refused() -> None:
    settings = _production(webhook_secret="   ")

    problems = production_config_problems(settings)

    assert len(problems) == 1
    assert "WEBHOOK_SECRET" in problems[0]


def test_an_unconfigured_mini_app_origin_is_refused() -> None:
    """Left at the shipped default the browser blocks every API call, so the Mini
    App is dead on arrival rather than degraded."""
    settings = _production(cors_origins="https://web.telegram.org/")

    problems = production_config_problems(settings)

    assert len(problems) == 1
    assert "CORS_ORIGINS" in problems[0]


def test_every_problem_is_reported_at_once() -> None:
    """An operator fixing one variable per failed deploy across three services is
    the slow path; the message names everything wrong in one go."""
    settings = _production(
        storage_backend="memory",
        generation_queue_backend="inline",
        webhook_secret="",
        cors_origins="https://web.telegram.org",
    )

    problems = production_config_problems(settings)

    assert len(problems) == 4
    with pytest.raises(RuntimeError) as error:
        assert_production_ready(settings)
    message = str(error.value)
    for variable in (
        "STORAGE_BACKEND",
        "GENERATION_QUEUE_BACKEND",
        "WEBHOOK_SECRET",
        "CORS_ORIGINS",
    ):
        assert variable in message


def test_each_problem_says_what_to_set() -> None:
    """A guard that only says "no" moves the outage from data loss to a confused
    operator at 3am."""
    settings = _production(
        storage_backend="memory",
        generation_queue_backend="inline",
        webhook_secret="",
        cors_origins="https://web.telegram.org",
    )

    for problem in production_config_problems(settings):
        assert "Set " in problem, problem


def test_runtime_summary_reports_switches_and_never_a_secret() -> None:
    """Railway does not expose variable values to the running app's operators, so
    this line is the only way to confirm from outside what production is actually
    running. It must therefore never become a place secrets leak."""
    secret = "super-secret-webhook-value"
    settings = _production(webhook_secret=secret, storage_backend="s3")

    summary = runtime_config_summary(settings)

    assert "storage=s3" in summary
    assert "queue=arq" in summary
    assert "webhook_secret=set" in summary
    assert secret not in summary


def test_runtime_summary_reports_an_absent_secret_as_empty() -> None:
    summary = runtime_config_summary(_production(webhook_secret=""))

    assert "webhook_secret=empty" in summary
