"""Signed Ledger cursor and request validation contracts."""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.schemas.ledger_window import LedgerWindowQuery
from app.services import ledger_window_cursor as cursor


def _payload() -> dict:
    return {
        "s": "user-a", "q": "query-a", "d": "dataset-a",
        "k": {"date": "2025-01-01", "no": "001", "id": "00000000-0000-0000-0000-000000000001"},
        "a": "123.45", "m": {"total": 1}, "i": 1, "n": 11,
    }


def _decode(token: str, **overrides):
    expected = {"subject": "user-a", "fingerprint": "query-a", "dataset_id": "dataset-a", "now": 101}
    expected.update(overrides)
    return cursor.decode(token, **expected)


def test_cursor_roundtrip_and_canonical_query_fingerprint() -> None:
    token = cursor.issue(_payload(), now=100)
    assert _decode(token)["a"] == "123.45"
    left = {"year": 2025, "filter": {"b": 2, "a": 1}}
    right = {"filter": {"a": 1, "b": 2}, "year": 2025}
    assert cursor.query_fingerprint(left) == cursor.query_fingerprint(right)


@pytest.mark.parametrize("case", ["tamper", "other-user", "expired"])
def test_cursor_tamper_user_and_expiry_fail_visibly(case: str) -> None:
    token = cursor.issue(_payload(), now=100)
    kwargs = {}
    if case == "tamper":
        token = token[:-1] + ("A" if token[-1] != "A" else "B")
    elif case == "other-user":
        kwargs["subject"] = "user-b"
    else:
        kwargs["now"] = 2000
    with pytest.raises(HTTPException) as exc:
        _decode(token, **kwargs)
    assert exc.value.status_code == 400
    assert exc.value.detail["error_code"] == "LEDGER_CURSOR_INVALID"


@pytest.mark.parametrize(("change", "code"), [
    ({"fingerprint": "query-b"}, "LEDGER_CURSOR_QUERY_MISMATCH"),
    ({"dataset_id": "dataset-b"}, "LEDGER_SNAPSHOT_CHANGED"),
])
def test_cursor_query_or_dataset_change_is_distinct(change: dict, code: str) -> None:
    token = cursor.issue(_payload(), now=100)
    with pytest.raises(HTTPException) as exc:
        _decode(token, **change)
    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == code


def test_window_query_rejects_bad_range_and_caps_limit() -> None:
    with pytest.raises(ValidationError, match="开始日期不能晚于结束日期"):
        LedgerWindowQuery(year=2025, account_code="1002", date_from="2025-02-01", date_to="2025-01-01")
    with pytest.raises(ValidationError):
        LedgerWindowQuery(year=2025, account_code="1002", limit=501)
    with pytest.raises(ValidationError, match="开始日期必须属于查询年度"):
        LedgerWindowQuery(year=2025, account_code="1002", date_from="2024-12-31")
    with pytest.raises(ValidationError, match="结束日期必须属于查询年度"):
        LedgerWindowQuery(year=2025, account_code="1002", date_to="2026-01-01")
    query = LedgerWindowQuery(year=2025, account_code=" 1002 ", aux_type=" 客户 ")
    assert query.account_code == "1002" and query.aux_type == "客户"
