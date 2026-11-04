"""Loop prompts are plain English: no tool or function names. Tool names live in loop.yaml."""
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "agents" / "runtime"))
from tools import TOOLS  # noqa: E402

LOOPS = sorted(p for p in (ROOT / "agents" / "loops").iterdir() if p.is_dir())


def test_prompts_name_no_tools_or_identifiers():
    for d in LOOPS:
        text = (d / "prompt.md").read_text()
        assert not [t for t in TOOLS if t in text], d.name
        assert not re.search(r"\b[a-z]+_[a-z_]+\b", text), f"{d.name}: snake_case identifier in prompt"


def test_every_loop_has_technical_notes():
    for d in LOOPS:
        assert yaml.safe_load((d / "loop.yaml").read_text()).get("technical_notes"), d.name
