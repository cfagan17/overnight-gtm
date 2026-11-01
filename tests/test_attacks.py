"""Every shared attack is blocked on the hardened schema."""
import pytest

from attacks import ATTACKS, run_attack


@pytest.mark.parametrize("attack", ATTACKS, ids=[a.name for a in ATTACKS])
def test_attack_blocked(conn, attack):
    blocked, detail = run_attack(conn, attack)
    assert blocked, f"{attack.name}: {detail}"
