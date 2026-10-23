from __future__ import annotations

import pytest

from app.normalization import normalize_goal_title


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Deep   Work.  ", "deep work"),
        ("READ!!!", "read"),
        ("Read; then: reflect?!", "read; then: reflect"),
        ("Straße", "strasse"),
        ("Ｇｏａｌ！", "goal"),
        ("Café", "café"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_goal_title(raw: str, expected: str) -> None:
    assert normalize_goal_title(raw) == expected
