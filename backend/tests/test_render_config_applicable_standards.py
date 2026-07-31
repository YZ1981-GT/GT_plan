"""render-config 适用准则统一注入守卫（R1.1/R1.2/R1.5/R4.3）。

直测纯函数 `inject_applicable_standards`（不起全栈），并锁死三件事：

1. 每个含 dict 型 `html_data` 的 sheet 都被注入，值等于顶层派生列表
2. 🔴 **覆盖式**注入：策略层残留的**原始 v2 对象**必须被规范字符串列表替换
   （I1~I6 的 `_load_project_context` 就是把 `applicable_standard_v2` 原样下发，
   前端 `normalizeApplicableStandards` 拿到对象直接返回 `[]` → 门控恒空）
3. 非 dict 型 `html_data`（onlyoffice 占位 / None）不报错、不被计入
"""
from __future__ import annotations

import inspect

from app.routers.wp_render_config_helpers import inject_applicable_standards
from app.services.standard_unification_service import derive_applicable_standards

STANDARDS = derive_applicable_standards({"entity_type": "soe", "scope": "standalone"})


def test_injects_into_every_dict_html_data() -> None:
    sheets = [
        {"sheet_name": "底稿目录", "html_data": {}},
        {"sheet_name": "审定表D3-1", "html_data": {"project_context": {"client_name": "甲公司"}}},
        {"sheet_name": "附注披露信息（国企）", "html_data": {"rows": []}},
    ]
    n = inject_applicable_standards(sheets, STANDARDS)
    assert n == 3
    for s in sheets:
        ctx = s["html_data"]["project_context"]
        assert ctx["applicable_standards"] == STANDARDS
    # 加法式：原有字段不被破坏
    assert sheets[1]["html_data"]["project_context"]["client_name"] == "甲公司"
    assert sheets[2]["html_data"]["rows"] == []


def test_overwrites_raw_v2_object() -> None:
    """🔴 I1~I6 残留的原始 v2 对象必须被替换成字符串列表。"""
    sheets = [
        {
            "sheet_name": "I5",
            "html_data": {
                "project_context": {
                    "applicable_standards": {
                        "entity_type": "soe", "scope": "standalone", "stage": "normal",
                    }
                }
            },
        }
    ]
    inject_applicable_standards(sheets, STANDARDS)
    got = sheets[0]["html_data"]["project_context"]["applicable_standards"]
    assert isinstance(got, list), "残留 dict 会让前端归一返回 [] → 门控恒空"
    assert got == STANDARDS


def test_skips_non_dict_html_data() -> None:
    sheets = [
        {"sheet_name": "a", "html_data": None},
        {"sheet_name": "b"},
        {"sheet_name": "c", "html_data": "not-a-dict"},
        {"sheet_name": "d", "html_data": {"project_context": "not-a-dict"}},
        "not-a-sheet",
    ]
    assert inject_applicable_standards(sheets, STANDARDS) == 0  # type: ignore[arg-type]


def test_empty_standards_is_noop() -> None:
    sheets = [{"sheet_name": "a", "html_data": {}}]
    assert inject_applicable_standards(sheets, []) == 0
    assert "project_context" not in sheets[0]["html_data"]


def test_each_sheet_gets_its_own_list_copy() -> None:
    """逐 sheet 独立列表：某个策略后续 append 不得污染其它 sheet。"""
    sheets = [{"sheet_name": "a", "html_data": {}}, {"sheet_name": "b", "html_data": {}}]
    inject_applicable_standards(sheets, STANDARDS)
    sheets[0]["html_data"]["project_context"]["applicable_standards"].append("x")
    assert sheets[1]["html_data"]["project_context"]["applicable_standards"] == STANDARDS


def test_render_config_wires_injection_and_top_level_field() -> None:
    """render-config 主流程必须调用注入并在顶层下发（防接线被回退）。"""
    from app.routers import wp_render_config as mod

    src = inspect.getsource(mod)
    assert "inject_applicable_standards" in src, "render-config 未调用统一注入"
    assert '"applicable_standards": _standards' in src, "响应顶层缺 applicable_standards"
    assert "derive_applicable_standards" in src, "未走共享派生函数（防第二套口径）"
