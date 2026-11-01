"""合并附注重聚合记录缓存的轻量单元测试。"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.models.consol_note_data_models import ConsolNoteData
from app.services.consol_note_subtree_reaggregate import _Run
from app.services.consol_tree_service import TreeNode


def _tree() -> tuple[TreeNode, TreeNode]:
    child = TreeNode(
        project_id=uuid.uuid4(), company_code="A", company_name="A",
        parent_company_code="G", ultimate_company_code="G", consol_level=1,
        node_key="A:subsidiary", role="subsidiary", kind="data",
    )
    root = TreeNode(
        project_id=uuid.uuid4(), company_code="G", company_name="G",
        parent_company_code=None, ultimate_company_code="G", consol_level=0,
        children=[child], node_key="G:consol", role="consol", kind="aggregate",
    )
    return root, child


@pytest.mark.asyncio
async def test_records_are_prefetched_once_and_legacy_is_root_only():
    root, child = _tree()
    exact = SimpleNamespace(section_id="S1", node_key=child.node_key)
    legacy = SimpleNamespace(section_id="S1", node_key=None)

    class Scalars:
        def all(self):
            return [exact, legacy]

    class Result:
        def scalars(self):
            return Scalars()

    class Db:
        def __init__(self):
            self.execute_count = 0

        async def execute(self, _statement):
            self.execute_count += 1
            return Result()

    db = Db()
    run = _Run(db, root.project_id, 2025, root, root, "soe", ["S1"])
    await run._load_records()

    assert db.execute_count == 1
    assert run._records("S1", [child.node_key]) == {child.node_key: exact}
    assert run._source_record("S1", child, allow_legacy=False) is exact
    assert run._source_record("S1", root, allow_legacy=True) is legacy
    assert db.execute_count == 1


@pytest.mark.asyncio
async def test_new_aggregate_record_enters_working_set_without_early_flush():
    root, _child = _tree()

    class Db:
        def __init__(self):
            self.added = []

        def add(self, value):
            self.added.append(value)

    db = Db()
    run = _Run(db, root.project_id, 2025, root, root, "soe", ["S1"])
    record = await run._writable_record("S1", root, None)

    assert isinstance(record, ConsolNoteData)
    assert db.added == [record]
    assert run._exact_record("S1", root.node_key) is record


@pytest.mark.asyncio
async def test_legacy_root_copy_is_deferred_and_does_not_mutate_legacy_data():
    root, _child = _tree()
    legacy = SimpleNamespace(
        node_key=None,
        data={"rows": [["现金", "1"]]},
        is_stale=True,
    )

    class Db:
        def __init__(self):
            self.added = []

        def add(self, value):
            self.added.append(value)

    db = Db()
    run = _Run(db, root.project_id, 2025, root, root, "soe", ["S1"])
    copied = await run._writable_record("S1", root, legacy)
    copied.data["rows"][0][1] = "2"

    assert copied.node_key == root.node_key
    assert copied.is_stale is True
    assert legacy.data["rows"][0][1] == "1"
    assert db.added == [copied]
