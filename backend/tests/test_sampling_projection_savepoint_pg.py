"""抽凭投影写入的保存点（承接 spec voucher-runtime-integrity-and-visibility-closure R4，任务 5~8）

四个投影函数（批次登记 / 已抽凭证登记 / 撤销投影 / 评价投影）失败时只回滚自己那一步，返回兜底值，不连累调用方事务。
判据是 PostgreSQL 事务语义：一条语句失败，没有保存点时整个事务进入 aborted，吞掉异常后调用方后续语句与 COMMIT
全部失败（COMMIT 等价 ROLLBACK）。SQLite 不进 aborted，测不出 ⇒ 真 PG。

- 会话：``tests.formula_hub._pg_harness.pg_tx_session``（独立连接 + 外层事务，退出一律回滚）；
- 注入：函数里第一条语句执行前，先在同一会话上执行一条服务端报错的语句（除零）再抛出 —— 与投影 SQL 真实失败
  同一形态；投影的 SELECT / INSERT / UPDATE 本身一条都不执行（不写任何数据）；
- 反向对照：同样注入、保存点换成空上下文时调用方事务确实被拖进 aborted；对照不红说明注入没复现缺陷，正向断言就是空转。
"""
from __future__ import annotations

import contextlib
import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from app.services import sampling_registry_service as reg
from tests.formula_hub._pg_harness import pg_tx_session

pytestmark = [pytest.mark.asyncio, pytest.mark.pg_only]

BATCH = uuid.uuid4()


def _log() -> SimpleNamespace:
    return SimpleNamespace(
        project_id=uuid.uuid4(), workpaper_id=uuid.uuid4(), batch_id=BATCH, user_id=None,
        extraction_criteria={"filled_voucher_nos": ["0001"], "phase": "final"}, total_matched=1, filled_count=1,
    )


#: 名称 → (调用, 失败时的兜底返回值)
CALLS = {
    "批次登记": (lambda db: reg.register_sampling_batch(db, log=_log()), None),
    "已抽凭证登记": (lambda db: reg.register_sampled_vouchers(db, log=_log(), year=2025), 0),
    "撤销投影": (lambda db: reg.undo_sampling_registration(db, batch_id=BATCH), {"records": 0, "vouchers": 0}),
    "评价投影": (lambda db: reg.update_sampling_record_evaluation(db, batch_id=BATCH, evaluation={}), False),
}


@contextlib.asynccontextmanager
async def _session_whose_first_statement_fails():
    """返回 (会话, 未被替换的 execute)；会话上第一条语句执行前先触发一次服务端报错并抛出。"""
    async with pg_tx_session() as db:
        real = db.execute
        armed = {"on": True}

        async def execute(statement, *args, **kwargs):
            if armed["on"]:
                armed["on"] = False
                await real(sa.text("SELECT 1 / 0"))  # division_by_zero：服务端报错，事务（或当前保存点）进入 aborted
            return await real(statement, *args, **kwargs)

        db.execute = execute  # 只替换本用例的会话实例
        yield db, real


@pytest.mark.parametrize("name", list(CALLS))
async def test_projection_failure_rolls_back_only_its_savepoint(name):
    call, fallback = CALLS[name]
    async with _session_whose_first_statement_fails() as (db, real):
        assert await call(db) == fallback
        # 调用方事务照常可用（没有保存点时这里报 current transaction is aborted）
        assert (await real(sa.text("SELECT 1"))).scalar_one() == 1


async def test_negative_control_without_savepoint_the_caller_transaction_is_aborted(monkeypatch):
    async with _session_whose_first_statement_fails() as (db, real):
        monkeypatch.setattr(db, "begin_nested", contextlib.nullcontext)
        assert await reg.undo_sampling_registration(db, batch_id=BATCH) == {"records": 0, "vouchers": 0}
        with pytest.raises(sa.exc.DBAPIError, match="current transaction is aborted"):
            await real(sa.text("SELECT 1"))
