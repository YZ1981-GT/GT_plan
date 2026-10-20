"""QC 规则定义加载器测试

验证 qc_rule_definitions 表的 enabled 过滤逻辑：
1. seed 22 条规则全部加载
2. enabled=false 的规则被 QCEngine 跳过
3. 非 python expression_type 规则产生 warning 日志

需求 4 AC3-7。
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401
import app.models.qc_rule_models  # noqa: E402, F401

from app.models.qc_rule_models import QcRuleDefinition  # noqa: E402

#: QCEngine 内置的 20 条规则（qc_engine.QCEngine.rules）
BUILTIN_QC_RULES = frozenset({f"QC-{n:02d}" for n in range(1, 19)} | {"QC-27", "QC-28"})


@pytest.mark.asyncio
async def test_empty_registry_runs_all_builtin_rules(db_session: AsyncSession, caplog):
    """登记表为空（真实库就是空表）⇒ 内置规则全部执行并给 WARNING，不是「全部禁用」（R7 修过的 P0）。"""
    from app.services.qc_engine import QCEngine

    with caplog.at_level(logging.WARNING, logger="app.services.qc_engine"):
        enabled_codes = await QCEngine()._get_enabled_rule_codes(db_session)
    assert enabled_codes == BUILTIN_QC_RULES
    assert any("为空表" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)


def test_builtin_rule_set_is_pinned():
    """内置规则集合变了要同步本文件的期望（防止新增 / 删规则后这里的精确断言悄悄失真）。"""
    from app.services.qc_engine import QCEngine

    assert {rule.rule_id for rule in QCEngine().rules} == BUILTIN_QC_RULES


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _seed_all_rules(db: AsyncSession) -> None:
    """从 seed JSON 加载全部 22 条规则到数据库。"""
    seed_path = Path(__file__).parent.parent / "data" / "qc_rule_definitions_seed.json"
    with open(seed_path, "r", encoding="utf-8") as f:
        rules_data = json.load(f)
    for item in rules_data:
        rule = QcRuleDefinition(
            id=uuid.uuid4(),
            rule_code=item["rule_code"],
            severity=item["severity"],
            scope=item["scope"],
            category=item["category"],
            title=item["title"],
            description=item.get("description"),
            standard_ref=item.get("standard_ref"),
            expression_type=item.get("expression_type", "python"),
            expression=item.get("expression"),
            enabled=item.get("enabled", True),
            version=item.get("version", 1),
        )
        db.add(rule)
    await db.flush()


# ── 场景 1：seed 22 条规则全部加载 ─────────────────────────────────

@pytest.mark.asyncio
async def test_seed_22_rules_loaded(db_session: AsyncSession):
    """验证 seed JSON 包含 22 条规则，全部可加载到 DB 且 enabled=true。"""
    await _seed_all_rules(db_session)

    import sqlalchemy as sa
    result = await db_session.execute(
        sa.select(sa.func.count()).select_from(QcRuleDefinition)
    )
    total = result.scalar()
    assert total == 22, f"Expected 22 seed rules, got {total}"

    # 全部 enabled
    enabled_result = await db_session.execute(
        sa.select(sa.func.count()).select_from(QcRuleDefinition).where(
            QcRuleDefinition.enabled == sa.true()
        )
    )
    enabled_count = enabled_result.scalar()
    assert enabled_count == 22, f"Expected all 22 enabled, got {enabled_count}"

    # QCEngine 解析出的执行集合：内置 20 条全部执行。
    # 83614b612（sampling-evaluation-and-governance-closure R7）起登记表是**禁用清单**而非准入白名单：
    # 只排除显式 enabled=false 的内置规则；seed 里的 QC-19~26 是提交复核 / 签字门的规则，不在
    # QCEngine 内置集合里；内置的 QC-15~18、QC-27/28 未登记 ⇒ 按启用处理。
    from app.services.qc_engine import QCEngine
    engine = QCEngine()
    enabled_codes = await engine._get_enabled_rule_codes(db_session)
    assert enabled_codes == BUILTIN_QC_RULES


# ── 场景 2：enabled=false 的规则被跳过 ─────────────────────────────

@pytest.mark.asyncio
async def test_disabled_rule_skipped(db_session: AsyncSession):
    """验证 enabled=false 的规则不在 QCEngine 的 active 规则集中。"""
    await _seed_all_rules(db_session)

    # 禁用 QC-14
    import sqlalchemy as sa
    await db_session.execute(
        sa.update(QcRuleDefinition)
        .where(QcRuleDefinition.rule_code == "QC-14")
        .values(enabled=False)
    )
    await db_session.flush()

    from app.services.qc_engine import QCEngine
    engine = QCEngine()
    enabled_codes = await engine._get_enabled_rule_codes(db_session)

    assert enabled_codes == BUILTIN_QC_RULES - {"QC-14"}, "只应排除显式禁用的 QC-14"


# ── 场景 3：非 python 类型规则产生 warning 日志 ─────────────────────

@pytest.mark.asyncio
async def test_non_python_rule_warning(db_session: AsyncSession, caplog):
    """验证 expression_type != 'python' 的规则产生 warning 日志且不加入 enabled 集合。"""
    await _seed_all_rules(db_session)

    # 插入一条 jsonpath 类型规则
    non_python_rule = QcRuleDefinition(
        id=uuid.uuid4(),
        rule_code="QC-99",
        severity="warning",
        scope="workpaper",
        category="测试",
        title="非 Python 测试规则",
        description="jsonpath 类型规则，应被忽略",
        expression_type="jsonpath",
        expression="$.parsed_data.conclusion",
        enabled=True,
        version=1,
    )
    db_session.add(non_python_rule)
    await db_session.flush()

    from app.services.qc_engine import QCEngine
    engine = QCEngine()

    with caplog.at_level(logging.WARNING, logger="app.services.qc_engine"):
        enabled_codes = await engine._get_enabled_rule_codes(db_session)

    # QC-99 不应在 enabled 集合中；内置 20 条照常执行
    assert "QC-99" not in enabled_codes, "Non-python rule should not be in enabled set"
    assert enabled_codes == BUILTIN_QC_RULES

    # 验证 warning 日志
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("R6 stub: non-python rule ignored" in msg and "QC-99" in msg for msg in warning_messages), \
        f"Expected warning about non-python rule QC-99, got: {warning_messages}"
