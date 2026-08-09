"""附注模板列元数据 / 表名 / guidance 覆盖率守卫（不连库，可进 CI）。

spec: note-template-columns-and-legacy-snapshot-closure（Task 2）

设计要点
--------
1. **判据与探针同源**：本守卫直接调 ``diagnose_note_columns_coverage.scan_templates()``，
   与 Task 1 的探针共用一套判据 —— 探针坏了守卫必红，不会出现「探针报 0 缺口、
   守卫也绿」的双假绿。
2. **基线只许降不许升**：当前欠账数登记在 ``EXPECTED_GAPS``，断言「实测 ≤ 基线」
   且配一条「基线不得被上调」的说明断言（防往基线里加条目绕过）。
3. **按 (variant, scope) 分桶**：一个 scope 的改善不得掩盖另一个 scope 的回退。
4. **母公司章走真源判定不走 section_id 前缀** —— listed 的 ``chapter-12-*`` 是
   「十二、股份支付」而**不是**母公司章（母公司章是 ``chapter-16-*``），按前缀判会
   把股份支付误排除。真源 = ``parent_company_note_sections.load_parent_company_sections()``。
5. 每组断言配反向自检（构造违规替身必须被判据抓到），防判据失效变成空转。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve()
BACKEND_ROOT = _HERE.parents[1]
REPO_ROOT = _HERE.parents[2]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_probe():
    path = BACKEND_ROOT / "scripts" / "diagnose" / "diagnose_note_columns_coverage.py"
    assert path.exists(), f"探针缺失：{path}"
    spec = importlib.util.spec_from_file_location("note_columns_probe_for_guard", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


PROBE = _load_probe()
VARIANTS = ("listed", "soe")

SCOPE_PARENT = PROBE.SCOPE_PARENT
SCOPE_REGISTRY = PROBE.SCOPE_REGISTRY
SCOPE_UNREGISTERED = PROBE.SCOPE_UNREGISTERED

# ---------------------------------------------------------------------------
# 基线（2026-08-07 实测；只许降不许升）
#
# 🔴 与 spec 立项数字（listed 240 / soe 97 等）不同，原因是 A spec
# (parent-company-note-chapter-and-sourcing) 已于 2026-08-07 收口并补齐了
# 母公司章 104 张表的 columns/guidance，同时新增了若干表。立项数字已过期。
# ---------------------------------------------------------------------------

EXPECTED_GAPS: dict[str, dict[str, dict[str, int]]] = {
    "listed": {
        SCOPE_PARENT: {"cols0": 0, "no_guidance": 0, "empty_name": 0, "leak_name": 0},
        # registry_covered 的欠账归各 per-cycle spec（本 spec 只登记不修，见 Notes）
        SCOPE_REGISTRY: {"cols0": 4, "no_guidance": 1, "empty_name": 0, "leak_name": 4},
        # Wave 2（Task 4~6）已把 unregistered 的空名 15→0 / 泄漏名 93→0 / 重名 14→0
        # Wave 3（Task 8~11）按源 docx 列头补齐 70 张 → cols0 175→105
        # Wave 4（Task 12）按源 docx 表前指引段补齐 51 张 -> no_guidance 175->123
        SCOPE_UNREGISTERED: {
            "cols0": 105,
            "no_guidance": 123,
            "empty_name": 0,
            "leak_name": 0,
        },
    },
    "soe": {
        SCOPE_PARENT: {"cols0": 0, "no_guidance": 0, "empty_name": 0, "leak_name": 0},
        SCOPE_REGISTRY: {"cols0": 2, "no_guidance": 1, "empty_name": 0, "leak_name": 1},
        # Wave 3 按源 docx 列头补齐 15 张 → cols0 59→44
        # Wave 4（Task 12）补齐 2 张 -> no_guidance 59->56
        SCOPE_UNREGISTERED: {
            "cols0": 44,
            "no_guidance": 56,
            "empty_name": 0,
            "leak_name": 0,
        },
    },
}

# 含重名表的 section 数（`sub_table_data` 以表名为键，重名互相覆盖丢整表）
# Wave 2 后 listed 14→0：本 spec 的核心数据完整性成果，此处硬锁 0
EXPECTED_DUP_SECTIONS = {"listed": 0, "soe": 0}

# 有 columns 但至少一列未表态 flat/group 的表数。
# 存量普遍不表态（模板 seed 侧历史欠账，flat 多只在前端同步载荷声明），
# 故登记为基线；**本 spec 新补的 columns 必须表态**（见 TestNewColumnsMustDeclareStance）。
# 2026-08-07 实测 336/242（A spec 的 `fix_note_parent_company_chapter.py` 幂等重放后，
# 母公司章各多出 1 张有 columns 但未表态的表 —— 属 A spec 数据，非本 spec 改动）
EXPECTED_STANCE_NONE_TABLES = {"listed": 336, "soe": 242}

# guidance 含 markdown 粗体的表数（`fix_note_bold_markers.py` 会剥离，两脚本会打架）
EXPECTED_GUIDANCE_BOLD = {"listed": 1, "soe": 1}

# 母公司章规模（A spec 的作用域，本 spec 排除；反向自检用）
PARENT_CHAPTER_SHAPE = {
    "listed": {"sections": 6, "tables": 62},
    "soe": {"sections": 6, "tables": 42},
}

# `row_type` 允许取值域。前五个是既有语义；`expandable` 由本 spec Wave 4 additive 新增。
ALLOWED_ROW_TYPES = frozenset(
    {"data", "total", "subtotal", "header_label", "unowned", "expandable"}
)

# 本 spec 落地前实际出现的取值（Wave 4 后会多出 expandable）
OBSERVED_ROW_TYPES_BEFORE_WAVE4 = frozenset(
    {"data", "total", "subtotal", "header_label", "unowned"}
)


@pytest.fixture(scope="module")
def scanned() -> dict[str, Any]:
    return PROBE.scan_templates()


# ---------------------------------------------------------------------------
# Property 1：探针计数与模板文件独立重算一致
# ---------------------------------------------------------------------------


class TestProbeFactsMatchTemplates:
    def test_section_and_table_counts_match_independent_recount(self, scanned) -> None:
        for variant in VARIANTS:
            raw = json.loads(
                (BACKEND_ROOT / "data" / f"note_template_{variant}.json").read_text(
                    encoding="utf-8"
                )
            )
            raw_sections = [s for s in (raw.get("sections") or []) if isinstance(s, dict)]
            raw_tables = sum(
                len(s.get("tables") or [])
                for s in raw_sections
                if isinstance(s.get("tables"), list)
            )
            summary = scanned[variant]["summary"]["total"]
            assert summary["sections"] == len(raw_sections), (
                f"[{variant}] 探针 sections={summary['sections']} "
                f"与独立重算 {len(raw_sections)} 不符"
            )
            assert summary["tables"] == raw_tables, (
                f"[{variant}] 探针 tables={summary['tables']} 与独立重算 {raw_tables} 不符"
            )

    def test_scope_buckets_partition_all_tables(self, scanned) -> None:
        """三个 scope 互斥且穷尽：分桶表数之和 == 总表数。"""
        for variant in VARIANTS:
            total = scanned[variant]["summary"]["total"]["tables"]
            by_scope = scanned[variant]["summary"]["by_scope"]
            assert set(by_scope) <= {
                SCOPE_PARENT,
                SCOPE_REGISTRY,
                SCOPE_UNREGISTERED,
            }, f"[{variant}] 出现未知 scope：{sorted(by_scope)}"
            summed = sum(c.get("tables", 0) for c in by_scope.values())
            assert summed == total, f"[{variant}] 分桶 {summed} != 总数 {total}"

    def test_probe_has_nonzero_scan_surface(self, scanned) -> None:
        """反向自检：扫描面非空（防判据/路径失效让所有断言空转）。"""
        for variant in VARIANTS:
            assert scanned[variant]["summary"]["total"]["tables"] > 200, (
                f"[{variant}] 扫描到的表数异常少，判据可能失效"
            )


# ---------------------------------------------------------------------------
# Property 2：母公司章按真源排除且形态可核
# ---------------------------------------------------------------------------


class TestParentChapterExclusion:
    def test_parent_sections_source_is_not_empty(self, scanned) -> None:
        """反向自检：母公司章真源必须非空。

        ``load_parent_company_sections`` 读不到判据文件时会 fail-open 返回空集合
        （附注生成是交付件路径，不抛异常）—— 那会让整个排除逻辑静默失效。
        """
        parents = scanned["_parent_sections"]
        for variant in VARIANTS:
            assert parents[variant], (
                f"[{variant}] 母公司章真源为空 —— "
                "note_template_variant_matrix.json 的 parent_company_sections 丢了？"
            )

    def test_parent_chapter_shape(self, scanned) -> None:
        for variant in VARIANTS:
            bucket = scanned[variant]["summary"]["by_scope"].get(SCOPE_PARENT, {})
            want = PARENT_CHAPTER_SHAPE[variant]
            assert bucket.get("sections") == want["sections"], (
                f"[{variant}] 母公司章 section 数 {bucket.get('sections')} != {want['sections']}"
            )
            assert bucket.get("tables") == want["tables"], (
                f"[{variant}] 母公司章表数 {bucket.get('tables')} != {want['tables']}"
            )

    def test_listed_chapter12_is_not_parent(self, scanned) -> None:
        """钉死一条易错判据：listed 的 ``chapter-12-*`` 是股份支付，不是母公司章。

        若有人把排除条件改成 ``section_id`` 前缀 ``chapter-12-``，listed 侧
        「十二、股份支付」6 张表会被误排除出本 spec 作用域。
        """
        offenders = [
            s
            for s in scanned["listed"]["sections"]
            if s["section_id"].startswith("chapter-12-") and s["scope"] == SCOPE_PARENT
        ]
        assert not offenders, (
            "listed 的 chapter-12-*（股份支付）被判成母公司章："
            + ", ".join(s["section_number"] for s in offenders)
        )

    def test_soe_parent_chapter_is_chapter12(self, scanned) -> None:
        """soe 侧母公司章确实是 ``chapter-12-mu-gong-si-*``（与 listed 相反）。"""
        parents = [s for s in scanned["soe"]["sections"] if s["scope"] == SCOPE_PARENT]
        assert parents, "soe 侧一个母公司章都没识别出来"
        for s in parents:
            assert s["section_id"].startswith("chapter-12-mu-gong-si-"), (
                f"soe 母公司章 section_id 形态意外：{s['section_id']}"
            )


# ---------------------------------------------------------------------------
# Property 3 / 9：columns 覆盖（基线只许降）
# ---------------------------------------------------------------------------


def _gap(scanned: dict[str, Any], variant: str, scope: str, key: str) -> int:
    return scanned[variant]["summary"]["by_scope"].get(scope, {}).get(key, 0)


class TestColumnsCoverage:
    @pytest.mark.parametrize("variant", VARIANTS)
    @pytest.mark.parametrize(
        "scope", [SCOPE_PARENT, SCOPE_REGISTRY, SCOPE_UNREGISTERED]
    )
    def test_cols0_not_worse_than_baseline(self, scanned, variant, scope) -> None:
        actual = _gap(scanned, variant, scope, "cols0")
        baseline = EXPECTED_GAPS[variant][scope]["cols0"]
        assert actual <= baseline, (
            f"[{variant}/{scope}] columns==0 的表数从 {baseline} 涨到 {actual} —— "
            "有人往模板里加了不带列头的表，或删掉了已补的 columns"
        )

    def test_parent_chapter_columns_already_complete(self, scanned) -> None:
        """A spec 已补齐母公司章 columns；此断言防它被回退。"""
        for variant in VARIANTS:
            assert _gap(scanned, variant, SCOPE_PARENT, "cols0") == 0, (
                f"[{variant}] 母公司章又出现 columns==0 —— A spec 的成果被回退？"
            )

    def test_columns_length_equals_headers_length(self, scanned) -> None:
        """有 columns 的表，其列数必须与 headers 长度一致（当前全库为 0 违规）。"""
        bad: list[str] = []
        for variant in VARIANTS:
            for sec in scanned[variant]["sections"]:
                for t in sec["tables"]:
                    if t["column_count"] and t["column_count"] != t["header_count"]:
                        bad.append(
                            f"{variant} {sec['section_number']} #{t['index']} "
                            f"{t['name']!r} cols={t['column_count']} headers={t['header_count']}"
                        )
        assert not bad, "columns 与 headers 列数不一致：\n" + "\n".join(bad[:20])

    def test_baseline_must_not_be_raised(self) -> None:
        """基线上限锁死：只许改小，不许往里加额度。

        这些数字是 2026-08-07 实测值，任何上调都等于把新增欠账合法化。
        """
        # cols0 上限（Wave 3 补齐后）
        cols0_ceiling = {
            ("listed", SCOPE_REGISTRY): 4,
            # Wave 3（Task 8~11）后 175 → 105（补齐 70 张）
            ("listed", SCOPE_UNREGISTERED): 105,
            ("soe", SCOPE_REGISTRY): 2,
            # Wave 3 后 59 → 44（补齐 15 张）
            ("soe", SCOPE_UNREGISTERED): 44,
        }
        for (variant, scope), cap in cols0_ceiling.items():
            assert EXPECTED_GAPS[variant][scope]["cols0"] <= cap, (
                f"EXPECTED_GAPS[{variant}][{scope}]['cols0'] 被上调到 "
                f"{EXPECTED_GAPS[variant][scope]['cols0']}（上限 {cap}）"
            )
        # no_guidance 上限（Wave 4 / Task 12 补齐后必须同步锁死，否则补完又被回退不打红）
        guidance_ceiling = {
            ("listed", SCOPE_REGISTRY): 1,
            # Wave 4（Task 12）后 175 → 123（补齐 51 张）
            ("listed", SCOPE_UNREGISTERED): 123,
            ("soe", SCOPE_REGISTRY): 1,
            # Wave 4 后 59 → 56（补齐 2 张）
            ("soe", SCOPE_UNREGISTERED): 56,
        }
        for (variant, scope), cap in guidance_ceiling.items():
            assert EXPECTED_GAPS[variant][scope]["no_guidance"] <= cap, (
                f"EXPECTED_GAPS[{variant}][{scope}]['no_guidance'] 被上调到 "
                f"{EXPECTED_GAPS[variant][scope]['no_guidance']}（上限 {cap}）—— "
                "Task 12 补齐的 guidance 不许回退"
            )
        # Wave 2 的成果硬锁 0：表名类欠账在作用域内不许再有额度
        for variant in VARIANTS:
            for key in ("empty_name", "leak_name"):
                assert EXPECTED_GAPS[variant][SCOPE_UNREGISTERED][key] == 0, (
                    f"EXPECTED_GAPS[{variant}][unregistered][{key}] 不得从 0 上调"
                    "（Wave 2 已清零）"
                )
            assert EXPECTED_DUP_SECTIONS[variant] == 0, (
                f"EXPECTED_DUP_SECTIONS[{variant}] 不得从 0 上调（Wave 2 已清零）"
            )


# ---------------------------------------------------------------------------
# Property 5：表名（空名 / 表头泄漏 / 章节内唯一）
# ---------------------------------------------------------------------------


class TestTableNames:
    @pytest.mark.parametrize("variant", VARIANTS)
    @pytest.mark.parametrize("key", ["empty_name", "leak_name"])
    def test_name_gaps_not_worse_than_baseline(self, scanned, variant, key) -> None:
        for scope in (SCOPE_PARENT, SCOPE_REGISTRY, SCOPE_UNREGISTERED):
            actual = _gap(scanned, variant, scope, key)
            baseline = EXPECTED_GAPS[variant][scope][key]
            assert actual <= baseline, (
                f"[{variant}/{scope}] {key} 从 {baseline} 涨到 {actual}"
            )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_dup_sections_not_worse_than_baseline(self, scanned, variant) -> None:
        actual = scanned[variant]["summary"]["total"].get("dup_sections", 0)
        assert actual <= EXPECTED_DUP_SECTIONS[variant], (
            f"[{variant}] 含重名表的 section 从 {EXPECTED_DUP_SECTIONS[variant]} "
            f"涨到 {actual} —— sub_table_data 以表名为键，重名会丢整表"
        )

    def test_leak_name_judgement_reuses_migrator_source(self) -> None:
        """Property 4：泄漏名判据必须复用迁移器的 ``_name_is_meaningful``。"""
        assert PROBE.name_is_meaningful is not None
        # 逐例：表名 == headers[0] / 常见表头词 / 正常业务名
        assert PROBE.name_is_meaningful("交易性金融资产", ["项目", "期末"]) is True
        assert PROBE.name_is_meaningful("项目", ["项目", "期末"]) is False
        assert PROBE.name_is_meaningful("项  目", ["期末"]) is False
        assert PROBE.name_is_meaningful("", ["项目"]) is False


# ---------------------------------------------------------------------------
# Property 13 / 14：guidance 与表头纯文本
# ---------------------------------------------------------------------------


class TestGuidanceAndPlainText:
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_no_guidance_not_worse_than_baseline(self, scanned, variant) -> None:
        for scope in (SCOPE_PARENT, SCOPE_REGISTRY, SCOPE_UNREGISTERED):
            actual = _gap(scanned, variant, scope, "no_guidance")
            baseline = EXPECTED_GAPS[variant][scope]["no_guidance"]
            assert actual <= baseline, (
                f"[{variant}/{scope}] guidance 为空的表从 {baseline} 涨到 {actual}"
            )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_guidance_bold_not_worse(self, scanned, variant) -> None:
        actual = scanned[variant]["summary"]["total"].get("guidance_bold", 0)
        assert actual <= EXPECTED_GUIDANCE_BOLD[variant], (
            f"[{variant}] guidance 含 markdown 粗体的表从 "
            f"{EXPECTED_GUIDANCE_BOLD[variant]} 涨到 {actual} —— "
            "fix_note_bold_markers.py 会剥掉它，两个脚本会互相打架"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_guidance_has_no_html(self, scanned, variant) -> None:
        actual = scanned[variant]["summary"]["total"].get("guidance_html", 0)
        assert actual == 0, f"[{variant}] {actual} 张表的 guidance 含 HTML 标签"

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_headers_and_labels_have_no_html(self, scanned, variant) -> None:
        actual = scanned[variant]["summary"]["total"].get("html_in_headers", 0)
        assert actual == 0, (
            f"[{variant}] {actual} 张表的 headers/columns.label 含 HTML 标签"
            "（平台级修订入口 fix_note_headers_plaintext.py）"
        )


# ---------------------------------------------------------------------------
# Property 10：两级结构表态
# ---------------------------------------------------------------------------


class TestColumnStance:
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_stance_none_not_worse_than_baseline(self, scanned, variant) -> None:
        actual = scanned[variant]["summary"]["total"].get("stance_none_tables", 0)
        assert actual <= EXPECTED_STANCE_NONE_TABLES[variant], (
            f"[{variant}] 有 columns 但未表态 flat/group 的表从 "
            f"{EXPECTED_STANCE_NONE_TABLES[variant]} 涨到 {actual} —— "
            "未表态会让 _extract_column_groups 回退 _infer_groups_from_headers 前缀推断，"
            "凭空推出父表头"
        )

    def test_stance_helper_reverse_selfcheck(self) -> None:
        """反向自检：表态判据能区分三态。"""
        assert PROBE._column_stance({"key": "a", "label": "a", "flat": True}) == "flat"
        assert PROBE._column_stance({"key": "a", "label": "a", "group": "期末"}) == "group"
        assert PROBE._column_stance({"key": "a", "label": "a"}) == "none"
        assert PROBE._column_stance({"key": "a", "group": "   "}) == "none"
        assert PROBE._column_stance("not-a-dict") == "none"


# ---------------------------------------------------------------------------
# Property 33：row_type 取值域
# ---------------------------------------------------------------------------


class TestRowTypeDomain:
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_row_types_within_allowed_domain(self, scanned, variant) -> None:
        observed = set(scanned[variant]["summary"]["row_types"])
        extra = observed - ALLOWED_ROW_TYPES
        assert not extra, (
            f"[{variant}] 出现允许域外的 row_type：{sorted(extra)}；"
            f"允许域 = {sorted(ALLOWED_ROW_TYPES)}"
        )

    def test_expandable_is_additive_sixth_value(self, scanned) -> None:
        """`expandable` 是本 spec Wave 4 additive 新增的第 6 个取值。

        Wave 4 之前全库不应出现它；出现即说明 Wave 4 已落地，此断言要随之更新
        （连带 Property 33 的「零可见内容」断言必须已实现）。
        """
        observed: set[str] = set()
        for variant in VARIANTS:
            observed |= set(scanned[variant]["summary"]["row_types"])
        assert observed <= ALLOWED_ROW_TYPES
        assert observed >= {"data", "total"}, "row_type 扫描面异常（判据失效？）"


# ---------------------------------------------------------------------------
# 反向自检：替身表必须被判据抓到
# ---------------------------------------------------------------------------


class TestJudgementReverseSelfCheck:
    def test_scan_table_flags_all_violation_kinds(self) -> None:
        empty_name = PROBE.scan_table({"name": "  ", "headers": ["项目"]}, index=0)
        assert empty_name["is_empty_name"] is True
        assert empty_name["column_count"] == 0

        leak = PROBE.scan_table({"name": "项  目", "headers": ["项  目", "期末"]}, index=0)
        assert leak["is_leak_name"] is True

        bold = PROBE.scan_table(
            {"name": "X", "headers": ["a"], "guidance": "**加粗**"}, index=0
        )
        assert bold["guidance_has_bold"] is True
        assert bold["has_guidance"] is True

        html = PROBE.scan_table(
            {"name": "X", "headers": ["a<br/>b"], "guidance": "<b>x</b>"}, index=0
        )
        assert html["headers_have_html"] is True
        assert html["guidance_has_html"] is True

        ok = PROBE.scan_table(
            {
                "name": "交易性金融资产",
                "headers": ["项目", "期末余额"],
                "columns": [
                    {"key": "项目", "label": "项目", "flat": True},
                    {"key": "期末余额", "label": "期末余额", "flat": True},
                ],
                "guidance": "勾稽：合计 = 各明细行之和",
                "rows": [{"row_type": "data"}, {"row_type": "total"}],
            },
            index=0,
        )
        assert ok["is_empty_name"] is False
        assert ok["is_leak_name"] is False
        assert ok["stance_none"] == 0
        assert ok["stance_flat"] == 2
        assert ok["has_guidance"] is True
        assert ok["row_types"] == {"data": 1, "total": 1}

    def test_classify_section_reverse_selfcheck(self) -> None:
        parents = {"listed": frozenset({"十六、应收票据"}), "soe": frozenset()}
        registry = {"listed": {"五、4"}, "soe": set()}
        assert (
            PROBE.classify_section(
                section_number="十六、应收票据",
                variant="listed",
                parent_sections=parents,
                registry_sections=registry,
            )
            == SCOPE_PARENT
        )
        assert (
            PROBE.classify_section(
                section_number="五、4",
                variant="listed",
                parent_sections=parents,
                registry_sections=registry,
            )
            == SCOPE_REGISTRY
        )
        assert (
            PROBE.classify_section(
                section_number="三、套期",
                variant="listed",
                parent_sections=parents,
                registry_sections=registry,
            )
            == SCOPE_UNREGISTERED
        )
        # 同一章节号在另一变体下不得沿用（两版章节号会撞号，13 个标题不同）
        assert (
            PROBE.classify_section(
                section_number="十六、应收票据",
                variant="soe",
                parent_sections=parents,
                registry_sections=registry,
            )
            == SCOPE_UNREGISTERED
        )

# ---------------------------------------------------------------------------
# Wave 3（Task 8~11）：列真源交叉锁死
#
# 判据方向：**模板的 columns 必须来自源 docx，不得由 JSON headers 反推**。
# JSON headers 本身可能是 md 重建压扁的产物（本 spec Introduction 已实证 49+2 张
# 表的 docx 列数与 JSON headers 长度不等）→ 拿 headers 补 columns 等于把压扁
# 固化成"正确"。故守卫从两侧钉：
#   ① 规则表每条的 labels 必须与 **源 docx facts** 逐字相等（不是与 JSON 相等）
#   ② 生产脚本源码里不得出现「按 headers 兜底」的回退分支
# ---------------------------------------------------------------------------

COLUMNS_RULES_PATH = REPO_ROOT / "backend" / "data" / "note_columns_rules.json"
HEADERS_FACTS_PATH = (
    REPO_ROOT / "backend" / "data" / "note_table_headers_source_facts.json"
)
FIX_COLUMNS_SCRIPT = (
    REPO_ROOT / "backend" / "scripts" / "fix" / "fix_note_columns_coverage.py"
)


@pytest.fixture(scope="module")
def columns_rules() -> dict[str, Any]:
    assert COLUMNS_RULES_PATH.is_file(), (
        f"列规则表缺失：{COLUMNS_RULES_PATH}（跑 build_note_columns_rules.py）"
    )
    return json.loads(COLUMNS_RULES_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def headers_facts() -> dict[str, Any]:
    assert HEADERS_FACTS_PATH.is_file(), (
        f"源 docx 列头事实缺失：{HEADERS_FACTS_PATH}"
        "（跑 diagnose/extract_note_table_headers.py）"
    )
    return json.loads(HEADERS_FACTS_PATH.read_text(encoding="utf-8"))


def _iter_rule_tables(columns_rules: dict[str, Any], variant: str):
    """规则表真实结构 = ``rules[variant][section_id] -> {section_number, tables[]}``。

    展平成 ``(section_number, table_dict)`` 序列。写守卫前先落探针实测过结构，
    别按记忆里的形态读（首版按 ``variants[variant].rules`` 读 → 恒空 → 假红）。
    """
    by_section = (columns_rules.get("rules") or {}).get(variant) or {}
    for sec in by_section.values():
        if not isinstance(sec, dict):
            continue
        num = str(sec.get("section_number") or "")
        for t in sec.get("tables") or []:
            if isinstance(t, dict):
                yield num, t


class TestColumnsRuleProvenance:
    """规则表的每条 labels 必须能在源 docx 事实里逐字找到。"""

    def test_rules_non_empty(self, columns_rules) -> None:
        total = sum(
            len(list(_iter_rule_tables(columns_rules, v))) for v in VARIANTS
        )
        assert total >= 80, (
            f"规则表条目数 {total} 异常偏少 —— 生成器可能失效（实测 85 条）。"
            "此断言防「规则表变空 → 补列脚本无事可做 → --check 假绿」"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_every_rule_label_matches_source_docx(
        self, columns_rules, headers_facts, variant
    ) -> None:
        """Property 12 的强化：labels 逐字来自源 docx，不是来自 JSON headers。

        🔴 判据方向：与 **源 docx 事实** 比对，不与模板 JSON 的 headers 比对。
        两者恰好相等时也不能改成比 JSON —— 那会让「headers 已被 md 重建压扁」
        的表在将来悄悄通过。
        """
        rules = list(_iter_rule_tables(columns_rules, variant))
        assert rules, f"{variant} 规则表为空"

        facts = headers_facts.get(variant) or {}

        bad: list[str] = []
        for num, r in rules:
            src = str(r.get("source_ref") or "")
            assert src.startswith("docx:"), (
                f"{variant} {num} #{r.get('index')} 的 source_ref 不是 docx 型"
                f"（实为 {src!r}）—— 列真源只能是源 docx，禁止 JSON headers 兜底"
            )
            labels = [c.get("label") for c in (r.get("columns") or [])]
            assert labels and all(isinstance(x, str) for x in labels), (
                f"{variant} {num} 的 labels 形态异常：{labels!r}"
            )
            if not _labels_exist_in_facts(labels, facts):
                bad.append(
                    f"{variant} {num} #{r.get('index')} "
                    f"labels={labels!r} 在源 docx 事实里找不到"
                )
        assert not bad, "规则 labels 与源 docx 不符：\n" + "\n".join(bad[:10])

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_every_rule_column_states_stance(self, columns_rules, variant) -> None:
        """Property 10：每列必须表态 ``flat`` 或 ``group``，且首列是标签列。"""
        bad: list[str] = []
        for num, r in _iter_rule_tables(columns_rules, variant):
            cols = r.get("columns") or []
            for i, c in enumerate(cols):
                if not (c.get("flat") or c.get("group")):
                    bad.append(f"{variant} {num} #{r.get('index')} 列{i} 未表态")
            if cols and not cols[0].get("is_label"):
                bad.append(f"{variant} {num} #{r.get('index')} 首列缺 is_label")
        assert not bad, "列表态缺失：\n" + "\n".join(bad[:20])

    def test_deficits_are_registered_not_guessed(self, columns_rules) -> None:
        """规则外的表必须进 deficits 并带原因码，不得静默跳过。

        实测 149 张（listed 105 / soe 44），三类原因：
        ``NO_SECTION``（docx 无该章节）/ ``COUNT_MISMATCH``（表数不等）/
        ``LEN_MISMATCH``（列数与 JSON headers 不等 → 需人工裁决压扁问题）。
        """
        deficits = columns_rules.get("deficits") or {}
        total = sum(len(v or []) for v in deficits.values())
        assert total >= 100, (
            f"deficits 只有 {total} 条 —— 实测 149 条。变少说明有表被静默跳过"
        )
        # 🔴 reason 形态 = 「原因码 + 中文明细」拼串（如
        # `LEN_MISMATCH（docx 13 列 vs JSON 3 列，疑为两级表头被 md 重建压扁）`），
        # 故按**前缀**判定而非全等；明细是人工裁决的依据，不能要求它消失。
        # 🔴 五类原因码，每类都是**不同的**人工裁决路径，不得合并：
        #   NO_SECTION       docx 无该章节 → 该章节列真源缺失，须另找依据
        #   COUNT_MISMATCH   docx 与 JSON 表数不等 → 表集合本身有分歧
        #   LEN_MISMATCH     列数不等（多为两级表头被 md 重建压扁）→ 归 R2.7
        #   CROSS_CHAPTER    章归属闸门拦下的跨章错配 → 要么登记等价、要么另找依据
        #   EXISTING_DIFFERS 已有 columns 与 docx 不一致 → fail-closed 不覆盖，
        #                    归该章节的 per-cycle spec 裁决（R10.7）
        allowed = (
            "NO_SECTION",
            "COUNT_MISMATCH",
            "LEN_MISMATCH",
            "CROSS_CHAPTER",
            "EXISTING_DIFFERS",
        )
        seen: set[str] = set()
        for variant, items in deficits.items():
            for d in items or []:
                reason = str(d.get("reason") or "")
                code = next((c for c in allowed if reason.startswith(c)), "")
                assert code, (
                    f"{variant} {d.get('section_number')} 的 reason={reason!r} "
                    f"不以已登记原因码 {list(allowed)} 之一开头"
                )
                seen.add(code)
        # 反向自检：三类原因码都必须真实出现过，否则说明分类逻辑退化成单一分支
        assert seen == set(allowed), (
            f"deficits 只出现原因码 {sorted(seen)}，实测应三类齐全 {list(allowed)}"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_every_rule_passes_chapter_gate(self, columns_rules, variant) -> None:
        """Property 13（本轮新增）：每条规则的 docx 归属必须过章归属闸门。

        🔴 缺陷背景：生成器原先只按「末级 heading 归一后相等/互含」匹配 docx 章节，
        **不校验章归属** ⇒ 跨章同名表会被静默配错。实测最毒的一例：

            JSON  `三、长期股权投资`（第三章 = 重要会计政策及会计估计）
                  headers = ['项  目', '期末余额', '上年年末余额']
            docx  `合并财务报表项目附注 / 长期股权投资`（= JSON 第五章）
                  13 列两级变动表

        它只是**恰好**被「列数相等」这道弱闸门挡住 —— 跨章且列数相等时会静默写错列名。
        本断言把 `chapter_verdict` 的判定钉在规则表上：凡已生成规则的条目，
        其 (JSON 章, docx root) 必须是 same / equiv / allowlisted 之一。
        """
        gen = _load_rules_generator()
        chapters = _chapter_titles(variant)

        bad: list[str] = []
        for num, r in _iter_rule_tables(columns_rules, variant):
            docx_key = str(r.get("_docx_key") or r.get("source_ref") or "")
            root = gen._docx_root(docx_key.replace("docx:", ""))
            json_chapter = chapters.get(gen._chapter_no(num), "")
            ok, kind = gen.chapter_verdict(variant, json_chapter, root)
            if not ok:
                bad.append(
                    f"{variant} {num} #{r.get('index')} JSON章={json_chapter!r} "
                    f"docx_root={root!r} verdict={kind}"
                )
        assert not bad, (
            "规则表存在未过章归属闸门的条目（跨章错配风险）：\n" + "\n".join(bad[:10])
        )

    def test_chapter_gate_rejects_real_cross_chapter_case(self) -> None:
        """反向自检：闸门必须拒绝真实的跨章错配，且放行已登记的三类合法形态。

        没有这条，闸门可能退化成「恒返 True」而上面那条断言照样全绿。
        """
        gen = _load_rules_generator()

        # (1) 真跨章必拒 —— listed 第三章（会计政策）不得配到 docx「税项」根节点
        ok, kind = gen.chapter_verdict("listed", "重要会计政策及会计估计", "税项")
        assert not ok and kind == "cross", (
            f"闸门放过了真实跨章（会计政策 ↔ 税项），verdict={kind} —— 闸门已失效"
        )

        # (2) 同章必放行
        ok, kind = gen.chapter_verdict("soe", "财务报表主要项目注释", "财务报表主要项目注释")
        assert ok and kind == "same", f"同章被拒，verdict={kind}"

        # (3) 章名等价必放行（JSON「注释」↔ docx「附注」）
        ok, kind = gen.chapter_verdict(
            "listed", "合并财务报表项目注释", "合并财务报表项目附注"
        )
        assert ok and kind == "equiv", f"章名等价形态被拒，verdict={kind}"

        # (4) 白名单必放行，且每条理由 >= 12 字（防塞空理由当万能开关）
        ok, kind = gen.chapter_verdict(
            "listed", "重要会计政策及会计估计", "合并财务报表项目附注"
        )
        assert ok and kind == "allowlisted", f"白名单形态被拒，verdict={kind}"
        short = [
            k for k, v in gen.CROSS_CHAPTER_ALLOWLIST.items() if len(str(v or "")) < 12
        ]
        assert not short, (
            f"白名单条目理由过短（<12 字）：{short} —— 每条跨章放行必须写明实证依据"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_every_rule_passes_chapter_gate(self, columns_rules, variant) -> None:
        """🔴 章归属闸门：每条规则的 docx 匹配必须同章或已登记为等价/已知错落章。

        缺陷背景（2026-08-07 实证）：生成器原按「末级 heading 归一后相等/互含」
        匹配 docx 章节，**不校验章归属** ⇒ 跨章同名表会被静默配错。最毒的一例：

            JSON  `三、长期股权投资`（第三章 = 重要会计政策及会计估计）
                  headers = ['项  目', '期末余额', '上年年末余额']
            docx  `合并财务报表项目附注 / 长期股权投资`（= JSON 第五章）
                  13 列两级变动表

        它恰好被「列数相等」这道**弱**安全阀挡住了；但跨章同名且列数相等时
        没有任何东西能拦住静默错配。本断言要求每条已生成的规则都过闸门。
        """
        gen = _load_rules_generator()
        chapters = _chapter_titles(variant)

        bad: list[str] = []
        for num, r in _iter_rule_tables(columns_rules, variant):
            docx_key = str(r.get("docx_key") or "")
            chapter = chapters.get(gen._chapter_no(num), "")
            ok, kind = gen.chapter_verdict(variant, chapter, gen._docx_root(docx_key))
            if not ok:
                bad.append(
                    f"{variant} {num} #{r.get('index')} JSON 章={chapter!r} "
                    f"docx root={gen._docx_root(docx_key)!r} verdict={kind}"
                )
        assert not bad, (
            "规则表存在未过章归属闸门的条目（跨章匹配且未登记）：\n"
            + "\n".join(bad[:15])
        )

    def test_chapter_gate_actually_rejects_cross_chapter(self) -> None:
        """反向自检：闸门必须真的拒绝未登记的跨章组合（防它退化成恒 True）。"""
        gen = _load_rules_generator()

        # 未登记的跨章组合必须被拒
        ok, kind = gen.chapter_verdict("listed", "重要会计政策及会计估计", "补充资料")
        assert not ok and kind == "cross", (
            f"闸门放行了未登记的跨章组合（verdict={kind}）—— 它已退化成恒真，"
            "跨章同名且列数相等的静默错配会重新可能发生"
        )

        # 同章必须放行
        ok, _ = gen.chapter_verdict("listed", "政府补助", "政府补助")
        assert ok, "闸门拒绝了同章匹配 —— 判据反了"

        # 已登记的等价章必须放行
        ok, kind = gen.chapter_verdict(
            "listed", "合并财务报表项目注释", "合并财务报表项目附注"
        )
        assert ok and kind in ("equiv", "allowlisted"), (
            f"闸门拒绝了已登记的等价章（verdict={kind}）"
        )

        # 白名单每条必须写明依据（≥12 字），防它变成万能开关
        short = [
            k for k, v in gen.CROSS_CHAPTER_ALLOWLIST.items() if len(str(v or "")) < 12
        ]
        assert not short, f"白名单条目缺少依据说明：{short}"

    def test_script_has_no_headers_fallback(self) -> None:
        """源码级：补列脚本不得含「按 JSON headers 兜底」的回退分支。

        反向自检：先断言脚本里确实有那句禁令注释（证明扫描面非空），
        再断言没有真实的 headers 兜底赋值。
        """
        src = FIX_COLUMNS_SCRIPT.read_text(encoding="utf-8")
        assert "headers" in src, "扫描面为空 —— 脚本内容异常"

        body = _strip_py_comments(src)
        # 禁止：把 headers 直接当 columns 用
        for pat in (
            r"columns\s*=\s*\[?\s*\{?\s*[\"']?key[\"']?\s*:\s*h\b",
            r"for\s+h\s+in\s+.*headers.*:\s*\n\s*.*columns\.append",
            r"fallback[_ ]?headers",
        ):
            assert not re.search(pat, body), (
                f"补列脚本出现 headers 兜底形态（{pat}）—— "
                "JSON headers 可能是 md 重建压扁的产物，不得据它补 columns"
            )


def _load_rules_generator():
    """加载规则生成器模块（闸门判定函数的单一真源，守卫不抄第二份）。"""
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "diagnose"
        / "build_note_columns_rules.py"
    )
    assert path.exists(), f"规则生成器不存在：{path}"
    spec = importlib.util.spec_from_file_location("rules_gen_for_guard", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    for name in ("chapter_verdict", "_docx_root", "_chapter_no", "CROSS_CHAPTER_ALLOWLIST"):
        assert hasattr(mod, name), f"生成器缺少 {name} —— 闸门可能被移除"
    return mod


def _chapter_titles(variant: str) -> dict[str, str]:
    """章号 -> 章标题（``level == 1`` 的顶层 section）。"""
    gen = _load_rules_generator()
    raw = json.loads(
        (Path(__file__).resolve().parents[1] / "data" / f"note_template_{variant}.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        gen._chapter_no(str(s.get("section_number") or "")): str(s.get("section_title") or "")
        for s in (raw.get("sections") or [])
        if isinstance(s, dict) and s.get("level") == 1
    }


def _labels_exist_in_facts(labels: list[str], fact_tables: Any) -> bool:
    """labels 序列是否在 docx 事实里出现过（按归一后逐字比对）。"""
    want = [_norm_label(x) for x in labels]

    def walk(node: Any) -> bool:
        if isinstance(node, dict):
            for key in ("level1", "leaf", "headers", "columns"):
                val = node.get(key)
                if isinstance(val, list) and val and all(isinstance(x, str) for x in val):
                    if [_norm_label(x) for x in val] == want:
                        return True
            return any(walk(v) for v in node.values())
        if isinstance(node, list):
            return any(walk(v) for v in node)
        return False

    return walk(fact_tables)


def _norm_label(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _strip_py_comments(src: str) -> str:
    """剥 python 注释与 docstring（守卫自身的踩坑说明会含被禁字样）。"""
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    out = re.sub(r"(?m)#.*$", "", out)
    return out


# ---------------------------------------------------------------------------
# Task 12：guidance 真源 provenance
# ---------------------------------------------------------------------------

GUIDANCE_RULES_PATH = BACKEND_ROOT / "data" / "note_guidance_rules.json"
BUILD_GUIDANCE_SCRIPT = (
    BACKEND_ROOT / "scripts" / "diagnose" / "build_note_guidance_rules.py"
)


@pytest.fixture(scope="module")
def guidance_rules() -> dict[str, Any]:
    assert GUIDANCE_RULES_PATH.exists(), (
        f"缺少 guidance 真源 {GUIDANCE_RULES_PATH}；"
        "生成器 = backend/scripts/diagnose/build_note_guidance_rules.py"
    )
    return json.loads(GUIDANCE_RULES_PATH.read_text(encoding="utf-8"))


def _iter_guidance_rules(rules: dict[str, Any], variant: str):
    for spec in (rules.get("rules", {}).get(variant, {})).values():
        for entry in spec.get("tables") or []:
            yield spec.get("section_number", ""), entry


class TestGuidanceRuleProvenance:
    """guidance 必须逐字来自源 docx 的指引段，不得自造披露口径（R3.2）。

    🔴 为什么判据是「逐表」而不是「同章有指引段」
    ------------------------------------------------------------------
    首轮探针按章级判可用性得 listed 160/175、soe 43/59，看起来能补大半；
    但 `三、现金流量表项目注释` 一章有 9 张表 —— 按章取会把第 1 张表的指引
    贴到第 9 张表上 = 自造口径。故真源 `guidance_candidates` 是从**表前 6 段
    缓冲区**抽的（`extract_note_table_headers._pick_guidance`），逐表精准；
    产量因此低（listed 52 / soe 3，欠账 179），这是 R3.3「宁缺勿造」的预期结果。
    """

    def test_rules_non_empty(self, guidance_rules) -> None:
        total = sum(
            len(list(_iter_guidance_rules(guidance_rules, v))) for v in VARIANTS
        )
        assert total >= 50, (
            f"guidance 规则条目数 {total} 异常偏少（实测 55 条）——"
            "生成器可能失效，会让 --check 变成假绿"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_every_guidance_comes_from_source_docx(
        self, guidance_rules, variant
    ) -> None:
        """每条 guidance 必须能在源 docx 事实的 ``guidance_candidates`` 里逐字找到。"""
        facts_path = BACKEND_ROOT / "data" / "note_table_headers_source_facts.json"
        assert facts_path.exists(), f"缺少列头/指引事实 {facts_path}"
        facts = json.loads(facts_path.read_text(encoding="utf-8"))

        pool: set[str] = set()
        for meta in (facts.get(variant, {}).get("sections") or {}).values():
            for t in meta.get("tables") or []:
                for cand in t.get("guidance_candidates") or []:
                    pool.add(re.sub(r"\s+", "", str(cand)))
        assert pool, f"{variant} 源 docx 指引段池为空 —— 抽取器可能失效"

        # 🔴 判据必须**逐段**比对，不能拿整条 guidance 去池里找（本轮踩坑）
        # ------------------------------------------------------------------
        # 一张表可以有多段指引（源 docx 表前常有「（15号文第N条…）」+「【提示：…】」
        # 两三段并列），生成器按 `\n` 把它们拼成一条 guidance —— 这是**正确**的
        # （附注 TAB 的编制提示要把该表全部依据都显示出来）。
        # 首版守卫按「整条必须等于池中某一条」判定，于 23 处打红，逐个核实后
        # 全部是拼接形态、每一段都能在池里找到 ⇒ 是**守卫判据缺陷**不是规则问题。
        bad: list[str] = []
        for num, entry in _iter_guidance_rules(guidance_rules, variant):
            text = str(entry.get("guidance") or "")
            src = str(entry.get("source_ref") or "")
            if not src.startswith("docx:"):
                bad.append(f"{variant} {num} #{entry.get('index')} source_ref 非 docx 型")
                continue
            segs = [x for x in (text.split("\n")) if x.strip()]
            assert segs, f"{variant} {num} #{entry.get('index')} guidance 为空"
            for seg in segs:
                if re.sub(r"\s+", "", seg) not in pool:
                    bad.append(
                        f"{variant} {num} #{entry.get('index')} 段 {seg[:40]!r} "
                        "不在源 docx 指引段池中（自造口径？）"
                    )
        assert not bad, "guidance 与源 docx 不符：\n" + "\n".join(bad[:10])

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_guidance_segments_are_joined_by_newline(
        self, guidance_rules, variant
    ) -> None:
        """反向自检：确实存在多段拼接的 guidance，证明上面的逐段判据不是空转。

        若哪天生成器改成只取第一段，这条会打红提醒「多段依据被丢弃」。
        """
        multi = [
            num
            for num, entry in _iter_guidance_rules(guidance_rules, variant)
            if len([x for x in str(entry.get("guidance") or "").split("\n") if x.strip()]) > 1
        ]
        assert multi, (
            f"{variant} 没有任何多段拼接的 guidance —— "
            "逐段比对判据无从生效（实测 listed 22 处 / soe 1 处）"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_guidance_is_plain_text(self, guidance_rules, variant) -> None:
        """R3.4 / R3.5：无 markdown 粗体、无 HTML 标签。"""
        bad: list[str] = []
        for num, entry in _iter_guidance_rules(guidance_rules, variant):
            text = str(entry.get("guidance") or "")
            if "**" in text:
                bad.append(f"{variant} {num} 含 markdown 粗体（fix_note_bold_markers 会剥掉）")
            if re.search(r"<[^>]+>", text):
                bad.append(f"{variant} {num} 含 HTML 标签")
        assert not bad, "guidance 非纯文本：\n" + "\n".join(bad[:10])

    def test_deficits_registered_with_reason(self, guidance_rules) -> None:
        """规则外的表必须进 deficits 带原因码，不得静默跳过也不得自造。"""
        deficits = guidance_rules.get("deficits") or {}
        total = sum(len(v or []) for v in deficits.values())
        assert total >= 150, (
            f"guidance deficits 只有 {total} 条（实测 179）—— 变少说明有表被静默跳过"
        )
        allowed = ("NO_SECTION", "COUNT_MISMATCH", "NO_GUIDANCE_IN_SOURCE", "CROSS_CHAPTER")
        seen: set[str] = set()
        for variant, items in deficits.items():
            for d in items or []:
                reason = str(d.get("reason") or "")
                code = next((c for c in allowed if reason.startswith(c)), "")
                assert code, f"{variant} {d.get('section_number')} reason={reason!r} 未登记"
                seen.add(code)
        assert "NO_GUIDANCE_IN_SOURCE" in seen, (
            "deficits 里没有 NO_GUIDANCE_IN_SOURCE —— "
            "该码代表「源 docx 表前确实无指引段」，是宁缺勿造的证据，不该消失"
        )

    def test_fix_script_has_guidance_channel_and_no_fabrication(self) -> None:
        """源码级：补 guidance 走同一脚本，且不得含「自造口径」的兜底分支。

        反向自检：先断言脚本里确实提到 guidance（扫描面非空）。
        """
        path = BACKEND_ROOT / "scripts" / "fix" / "fix_note_columns_coverage.py"
        src = path.read_text(encoding="utf-8")
        assert "guidance" in src, "扫描面为空 —— 补列脚本未接 guidance 通道"

        body = _strip_py_comments(src)
        assert "plan_table_guidance" in body, (
            "补列脚本缺 plan_table_guidance —— guidance 通道未接线（注入即死代码）"
        )
        assert "GUIDANCE_RULES" in body, "补列脚本未引用 guidance 真源路径"
        # 禁止：拿章节标题/表名当 guidance 兜底
        for pat in (
            r"guidance\s*=\s*.*section_title",
            r"guidance\s*=\s*.*table_name",
            r"guidance\s*=\s*f?[\"']本表编制口径",
        ):
            assert not re.search(pat, body), (
                f"补 guidance 出现自造口径形态（{pat}）—— R3.2 只许源模板/条款/勾稽三种来源"
            )
