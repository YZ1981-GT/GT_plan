"""委派预览前置的就绪标记（spec procedure-chain-hardening-and-java-contracts R13）。

``prepare_row_tasks`` 只接住库 / 业务校验失败（``SQLAlchemyError / HTTPException / ValueError / LookupError``）：
回执 ``ready=False``、``error`` 写明原因、各计数清零（保存点已回滚，此前累加的计数不成立）；程序错误照常抛出。
原先 ``except Exception`` 全吞、计数照报。真库里预览回执的 ``preparation_ready`` 见 test_program_chain_hardening_batch3_pg.py。
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from app.services import procedure_delegation_prepare as prep_mod
from app.services.procedure_delegation_prepare import prepare_row_tasks
from app.services.procedure_task_materialization_service import ProcedureTaskMaterializationService

pytestmark = pytest.mark.asyncio

_WP = uuid.uuid4()


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeDB:
    def begin_nested(self):
        return _Nested()


class _Materialization:
    """只走到「列出要物化的行」那一步：``overlay_error`` 非空就在这里抛出。"""

    def __init__(self, overlay_error: BaseException | None):
        self.overlay_error = overlay_error

    async def load_wp_indexes(self, project_id, wp_index_ids):
        return {_WP: {"wp_code": "D2", "audit_cycle": "D", "wp_name": "应收账款"}}

    async def build_row_overlay(self, project_id, wp_index_id, *, definition_keys_by_wp_code):
        raise self.overlay_error


@pytest.fixture(autouse=True)
def _definitions(monkeypatch):
    async def _ensure(db, wp_codes):
        return 2, {"D2": frozenset({"k1", "k2"})}  # 先导入了 2 条定义，随后一步失败

    monkeypatch.setattr(prep_mod, "ensure_current_definitions", _ensure)


@pytest.mark.parametrize("error", [
    OperationalError("SELECT 1", {}, Exception("connection reset")),
    HTTPException(status_code=409, detail="目标版本已变化"),
    ValueError("定义键冲突"),
    LookupError("模板不存在"),
])
async def test_recoverable_failure_reports_not_ready_and_resets_counts(error):
    out = await prepare_row_tasks(_FakeDB(), _Materialization(error), uuid.uuid4(), [_WP], actor_user_id=uuid.uuid4())
    assert out["ready"] is False
    assert out["error"] == f"程序行定义导入或任务生成失败：{type(error).__name__}"
    assert (out["definitions_created"], out["tasks_created"], out["tasks_bound"], out["with_program_table"]) == \
        (0, 0, 0, 0), "保存点已回滚：先前累加的「导入 2 条定义」不成立"


@pytest.mark.parametrize("error", [AttributeError("no attribute"), TypeError("bad call"), NameError("x")])
async def test_programming_errors_are_not_swallowed(error):
    with pytest.raises(type(error)):
        await prepare_row_tasks(_FakeDB(), _Materialization(error), uuid.uuid4(), [_WP], actor_user_id=uuid.uuid4())


async def test_nothing_to_prepare_is_ready():
    out = await prepare_row_tasks(_FakeDB(), _Materialization(None), uuid.uuid4(), [], actor_user_id=uuid.uuid4())
    assert out == {"definitions_created": 0, "tasks_created": 0, "tasks_bound": 0, "with_program_table": 0,
                   "ready": True, "error": None}


async def test_materialization_exposes_public_loader_and_prepare_uses_it():
    import ast
    import inspect

    assert ProcedureTaskMaterializationService.load_wp_indexes is ProcedureTaskMaterializationService._load_wp_indexes
    attrs = {n.attr for n in ast.walk(ast.parse(inspect.getsource(prep_mod))) if isinstance(n, ast.Attribute)}
    private = {a for a in attrs if a.startswith("_") and not a.startswith("__")}
    assert "load_wp_indexes" in attrs and not private, f"不跨模块调用私有方法：{private}"
