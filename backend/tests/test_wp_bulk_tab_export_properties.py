"""Property-based tests for wp_bulk_tab_export — Bulk Export Tab Naming (P12).

Property 12: Bulk Export Tab Names Match sheet_code
    对于随机生成的 manifest entries（含/不含 wp_id），验证 `list_export_sheets`
    产出的导出列表满足：
      (1) wp_id=None 的 entry 被剔除（不进入导出列表 / ZIP）；
      (2) 每个存活 entry 的 ZIP tab 名称 == 其 sheet_code（Req 6.4）。

Monkeypatch 方式：
    `list_export_sheets` 内部通过 `from app.services.acnr.manifest import
    list_import_export` 惰性导入 manifest 层函数。因此用
    `unittest.mock.patch("app.services.acnr.manifest.list_import_export", ...)`
    以 AsyncMock 替换真实实现，返回 Hypothesis 生成的 entries，再经
    `asyncio.run(list_export_sheets(...))` 驱动被测异步函数（同步 Hypothesis
    用例内驱动 async 目标）。

Validates: Requirements 6.4
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_bulk_tab_export import list_export_sheets

# sheet_code 字面量（大写字母 + 数字 + 可选 -N 后缀），保证形似真实 catalog 编码
_SHEET_CODE = st.from_regex(r"[A-N][0-9]{1,2}(-[0-9]{1,2})?", fullmatch=True)


@st.composite
def _manifest_entries(draw: st.DrawFn) -> list[dict]:
    """生成一组 sheet_code 唯一的 manifest entries（wp_id 可为 None）。

    每条 entry 结构对齐 manifest.list_import_export 输出：
    sheet_code / wp_id / depends_on_sheets / import_order / api_prefix / item_id。
    """
    codes = draw(
        st.lists(_SHEET_CODE, min_size=0, max_size=8, unique=True)
    )
    entries: list[dict] = []
    for code in codes:
        # wp_id：约一半概率为 None（未解析实例），否则随机字符串
        wp_id = draw(st.one_of(st.none(), st.uuids().map(str)))
        # depends_on_sheets：从其它 code 中抽取任意子集（可能含不存在的 code）
        deps = draw(
            st.lists(
                st.one_of(st.sampled_from(codes) if codes else st.just(code), _SHEET_CODE),
                min_size=0,
                max_size=3,
                unique=True,
            )
        )
        entries.append(
            {
                "sheet_code": code,
                "api_prefix": draw(st.text(alphabet="abcdefghijkl", min_size=1, max_size=4)),
                "item_id": draw(st.text(alphabet="abcdefghijkl", min_size=1, max_size=6)),
                "storage_field": "remark",
                "import_order": draw(st.integers(min_value=0, max_value=50)),
                "depends_on_sheets": deps,
                "wp_id": wp_id,
                "jump_route": None,
                "parent_wp_code": code.split("-")[0],
                "addr_id": "",
            }
        )
    return entries


@given(entries=_manifest_entries())
@settings(max_examples=150)
def test_property_12_bulk_export_tab_names_match_sheet_code(entries: list[dict]) -> None:
    """Property 12: 存活 entry 的 tab 名 == sheet_code；wp_id=None 被排除。

    Validates: Requirements 6.4
    """
    with patch(
        "app.services.acnr.manifest.list_import_export",
        new=AsyncMock(return_value=[dict(e) for e in entries]),
    ):
        result = asyncio.run(list_export_sheets(db=None, project_id="p1", cycle="D"))

    # (1) 没有 wp_id=None 的 entry 出现在导出列表中
    assert all(e.get("wp_id") is not None for e in result), (
        "wp_id=None 的未解析实例不应出现在导出列表中"
    )

    # (2) 每个存活 entry 的 ZIP tab 名称 == sheet_code（且非空）
    for e in result:
        tab_name = e["sheet_code"]  # ZIP tab 名称即 entry 的 sheet_code
        assert tab_name is not None and tab_name != "", "tab 名称必须存在且非空"
        assert tab_name == e["sheet_code"], "tab 名称必须等于 sheet_code"

    # 存活集合恰好等于输入中 wp_id != None 的 sheet_code 集合（无遗漏 / 无凭空产生）
    surviving_codes = {e["sheet_code"] for e in result}
    expected_codes = {e["sheet_code"] for e in entries if e.get("wp_id") is not None}
    assert surviving_codes == expected_codes
