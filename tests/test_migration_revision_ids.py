"""Static guards for the Alembic revision graph.

`alembic_version.version_num` is VARCHAR(32). An over-long revision id applies
its DDL happily and then fails on the bookkeeping UPDATE, aborting the whole
upgrade. That surfaces as a broken deploy rather than a schema error, so it is
worth catching here instead of in a release. Revision ids may therefore be
shorter than their file names — see 0015 and 0022.
"""

from __future__ import annotations

import re
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"

#: Width of alembic_version.version_num created by Alembic's default template.
MAX_REVISION_LENGTH = 32

_REVISION = re.compile(r'^revision\s*:[^=]*=\s*"([^"]+)"', re.MULTILINE)
_DOWN_REVISION = re.compile(r'^down_revision\s*:[^=]*=\s*(?:"([^"]+)"|None)', re.MULTILINE)


def _migrations() -> list[tuple[str, str, str | None]]:
    """Return (file name, revision, down_revision) for every migration."""

    found: list[tuple[str, str, str | None]] = []
    for path in sorted(VERSIONS_DIR.glob("[0-9]*.py")):
        text = path.read_text(encoding="utf-8")
        revision = _REVISION.search(text)
        down_revision = _DOWN_REVISION.search(text)
        assert revision is not None, f"{path.name} declares no revision"
        assert down_revision is not None, f"{path.name} declares no down_revision"
        found.append((path.name, revision.group(1), down_revision.group(1)))
    return found


def test_migrations_are_discovered() -> None:
    assert _migrations(), f"no migrations found under {VERSIONS_DIR}"


def test_revision_ids_fit_the_version_table() -> None:
    too_long = {
        name: f"{revision} ({len(revision)} chars)"
        for name, revision, _ in _migrations()
        if len(revision) > MAX_REVISION_LENGTH
    }
    assert not too_long, (
        "revision ids longer than alembic_version.version_num VARCHAR"
        f"({MAX_REVISION_LENGTH}); upgrade would fail on the version bump: {too_long}"
    )


def test_revision_ids_are_unique() -> None:
    revisions = [revision for _, revision, _ in _migrations()]
    duplicates = sorted({item for item in revisions if revisions.count(item) > 1})
    assert not duplicates, f"duplicate revision ids: {duplicates}"


def test_down_revisions_resolve() -> None:
    migrations = _migrations()
    known = {revision for _, revision, _ in migrations}
    dangling = {
        name: down for name, _, down in migrations if down is not None and down not in known
    }
    assert not dangling, f"down_revision points at unknown revisions: {dangling}"


def test_chain_is_linear_with_a_single_head() -> None:
    migrations = _migrations()
    revisions = {revision for _, revision, _ in migrations}
    parents = [down for _, _, down in migrations if down is not None]

    bases = sorted(revision for _, revision, down in migrations if down is None)
    assert len(bases) == 1, f"expected exactly one base migration, found {bases}"

    heads = sorted(revisions - set(parents))
    assert len(heads) == 1, f"expected exactly one head, found {heads}"

    branched = sorted({item for item in parents if parents.count(item) > 1})
    assert not branched, f"these revisions have several children and branch the chain: {branched}"
