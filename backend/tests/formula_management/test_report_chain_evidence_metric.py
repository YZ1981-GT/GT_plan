"""Task 4.3 · 报表链口径澄清（按 distinct 模板计，不按项目克隆夸大）。

Feature: formula-manager-closure
需求: 15.1
design 锚点: §5 步骤 4「report=report_config」/「formula_push 为自动物化层」、
            §3 数据流表「报表链」、深化 12.3

本任务**只澄清口径 + 固化测试断言口径**，不改模板范式：

- 报表链「生产实证」按 **distinct** 模板/标准计（去重 ``(row_code, formula_used)``），
  **不按项目数夸大**为 N 倍（同一模板的 N 份项目克隆不是 N 份独立证据）。
- ``formula_push`` 明确为**自动物化层、非权威定义源**（权威源 = ``report_config``）。

两层断言：
  1. **纯逻辑层（永不 skip）**：对合成行验证「distinct ≠ clone」的判别逻辑本身，
     并以变异/反向断言证明「若按克隆口径当证据数即被夸大」会被识别。量级由传入
     行现算，**不写死** 82/492/6。
  2. **真库层（PG 不可达则 skip，不假绿）**：对真实 ``financial_report`` 现算两套
     口径，断言 ``clone_count ≈ distinct_pairs × distinct_project_count`` 的克隆关系，
     且断言不以项目数夸大。全部量级现算，禁写死。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.services.formula_management.report_chain_evidence import (
    FORMULA_PUSH_IS_AUTHORITATIVE_SOURCE,
    FORMULA_PUSH_ROLE,
    REPORT_AUTHORITATIVE_SOURCE,
    ReportChainEvidence,
    classify_report_chain_evidence,
)


# ─────────────────────────────────────────────────────────────────────────────
# 第 1 层：纯逻辑判别（永不 skip）——量级由合成行现算，禁写死
# ─────────────────────────────────────────────────────────────────────────────


def _make_cloned_template(n_projects: int, n_template_rows: int) -> list[tuple]:
    """造「同一套模板在 n_projects 个项目各物化一份」的行，无跨项目公式冲突。

    每项目 n_template_rows 行，公式与 row_code 跨项目完全一致（纯克隆）。
    返回 (project_id, report_type, row_code, formula_used) 四元组列表。
    """
    rows: list[tuple] = []
    for p in range(n_projects):
        for r in range(n_template_rows):
            rows.append(
                (
                    f"project-{p}",
                    "balance_sheet",
                    f"BS-{r:03d}",
                    f"=TB(1{r:03d})",  # 跨项目相同公式
                )
            )
    return rows


def test_distinct_vs_clone_discrimination_pure_logic():
    """clone 口径 = distinct × 项目数（纯克隆），distinct 口径不随项目数放大。

    量级全部现算：distinct_pairs 由 row_code+formula 去重得出，不写死。

    **Validates: Requirements 15.1**
    """
    n_projects = 6
    n_template_rows = 82
    rows = _make_cloned_template(n_projects, n_template_rows)

    ev = classify_report_chain_evidence(rows)

    # distinct 口径 = 模板行数（与项目数无关）；现算，非写死。
    assert ev.distinct_pairs == n_template_rows
    # clone 口径 = 物化总行数 = 项目数 × 模板行数。
    assert ev.clone_count == n_projects * n_template_rows
    assert ev.project_count == n_projects
    # 纯克隆：无任何跨项目公式冲突。
    assert ev.cross_project_conflict == 0
    # 核心关系：克隆口径 ≈ distinct × 项目数（这正是「按项目数夸大」的来源）。
    assert ev.clone_count == ev.distinct_pairs * ev.project_count
    # 夸大倍数 == 项目数：把 clone 当证据数即夸大了 project_count 倍。
    assert ev.inflation_ratio == pytest.approx(float(n_projects))


def test_distinct_scales_with_template_not_projects():
    """变异/反向断言：再克隆一份项目，distinct 口径不变、clone 口径才涨。

    证明「用项目数衡量证据」是错的——加项目只增克隆、不增独立证据。

    **Validates: Requirements 15.1**
    """
    base = _make_cloned_template(n_projects=3, n_template_rows=10)
    more_projects = _make_cloned_template(n_projects=9, n_template_rows=10)

    ev_base = classify_report_chain_evidence(base)
    ev_more = classify_report_chain_evidence(more_projects)

    # 加项目：clone 口径随项目数增大（被夸大的那个口径）。
    assert ev_more.clone_count > ev_base.clone_count
    # distinct 口径不随项目数变化（真实证据量级）。
    assert ev_more.distinct_pairs == ev_base.distinct_pairs == 10


def test_genuine_variant_counts_as_independent_evidence():
    """反向断言：若某项目确有不同公式（真变体），distinct 口径才增、冲突被记。

    保证判别逻辑不会把真实变体也当成克隆（避免反向误判）。

    **Validates: Requirements 15.1**
    """
    rows = _make_cloned_template(n_projects=2, n_template_rows=5)
    # 给 project-1 的 BS-000 换一条不同公式 → 真变体。
    rows = [
        (p, rt, rc, ("=TB(9999)" if (p == "project-1" and rc == "BS-000") else f)
         )
        for (p, rt, rc, f) in rows
    ]

    ev = classify_report_chain_evidence(rows)

    # 原 5 对 + 1 条新变体 = 6 distinct 对（现算关系，非写死具体业务量级）。
    assert ev.distinct_pairs == 6
    # (balance_sheet, BS-000) 下出现了 2 条不同公式 → 1 组跨项目冲突。
    assert ev.cross_project_conflict == 1


def test_formula_push_documented_as_materialization_layer():
    """formula_push 文档化为自动物化层、非权威源；权威源 = report_config。

    **Validates: Requirements 15.1**
    """
    assert FORMULA_PUSH_IS_AUTHORITATIVE_SOURCE is False
    assert FORMULA_PUSH_ROLE == "automatic_materialization_layer"
    assert REPORT_AUTHORITATIVE_SOURCE == "report_config"


# ─────────────────────────────────────────────────────────────────────────────
# 第 2 层：真库现算（PG 不可达则 skip，不假绿）
# ─────────────────────────────────────────────────────────────────────────────


def _pg_available() -> bool:
    from app.core.config import settings

    return settings.DATABASE_URL.startswith("postgresql")


@asynccontextmanager
async def _live_engine():
    """连接**现有真实数据库**（非 throwaway），只读查询 financial_report。"""
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import settings

    connect_args = (
        {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    )
    engine = create_async_engine(
        settings.DATABASE_URL, connect_args=connect_args, echo=False
    )
    try:
        yield engine
    finally:
        await engine.dispose()


async def _query_live_rows(engine) -> list[tuple]:
    """现算：取 financial_report 里 formula_used 非空且未软删的行。

    PG 坑（memory）：独立只读查询 + is_deleted 过滤。
    """
    import sqlalchemy as sa

    sql = sa.text(
        "SELECT project_id, report_type, row_code, formula_used "
        "FROM financial_report "
        "WHERE formula_used IS NOT NULL "
        "AND btrim(formula_used) <> '' "
        "AND is_deleted = false"
    )
    async with engine.connect() as conn:
        result = await conn.execute(sql)
        return [tuple(r) for r in result.fetchall()]


@pytest.mark.asyncio
async def test_report_chain_evidence_live_distinct_not_inflated():
    """真库现算：clone 口径 ≈ distinct × 项目数；断言不以项目数夸大。

    量级全部现算输出，**不写死** 82/492/6。PG 不可达则 skip（不假绿）。

    **Validates: Requirements 15.1**
    """
    if not _pg_available():
        pytest.skip(
            "需真实 PostgreSQL（SQLite 不得替代）——报表链真库现算待 PG 可达时生效；"
            "纯逻辑判别层已覆盖口径区分，不假绿"
        )

    try:
        async with _live_engine() as engine:
            rows = await _query_live_rows(engine)
    except Exception as exc:  # 连接失败/表缺失 → skip，不假绿
        pytest.skip(f"真实 PostgreSQL 不可达或 financial_report 表缺失：{exc!r}")

    ev: ReportChainEvidence = classify_report_chain_evidence(rows)

    # 现算输出（供报告引用；不写死任何量级）。
    print(
        "[Task 4.3 现算] clone_count(物化行数)="
        f"{ev.clone_count} distinct_pairs(去重 row_code+formula)="
        f"{ev.distinct_pairs} project_count={ev.project_count} "
        f"cross_project_conflict={ev.cross_project_conflict} "
        f"inflation_ratio={ev.inflation_ratio:.2f}"
    )

    if ev.clone_count == 0:
        pytest.skip(
            "真库 financial_report 当前无含公式行（P1-正式运行数据为空，待 Phase 7 "
            "最小数据运行点亮）——口径脚本已就绪，不假绿"
        )

    # distinct 口径 ≤ clone 口径（去重不可能大于总数）。
    assert ev.distinct_pairs <= ev.clone_count
    # 断言「不以项目数夸大」：克隆口径不是独立证据数——当多项目套同一模板时，
    # clone_count 约等于 distinct × 项目数（现算关系，禁写死具体数）。
    if ev.project_count > 1:
        # 纯克隆上界：distinct × 项目数 ≥ clone（跨项目有变体时 distinct 更大）。
        assert ev.clone_count <= ev.distinct_pairs * ev.project_count
        # 若无跨项目冲突（纯克隆），clone 恰 = distinct × 项目数。
        if ev.cross_project_conflict == 0:
            assert ev.clone_count == ev.distinct_pairs * ev.project_count
            # 夸大倍数 == 项目数：证明「按项目数计」会把证据量放大 project_count 倍。
            assert ev.inflation_ratio == pytest.approx(float(ev.project_count))
