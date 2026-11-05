import pathlib
import sys

import psycopg
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from helpers import ADMIN_DSN, HOSTED_DSN, build  # noqa: E402

# With EA_HOSTED_DSN set, tests run against an existing seeded project (for example a real
# Supabase project installed with scripts/install_hosted.py --seed). Every test that runs there
# works inside a transaction that is rolled back. Tests that need to create scratch databases or
# commit data are skipped.
NEEDS_SCRATCH_DB = {"test_runtime.py", "test_sidecars.py"}
NEEDS_SCRATCH_TEST = {"test_stock_atomic_has_high_findings"}


def pytest_collection_modifyitems(config, items):
    if not HOSTED_DSN:
        return
    skip = pytest.mark.skip(reason="creates scratch databases or commits data; not run against a hosted project")
    for item in items:
        if item.fspath.basename in NEEDS_SCRATCH_DB or item.name in NEEDS_SCRATCH_TEST:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def dsn():
    return HOSTED_DSN or build(ADMIN_DSN, "ea_test", seed=True)


@pytest.fixture()
def conn(dsn):
    with psycopg.connect(dsn) as c:
        yield c
