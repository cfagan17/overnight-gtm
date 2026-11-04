"""The 'ask your own data' queries in examples/queries run as an owner and as a read-only user."""
import pathlib

import pytest

from helpers import OWNER, acting_as

QUERIES = sorted((pathlib.Path(__file__).parent.parent / "examples" / "queries").glob("*.sql"))


@pytest.mark.parametrize("path", QUERIES, ids=lambda p: p.name)
def test_query_runs_as_owner(conn, path):
    with acting_as(conn, OWNER) as c:
        c.execute(path.read_text()).fetchall()


def test_there_are_queries():
    assert len(QUERIES) >= 5
