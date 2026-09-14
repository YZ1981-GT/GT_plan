"""回填上游适配器守卫 — deliverable-lineage-wiring-and-writeback-closure Task 18/19

**Validates: Requirements 9.2, 9.3, 9.4, 9.5**

Property 17：报告正文回填**只写** ``AuditReport.report_body_json``，``DisclosureNote`` 不变
Property 18：派生/模板固定段落不可回填
Property 19：回填内容在重新生成后保留（`_update_report_body_json` 的 sections 保留语义）

反向自检：
- 主流程若回到硬编码 ``DisclosureNote`` 则打红（Task 18 的核心价值）
- JSONB 就地改嵌套对象不整体重赋值时 SQLAlchemy 不视为脏 → 静默不落库
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.deliverable_capabilities import WRITEBACK_SUPPORTED_DOC_TYPES
from app.services.writeback_target_adapters import (
    ADAPTER_BY_DOC_TYPE,
    DERIVED_REPORT_BODY_SECTIONS,
    DisclosureNoteAdapter,
    ReportBodyAdapter,
    get_writeback_adapter,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

WB_SRC = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "deliverable_writeback_service.py"
)


def _strip_comments(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    return re.sub(r"#[^\n]*", "", src)


# ─── Property 11 延伸：能力矩阵与适配器表必须一致 ───────────────────────────


def test_adapter_table_matches_capability_matrix():
    """能力矩阵说支持回填的 doc_type，必须都有适配器；反之亦然。

    双真源漂移的经典形态：矩阵开了但没适配器 ⇒ 端点放行、`get_writeback_adapter`
    返 None ⇒ 回填静默返回全空（用户点了没反应）。
    """
    assert set(ADAPTER_BY_DOC_TYPE) == set(WRITEBACK_SUPPORTED_DOC_TYPES), (
        f"适配器表 {sorted(ADAPTER_BY_DOC_TYPE)} 与能力矩阵 "
        f"{sorted(WRITEBACK_SUPPORTED_DOC_TYPES)} 不一致"
    )


def test_get_adapter_returns_none_for_unsupported():
    assert get_writeback_adapter(None, "financial_report") is None
    assert get_writeback_adapter(None, None) is None
    assert isinstance(
        get_writeback_adapter(None, "disclosure_notes"), DisclosureNoteAdapter
    )
    assert isinstance(get_writeback_adapter(None, "audit_report"), ReportBodyAdapter)


def test_adapters_expose_chinese_upstream_label():
    """UI 全中文化：错误文案要拼上游名，标签不得是英文。"""
    for cls in ADAPTER_BY_DOC_TYPE.values():
        label = cls.upstream_label
        assert label and re.search(r"[\u4e00-\u9fff]", label), label


# ─── Task 18 接线：主流程不得再硬编码 DisclosureNote ────────────────────────


def test_writeback_main_flow_has_no_hardcoded_disclosure_note():
    """反向自检：主流程五处上游读写必须全部走适配器。

    历史实现把 ``DisclosureNote`` 硬编码在提取/读上游/写上游/冲突读/裁决写
    五处，于是报告正文交付件点回填也去写 ``disclosure_notes``
    （章节标识 `opinion` 与附注章节号不同命名空间）⇒ UPDATE 恒 0 行。
    """
    code = _strip_comments(WB_SRC.read_text(encoding="utf-8"))
    assert "sa.update(DisclosureNote)" not in code, "仍有硬编码的附注 UPDATE"
    assert "from app.models.report_models import DisclosureNote" not in code, (
        "仍直接 import DisclosureNote ⇒ 上游未收敛到适配器"
    )
    # 正向：适配器确实被使用
    assert "_resolve_adapter(" in code
    assert "self._adapter.read_upstream(" in code
    assert "self._adapter.write_upstream(" in code or "adapter.write_upstream(" in code


def test_adapter_defaults_to_disclosure_note_for_zero_regression():
    """`__init__` 默认附注适配器 —— 使**直接调用** `_write_text_content`
    的既有测试零改动（抽适配器前它就是硬编码附注）。"""
    code = _strip_comments(WB_SRC.read_text(encoding="utf-8"))
    assert "self._adapter" in code
    assert "DisclosureNoteAdapter(db)" in code


# ─── Property 18：派生段落不可回填 ──────────────────────────────────────────


def test_property_18_derived_sections_are_not_writable():
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 18
    assert DERIVED_REPORT_BODY_SECTIONS, "派生段落集合为空 ⇒ 本守卫空转"
    for sid in ("mgmt_responsibility", "cpa_responsibility", "signature"):
        assert ReportBodyAdapter.is_derived_section(sid), sid


def test_property_18_human_authored_sections_stay_writable():
    """反面：人工撰写的段落**必须**可回填（回填的价值所在）。

    若有人把 opinion / kam 加进派生集合，报告正文回填就等于全废。
    """
    for sid in (
        "opinion",
        "basis",
        "kam",
        "emphasis",
        "other_info",
        "other_matter",
        "qualified_basis",
        "adverse_basis",
        "disclaimer_basis",
    ):
        assert not ReportBodyAdapter.is_derived_section(sid), (
            f"{sid} 被误判为派生段落 ⇒ 人工润色的文字无法回填"
        )


# ─── Property 17：报告正文只写 report_body_json ─────────────────────────────


async def _session():
    from app.models.report_models import AuditReport, DisclosureNote

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            AuditReport.metadata.create_all,
            tables=[AuditReport.__table__, DisclosureNote.__table__],
        )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _run(factory_coro):
    async def _main():
        engine, factory = await _session()
        try:
            async with factory() as session:
                return await factory_coro(session)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


async def _seed_report(session, project_id, year, sections):
    from app.models.report_models import AuditReport, OpinionType

    # 🔴 audit_report 的 NOT NULL 无默认列恰为 project_id / year / opinion_type ——
    # 漏 opinion_type 会以 IntegrityError 形式在 flush 时炸（不是断言失败）。
    report = AuditReport(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        opinion_type=OpinionType.unqualified,
        report_body_json={
            "optional_sections": {},
            "template_version": "2025-v1",
            "sections": sections,
        },
    )
    session.add(report)
    await session.flush()
    return report


@pytest.mark.parametrize("resolution_text", ["审计师润色后的意见段。"])
def test_property_17_report_body_write_targets_report_body_json(resolution_text):
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 17
    pid, year = uuid.uuid4(), 2025

    async def _scenario(session):
        from app.models.report_models import AuditReport, DisclosureNote

        await _seed_report(
            session,
            pid,
            year,
            [{"section_id": "opinion", "section_name": "审计意见段", "content": "旧文字"}],
        )
        # 同时放一条附注记录，用于断言它**不被**触碰
        # 🔴 disclosure_notes.section_title 也是 NOT NULL（漏了会 IntegrityError）
        note = DisclosureNote(
            id=uuid.uuid4(),
            project_id=pid,
            year=year,
            note_section="八、1",
            section_title="货币资金",
            text_content="附注原文",
        )
        session.add(note)
        await session.flush()

        adapter = ReportBodyAdapter(session)
        rc = await adapter.write_upstream(pid, year, "opinion", resolution_text)
        got = await adapter.read_upstream(pid, year, "opinion")

        report = (
            await session.execute(sa.select(AuditReport).where(AuditReport.project_id == pid))
        ).scalar_one()
        note_after = (
            await session.execute(
                sa.select(DisclosureNote.text_content).where(
                    DisclosureNote.project_id == pid
                )
            )
        ).scalar_one()
        return rc, got, report.report_body_json, note_after

    rc, got, body, note_after = _run(_scenario)

    assert rc == 1
    assert got == resolution_text
    assert body["sections"][0]["content"] == resolution_text
    # 既有元数据键不得被抹掉
    assert body["template_version"] == "2025-v1"
    assert "optional_sections" in body
    # 附注完全未被触碰（需求 9.2 SHALL NOT 写 DisclosureNote）
    assert note_after == "附注原文"


def test_report_body_write_returns_zero_when_sections_missing():
    """交付件里有该章节但 DB 无 `sections`（生成于锚点接线之前）⇒ 0 行。

    如实落 failed 让用户重新生成，**不凭空造章节**。
    """
    pid, year = uuid.uuid4(), 2025

    async def _scenario(session):
        from app.models.report_models import AuditReport

        from app.models.report_models import OpinionType

        report = AuditReport(
            id=uuid.uuid4(),
            project_id=pid,
            year=year,
            opinion_type=OpinionType.unqualified,
            report_body_json={"template_version": "2025-v1"},  # 无 sections
        )
        session.add(report)
        await session.flush()
        adapter = ReportBodyAdapter(session)
        rc = await adapter.write_upstream(pid, year, "opinion", "新文字")
        after = (
            await session.execute(
                sa.select(AuditReport.report_body_json).where(
                    AuditReport.project_id == pid
                )
            )
        ).scalar_one()
        return rc, after

    rc, after = _run(_scenario)
    assert rc == 0
    assert "sections" not in after, "不得凭空创建 sections 数组"


def test_report_body_write_rejects_derived_section():
    """派生段落 ⇒ 0 行且内容未变（需求 9.4）。"""
    pid, year = uuid.uuid4(), 2025

    async def _scenario(session):
        await _seed_report(
            session,
            pid,
            year,
            [
                {
                    "section_id": "cpa_responsibility",
                    "section_name": "注册会计师对财务报表审计的责任段",
                    "content": "准则标准表述",
                }
            ],
        )
        adapter = ReportBodyAdapter(session)
        rc = await adapter.write_upstream(
            pid, year, "cpa_responsibility", "我改了准则用语"
        )
        got = await adapter.read_upstream(pid, year, "cpa_responsibility")
        return rc, got

    rc, got = _run(_scenario)
    assert rc == 0
    assert got == "准则标准表述", "派生段落被改写了"


def test_report_body_read_returns_empty_for_unknown_section():
    pid, year = uuid.uuid4(), 2025

    async def _scenario(session):
        await _seed_report(session, pid, year, [])
        adapter = ReportBodyAdapter(session)
        return await adapter.read_upstream(pid, year, "opinion")

    assert _run(_scenario) == ""


def test_report_body_write_is_idempotent_on_same_value():
    """同值写入仍算成功（与 SQL UPDATE 同值 rowcount=1 的语义对齐）。"""
    pid, year = uuid.uuid4(), 2025

    async def _scenario(session):
        await _seed_report(
            session, pid, year,
            [{"section_id": "opinion", "section_name": "审计意见段", "content": "同一段文字"}],
        )
        adapter = ReportBodyAdapter(session)
        return await adapter.write_upstream(pid, year, "opinion", "同一段文字")

    assert _run(_scenario) == 1


# ─── Property 19：重新生成后保留人工文字 ────────────────────────────────────


def test_property_19_confirm_preserves_previous_sections_when_scan_fails():
    """`_update_report_body_json(sections=None)` 必须**保留**上一版 sections。

    否则一次锚点扫描失败就把已回填的人工文字抹掉（需求 9.6 的反面）。
    源码级断言 —— 该分支只在扫描异常时走到，构造真实场景成本过高。
    """
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "template_fill_service.py"
    ).read_text(encoding="utf-8")
    i = src.index("async def _update_report_body_json")
    nxt = re.search(r"\n    (?:async )?def ", src[i:])
    fn = _strip_comments(src[i : i + nxt.start()] if nxt else src[i:])

    assert "if sections:" in fn, "未区分「有 sections」与「未提供」"
    assert 'get("sections")' in fn, "未读取上一版 sections 做保留"
    # 反向自检：不得无条件写入（那等于未提供时清空）
    assert 'body_json["sections"] = sections\n' in fn or "body_json[\"sections\"] = sections" in fn


def test_jsonb_write_actually_hits_the_db_column():
    """🔴 判据必须查 **DB 列真值**，不能查内存对象。

    2026-08-04 实测：就地改 `sections[i]["content"]` + 整体重赋值
    `report.report_body_json = {**body, ...}` 时——

    - `read_upstream` 返回**新值**（走 identity map 读内存对象）✅ 看着对
    - 而 `SELECT report_body_json` 的**列真值仍是旧值** ❌

    两层坑叠加：①未声明 MutableDict 的 JSON 列，就地改嵌套对象不标脏；
    ②整体重赋值时 `body` 就是 ORM 持有的那个 dict、嵌套已被就地改过 ⇒
    新旧值 `==` 相等 ⇒ 工作单元判「无净变更」⇒ 不发 UPDATE。

    故适配器必须**深拷贝构造新结构**。只断言「有整体重赋值」是**不充分**的
    （我上一版守卫就漏在这里，源码级断言通过而 DB 没写进去）。
    """
    pid, year = uuid.uuid4(), 2025

    async def _scenario(session):
        from app.models.report_models import AuditReport

        await _seed_report(
            session, pid, year,
            [{"section_id": "opinion", "section_name": "审计意见段", "content": "旧文字"}],
        )
        adapter = ReportBodyAdapter(session)
        rc = await adapter.write_upstream(pid, year, "opinion", "新文字")
        # 绕过 identity map，直接取列值
        raw = (
            await session.execute(
                sa.select(AuditReport.report_body_json).where(
                    AuditReport.project_id == pid
                )
            )
        ).scalar_one()
        return rc, raw

    rc, raw = _run(_scenario)
    assert rc == 1
    assert raw["sections"][0]["content"] == "新文字", (
        "DB 列真值未更新 ⇒ JSONB 变更未被 SQLAlchemy 识别（内存对象可能看着是对的）"
    )


def test_adapter_does_not_mutate_nested_dict_in_place():
    """反向自检：源码不得就地改嵌套 content（那会让工作单元判无净变更）。"""
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "writeback_target_adapters.py"
    ).read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert 'hit["content"] = new_text' not in code, "仍在就地改嵌套 dict"
    assert 'sections[idx]["content"] =' not in code, "仍在就地改嵌套 dict"
    assert "new_sections" in code, "未深拷贝构造新 sections"
    assert 'report.report_body_json = {**body, "sections": new_sections}' in code
