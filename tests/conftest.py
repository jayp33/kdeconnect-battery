"""Gemeinsame Fixtures der Testsuite.

Die Sandbox wird pro Test neu angelegt (pytest tmp_path) und danach
aufgeräumt. Tests bekommen sie als Argument ``sandbox``.
"""

from __future__ import annotations

import pytest
from harness import Sandbox


@pytest.fixture
def sandbox(tmp_path):
    box = Sandbox(tmp_path)
    try:
        yield box
    finally:
        box.cleanup()
