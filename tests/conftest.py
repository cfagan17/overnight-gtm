import pathlib
import sys

import psycopg
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from helpers import ADMIN_DSN, build  # noqa: E402


@pytest.fixture(scope="session")
def dsn():
    return build(ADMIN_DSN, "ea_test", seed=True)


@pytest.fixture()
def conn(dsn):
    with psycopg.connect(dsn) as c:
        yield c
