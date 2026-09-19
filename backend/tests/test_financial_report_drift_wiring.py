"""报表差异检测的**生产接线** — deliverable-lineage-wiring-and-writeback-closure Wave 4 Task 22

Task 21 交付了 `FinancialReportDriftService`，但当时**没有任何生产调用方** ⇒
`drift_report` 列恒为 NULL ⇒ `confirm_deliverable` 的闸门恒放行。这正是平台反复
出现的「additive 列/服务 + 未接线 = 死代码」形态（memory 已登记多例）。本文件守住：

1. 接线存在且只挂在 **OO 保存路径**（不挂生成路径 —— 见 `test_detect_not_wired_into_generate_path`）
2. 检测结果**真的落库**到 `word_export_task_versions.drift_report`
3. 非财务报表交付件不被误检
4. 检测失败 fail-open（保存已成功，不得回滚）
5. Property 20：接线面上不存在 xlsx → 上游的写入通道
6. 基线归因（`pre_existing`）：配置错位导致的既存差异**不得**被归因为手工改动
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.phase13_models import (
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.services.financial_report_drift_service import (
    annotate_pre_existing,
    should_block_confirm,
)
from app.services.onlyoffice_callback_service import OnlyOfficeCallbackService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

BACKEND = Path(__file__).resolve().parents[1]


def _strip_py_comments(src: str) -> str:
    """剥掉 `#` 行注释与三引号 docstring。

    🔴 memory 铁律：读源码型守卫必须先剥注释。本文件的被测源码（`detect_and_store_report_drift`
    的 docstring）里**大段解释了「为什么不挂生成路径」**，不剥注释会让
    `test_detect_not_wired_into_generate_path` 假红。
    """
    out: list[str] = []
    i, n = 0, len(src)
    in_str: str | None = None
    while i < n:
        if in_str:
            if src.startswith(in_str, i):
                i += len(in_str)
                in_str = None
            else:
                i += 1
            continue
        if src.startswith('"""', i) or src.startswith("'''", i):
            in_str = src[i : i + 3]
            i += 3
            continue
        ch = src[i]
        if ch == "#":
            while i < n and src[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def test_strip_comments_selfcheck():
    """反向自检：剥注释确实生效（否则源码级断言全是空转）。"""
    sample = 'a = 1  # ReportExcelExporter\n"""doc ReportExcelExporter"""\nb = 2\n'
    stripped = _strip_py_comments(sample)
    assert "ReportExcelExporter" not in stripped
    assert "a = 1" in stripped and "b = 2" in stripped
    assert sample.count("ReportExcelExporter") == 2


# ─── 接线：源码级 ───────────────────────────────────────────────────────────


def _oo_src() -> str:
    return _strip_py_comments(
        (BACKEND / "app" / "services" / "onlyoffice_callback_service.py").read_text(
            encoding="utf-8"
        )
    )


def test_handle_callback_triggers_drift_detection():
    """`handle_callback` 保存后必须触发差异检测（需求 10.2）。

    反向自检语义：删掉这一行 ⇒ `drift_report` 恒 NULL ⇒ 闸门恒放行，
    Task 21 的全部工作变成死代码。
    """
    src = _oo_src()
    i = src.index("async def handle_callback")
    j = src.index("async def detect_and_store_report_drift")
    body = src[i:j]
    assert "detect_and_store_report_drift" in body, (
        "handle_callback 未触发差异检测 ⇒ drift_report 恒 NULL、闸门恒放行"
    )
    assert "baseline_version_no=" in body, (
        "未传基线版本 ⇒ 无法区分「本次编辑引入」与「配置错位导致的既存差异」"
    )


def test_detect_result_is_persisted_to_version_column():
    """检测结果必须落 `version.drift_report` 并 flush（否则读不到）。"""
    src = _oo_src()
    i = src.index("async def detect_and_store_report_drift")
    body = src[i:]
    assert "version.drift_report = report" in body, "检测结果未落库"
    assert "await self.db.flush()" in body, "未 flush ⇒ 同一事务内后续读取拿不到"
    assert ".detect(" in body, "未调用 detect"


def test_non_financial_report_is_skipped_source_level():
    src = _oo_src()
    i = src.index("async def detect_and_store_report_drift")
    body = src[i:]
    assert 'startswith("financial_report")' in body, (
        "未按 doc_type 门控 ⇒ 附注/报告正文也会被当报表比对数字"
    )


def test_detect_not_wired_into_generate_path():
    """🔴 差异检测**不得**挂在生成路径上（本次的关键设计判断）。

    报表 xlsx 由 `ReportExcelExporter` 按试算表重算值写出，生成路径天然一致；
    但真实库实证 `cell_mapping.json` 的坐标与部分模板变体布局不一致
    （项目 0ec33ac9 报表 v8 报 22 处系统性错位）—— 若在生成时检测并阻断 confirmed，
    配置问题会立刻变成业务阻塞（刚生成的报表就确认不了）。

    判据：`FinancialReportDriftService` 的生产实例化点**只有** OO 回调服务；
    `deliverable_service` 只许引用 `should_block_confirm`（判定，不检测）。
    """
    hits: list[str] = []
    for path in (BACKEND / "app").rglob("*.py"):
        if path.name == "financial_report_drift_service.py":
            continue
        src = _strip_py_comments(path.read_text(encoding="utf-8"))
        if "FinancialReportDriftService" in src:
            hits.append(str(path.relative_to(BACKEND)).replace("\\", "/"))
    assert hits == ["app/services/onlyoffice_callback_service.py"], (
        f"差异检测的生产调用方应只有 OO 回调，实得 {hits}"
    )

    ds = _strip_py_comments(
        (BACKEND / "app" / "services" / "deliverable_service.py").read_text(
            encoding="utf-8"
        )
    )
    assert "should_block_confirm" in ds, "confirm 闸门未走判定唯一入口"
    assert "FinancialReportDriftService" not in ds, (
        "confirm 路径不得自己跑检测（confirm 时重算会让阻断结论随上游变化而漂移）"
    )


def test_property_20_no_xlsx_writeback_on_wiring_surface():
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 20
    """接线面（OO 回调）上不得出现 xlsx → 上游的写入通道（需求 10.1）。

    Task 21 已守住差异服务自身；本条守住**接线之后**没人顺手加回写：
    回调服务不得 update/insert `TrialBalance` / `ReportConfig` / `AuditReport` /
    `FinancialReport`。
    """
    import re

    src = _oo_src()
    for model in ("TrialBalance", "ReportConfig", "AuditReport", "FinancialReport"):
        # 用词边界匹配：`FinancialReportDriftService` 含 `FinancialReport` 子串，
        # 裸 `in` 会把「引用了差异检测服务」误报成「引用了报表模型」。
        assert re.search(rf"\b{model}\b", src) is None, (
            f"OO 回调引用了 {model} ⇒ 可能存在 xlsx→上游 写入通道（违反需求 10.1）"
        )
    # 反向自检：差异服务名确实在源码里（证明上面的词边界不是因为整段都没内容）
    assert "FinancialReportDriftService" in src


# ─── 接线：行为级 ───────────────────────────────────────────────────────────


async def _mk_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            WordExportTask.metadata.create_all,
            tables=[WordExportTask.__table__, WordExportTaskVersion.__table__],
        )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _run(scenario):
    async def _main():
        engine, factory = await _mk_session()
        try:
            async with factory() as session:
                return await scenario(session)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


async def _seed(session, doc_type: str):
    task = WordExportTask(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        doc_type=doc_type,
        status=WordExportStatus.generated.value,
        created_by=uuid.uuid4(),
    )
    session.add(task)
    await session.flush()
    version = WordExportTaskVersion(
        id=uuid.uuid4(),
        word_export_task_id=task.id,
        version_no=2,
        file_path="storage/deliverables/x_v2.xlsx",
        created_by=task.created_by,
        created_via="onlyoffice_edit",
    )
    session.add(version)
    await session.flush()
    return task, version


_FAKE_REPORT = {"diffs": [{"row_code": "BS-006", "period": "current"}], "checked": 10}


def _patch_detect(monkeypatch, result, *, raises: bool = False):
    import app.services.financial_report_drift_service as mod

    calls: list[tuple] = []

    async def _fake(self, task_id, version_no, *, baseline_version_no=None):  # noqa: ANN001
        calls.append((task_id, version_no, baseline_version_no))
        if raises:
            raise RuntimeError("boom")
        return result

    monkeypatch.setattr(mod.FinancialReportDriftService, "detect", _fake)
    return calls


@pytest.mark.parametrize(
    "doc_type,expect_called",
    [
        ("financial_report", True),
        ("financial_report_unadjusted", True),
        ("disclosure_notes", False),
        ("audit_report", False),
    ],
)
def test_detect_gated_by_doc_type_and_persists(monkeypatch, doc_type, expect_called):
    calls = _patch_detect(monkeypatch, _FAKE_REPORT)

    async def _scenario(session):
        task, version = await _seed(session, doc_type)
        svc = OnlyOfficeCallbackService(session)
        got = await svc.detect_and_store_report_drift(
            task, version=version, baseline_version_no=1
        )
        await session.refresh(version)
        return got, version.drift_report

    got, stored = _run(_scenario)

    assert bool(calls) is expect_called
    if expect_called:
        assert got == _FAKE_REPORT
        assert stored == _FAKE_REPORT, "检测结果未落库 ⇒ 闸门读不到"
        assert calls[0][2] == 1, "基线版本号未透传"
    else:
        assert got is None
        assert stored is None, "非报表交付件不得写 drift_report"


def test_none_result_is_stored_as_none_not_empty_dict(monkeypatch):
    """未配映射（`None`）必须照实写 None。

    写 `{}` 虽然同样放行，但语义变成「已检测且无差异」—— 前端与后来者会据此
    以为检测跑过了，而实际上一格都没比。
    """
    _patch_detect(monkeypatch, None)

    async def _scenario(session):
        task, version = await _seed(session, "financial_report")
        svc = OnlyOfficeCallbackService(session)
        await svc.detect_and_store_report_drift(
            task, version=version, baseline_version_no=None
        )
        await session.refresh(version)
        return version.drift_report

    assert _run(_scenario) is None


def test_detect_failure_is_fail_open(monkeypatch):
    """检测抛异常不得冒泡 —— 保存已成功，抛出会让 OnlyOffice 认为保存失败并重试。"""
    _patch_detect(monkeypatch, None, raises=True)

    async def _scenario(session):
        task, version = await _seed(session, "financial_report")
        svc = OnlyOfficeCallbackService(session)
        return await svc.detect_and_store_report_drift(
            task, version=version, baseline_version_no=1
        )

    assert _run(_scenario) is None


# ─── 基线归因：不得把配置错位说成手工改动 ────────────────────────────────────


def test_annotate_pre_existing_marks_both_sides():
    diffs = [
        {"row_code": "BS-006", "period": "current"},
        {"row_code": "BS-009", "period": "prior"},
    ]
    out = annotate_pre_existing(diffs, {("BS-006", "current")})
    assert out[0]["pre_existing"] is True
    assert out[1]["pre_existing"] is False
    # 纯函数：不得就地改入参
    assert "pre_existing" not in diffs[0]


def test_annotate_pre_existing_unknown_baseline_marks_nothing():
    """🔴 基线未知（读不到上一版文件）⇒ 一个标记都不打。

    若退化成「未命中即 False」，「基线读不到」会被显示成「本次编辑引入」——
    正是要避免的误指控。
    """
    diffs = [{"row_code": "BS-006", "period": "current"}]
    out = annotate_pre_existing(diffs, None)
    assert out == diffs
    assert "pre_existing" not in out[0]


def test_attribute_prefers_pre_existing_over_manual_edit():
    """🔴 反向自检：差异全为既存时**不得**归因 manual_edit。

    场景 = 映射坐标错位（既存差异）+ 恰好有人做过在线编辑。旧顺序
    （先看 created_via）会把它判成「有人改了报表数字」= 误指控。
    """
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from app.services.financial_report_drift_service import (
        FinancialReportDriftService,
    )

    created = datetime(2026, 1, 2, tzinfo=timezone.utc)

    class _Res:
        def __init__(self, value):
            self._value = value

        def first(self):
            return self._value

        def scalar_one_or_none(self):
            return self._value

    class _DB:
        def __init__(self):
            self._n = 0

        async def execute(self, *_a, **_kw):
            self._n += 1
            if self._n == 1:
                return _Res(
                    SimpleNamespace(created_at=created, created_via="onlyoffice_edit")
                )
            # DB 未在版本之后更新 ⇒ 排除 upstream_changed
            return _Res(datetime(2026, 1, 1, tzinfo=timezone.utc))

    svc = FinancialReportDriftService(_DB())

    got = asyncio.run(
        svc._attribute(  # noqa: SLF001
            uuid.uuid4(),
            2,
            uuid.uuid4(),
            2025,
            False,
            diff_count=3,
            introduced_count=0,
        )
    )
    assert got == "pre_existing", "既存差异被误归因为手工改动"

    # 同一场景但确有新引入的差异 ⇒ 才允许 manual_edit
    svc2 = FinancialReportDriftService(_DB())
    got2 = asyncio.run(
        svc2._attribute(  # noqa: SLF001
            uuid.uuid4(),
            2,
            uuid.uuid4(),
            2025,
            False,
            diff_count=3,
            introduced_count=2,
        )
    )
    assert got2 == "manual_edit"


def test_attribute_without_baseline_falls_back_to_manual_edit():
    """无基线可比（`introduced_count is None`）时保持既有判据，不误标 pre_existing。"""
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from app.services.financial_report_drift_service import (
        FinancialReportDriftService,
    )

    class _Res:
        def __init__(self, v):
            self._v = v

        def first(self):
            return self._v

        def scalar_one_or_none(self):
            return self._v

    class _DB:
        def __init__(self):
            self._n = 0

        async def execute(self, *_a, **_kw):
            self._n += 1
            if self._n == 1:
                return _Res(
                    SimpleNamespace(
                        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                        created_via="onlyoffice_edit",
                    )
                )
            return _Res(None)

    got = asyncio.run(
        FinancialReportDriftService(_DB())._attribute(  # noqa: SLF001
            uuid.uuid4(), 2, uuid.uuid4(), 2025, False, diff_count=3
        )
    )
    assert got == "manual_edit"


def test_block_reason_mentions_pre_existing_when_attributed():
    report = {
        "diffs": [
            {
                "row_code": "BS-006",
                "row_name": "应收账款",
                "sheet": "balance_sheet",
                "coord": "C12",
                "period": "current",
                "file_value": "500.00",
                "expected_value": "400.00",
                "diff": "100.00",
                "pre_existing": True,
            }
        ],
        "attribution": "pre_existing",
        "pre_existing_count": 1,
        "introduced_count": 0,
    }
    blocked, reason = should_block_confirm(report)
    assert blocked is True, "有差异仍须阻断（数字仍与试算表不符）"
    assert "上一版就已存在" in reason
    assert "映射" in reason
    # 仍不得断言手工改动
    assert "手工改动共" not in reason


def test_pre_existing_hint_absent_when_not_attributed():
    """无归因结论时不得凭空出现「上一版就已存在」（反向自检防文案恒显示）。"""
    report = {
        "diffs": [
            {
                "row_code": "BS-006",
                "row_name": "应收账款",
                "sheet": "balance_sheet",
                "coord": "C12",
                "period": "current",
                "file_value": "500.00",
                "expected_value": "400.00",
                "diff": "100.00",
            }
        ]
    }
    _, reason = should_block_confirm(report)
    assert "上一版就已存在" not in reason
