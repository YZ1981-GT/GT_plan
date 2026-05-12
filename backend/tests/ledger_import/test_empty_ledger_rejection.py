"""F42 / Sprint 7.9-7.11 + 10.42-10.44: 规模异常拦截（零行 / 异常规模）。

覆盖 design D30 的四类场景：

1. **零行**：``total_rows_estimate < 10`` → ``EMPTY_LEDGER_WARNING``。
2. **极小（相对历史）**：同 project 历史均值 N，新导入 < 0.1N → ``SUSPICIOUS_DATASET_SIZE``。
3. **正常规模**：历史均值附近（0.1-10 倍之间）→ 无警告。
4. **门控拒绝**：有警告且 ``force_submit=False`` → 调用路径必须抛 400 +
   ``SCALE_WARNING_BLOCKED``（模拟 submit 端点内部的 gate 判断）。

本测试复用 ``test_cross_project_isolation.py`` 的 SQLite 内存库 fixture 模板，
不依赖任何真实 PG 或文件系统，跑 <1s。

注：端到端 HTTP 层调用涉及 require_project_access + bundle 文件系统，
被 Sprint 9 的 UAT 覆盖。本文件聚焦"规则函数 + 门控行为"的单元/集成测试。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容适配：PG JSONB/UUID 降级到 JSON/uuid（必须在 Base.metadata 构建前生效）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
from app.services.ledger_import.scale_warnings import (  # noqa: E402
    EMPTY_ROW_THRESHOLD,
    SUSPICIOUS_MAX_RATIO,
    SUSPICIOUS_MIN_RATIO,
    check_scale_warnings,
)


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# 辅助：在目标 project 下建立 N 个 active 历史数据集（指定行数）
# ---------------------------------------------------------------------------
async def _seed_history(
    db: AsyncSession,
    project_id: uuid.UUID,
    total_rows_list: list[int],
    *,
    base_year: int = 2022,
) -> None:
    """为 project 直接插入多条 active 历史数据集记录（绕过 activate 的 integrity check）。

    每个数据集使用独立的 year（避免同 year 互相 supersede）；``record_summary``
    写入 4 张表的行数，总和等于 ``total_rows``。本函数只写 ledger_datasets 表
    metadata，不插真实 Tb* 物理行（scale_warnings 只读 record_summary，不查
    物理行数），避免 fixture 变慢。
    """
    from app.models.dataset_models import DatasetStatus, LedgerDataset

    for idx, total_rows in enumerate(total_rows_list):
        per_table = total_rows // 4
        record_summary = {
            "tb_balance": per_table,
            "tb_ledger": total_rows - per_table * 3,
            "tb_aux_balance": per_table,
            "tb_aux_ledger": per_table,
        }
        db.add(
            LedgerDataset(
                id=uuid.uuid4(),
                project_id=project_id,
                year=base_year + idx,
                status=DatasetStatus.active,
                source_type="import",
                record_summary=record_summary,
            )
        )
    await db.flush()


def _codes(warnings: list[dict]) -> set[str]:
    return {w["code"] for w in warnings}


# ===========================================================================
# 1) 零行文件 → EMPTY_LEDGER_WARNING
# ===========================================================================
@pytest.mark.asyncio
async def test_zero_rows_triggers_empty_ledger_warning(db_session: AsyncSession):
    project_id = uuid.uuid4()

    # 没有任何历史，保证不会撞到 SUSPICIOUS 规则
    for rows in (0, EMPTY_ROW_THRESHOLD - 1):
        warnings = await check_scale_warnings(
            {"total_rows_estimate": rows}, project_id, db_session
        )
        assert "EMPTY_LEDGER_WARNING" in _codes(warnings), (
            f"rows={rows} 应该触发 EMPTY_LEDGER_WARNING，实际 {warnings}"
        )
        for w in warnings:
            if w["code"] == "EMPTY_LEDGER_WARNING":
                assert w["severity"] == "warning"
                assert str(rows) in w["message"], "message 应含实际行数"


# ===========================================================================
# 2) 相对历史均值异常（极小 / 极大）→ SUSPICIOUS_DATASET_SIZE
# ===========================================================================
@pytest.mark.asyncio
async def test_tiny_vs_history_triggers_suspicious(db_session: AsyncSession):
    """历史均值 ~1M 行，当前 50k → ratio 0.05 < 0.1，触发 SUSPICIOUS。"""
    project_id = uuid.uuid4()
    await _seed_history(db_session, project_id, [1_000_000, 1_000_000, 1_000_000])

    warnings = await check_scale_warnings(
        {"total_rows_estimate": 50_000}, project_id, db_session
    )
    codes = _codes(warnings)
    assert "SUSPICIOUS_DATASET_SIZE" in codes, (
        f"tiny dataset vs 历史 1M 应该触发 SUSPICIOUS，实际 {warnings}"
    )
    assert "EMPTY_LEDGER_WARNING" not in codes, (
        "50k > EMPTY_ROW_THRESHOLD，不应该再触发 EMPTY"
    )


@pytest.mark.asyncio
async def test_huge_vs_history_triggers_suspicious(db_session: AsyncSession):
    """历史均值 10k 行，当前 500k → ratio 50 > 10，触发 SUSPICIOUS。"""
    project_id = uuid.uuid4()
    await _seed_history(db_session, project_id, [10_000, 10_000, 10_000])

    warnings = await check_scale_warnings(
        {"total_rows_estimate": 500_000}, project_id, db_session
    )
    assert "SUSPICIOUS_DATASET_SIZE" in _codes(warnings), (
        f"500k >> 历史 10k 均值应该触发 SUSPICIOUS，实际 {warnings}"
    )


# ===========================================================================
# 3) 正常规模 → 空 warnings
# ===========================================================================
@pytest.mark.asyncio
async def test_normal_size_no_warnings(db_session: AsyncSession):
    """历史均值 100k，当前 120k → ratio 1.2，在 [0.1, 10] 之间。"""
    project_id = uuid.uuid4()
    await _seed_history(db_session, project_id, [100_000, 100_000, 100_000])

    warnings = await check_scale_warnings(
        {"total_rows_estimate": 120_000}, project_id, db_session
    )
    assert warnings == [], f"正常规模不应产生警告，实际 {warnings}"


@pytest.mark.asyncio
async def test_first_import_skips_suspicious(db_session: AsyncSession):
    """首次导入（无历史）不应触发 SUSPICIOUS（无基线可比）。"""
    project_id = uuid.uuid4()

    warnings = await check_scale_warnings(
        {"total_rows_estimate": 100_000}, project_id, db_session
    )
    assert "SUSPICIOUS_DATASET_SIZE" not in _codes(warnings), (
        "首次导入不应触发 SUSPICIOUS_DATASET_SIZE，实际 " + str(warnings)
    )
    assert "EMPTY_LEDGER_WARNING" not in _codes(warnings), (
        "100k 正常行数也不应触发 EMPTY"
    )


# ===========================================================================
# 4) submit 端点门控：警告 + !force_submit → HTTPException(400, SCALE_WARNING_BLOCKED)
# ===========================================================================
@pytest.mark.asyncio
async def test_submit_gate_blocks_when_warnings_and_not_forced(
    db_session: AsyncSession,
):
    """复现 ledger_import_v2.submit_import 的门控语义。

    该函数检测到 warnings 非空且 ``force_submit=False`` 时，必须抛
    ``HTTPException(status_code=400)``，detail 含 ``error_code=SCALE_WARNING_BLOCKED``
    + ``warnings`` 数组。``force_submit=True`` 时放行。
    """
    project_id = uuid.uuid4()
    # 制造一个零行的 detection 触发 EMPTY_LEDGER_WARNING
    detection_payload = {"total_rows_estimate": 0}
    warnings = await check_scale_warnings(detection_payload, project_id, db_session)
    assert warnings, "前置条件：必须产生警告（否则门控测试无意义）"

    # 复现 submit_import 的门控判断逻辑
    def _submit_gate(force_submit: bool):
        if warnings and not force_submit:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "SCALE_WARNING_BLOCKED",
                    "message": "检测到规模异常，需用户确认后强制继续",
                    "warnings": warnings,
                    "total_rows_estimate": detection_payload["total_rows_estimate"],
                },
            )

    # 未 force_submit → 必须抛 400
    with pytest.raises(HTTPException) as exc_info:
        _submit_gate(force_submit=False)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error_code"] == "SCALE_WARNING_BLOCKED"
    assert exc_info.value.detail["warnings"] == warnings
    assert any(
        w["code"] == "EMPTY_LEDGER_WARNING"
        for w in exc_info.value.detail["warnings"]
    )

    # force_submit=True → 放行（函数不抛）
    _submit_gate(force_submit=True)  # no exception


# ===========================================================================
# 辅助：阈值常量未被意外改动
# ===========================================================================
def test_threshold_constants_match_design():
    """design D30 固定阈值：< 10 行 / ±10× 历史均值。"""
    assert EMPTY_ROW_THRESHOLD == 10
    assert SUSPICIOUS_MIN_RATIO == pytest.approx(0.1)
    assert SUSPICIOUS_MAX_RATIO == pytest.approx(10.0)
