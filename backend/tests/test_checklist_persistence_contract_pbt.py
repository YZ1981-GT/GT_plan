"""Property/contract tests for checklist batch persistence.

**Validates: Requirements 4.1, 4.3**
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from hypothesis import given, strategies as st

from app.routers.checklist_responses import (
    BatchSaveRequest,
    ChecklistResponseItem,
    batch_save_checklist_responses,
)


class _Result:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _TransactionalDb:
    def __init__(self, project_id: uuid.UUID):
        self.project_id = project_id
        self.pending: list[str] = []
        self.committed: list[str] = []
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement, params):
        sql = str(statement)
        if "SELECT wp.project_id" in sql:
            return _Result(SimpleNamespace(
                project_id=self.project_id, wp_code=None, audit_year=2025,
            ))
        if "SELECT updated_at" in sql:
            return _Result(None)
        if "INSERT INTO checklist_responses" in sql:
            self.pending.append(params["item_id"])
            return _Result(SimpleNamespace(
                id=uuid.uuid4(), item_id=params["item_id"],
                conclusion=params["conclusion"], remark=params["remark"],
                wp_ref=params["wp_ref"], updated_by=uuid.UUID(params["updated_by"]),
                updated_at=datetime.now(timezone.utc),
            ))
        raise AssertionError(f"unexpected SQL: {sql}")
    async def flush(self):
        return None

    async def commit(self):
        self.commit_count += 1
        self.committed.extend(self.pending)
        self.pending.clear()

    async def rollback(self):
        self.rollback_count += 1
        self.pending.clear()


@st.composite
def _invalid_batches(draw):
    size = draw(st.integers(min_value=1, max_value=6))
    invalid_index = draw(st.integers(min_value=0, max_value=size - 1))
    suffix = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
        min_size=1,
        max_size=10,
    ))
    invalid_conclusion = f"INVALID_{suffix}"
    items = [
        ChecklistResponseItem(
            item_id=f"PBT-item-{index}",
            conclusion=invalid_conclusion if index == invalid_index else "Y",
            remark=f"value-{index}",
        )
        for index in range(size)
    ]
    return items, invalid_index


@given(case=_invalid_batches())
def test_p6_invalid_item_rolls_back_whole_batch_and_reports_item_id(case):
    """P6: any invalid item makes the request atomic and locates item_id."""
    items, invalid_index = case

    async def run_case():
        project_id = uuid.uuid4()
        db = _TransactionalDb(project_id)
        body = BatchSaveRequest(project_id=project_id, items=items)
        user = SimpleNamespace(id=uuid.uuid4())

        with pytest.raises(HTTPException) as raised:
            await batch_save_checklist_responses(
                wp_id=uuid.uuid4(), body=body, db=db, current_user=user,
            )

        assert raised.value.status_code == 422
        assert raised.value.detail["item_id"] == items[invalid_index].item_id
        assert raised.value.detail["atomic"] is True
        assert db.commit_count == 0
        assert db.rollback_count == 1
        assert db.pending == []
        assert db.committed == []

    asyncio.run(run_case())
