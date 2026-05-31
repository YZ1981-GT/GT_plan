"""阶段 3 审计 PBT — Q5 审计完整性

spec: formula-engine-unification / tasks.md Task 18
**Validates: Requirements 4.5**
关联属性: Q5

═══════════════════════════════════════════════════════════════════════════════
目的
═══════════════════════════════════════════════════════════════════════════════
Q5 审计完整：每次公式变更恰好一条 formula.changed 入哈希链（不多不少）。

验证逻辑：
  - 模拟 N 次公式变更（report/consol/workpaper 三种 module）
  - 每次变更调 append_audit_log(action='formula.changed')
  - 验证 audit_log_entries 中 action_type='formula.changed' 的条目数恰好等于变更次数
  - 验证每条 entry 的 entry_hash 和 prev_hash 形成有效哈希链

hypothesis max_examples 15（用户偏好）
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import select, func
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# SQLite 兼容 JSONB + ARRAY
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

# 仅注册审计日志测试所需的模型
import app.models.core  # noqa: F401
import app.models.audit_log_models  # noqa: F401

from app.models.audit_log_models import AuditLogEntry
from app.services.audit_log_helper import (
    AuditLogPayload,
    GENESIS_HASH,
    append_audit_log,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@asynccontextmanager
async def fresh_db_session():
    """每次调用创建全新的内存数据库会话（避免 hypothesis 跨 example 状态泄漏）。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["audit_log_entries"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables_to_create)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


# ═══════════════════════════════════════════════════════════════════════════════
# 测试数据策略
# ═══════════════════════════════════════════════════════════════════════════════

_MODULES = ["report", "consol", "workpaper"]
_ROW_CODES = ["BS-001", "BS-002", "BS-010", "PL-001", "PL-002", "CF-001", "CF-002"]
_ACTIONS = ["execute", "update"]
_FORMULAS = [
    "TB('1001','期末余额')",
    "SUM_TB('1400~1499','期末余额')",
    "ROW('BS-001')+ROW('BS-002')",
    "PREV('1001','期末余额')",
    "TB('1002','审定数')+TB('1003','审定数')",
    "IF(TB('1001','期末余额')>0,TB('1001','期末余额'),0)",
    "ABS(TB('2001','期末余额'))",
]


@st.composite
def formula_change_sequence(draw):
    """生成一组公式变更操作序列（1~5 次变更）。

    每次变更包含 module/row_code/action/old_formula/new_formula/result_value。
    """
    n_changes = draw(st.integers(min_value=1, max_value=5))
    changes = []
    for _ in range(n_changes):
        module = draw(st.sampled_from(_MODULES))
        row_code = draw(st.sampled_from(_ROW_CODES))
        action = draw(st.sampled_from(_ACTIONS))
        old_formula = draw(st.sampled_from([""] + _FORMULAS))
        new_formula = draw(st.sampled_from(_FORMULAS))
        result_value = str(draw(st.decimals(
            min_value=-1_000_000, max_value=1_000_000,
            places=2, allow_nan=False, allow_infinity=False,
        )))
        changes.append({
            "module": module,
            "row_code": row_code,
            "action": action,
            "old_formula": old_formula,
            "new_formula": new_formula,
            "result_value": result_value,
        })
    return changes


# ═══════════════════════════════════════════════════════════════════════════════
# Q5 审计完整：每次公式变更恰好一条 formula.changed 入哈希链
# **Validates: Requirements 4.5**  属性: Q5
# ═══════════════════════════════════════════════════════════════════════════════

class TestQ5AuditCompleteness:
    """属性 Q5：每次公式变更恰好产生一条 formula.changed 审计条目入哈希链。"""

    @given(changes=formula_change_sequence())
    @settings(max_examples=15, deadline=None)
    def test_exactly_one_entry_per_change(self, changes):
        """N 次公式变更 → 恰好 N 条 action_type='formula.changed' 条目。

        验证：
        1. 条目数 == 变更次数（不多不少）
        2. 每条 entry 的 action_type 均为 'formula.changed'
        3. payload 含 event_type='formula_changed' + 必需字段
        """
        asyncio.run(self._check_exactly_one_entry_per_change(changes))

    async def _check_exactly_one_entry_per_change(self, changes):
        async with fresh_db_session() as db_session:
            project_id = uuid.uuid4()
            user_id = uuid.uuid4()

            # 执行 N 次公式变更，每次调 append_audit_log
            for change in changes:
                resource_type = "workpaper" if change["module"] == "workpaper" else "report_config"
                payload: AuditLogPayload = {
                    "user_id": user_id,
                    "project_id": project_id,
                    "action": "formula.changed",
                    "resource_type": resource_type,
                    "resource_id": change["row_code"],
                    "details": {
                        "event_type": "formula_changed",
                        "module": change["module"],
                        "row_code": change["row_code"],
                        "action": change["action"],
                        "old_formula": change["old_formula"],
                        "new_formula": change["new_formula"],
                        "result_value": change["result_value"],
                    },
                }
                await append_audit_log(db_session, payload)

            await db_session.flush()

            # 验证条目数恰好等于变更次数
            stmt = select(func.count()).select_from(AuditLogEntry).where(
                AuditLogEntry.action_type == "formula.changed"
            )
            result = await db_session.execute(stmt)
            count = result.scalar()

            assert count == len(changes), (
                f"Q5 违反：{len(changes)} 次公式变更产生了 {count} 条审计条目（应恰好 {len(changes)} 条）"
            )

            # 验证每条 entry 的 payload 含必需字段
            stmt_all = select(AuditLogEntry).where(
                AuditLogEntry.action_type == "formula.changed"
            ).order_by(AuditLogEntry.ts)
            result_all = await db_session.execute(stmt_all)
            entries = result_all.scalars().all()

            for i, entry in enumerate(entries):
                assert entry.payload["event_type"] == "formula_changed", (
                    f"Q5 违反：第 {i+1} 条 entry 的 event_type 不是 'formula_changed'"
                )
                assert "module" in entry.payload, f"Q5 违反：第 {i+1} 条 entry 缺少 module 字段"
                assert "row_code" in entry.payload, f"Q5 违反：第 {i+1} 条 entry 缺少 row_code 字段"
                assert entry.payload["module"] == changes[i]["module"]
                assert entry.payload["row_code"] == changes[i]["row_code"]

    @given(changes=formula_change_sequence())
    @settings(max_examples=15, deadline=None)
    def test_hash_chain_integrity(self, changes):
        """每条 formula.changed 条目的 prev_hash → entry_hash 形成有效哈希链。

        验证：
        1. 第一条 entry 的 prev_hash == GENESIS_HASH
        2. 后续每条 entry 的 prev_hash == 前一条的 entry_hash
        3. 所有 entry_hash 非空且唯一
        """
        asyncio.run(self._check_hash_chain_integrity(changes))

    async def _check_hash_chain_integrity(self, changes):
        async with fresh_db_session() as db_session:
            project_id = uuid.uuid4()
            user_id = uuid.uuid4()

            for change in changes:
                resource_type = "workpaper" if change["module"] == "workpaper" else "report_config"
                payload: AuditLogPayload = {
                    "user_id": user_id,
                    "project_id": project_id,
                    "action": "formula.changed",
                    "resource_type": resource_type,
                    "resource_id": change["row_code"],
                    "details": {
                        "event_type": "formula_changed",
                        "module": change["module"],
                        "row_code": change["row_code"],
                        "action": change["action"],
                        "old_formula": change["old_formula"],
                        "new_formula": change["new_formula"],
                        "result_value": change["result_value"],
                    },
                }
                await append_audit_log(db_session, payload)

            await db_session.flush()

            # 查询所有条目按时间排序
            stmt = select(AuditLogEntry).where(
                AuditLogEntry.action_type == "formula.changed"
            ).order_by(AuditLogEntry.ts)
            result = await db_session.execute(stmt)
            entries = result.scalars().all()

            assert len(entries) == len(changes), (
                f"Q5 违反：哈希链条目数 {len(entries)} != 变更次数 {len(changes)}"
            )

            # 验证哈希链完整性
            seen_hashes = set()
            for i, entry in enumerate(entries):
                # entry_hash 非空
                assert entry.entry_hash, f"Q5 违反：第 {i+1} 条 entry_hash 为空"
                assert len(entry.entry_hash) == 64, (
                    f"Q5 违反：第 {i+1} 条 entry_hash 长度 {len(entry.entry_hash)} != 64"
                )

                # entry_hash 唯一
                assert entry.entry_hash not in seen_hashes, (
                    f"Q5 违反：第 {i+1} 条 entry_hash 重复"
                )
                seen_hashes.add(entry.entry_hash)

                # prev_hash 链接验证
                if i == 0:
                    assert entry.prev_hash == GENESIS_HASH, (
                        f"Q5 违反：首条 prev_hash 应为 GENESIS_HASH，实际为 {entry.prev_hash}"
                    )
                else:
                    assert entry.prev_hash == entries[i - 1].entry_hash, (
                        f"Q5 违反：第 {i+1} 条 prev_hash 应为前一条 entry_hash\n"
                        f"  expected: {entries[i-1].entry_hash}\n"
                        f"  actual:   {entry.prev_hash}"
                    )
