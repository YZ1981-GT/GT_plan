"""核对表 xlsx 解析器单元测试（PRE-4-1，A17-5-1 首版）.

验证两节结构区分、item_id 模式、conclusion 列识别、mtime 缓存命中，
以及对 A17-5-1 真实模板文件的解析（50 条核对程序 + 6 条审计目标）。
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.checklist_xlsx_parser import (
    _CHECKLIST_XLSX_CACHE,
    _get_audit_entry,
    get_checklist_template,
    get_template_path,
    invalidate_cache,
    parse_checklist_xlsx,
)

_WP = "A17-5-1"


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def a1751_result():
    """解析 A17-5-1 真实模板文件的结果."""
    invalidate_cache()
    path = get_template_path(_WP)
    assert path is not None, "A17-5-1 模板文件未找到"
    return parse_checklist_xlsx(path, _WP)


def _section(result, sid):
    return next(s for s in result["sections"] if s["id"] == sid)


# ─── 输出结构 ─────────────────────────────────────────────────────────────────


class TestOutputStructure:
    """输出结构兼容 GtChecklistTable.vue."""

    def test_top_level_fields(self, a1751_result):
        for key in ("wp_code", "title", "sections", "toc", "stats", "parsed_at"):
            assert key in a1751_result
        assert a1751_result["wp_code"] == _WP

    def test_stats_fields(self, a1751_result):
        stats = a1751_result["stats"]
        assert "total_actionable" in stats
        assert "total_guidance" in stats
        assert "total_sections" in stats

    def test_toc_matches_sections(self, a1751_result):
        toc_ids = {t["id"] for t in a1751_result["toc"]}
        sec_ids = {s["id"] for s in a1751_result["sections"]}
        assert toc_ids == sec_ids

    def test_section_structure(self, a1751_result):
        for sec in a1751_result["sections"]:
            assert sec["id"].startswith("S")
            assert "title" in sec
            assert "items" in sec

    def test_title_extracted(self, a1751_result):
        assert "核对表" in a1751_result["title"]


# ─── 两节区分 ─────────────────────────────────────────────────────────────────


class TestTwoSections:
    """审计目标节（无 conclusion）与核对程序节（有 conclusion）区分."""

    def test_exactly_two_sections(self, a1751_result):
        assert a1751_result["stats"]["total_sections"] == 2

    def test_objective_section_title(self, a1751_result):
        assert "审计目标" in _section(a1751_result, "S01")["title"]

    def test_procedure_section_title(self, a1751_result):
        assert "核对程序" in _section(a1751_result, "S02")["title"]

    def test_objective_items_are_headers(self, a1751_result):
        """审计目标节条目应为只读 header（无 conclusion 填写列）."""
        obj = _section(a1751_result, "S01")
        assert len(obj["items"]) == 6
        for item in obj["items"]:
            assert item["type"] == "header"

    def test_procedure_items_are_actionable(self, a1751_result):
        """核对程序节条目应为 actionable（可填 conclusion）."""
        proc = _section(a1751_result, "S02")
        assert len(proc["items"]) == 50
        for item in proc["items"]:
            assert item["type"] == "actionable"

    def test_objective_count(self, a1751_result):
        """审计目标 6 条."""
        assert len(_section(a1751_result, "S01")["items"]) == 6

    def test_procedure_count(self, a1751_result):
        """核对程序 50 条."""
        assert len(_section(a1751_result, "S02")["items"]) == 50

    def test_total_actionable_is_procedure_only(self, a1751_result):
        """只有核对程序节计入 actionable 统计（审计目标不计）."""
        assert a1751_result["stats"]["total_actionable"] == 50


# ─── item_id 模式 ─────────────────────────────────────────────────────────────


class TestItemIdPattern:
    """item_id 模式 A17-5-1-{seq:03d}（对齐 persistence.md）."""

    def test_first_item_id(self, a1751_result):
        proc = _section(a1751_result, "S02")
        assert proc["items"][0]["id"] == "A17-5-1-001"

    def test_last_item_id(self, a1751_result):
        proc = _section(a1751_result, "S02")
        assert proc["items"][-1]["id"] == "A17-5-1-050"

    def test_all_item_ids_match_pattern(self, a1751_result):
        import re

        pat = re.compile(r"^A17-5-1-\d{3}$")
        for item in _section(a1751_result, "S02")["items"]:
            assert pat.match(item["id"]), f"非法 item_id: {item['id']}"

    def test_item_ids_sequential(self, a1751_result):
        proc = _section(a1751_result, "S02")
        ids = [item["id"] for item in proc["items"]]
        expected = [f"A17-5-1-{i:03d}" for i in range(1, 51)]
        assert ids == expected

    def test_all_ids_unique(self, a1751_result):
        all_ids = set()
        for sec in a1751_result["sections"]:
            assert sec["id"] not in all_ids
            all_ids.add(sec["id"])
            for item in sec["items"]:
                assert item["id"] not in all_ids, f"重复 ID: {item['id']}"
                all_ids.add(item["id"])


# ─── conclusion 列识别 / 预置参考索引 ─────────────────────────────────────────


class TestConclusionColumn:
    """核对程序节带 conclusion 填写能力 + 预置底稿索引号参考（G 列）."""

    def test_procedure_item_has_content(self, a1751_result):
        proc = _section(a1751_result, "S02")
        first = proc["items"][0]
        assert first["content"]  # 非空
        assert "承接" in first["content"] or "保持" in first["content"]

    def test_preset_wp_ref_populated(self, a1751_result):
        """首条核对程序应带预置底稿索引参考 B1（来自 G 列）."""
        proc = _section(a1751_result, "S02")
        assert proc["items"][0]["preset_wp_ref"] == "B1"

    def test_preset_wp_ref_field_present_on_all(self, a1751_result):
        """所有核对程序条目都应有 preset_wp_ref 字段（可空）."""
        for item in _section(a1751_result, "S02")["items"]:
            assert "preset_wp_ref" in item

    def test_objective_items_no_conclusion_role(self, a1751_result):
        """审计目标 header 条目不参与 conclusion 填写（type=header）."""
        for item in _section(a1751_result, "S01")["items"]:
            assert item["type"] != "actionable"


# ─── 缓存 ─────────────────────────────────────────────────────────────────────


class TestCaching:
    """mtime 缓存机制."""

    def setup_method(self):
        invalidate_cache()

    def test_get_template_path(self):
        path = get_template_path(_WP)
        assert path is not None
        assert path.exists()
        assert path.suffix.lower() == ".xlsx"

    def test_get_template_path_nonexistent(self):
        assert get_template_path("A99-99") is None

    def test_cache_populated(self):
        result = asyncio.run(get_checklist_template(_WP))
        assert _WP in _CHECKLIST_XLSX_CACHE
        assert result["wp_code"] == _WP

    def test_cache_returns_same_object(self):
        r1 = asyncio.run(get_checklist_template(_WP))
        r2 = asyncio.run(get_checklist_template(_WP))
        assert r1 is r2  # 命中缓存 → 同一引用

    def test_invalidate_single(self):
        asyncio.run(get_checklist_template(_WP))
        assert _WP in _CHECKLIST_XLSX_CACHE
        invalidate_cache(_WP)
        assert _WP not in _CHECKLIST_XLSX_CACHE

    def test_invalidate_all(self):
        asyncio.run(get_checklist_template(_WP))
        invalidate_cache()
        assert len(_CHECKLIST_XLSX_CACHE) == 0

    def test_get_template_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            asyncio.run(get_checklist_template("A99-99"))


# ─── 边界 / 错误处理 ──────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_audit_entry_found(self):
        entry = _get_audit_entry(_WP)
        assert entry is not None
        assert entry["wp_code"] == _WP

    def test_unconfigured_wp_code_raises(self):
        """audit JSON 未登记的 wp_code 应抛 ValueError."""
        path = get_template_path(_WP)
        with pytest.raises(ValueError, match="未找到"):
            parse_checklist_xlsx(path, "A99-99")

    def test_stats_consistent_with_data(self, a1751_result):
        actual_actionable = 0
        actual_guidance = 0
        for sec in a1751_result["sections"]:
            for item in sec["items"]:
                if item["type"] == "actionable":
                    actual_actionable += 1
                    actual_guidance += len(item.get("children", []))
        assert actual_actionable == a1751_result["stats"]["total_actionable"]
        assert actual_guidance == a1751_result["stats"]["total_guidance"]
        assert len(a1751_result["sections"]) == a1751_result["stats"]["total_sections"]


# ═══════════════════════════════════════════════════════════════════════════
# PRE-4-2：A17-5-2~5-5 扩展（内控 / IPO / 新三板 / 函证）
# ═══════════════════════════════════════════════════════════════════════════

import re

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# 各核对表预期：核对程序条数、审计目标条数、参考列角色、披露章节列。
# 数据来源：a17_xlsx_audit.json（PRE-4-0 产出，已验证 ready）。
_EXPECTED = {
    "A17-5-2": {
        "procedure_count": 35,
        "objective_count": 6,
        "conclusion_col": "E",
        "index_reference_col": "H",
        "has_disclosure": False,
    },
    "A17-5-3": {
        "procedure_count": 24,
        "objective_count": 3,
        "conclusion_col": "E",
        "index_reference_col": None,
        "has_disclosure": False,
    },
    "A17-5-4": {
        "procedure_count": 61,
        "objective_count": 3,
        "conclusion_col": "E",
        "index_reference_col": None,
        "has_disclosure": True,
    },
    "A17-5-5": {
        "procedure_count": 60,
        "objective_count": 2,
        "conclusion_col": "E",
        "index_reference_col": None,
        "has_disclosure": False,
    },
}

_WP_CODES = list(_EXPECTED.keys())


def _parse(wp_code):
    invalidate_cache()
    path = get_template_path(wp_code)
    assert path is not None, f"{wp_code} 模板文件未找到"
    return parse_checklist_xlsx(path, wp_code)


def _proc_section(result):
    """取核对程序节（最后一节；审计目标节在前）."""
    return _section(result, "S02")


@pytest.fixture(scope="module")
def parsed_all():
    """一次性解析 4 个新核对表，供多个测试复用."""
    return {wp: _parse(wp) for wp in _WP_CODES}


# ─── 解析条数 ─────────────────────────────────────────────────────────────────


class TestExtendedCounts:
    """每个新核对表的核对程序条数 / 审计目标条数符合 audit JSON 登记."""

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_procedure_count(self, parsed_all, wp_code):
        proc = _proc_section(parsed_all[wp_code])
        assert len(proc["items"]) == _EXPECTED[wp_code]["procedure_count"]

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_objective_count(self, parsed_all, wp_code):
        obj = _section(parsed_all[wp_code], "S01")
        assert len(obj["items"]) == _EXPECTED[wp_code]["objective_count"]

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_total_actionable_is_procedure_only(self, parsed_all, wp_code):
        result = parsed_all[wp_code]
        assert (
            result["stats"]["total_actionable"]
            == _EXPECTED[wp_code]["procedure_count"]
        )

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_exactly_two_sections(self, parsed_all, wp_code):
        assert parsed_all[wp_code]["stats"]["total_sections"] == 2


# ─── 两节区分 ─────────────────────────────────────────────────────────────────


class TestExtendedTwoSections:
    """审计目标（header）与核对程序（actionable）区分."""

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_objective_items_are_headers(self, parsed_all, wp_code):
        obj = _section(parsed_all[wp_code], "S01")
        assert len(obj["items"]) > 0
        for item in obj["items"]:
            assert item["type"] == "header"

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_procedure_items_are_actionable(self, parsed_all, wp_code):
        proc = _proc_section(parsed_all[wp_code])
        for item in proc["items"]:
            assert item["type"] == "actionable"

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_objective_title(self, parsed_all, wp_code):
        assert "审计目标" in _section(parsed_all[wp_code], "S01")["title"]

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_procedure_title(self, parsed_all, wp_code):
        assert "核对程序" in _proc_section(parsed_all[wp_code])["title"]


# ─── item_id 模式 ─────────────────────────────────────────────────────────────


class TestExtendedItemIdPattern:
    """item_id 模式 A17-5-{x}-{seq:03d}，连续且唯一."""

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_item_ids_sequential(self, parsed_all, wp_code):
        proc = _proc_section(parsed_all[wp_code])
        ids = [item["id"] for item in proc["items"]]
        count = _EXPECTED[wp_code]["procedure_count"]
        expected = [f"{wp_code}-{i:03d}" for i in range(1, count + 1)]
        assert ids == expected

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_all_item_ids_match_pattern(self, parsed_all, wp_code):
        pat = re.compile(rf"^{re.escape(wp_code)}-\d{{3}}$")
        for item in _proc_section(parsed_all[wp_code])["items"]:
            assert pat.match(item["id"]), f"非法 item_id: {item['id']}"

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_all_ids_unique(self, parsed_all, wp_code):
        all_ids = set()
        for sec in parsed_all[wp_code]["sections"]:
            for item in sec["items"]:
                assert item["id"] not in all_ids, f"重复 ID: {item['id']}"
                all_ids.add(item["id"])


# ─── 列角色动态解析 ───────────────────────────────────────────────────────────


class TestColumnRoleParsing:
    """列角色从 audit JSON column_roles 动态读取（结论列 E、参考列差异、披露章节）."""

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_conclusion_col_is_E(self, wp_code):
        """A17-5-2~5-5 结论列均在 E（区别于 A17-5-1 的 D）."""
        entry = _get_audit_entry(wp_code)
        roles = entry["sheets"][0]["procedure_section"]["column_roles"]
        assert roles["conclusion"] == _EXPECTED[wp_code]["conclusion_col"]

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_index_reference_col_matches(self, wp_code):
        """参考列角色：A17-5-2=H，A17-5-3/4/5 无 index_reference 列."""
        entry = _get_audit_entry(wp_code)
        roles = entry["sheets"][0]["procedure_section"]["column_roles"]
        assert roles.get("index_reference") == _EXPECTED[wp_code][
            "index_reference_col"
        ]

    def test_a1752_preset_wp_ref_from_H(self, parsed_all):
        """A17-5-2 首条预置参考索引 B1 来自 H 列（动态列角色，非硬编码 G）."""
        proc = _proc_section(parsed_all["A17-5-2"])
        assert proc["items"][0]["preset_wp_ref"] == "B1"

    @pytest.mark.parametrize("wp_code", _WP_CODES)
    def test_preset_wp_ref_field_present(self, parsed_all, wp_code):
        for item in _proc_section(parsed_all[wp_code])["items"]:
            assert "preset_wp_ref" in item

    def test_a1753_no_index_reference_no_spurious_ref(self, parsed_all):
        """A17-5-3 无 index_reference 列，预置参考应全空（不误读其他列）."""
        proc = _proc_section(parsed_all["A17-5-3"])
        for item in proc["items"]:
            assert item["preset_wp_ref"] == ""

    def test_a1754_has_disclosure_chapter_field(self, parsed_all):
        """A17-5-4 特有披露章节列 → 每条带 preset_disclosure_chapter 字段."""
        proc = _proc_section(parsed_all["A17-5-4"])
        for item in proc["items"]:
            assert "preset_disclosure_chapter" in item

    @pytest.mark.parametrize(
        "wp_code", ["A17-5-2", "A17-5-3", "A17-5-5"]
    )
    def test_no_disclosure_chapter_field_when_absent(self, parsed_all, wp_code):
        """非新三板核对表无 disclosure_chapter 列 → 不应附加该字段."""
        proc = _proc_section(parsed_all[wp_code])
        for item in proc["items"]:
            assert "preset_disclosure_chapter" not in item


# ─── A17-5-5 审计目标 seq=null 容错 ──────────────────────────────────────────


class TestNullObjectiveSeq:
    """A17-5-5 审计目标节 seq 为 null，不应崩溃且 standard_ref 为空串."""

    def test_objective_parsed_with_null_seq(self, parsed_all):
        obj = _section(parsed_all["A17-5-5"], "S01")
        assert len(obj["items"]) == 2
        for item in obj["items"]:
            assert item["type"] == "header"
            assert item["standard_ref"] == ""  # seq=null → 空串
            assert item["content"]  # 内容非空


# ─── 不回归 A17-5-1 ──────────────────────────────────────────────────────────


class TestNoRegressionA1751:
    """确认 A17-5-1（结论列 D、参考列 G）解析未被扩展破坏."""

    def test_a1751_still_50_procedures(self):
        result = _parse("A17-5-1")
        assert len(_section(result, "S02")["items"]) == 50

    def test_a1751_preset_ref_from_G(self):
        result = _parse("A17-5-1")
        assert _section(result, "S02")["items"][0]["preset_wp_ref"] == "B1"

    def test_a1751_no_disclosure_field(self):
        result = _parse("A17-5-1")
        for item in _section(result, "S02")["items"]:
            assert "preset_disclosure_chapter" not in item


# ─── 属性测试（PBT，max_examples=5） ─────────────────────────────────────────


class TestChecklistProperties:
    """跨所有 A17-5-x 核对表的通用属性.

    Validates: 解析器对全部核对表保持 item_id 唯一性 + 两节结构不变量。
    """

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(wp_code=st.sampled_from(_WP_CODES))
    def test_all_actionable_ids_unique_and_well_formed(self, parsed_all, wp_code):
        """属性：任一核对表，所有 actionable item_id 唯一且匹配 wp_code 前缀模式."""
        result = parsed_all[wp_code]
        pat = re.compile(rf"^{re.escape(wp_code)}-\d{{3}}$")
        seen = set()
        for sec in result["sections"]:
            for item in sec["items"]:
                if item["type"] == "actionable":
                    assert pat.match(item["id"])
                    assert item["id"] not in seen
                    seen.add(item["id"])
        assert len(seen) == _EXPECTED[wp_code]["procedure_count"]

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(wp_code=st.sampled_from(_WP_CODES))
    def test_two_section_invariant(self, parsed_all, wp_code):
        """属性：任一核对表恒为两节（审计目标 header + 核对程序 actionable）."""
        result = parsed_all[wp_code]
        assert result["stats"]["total_sections"] == 2
        obj = _section(result, "S01")
        proc = _section(result, "S02")
        assert all(i["type"] == "header" for i in obj["items"])
        assert all(i["type"] == "actionable" for i in proc["items"])


# ═══════════════════════════════════════════════════════════════════════════
# PRE-4-3：A15-1（分章节问卷）、A14-1（动态行 grid）+ 多 audit 源加载
# ═══════════════════════════════════════════════════════════════════════════

from app.services.checklist_xlsx_parser import (
    _AUDIT_JSON_PATHS,
    _load_audit_config,
)


# ─── 多 audit 源加载 ─────────────────────────────────────────────────────────


class TestMultiAuditSources:
    """列映射权威源现为两份 JSON（a17 + a7_a15），按 wp_code 命中决定源."""

    def test_both_audit_sources_registered(self):
        names = {p.name for p in _AUDIT_JSON_PATHS}
        assert "a17_xlsx_audit.json" in names
        assert "a7_a15_xlsx_audit.json" in names

    def test_a17_entries_loaded(self):
        """A17-5-x 条目来自 a17 源，合并后仍可命中（不回归）."""
        index = _load_audit_config()
        for wp in ("A17-5-1", "A17-5-2", "A17-5-5"):
            assert wp in index, f"{wp} 应从 a17 源加载"

    def test_a7_a15_entries_loaded(self):
        """A15-1、A14-1 条目来自 a7_a15 源，合并后可命中."""
        index = _load_audit_config()
        assert "A15-1" in index
        assert "A14-1" in index

    def test_a17_takes_precedence_on_conflict(self):
        """同 wp_code 冲突时 a17 源优先（A17-5-1 必为两节结构）."""
        entry = _get_audit_entry("A17-5-1")
        sheet = next(
            s for s in entry["sheets"] if s.get("component_type") == "checklist-table"
        )
        # a17 源的 A17-5-1 有 objective_section/procedure_section（两节结构标志）
        assert "procedure_section" in sheet


# ─── A15-1 分章节问卷 ─────────────────────────────────────────────────────────


@pytest.fixture
def a151_result():
    invalidate_cache()
    path = get_template_path("A15-1")
    assert path is not None, "A15-1 模板文件未找到"
    return parse_checklist_xlsx(path, "A15-1")


class TestA151SectionedChecklist:
    """A15-1 持续经营调查表：财务11 / 经营6 / 其他4 + 调查结论."""

    def test_mode_is_sectioned(self, a151_result):
        assert a151_result["mode"] == "sectioned-checklist"

    def test_four_sections(self, a151_result):
        """三章节问卷 + 一个调查结论节 = 4 节."""
        assert a151_result["stats"]["total_sections"] == 4

    def test_section_titles(self, a151_result):
        titles = [s["title"] for s in a151_result["sections"]]
        assert any("财务" in t for t in titles)
        assert any("经营" in t for t in titles)
        assert any("其他" in t for t in titles)
        assert any("结论" in t for t in titles)

    def test_fin_count_11(self, a151_result):
        fin = next(s for s in a151_result["sections"] if "财务" in s["title"])
        assert len(fin["items"]) == 11

    def test_ops_count_6(self, a151_result):
        ops = next(s for s in a151_result["sections"] if "经营" in s["title"])
        assert len(ops["items"]) == 6

    def test_oth_count_4(self, a151_result):
        oth = next(s for s in a151_result["sections"] if "其他" in s["title"])
        assert len(oth["items"]) == 4

    def test_item_id_prefixes(self, a151_result):
        """item_id 对齐 persistence.md：fin/ops/oth + conclusion."""
        ids = [it["id"] for s in a151_result["sections"] for it in s["items"]]
        assert "A15-1-fin-01" in ids
        assert "A15-1-fin-11" in ids
        assert "A15-1-ops-01" in ids
        assert "A15-1-ops-06" in ids
        assert "A15-1-oth-01" in ids
        assert "A15-1-oth-04" in ids
        assert "A15-1-conclusion" in ids

    def test_total_actionable(self, a151_result):
        """11 + 6 + 4 + 1(结论) = 22 actionable."""
        assert a151_result["stats"]["total_actionable"] == 22

    def test_all_ids_unique(self, a151_result):
        ids = [it["id"] for s in a151_result["sections"] for it in s["items"]]
        assert len(ids) == len(set(ids))

    def test_items_have_content(self, a151_result):
        for s in a151_result["sections"]:
            for it in s["items"]:
                assert it["content"], f"空内容: {it['id']}"

    def test_no_header_row_leak(self, a151_result):
        """重复表头行（'序号'）不应作为 actionable 条目泄漏进来."""
        for s in a151_result["sections"]:
            for it in s["items"]:
                assert it["content"] != "可能导致对持续经营假设产生重大疑虑的事项或情况"
                assert it["standard_ref"] != "序号"

    def test_conclusion_item(self, a151_result):
        concl = next(
            s for s in a151_result["sections"] if "结论" in s["title"]
        )
        assert len(concl["items"]) == 1
        assert concl["items"][0]["id"] == "A15-1-conclusion"


# ─── A14-1 动态行 grid ────────────────────────────────────────────────────────


@pytest.fixture
def a141_result():
    invalidate_cache()
    path = get_template_path("A14-1")
    assert path is not None, "A14-1 模板文件未找到"
    return parse_checklist_xlsx(path, "A14-1")


class TestA141Grid:
    """A14-1 内部控制缺陷汇总表：双行表头 + 认定 6 列矩阵 → remark JSON."""

    def test_mode_is_grid(self, a141_result):
        assert a141_result["mode"] == "grid"

    def test_grid_block_present(self, a141_result):
        assert "grid" in a141_result
        assert a141_result["grid"]["columns"]

    def test_double_header_rows(self, a141_result):
        """双行表头：R5 主表头 + R6 子表头."""
        grid = a141_result["grid"]
        assert grid["header_row"] == 5
        assert grid["sub_header_row"] == 6

    def test_six_assertion_matrix(self, a141_result):
        """认定 6 列矩阵 G/H/I/J/K/L."""
        assertions = a141_result["grid"]["assertions"]
        assert len(assertions) == 6
        keys = [a["key"] for a in assertions]
        assert keys == [
            "existence",
            "completeness",
            "cutoff",
            "rights_obligations",
            "valuation_allocation",
            "presentation",
        ]
        cols = [a["col"] for a in assertions]
        assert cols == ["G", "H", "I", "J", "K", "L"]

    def test_remark_schema_fields(self, a141_result):
        """remark JSON 固定 schema（persistence.md）."""
        schema = a141_result["grid"]["remark_schema"]
        assert set(schema.keys()) == {
            "defect_no",
            "process",
            "description",
            "assertions",
            "compensating_control",
        }
        assert set(schema["assertions"].keys()) == {
            "existence",
            "completeness",
            "cutoff",
            "rights_obligations",
            "valuation_allocation",
            "presentation",
        }

    def test_row_id_pattern(self, a141_result):
        """item_id 模式 A14-1-row-{nnn}."""
        grid = a141_result["grid"]
        assert grid["row_id_pattern"] == "A14-1-row-{nnn}"
        assert grid["row_id_prefix"] == "A14-1-row-"

    def test_assertion_matrix_anchor_only_on_g(self, a141_result):
        """只有「财务报表认定」(G) 主列标记为认定矩阵，「缺陷认定结论」不应误标."""
        cols = a141_result["grid"]["columns"]
        matrix_cols = [c for c in cols if c.get("is_assertion_matrix")]
        assert len(matrix_cols) == 1
        assert matrix_cols[0]["label"] == "财务报表认定"
        # 「缺陷认定结论」含"认定"但非矩阵列
        concl = next(c for c in cols if c["label"] == "缺陷认定结论")
        assert not concl.get("is_assertion_matrix")

    def test_main_columns_mapped_to_remark_fields(self, a141_result):
        """主列映射到 remark 字段：缺陷编号→defect_no 等."""
        cols = {c["label"]: c for c in a141_result["grid"]["columns"]}
        assert cols["缺陷编号"]["remark_field"] == "defect_no"
        assert cols["相关业务流程、应用系统"]["remark_field"] == "process"
        assert cols["内部控制缺陷描述及影响"]["remark_field"] == "description"
        assert cols["补偿性控制"]["remark_field"] == "compensating_control"

    def test_example_sheet_skipped(self, a141_result):
        """example-skip 示例 sheet 应被跳过且登记."""
        assert "示例-控制缺陷汇总表" in a141_result["grid"]["example_sheets_skipped"]

    def test_grid_no_checklist_sections(self, a141_result):
        """grid 模式无 checklist 章节（actionable=0）."""
        assert a141_result["sections"] == []
        assert a141_result["stats"]["total_actionable"] == 0


# ─── 不回归 A17-5-x ──────────────────────────────────────────────────────────


class TestNoRegressionA175x:
    """确认 A17-5-x 两节结构在多 audit 源 + 新分派逻辑下未回归."""

    def test_a1751_two_section_still_works(self):
        invalidate_cache()
        path = get_template_path("A17-5-1")
        result = parse_checklist_xlsx(path, "A17-5-1")
        assert result.get("mode") != "grid"
        assert result.get("mode") != "sectioned-checklist"
        assert result["stats"]["total_sections"] == 2
        assert result["stats"]["total_actionable"] == 50

    def test_a1752_still_works(self):
        invalidate_cache()
        path = get_template_path("A17-5-2")
        result = parse_checklist_xlsx(path, "A17-5-2")
        assert result["stats"]["total_sections"] == 2
        assert len(_section(result, "S02")["items"]) == 35


# ─── 属性测试（PBT，max_examples=5） ─────────────────────────────────────────


class TestA15A14Properties:
    """A15-1 / A14-1 通用属性.

    Validates: A15-1 item_id 唯一且前缀对齐 persistence.md；A14-1 grid 认定矩阵恒为 6 列。
    """

    @settings(
        max_examples=5,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(prefix=st.sampled_from(["fin", "ops", "oth"]))
    def test_a151_prefix_ids_sequential(self, a151_result, prefix):
        """属性：A15-1 任一章节前缀的 item_id 连续编号且唯一."""
        ids = [
            it["id"]
            for s in a151_result["sections"]
            for it in s["items"]
            if it["id"].startswith(f"A15-1-{prefix}-")
        ]
        assert ids == sorted(ids)
        assert len(ids) == len(set(ids))
        # 连续编号从 01 开始
        for i, _id in enumerate(ids, start=1):
            assert _id == f"A15-1-{prefix}-{i:02d}"

    @settings(
        max_examples=5,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(_n=st.integers(min_value=0, max_value=4))
    def test_a141_assertion_matrix_invariant(self, a141_result, _n):
        """属性：A14-1 grid 认定矩阵恒为 6 列且 remark schema 含全部 6 认定键."""
        assertions = a141_result["grid"]["assertions"]
        assert len(assertions) == 6
        schema_keys = set(a141_result["grid"]["remark_schema"]["assertions"].keys())
        assert schema_keys == {a["key"] for a in assertions}


# ═══════════════════════════════════════════════════════════════════════════
# PRE-4-4：A11-2、A11-3（A11 bundle xlsx 内的两个调查问卷 sheet）
# ═══════════════════════════════════════════════════════════════════════════

from app.services.checklist_xlsx_parser import _find_bundle_sheet


@pytest.fixture
def a112_result():
    invalidate_cache()
    path = get_template_path("A11-2")
    assert path is not None, "A11-2 bundle 文件未找到"
    return parse_checklist_xlsx(path, "A11-2")


@pytest.fixture
def a113_result():
    invalidate_cache()
    path = get_template_path("A11-3")
    assert path is not None, "A11-3 bundle 文件未找到"
    return parse_checklist_xlsx(path, "A11-3")


class TestA11BundleResolution:
    """bundle 子码（A11-2/A11-3）→ 父 A11 bundle 文件 + sheet 解析."""

    def test_a112_no_top_level_entry(self):
        """A11-2 没有独立顶层 wp_code 条目（仅作为 A11 bundle sheet 存在）."""
        assert _get_audit_entry("A11-2") is None
        assert _get_audit_entry("A11-3") is None

    def test_a112_bundle_sheet_found(self):
        bundle = _find_bundle_sheet("A11-2")
        assert bundle is not None
        parent, sheet = bundle
        assert parent["wp_code"] == "A11"
        assert sheet["name"].endswith("A11-2")
        assert sheet["component_type"] == "checklist-table"

    def test_a113_bundle_sheet_found(self):
        bundle = _find_bundle_sheet("A11-3")
        assert bundle is not None
        parent, sheet = bundle
        assert parent["wp_code"] == "A11"
        assert sheet["name"].endswith("A11-3")

    def test_a112_template_path_is_a11_bundle(self):
        """A11-2 模板路径应解析到 A11 bundle 文件（父条目 filename）."""
        path = get_template_path("A11-2")
        assert path is not None
        assert path.name == "A11 期后事项程序表.xlsx"

    def test_a113_template_path_is_a11_bundle(self):
        path = get_template_path("A11-3")
        assert path is not None
        assert path.name == "A11 期后事项程序表.xlsx"

    def test_bundle_parent_recorded(self, a112_result, a113_result):
        assert a112_result["bundle_parent"] == "A11"
        assert a113_result["bundle_parent"] == "A11"
        assert a112_result["bundle_sheet"].endswith("A11-2")
        assert a113_result["bundle_sheet"].endswith("A11-3")


class TestA112Questionnaire:
    """A11-2 期后事项调查问卷：13 条 actionable."""

    def test_single_section(self, a112_result):
        assert a112_result["stats"]["total_sections"] == 1
        assert len(a112_result["sections"]) == 1

    def test_actionable_count_13(self, a112_result):
        assert a112_result["stats"]["total_actionable"] == 13
        assert len(a112_result["sections"][0]["items"]) == 13

    def test_all_actionable(self, a112_result):
        for item in a112_result["sections"][0]["items"]:
            assert item["type"] == "actionable"

    def test_item_id_pattern(self, a112_result):
        items = a112_result["sections"][0]["items"]
        assert items[0]["id"] == "A11-2-01"
        assert items[-1]["id"] == "A11-2-13"

    def test_item_ids_sequential(self, a112_result):
        ids = [it["id"] for it in a112_result["sections"][0]["items"]]
        assert ids == [f"A11-2-{i:02d}" for i in range(1, 14)]

    def test_conclusion_and_remark_cols(self, a112_result):
        for item in a112_result["sections"][0]["items"]:
            assert item["conclusion_col"] == "D"
            assert item["remark_col"] == "F"

    def test_items_have_content(self, a112_result):
        for item in a112_result["sections"][0]["items"]:
            assert item["content"]

    def test_lead_in_row_excluded(self, a112_result):
        """引导句行「在资产负债表日至…止，贵公司」不计入 actionable."""
        contents = [it["content"] for it in a112_result["sections"][0]["items"]]
        for c in contents:
            assert "贵公司" not in c or c.endswith("；") or c.endswith("。")
        # 引导句 row6 (seq=null) 不应成为条目
        assert not any(c.startswith("在资产负债表日至填写本调查问卷之日止") for c in contents)

    def test_footer_rows_excluded(self, a112_result):
        """落款行（被调查人/日期/*注）不计入 actionable."""
        contents = [it["content"] for it in a112_result["sections"][0]["items"]]
        for kw in ("被调查人", "日期", "*注"):
            assert not any(kw in c for c in contents)


class TestA113Questionnaire:
    """A11-3 期后内控事项调查问卷：6 条 actionable."""

    def test_single_section(self, a113_result):
        assert a113_result["stats"]["total_sections"] == 1

    def test_actionable_count_6(self, a113_result):
        assert a113_result["stats"]["total_actionable"] == 6
        assert len(a113_result["sections"][0]["items"]) == 6

    def test_item_id_pattern(self, a113_result):
        items = a113_result["sections"][0]["items"]
        assert items[0]["id"] == "A11-3-01"
        assert items[-1]["id"] == "A11-3-06"

    def test_item_ids_sequential(self, a113_result):
        ids = [it["id"] for it in a113_result["sections"][0]["items"]]
        assert ids == [f"A11-3-{i:02d}" for i in range(1, 7)]

    def test_all_ids_unique(self, a113_result):
        ids = [it["id"] for it in a113_result["sections"][0]["items"]]
        assert len(ids) == len(set(ids))

    def test_footer_rows_excluded(self, a113_result):
        contents = [it["content"] for it in a113_result["sections"][0]["items"]]
        for kw in ("被调查人", "日        期", "*注"):
            assert not any(kw in c for c in contents)


class TestA11NoRegression:
    """A11-2/A11-3 bundle 解析不影响既有 A17-5-x / A15-1 / A14-1."""

    def test_a1751_still_works(self):
        invalidate_cache()
        path = get_template_path("A17-5-1")
        result = parse_checklist_xlsx(path, "A17-5-1")
        assert result["stats"]["total_sections"] == 2
        assert result["stats"]["total_actionable"] == 50

    def test_a151_still_works(self):
        invalidate_cache()
        path = get_template_path("A15-1")
        result = parse_checklist_xlsx(path, "A15-1")
        assert result["mode"] == "sectioned-checklist"
        assert result["stats"]["total_actionable"] == 22

    def test_a141_still_works(self):
        invalidate_cache()
        path = get_template_path("A14-1")
        result = parse_checklist_xlsx(path, "A14-1")
        assert result["mode"] == "grid"


class TestA11Properties:
    """A11-2 / A11-3 通用属性.

    Validates: bundle 子码解析保持 item_id 唯一且 {wp_code}-{seq:02d} 模式。
    """

    @settings(
        max_examples=5,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(wp_code=st.sampled_from(["A11-2", "A11-3"]))
    def test_bundle_ids_unique_and_well_formed(self, wp_code):
        invalidate_cache()
        path = get_template_path(wp_code)
        result = parse_checklist_xlsx(path, wp_code)
        pat = re.compile(rf"^{re.escape(wp_code)}-\d{{2}}$")
        seen = set()
        for item in result["sections"][0]["items"]:
            assert item["type"] == "actionable"
            assert pat.match(item["id"]), f"非法 item_id: {item['id']}"
            assert item["id"] not in seen
            seen.add(item["id"])
        # 连续编号从 01 开始
        ids = [it["id"] for it in result["sections"][0]["items"]]
        assert ids == [f"{wp_code}-{i:02d}" for i in range(1, len(ids) + 1)]
