"""交付件能力矩阵守卫 — deliverable-lineage-wiring-and-writeback-closure Task 8 / 9.1

**Validates: Requirements 6.1, 6.2, 6.4, 6.5**（Property 11：能力矩阵前后端一致）

为什么必须有这份守卫：能力矩阵是**门控判据**，一旦出现第二份声明（路由里写一个
`if doc_type == 'disclosure_notes'`、DTO 里写另一份白名单），改一处另一处不红 ——
表现为「后端 400 拒绝但前端仍显示回填按钮」或反之「按钮藏了但端点放行」。

本文件锁死三件事：
1. 纯函数取值域（含 None / 空串 / 未知类型三态）
2. ``financial_report*`` 永不可回填（审计底线：报表数字只能由试算表 + 调整分录派生）
3. 端点门控与 DTO 下发**同源** —— 全仓不得出现第二份 doc_type 白名单
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.deliverable_capabilities import (
    SECTION_REFRESH_SUPPORTED_DOC_TYPES,
    WRITEBACK_FORBIDDEN_DOC_TYPES,
    WRITEBACK_SUPPORTED_DOC_TYPES,
    section_refresh_unsupported_message,
    supports_section_refresh,
    supports_writeback,
    writeback_unsupported_message,
)

BACKEND_ROOT = Path(__file__).resolve().parent.parent
CAPABILITIES_PY = BACKEND_ROOT / "app" / "services" / "deliverable_capabilities.py"
LINEAGE_ROUTER_PY = BACKEND_ROOT / "app" / "routers" / "deliverable_lineage.py"
DELIVERABLE_SERVICE_PY = BACKEND_ROOT / "app" / "services" / "deliverable_service.py"


def _strip_comments_and_docstrings(src: str) -> str:
    """去掉 # 注释与三引号块，避免把说明文字里的反例数成真实代码。

    反向自检见 ``test_strip_helper_actually_removes_prose``。
    """
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    return re.sub(r"(?m)#.*$", "", src)


# ─── Property 11（后端侧）：纯函数取值域 ─────────────────────────────────────


@pytest.mark.parametrize(
    ("doc_type", "wb", "refresh"),
    [
        ("disclosure_notes", True, True),
        ("financial_report", False, False),
        ("financial_report_unadjusted", False, False),
        # Wave 3 Task 18 起报告正文支持**回填**（写 report_body_json.sections）；
        # 但**不支持章节级增量刷新** —— 刷新需要按上游重算章节内容再就地替换，
        # 而报告正文的内容来自 Word 模板占位符填充，重算等于重新生成整份。
        ("audit_report", True, False),
        ("unknown_type", False, False),
        ("", False, False),
        (None, False, False),
    ],
)
def test_property_11_capability_matrix_values(doc_type, wb, refresh):
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 11
    assert supports_writeback(doc_type) is wb, f"{doc_type} 的回填能力判定不符"
    assert supports_section_refresh(doc_type) is refresh, f"{doc_type} 的刷新能力判定不符"


def test_none_and_empty_are_not_supported():
    """``None``/空串必须判**不支持** —— 「读不到 doc_type」不等于「支持」。

    历史踩坑：门控首版把「读不到」当不支持导致误拦；修成 fail-open 后又要保证
    这里的纯函数本身对 None 返回 False（fail-open 由调用方决定，不是纯函数的事）。
    """
    for bad in (None, ""):
        assert supports_writeback(bad) is False
        assert supports_section_refresh(bad) is False


# ─── 审计底线：报表永不可回填 ────────────────────────────────────────────────


def test_financial_report_never_writeback_capable():
    """**审计底线**：报表数字唯一合法来源是试算表 + 调整分录。

    允许 xlsx 回写 = 绕过 AJE/RJE，属违反审计逻辑，不是可配置项。
    """
    assert WRITEBACK_FORBIDDEN_DOC_TYPES, "禁止集合不得为空（否则本守卫空转）"
    overlap = WRITEBACK_FORBIDDEN_DOC_TYPES & (
        WRITEBACK_SUPPORTED_DOC_TYPES | SECTION_REFRESH_SUPPORTED_DOC_TYPES
    )
    assert not overlap, (
        f"以下 doc_type 同时出现在禁止集合与支持集合中：{sorted(overlap)}。"
        "报表数字必须走调整分录，不得从交付件回写。"
    )
    for dt in WRITEBACK_FORBIDDEN_DOC_TYPES:
        assert dt.startswith("financial_report"), (
            f"禁止集合出现非报表类型 {dt} —— 请确认是否真该永久禁止，"
            "而不是「暂未支持」（后者不该进这个集合）"
        )


def test_unsupported_messages_point_to_alternative_path():
    """不支持时必须说明**正确做法**，不能只说不支持（需求 6.3）。"""
    for dt in WRITEBACK_FORBIDDEN_DOC_TYPES:
        msg = writeback_unsupported_message(dt)
        assert "调整分录" in msg, f"{dt} 的回填拒绝文案未指向调整分录: {msg}"
        assert section_refresh_unsupported_message(dt), "刷新拒绝文案不得为空"

    # audit_report 自 Wave 3 Task 18 起**支持**回填 → 不再需要「尚未上线」文案；
    # 但仍不支持章节级刷新，故刷新侧必须有可读拒绝文案。
    assert supports_writeback("audit_report") is True
    assert section_refresh_unsupported_message("audit_report")

    # 未知类型也要有可读文案（不得抛异常 / 不得返回空串）
    for dt in (None, "", "weird"):
        assert writeback_unsupported_message(dt)
        assert section_refresh_unsupported_message(dt)


# ─── 单一真源：不得有第二份白名单 ────────────────────────────────────────────


def test_no_second_doc_type_whitelist_in_router_or_service():
    """路由与 DTO 填充必须**调用**能力函数，不得内联 doc_type 判定。

    判据：这两个文件里不允许出现 ``doc_type == "disclosure_notes"`` 这类字面比较
    （只允许 `supports_writeback(...)` / `supports_section_refresh(...)`）。
    """
    pattern = re.compile(
        r"doc_type\s*(?:==|!=|\bin\b)\s*[\(\[{]?\s*['\"]disclosure_notes['\"]"
    )
    for path in (LINEAGE_ROUTER_PY, DELIVERABLE_SERVICE_PY):
        code = _strip_comments_and_docstrings(path.read_text(encoding="utf-8"))
        hits = pattern.findall(code)
        assert not hits, (
            f"{path.name} 内联了 doc_type 白名单 {hits} —— 能力矩阵必须只在 "
            "deliverable_capabilities.py 声明一次，否则改一处另一处不红"
        )


def test_router_and_dto_both_consume_capability_functions():
    """正向断言：门控与 DTO 两侧都真的引用了能力函数（防守卫空转）。"""
    router = _strip_comments_and_docstrings(
        LINEAGE_ROUTER_PY.read_text(encoding="utf-8")
    )
    assert "supports_writeback(" in router, "回填端点未做能力门控"
    assert "supports_section_refresh(" in router, "刷新端点未做能力门控"

    service = _strip_comments_and_docstrings(
        DELIVERABLE_SERVICE_PY.read_text(encoding="utf-8")
    )
    assert "supports_writeback=supports_writeback(" in service, (
        "DeliverableDTO 未由能力函数派生 supports_writeback"
    )
    assert "supports_section_refresh=supports_section_refresh(" in service, (
        "DeliverableDTO 未由能力函数派生 supports_section_refresh"
    )


def test_dto_schema_exposes_capability_flags():
    """前端门控依赖 DTO 下发，schema 缺字段则前端恒 false（入口全隐藏）。"""
    from app.models.phase13_schemas import DeliverableDTOSchema

    fields = DeliverableDTOSchema.model_fields
    for name in ("supports_writeback", "supports_section_refresh"):
        assert name in fields, f"DeliverableDTOSchema 缺少 {name}"
        assert fields[name].default is False, (
            f"{name} 默认值必须为 False —— 旧后端/异常路径下应隐藏入口而非误显示"
        )


# ─── 反向自检 ────────────────────────────────────────────────────────────────


def test_strip_helper_actually_removes_prose():
    """反向自检：剥注释确有作用，否则上面的「无第二份白名单」断言是空转。

    ``deliverable_capabilities.py`` 的模块 docstring 里就写着 ``disclosure_notes``
    字样，剥离失效时这段说明会被数成真实代码。
    """
    raw = CAPABILITIES_PY.read_text(encoding="utf-8")
    assert "禁止" in raw, "前置条件变了：该文件已无中文说明，请更新本自检"
    stripped = _strip_comments_and_docstrings(raw)
    assert "禁止" not in stripped, "剥注释/docstring 失效 —— 上面的源码级断言全部空转"
    # 剥离后真实代码仍在
    assert "WRITEBACK_SUPPORTED_DOC_TYPES" in stripped


def test_reverse_selfcheck_inline_whitelist_would_be_caught():
    """反向自检：若把内联白名单写进被扫文件，检测正则必须命中。"""
    pattern = re.compile(
        r"doc_type\s*(?:==|!=|\bin\b)\s*[\(\[{]?\s*['\"]disclosure_notes['\"]"
    )
    for bad in (
        'if doc_type == "disclosure_notes":',
        "if doc_type != 'disclosure_notes':",
        'if doc_type in {"disclosure_notes"}:',
        "if doc_type in ['disclosure_notes']:",
    ):
        assert pattern.search(bad), f"检测正则漏掉了内联白名单形态: {bad}"
