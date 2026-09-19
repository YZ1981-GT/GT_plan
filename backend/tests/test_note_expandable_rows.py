"""附注可扩位行标记（`row_type: "expandable"`）守卫 —— 不连库，可进 CI。

spec: note-template-columns-and-legacy-snapshot-closure Task 14 / Property 33~34

设计要点
--------
1. **判据与落地脚本同源**：直接 import `build_note_expandable_markers` 的
   `MARKERS` / `LABEL_MARKERS` / `match_label_marker`，与 `fix_note_expandable_rows.py`
   共用同一份判据 —— 词表坏了守卫必红，不会出现「脚本报 0 欠账、守卫也绿」的双假绿。
2. **Property 34 的源真源验证只开 6 个文件**：不做全量 351 模板扫（CI 跑不动），
   改为按 `note_expandable_markers.json` 的逐词 `source_ref` 做
   **openpyxl 直读单元格** 的 stale 检测 —— 源模板一改动即打红。
3. **零可见内容是显式实现不是「照 header_label 那样」**：实测
   `note_word_exporter._render_table` 不读 `row_type`，`header_label` 在 Word 导出
   侧**是可见行** ⇒ `expandable` 的零可见必须自己实现（Property 33 修正说明）。
4. 每组断言配反向自检（构造违规替身必须被抓到），防判据失效变成空转。
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

DATA_DIR = BACKEND_ROOT / "data"
MARKERS_JSON = DATA_DIR / "note_expandable_markers.json"
VARIANTS = ("listed", "soe")
EXPANDABLE = "expandable"


def _load(rel: str, name: str):
    path = BACKEND_ROOT / rel
    assert path.exists(), f"缺失：{path}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


MARKERS_MOD = _load(
    "scripts/diagnose/build_note_expandable_markers.py", "expandable_markers_for_guard"
)
FIXER = _load(
    "scripts/fix/fix_note_expandable_rows.py", "expandable_fixer_for_guard"
)
PROBE = _load(
    "scripts/diagnose/diagnose_note_columns_coverage.py", "note_probe_for_expandable_guard"
)


def _strip_js_comments(src: str) -> str:
    """剥 JS/TS 的 `//` 行注释与 `/* */` 块注释，**保留字符串字面量原文**。

    🔴 必须带字符串状态：裸正则会被 URL 的 `//`（`https://x`）与
    MIME 通配的 `/*`（`accept="image/*"`）骗（memory 已记的平台级坑）。
    不剥注释则「把某项注释掉」这个变异会静默逃逸（M16 实测 GREEN）。
    """
    out: list[str] = []
    i, n = 0, len(src)
    quote: str | None = None
    while i < n:
        ch = src[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = src[i + 1]
            if nxt == "/":
                j = src.find("\n", i)
                i = n if j < 0 else j
                continue
            if nxt == "*":
                j = src.find("*/", i + 2)
                i = n if j < 0 else j + 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)

# ---------------------------------------------------------------------------
# 基线（2026-08-08 实测落地结果；只许升不许降 —— 标记被回退即打红）
# ---------------------------------------------------------------------------

#: 落地后各 variant 的 `expandable` 行数（母公司章 4 行按 R10.2 排除，故 125-4=121）
EXPECTED_EXPANDABLE: dict[str, int] = {"listed": 79, "soe": 42}

#: 母公司章内仍保留 `data` 的可扩位行数（归 A spec，本 spec 不动）
EXPECTED_PARENT_CHAPTER_UNMARKED: int = 4


@pytest.fixture(scope="module")
def markers_facts() -> dict[str, Any]:
    assert MARKERS_JSON.exists(), (
        f"缺少真源 {MARKERS_JSON}；先跑 "
        "backend/scripts/diagnose/build_note_expandable_markers.py"
    )
    return json.loads(MARKERS_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def templates() -> dict[str, Any]:
    return {
        v: json.loads((DATA_DIR / f"note_template_{v}.json").read_text(encoding="utf-8"))
        for v in VARIANTS
    }


def _iter_rows(doc: dict[str, Any]):
    for section in doc.get("sections") or []:
        if not isinstance(section, dict):
            continue
        num = str(section.get("section_number") or "")
        for ti, table in enumerate(section.get("tables") or []):
            if not isinstance(table, dict):
                continue
            rows = table.get("rows") if isinstance(table.get("rows"), list) else []
            for ri, row in enumerate(rows):
                if isinstance(row, dict):
                    yield num, ti, str(table.get("name") or ""), ri, row


# ---------------------------------------------------------------------------
# Property 34：词表非空 + 每词在源真源命中 + 顺序即优先级
# ---------------------------------------------------------------------------

class TestMarkerVocabulary:
    def test_vocabulary_is_single_source(self, markers_facts) -> None:
        """词表真源只有一份：JSON 与模块常量逐项相等。"""
        assert markers_facts["markers"] == list(MARKERS_MOD.MARKERS)
        assert markers_facts["label_markers"] == list(MARKERS_MOD.LABEL_MARKERS)

    def test_six_words_and_nonempty(self, markers_facts) -> None:
        assert len(markers_facts["markers"]) == 6, (
            "源侧词表应为 6 词（Requirement 11.1 实测）；实际 "
            f"{markers_facts['markers']}"
        )
        assert all(str(w).strip() for w in markers_facts["markers"])

    def test_every_word_hits_source(self, markers_facts) -> None:
        """Property 34：每词在源披露 sheet 命中 ≥1 次（命中 0 = 词表失效）。"""
        hits = markers_facts["source_hits"]
        zero = sorted(w for w, n in hits.items() if not n)
        assert not zero, f"以下词在源披露 sheet 零命中（词表失效或源模板变更）：{zero}"
        assert set(hits) == set(markers_facts["markers"])

    def test_scan_surface_is_nonempty(self, markers_facts) -> None:
        """反向自检：扫描面非空，否则「每词命中」是空转。"""
        assert markers_facts["files_scanned"] >= 300
        assert markers_facts["disclosure_sheets_scanned"] >= 100

    @pytest.mark.parametrize("word", list(MARKERS_MOD.MARKERS))
    def test_source_ref_still_holds_in_xlsx(self, markers_facts, word) -> None:
        """stale 检测：逐词 `source_ref` 指向的单元格必须仍含该词（openpyxl 直读）。

        只开 6 个文件，可进 CI；源模板一改动即打红。
        """
        openpyxl = pytest.importorskip("openpyxl")
        ref = (markers_facts.get("source_ref") or {}).get(word)
        assert ref, f"词 {word!r} 缺 source_ref 证据"
        path = BACKEND_ROOT / ref["path"]
        if not path.exists():
            pytest.skip(f"源模板不在本机：{ref['path']}")
        wb = openpyxl.load_workbook(path, data_only=True)
        try:
            assert ref["sheet"] in wb.sheetnames, (
                f"{ref['path']} 已无 sheet {ref['sheet']!r}（源模板变更）"
            )
            val = str(wb[ref["sheet"]][ref["cell"]].value or "")
        finally:
            wb.close()
        assert word in val, (
            f"{ref['path']}!{ref['sheet']}!{ref['cell']} 已不含 {word!r}"
            f"（实为 {val!r}）→ source_ref stale，需重跑 build_note_expandable_markers.py"
        )

    def test_long_forms_precede_short_forms(self) -> None:
        """顺序即优先级：`……` 必须先于 `…`、`......` 先于其子串形态。

        顺序反了 → 146 处 `……` 会被 `…` 抢走，统计与改标全部错位。
        """
        order = list(MARKERS_MOD.MARKERS)
        assert order.index("……") < order.index("…")
        assert order.index("......") < order.index("…")
        # 反向自检：把顺序打乱后 `……` 会被误判成 `…`
        shuffled = ["…", "……"]
        first = next(m for m in shuffled if m in "……")
        assert first == "…", "反向自检失效：短串在前时本应错判"


class TestLabelMarkerJudgement:
    def test_kenaiming_excluded_with_reason(self, markers_facts) -> None:
        """`可改名` 必须被排除出**行标签**判据，且理由已登记。

        它在源模板里只作示例行名后缀（`项目1（可改名）`），标 expandable
        （零可见内容）会把一条合法数据行藏起来。
        """
        assert "可改名" in markers_facts["markers"], "源侧词表应含它（Property 34）"
        assert "可改名" not in markers_facts["label_markers"]
        reason = (markers_facts.get("label_marker_excluded") or {}).get("可改名")
        assert reason and len(reason) >= 30, "排除必须写明理由（≥30 字）"
        assert MARKERS_MOD.match_label_marker("项目1（可改名）") is None

    @pytest.mark.parametrize(
        "label,expected",
        [
            ("……", "……"),
            ("  ……  ", "……"),
            ("1、……", "……"),
            ("2.……", "……"),
            ("…….", "……"),
            ("…", "…"),
            ("......", "......"),          # 🔴 整串都是尾标点，不得被剥空
            ("可无限量添加行", "可无限量添加行"),
            ("项目1（可改名）", None),
            ("其中：预留给关联方的份额", None),  # 「包含」不算，必须恰等于
            ("原材料", None),
            ("", None),
            ("合计", None),
        ],
    )
    def test_match_label_marker_is_exact_not_substring(self, label, expected) -> None:
        assert MARKERS_MOD.match_label_marker(label) == expected

    def test_dotted_form_not_stripped_to_empty(self) -> None:
        """反向自检：一次 rstrip 到底会把 `......` 吃成空串（实测漏标 4 行）。"""
        naive = "......".rstrip("。.、，,；;")
        assert naive == "", "反向自检失效：`......` 本应被一次 rstrip 吃空"
        assert MARKERS_MOD.match_label_marker("......") == "......", (
            "候选式归一必须挡住这个坑"
        )

    def test_candidates_never_empty_string(self) -> None:
        for label in ("......", "…", "……", "1、……", "。"):
            assert "" not in MARKERS_MOD.label_candidates(label)


# ---------------------------------------------------------------------------
# Property 33：取值域恰为六个 + 落地计数 + 母公司章排除
# ---------------------------------------------------------------------------

class TestExpandableLanded:
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_expandable_count_not_regressed(self, templates, variant) -> None:
        n = sum(
            1 for *_x, row in _iter_rows(templates[variant])
            if str(row.get("row_type") or "") == EXPANDABLE
        )
        assert n >= EXPECTED_EXPANDABLE[variant], (
            f"[{variant}] expandable 行 {n} < 基线 {EXPECTED_EXPANDABLE[variant]}"
            "（标记被回退？重跑 backend/scripts/fix/fix_note_expandable_rows.py --apply）"
        )

    def test_baseline_must_not_be_lowered(self) -> None:
        """基线只许升不许降 —— 防「标记被回退就顺手把基线调小」。"""
        assert EXPECTED_EXPANDABLE == {"listed": 79, "soe": 42}
        assert sum(EXPECTED_EXPANDABLE.values()) + EXPECTED_PARENT_CHAPTER_UNMARKED == 125, (
            "121 已标 + 4 母公司章未标 = 125 全部可扩位行（算术闭合）"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_no_expandable_row_left_as_data(self, templates, variant) -> None:
        """作用域内不得再有「label 是可扩位但 row_type 仍是 data」的行。"""
        parents = PROBE._load_parent_sections()
        registry = PROBE._load_registry_sections()
        leftovers: list[str] = []
        for num, ti, name, ri, row in _iter_rows(templates[variant]):
            if MARKERS_MOD.match_label_marker(row.get("label")) is None:
                continue
            scope = PROBE.classify_section(
                section_number=num, variant=variant,
                parent_sections=parents, registry_sections=registry,
            )
            if scope == PROBE.SCOPE_PARENT:
                continue  # R10.2：归 A spec
            if str(row.get("row_type") or "") != EXPANDABLE:
                leftovers.append(f"{num} #{ti} {name[:20]} r{ri} {row.get('label')!r}")
        assert not leftovers, "作用域内仍有未标记的可扩位行：" + "; ".join(leftovers[:10])

    def test_parent_chapter_rows_untouched(self, templates) -> None:
        """R10.2 反向自检：母公司章的可扩位行必须**仍是 data**（证明排除真生效）。"""
        parents = PROBE._load_parent_sections()
        registry = PROBE._load_registry_sections()
        untouched = 0
        for variant in VARIANTS:
            for num, _ti, _n, _ri, row in _iter_rows(templates[variant]):
                if MARKERS_MOD.match_label_marker(row.get("label")) is None:
                    continue
                scope = PROBE.classify_section(
                    section_number=num, variant=variant,
                    parent_sections=parents, registry_sections=registry,
                )
                if scope != PROBE.SCOPE_PARENT:
                    continue
                assert str(row.get("row_type") or "") == "data", (
                    f"母公司章 {variant} {num} 的可扩位行被本 spec 改动了（应归 A spec）"
                )
                untouched += 1
        assert untouched == EXPECTED_PARENT_CHAPTER_UNMARKED, (
            f"母公司章可扩位行数应为 {EXPECTED_PARENT_CHAPTER_UNMARKED}，实为 {untouched}"
            "（扫描面变化 → 排除断言可能已空转）"
        )

    @pytest.mark.parametrize("variant", VARIANTS)
    def test_expandable_rows_carry_no_values(self, templates, variant) -> None:
        """可扩位行是位置标记，不得携带任何数值 —— 否则「不参与合计」会丢数。"""
        offenders: list[str] = []
        for num, ti, name, ri, row in _iter_rows(templates[variant]):
            if str(row.get("row_type") or "") != EXPANDABLE:
                continue
            vals = row.get("values")
            if isinstance(vals, list) and any(
                v not in (None, "", 0) for v in vals
            ):
                offenders.append(f"{num} #{ti} {name[:20]} r{ri} values={vals!r}")
        assert not offenders, "可扩位行携带了数值：" + "; ".join(offenders[:5])


class TestFixerFailClosed:
    """Property 33：只许把 `data` 改标，其余既定语义 fail-closed 不动。"""

    @pytest.mark.parametrize(
        "row_type,expected",
        [
            ("data", "mark"),
            ("", "mark"),
            ("expandable", "noop"),
            ("total", "skip"),
            ("subtotal", "skip"),
            ("header_label", "skip"),
            ("unowned", "skip"),
        ],
    )
    def test_plan_row_verdicts(self, row_type, expected) -> None:
        row: dict[str, Any] = {"label": "……"}
        if row_type:
            row["row_type"] = row_type
        verdict, marker = FIXER.plan_row(row)
        assert verdict == expected
        assert marker == "……"

    def test_non_marker_row_untouched(self) -> None:
        assert FIXER.plan_row({"label": "原材料", "row_type": "data"}) == ("none", None)

    def test_convertible_from_is_narrow(self) -> None:
        """反向自检：可转换来源只允许 data / 缺省，扩大它即打红。"""
        assert set(FIXER.CONVERTIBLE_FROM) == {"data", ""}


# ---------------------------------------------------------------------------
# Property 33：零可见内容（投影器 / Word 导出 / 判空 / 合计）
# ---------------------------------------------------------------------------

class TestZeroVisibleContent:
    def test_projector_skips_expandable(self) -> None:
        from app.services.note_sub_table_projector import project_sub_tables

        td = {
            "_source": "workpaper",
            "sub_table_data": {
                "T": [
                    {"item": "原材料", "amt": 10},
                    {"item": "……", "row_type": EXPANDABLE},
                    {"label": "合计", "amt": 10, "is_total": True},
                ]
            },
            "_sub_table_columns": {
                "T": [
                    {"key": "item", "label": "项目", "is_label": True, "flat": True},
                    {"key": "amt", "label": "金额", "flat": True},
                ]
            },
        }
        tables = project_sub_tables(td)
        assert tables is not None and len(tables) == 1
        labels = [r["label"] for r in tables[0]["rows"]]
        assert labels == ["原材料", "合计"], f"可扩位行未被过滤：{labels}"

    def test_projector_degraded_path_skips_expandable(self) -> None:
        """无列头元数据的降级路径同样要过滤（两条路径都改到了）。"""
        from app.services.note_sub_table_projector import project_sub_tables

        td = {
            "_source": "workpaper",
            "sub_table_data": {
                "T": [
                    {"label": "原材料"},
                    {"label": "……", "row_type": EXPANDABLE},
                ]
            },
        }
        tables = project_sub_tables(td)
        assert tables is not None
        assert tables[0].get("_needs_columns") is True
        assert [r["label"] for r in tables[0]["rows"]] == ["原材料"]

    def test_projector_reverse_selfcheck_keeps_other_row_types(self) -> None:
        """反向自检：只过滤 expandable，`header_label` 等仍按既有行为保留
        （Requirement 10.9：既有五个取值的语义逐字不变）。"""
        from app.services.note_sub_table_projector import project_sub_tables

        td = {
            "_source": "workpaper",
            "sub_table_data": {
                "T": [
                    {"label": "项  目", "row_type": "header_label"},
                    {"label": "原材料"},
                ]
            },
        }
        tables = project_sub_tables(td)
        assert [r["label"] for r in tables[0]["rows"]] == ["项  目", "原材料"], (
            "header_label 的渲染行为不得被本 spec 改动"
        )

    def test_is_zero_visible_row_predicate(self) -> None:
        from app.services.note_sub_table_projector import (
            EXPANDABLE_ROW_TYPE,
            is_zero_visible_row,
        )

        assert EXPANDABLE_ROW_TYPE == EXPANDABLE
        assert is_zero_visible_row({"row_type": EXPANDABLE}) is True
        for rt in ("data", "total", "subtotal", "header_label", "unowned", ""):
            assert is_zero_visible_row({"row_type": rt}) is False
        assert is_zero_visible_row(None) is False

    def test_word_exporter_uses_shared_predicate(self) -> None:
        """Word 导出必须复用投影器的谓词（单一真源），不得自写一份判据。"""
        src = (BACKEND_ROOT / "app" / "services" / "note_word_exporter.py").read_text(
            encoding="utf-8"
        )
        assert "from app.services.note_sub_table_projector import" in src
        assert "is_zero_visible_row" in src
        # 函数体内真的过滤了（不是只 import）
        i = src.find("    def _render_table(")
        j = src.find("    def _table_to_html")
        assert 0 < i < j
        body = src[i:j]
        assert re.search(r"_is_zero_visible_row\(", body), (
            "_render_table 未真正调用零可见谓词 —— header_label/expandable 会被渲染成可见行"
        )

    def test_skip_sets_include_expandable(self) -> None:
        from app.services.note_empty_table_detector import SKIP_ROW_TYPES
        from app.services.note_is_empty_calc import _SKIP_ROW_TYPES as EMPTY_SKIP
        from app.services.note_total_recalc import _SKIP_ROW_TYPES as TOTAL_SKIP

        assert EXPANDABLE in SKIP_ROW_TYPES, "空表检测未跳过可扩位行"
        assert EXPANDABLE in EMPTY_SKIP, "判空未跳过可扩位行"
        assert EXPANDABLE in TOTAL_SKIP, "合计未跳过可扩位行"

    def test_expandable_is_not_unowned(self) -> None:
        """🔴 有意不加进 `note_shared_table_segments._TOTAL_ROW_TYPES`。

        源码注释已明确：「段内的 `……` / `可无限量添加行` **不是**无主行 ——
        那是该段留给 owner 的可扩行」。加进去会把可扩位排除出段可写区，
        owner 一推数据就把它删掉。
        """
        from app.services.note_shared_table_segments import (
            UNOWNED_ROW_TYPE,
            _TOTAL_ROW_TYPES,
        )

        assert EXPANDABLE not in _TOTAL_ROW_TYPES
        assert UNOWNED_ROW_TYPE != EXPANDABLE

    def test_frontend_skip_set_mirrors_backend(self) -> None:
        """跨前后端交叉锁死：前端空表判定的 skip 集合必须含 expandable。"""
        from app.services.note_empty_table_detector import SKIP_ROW_TYPES

        path = (
            REPO_ROOT
            / "audit-platform" / "frontend" / "src" / "views" / "composables"
            / "disclosureEmptyTable.ts"
        )
        assert path.exists(), f"前端文件缺失：{path}"
        raw = path.read_text(encoding="utf-8")
        # 🔴 必须先剥 JS 注释：裸 `re.findall(r"'([^']+)'")` 会把
        # `// 'expandable',` 里的字样也提取到 ⇒ 「注释掉该项」这个变异静默逃逸
        # （2026-08-08 变异 M16 实测 GREEN）。
        src = _strip_js_comments(raw)
        m = re.search(
            r"SKIP_ROW_TYPES:\s*ReadonlySet<string>\s*=\s*new Set\(\[(.*?)\]\)",
            src, re.S,
        )
        assert m, "未能解析前端 SKIP_ROW_TYPES（正则失效？）"
        fe = set(re.findall(r"'([^']+)'", m.group(1)))
        assert fe, "反向自检：前端集合解析为空，断言会空转"
        assert fe == set(SKIP_ROW_TYPES), (
            f"前后端 skip 集合漂移：前端 {sorted(fe)} vs 后端 {sorted(SKIP_ROW_TYPES)}"
        )

    def test_selfcheck_js_comment_stripper(self) -> None:
        """反向自检：注释掉的项必须**不被**提取（否则 M16 变异逃逸）。"""
        good = "const S = new Set([\n  'total',\n  'expandable',\n])\n"
        bad = "const S = new Set([\n  'total',\n  // 'expandable',\n])\n"
        assert set(re.findall(r"'([^']+)'", _strip_js_comments(good))) == {
            "total",
            "expandable",
        }
        assert set(re.findall(r"'([^']+)'", _strip_js_comments(bad))) == {"total"}
        # 块注释同样要剥
        blk = "const S = new Set([\n  'total',\n  /* 'expandable', */\n])\n"
        assert set(re.findall(r"'([^']+)'", _strip_js_comments(blk))) == {"total"}
        # 反向边界：字符串里的 `//`（如 URL）不得被当注释起点
        url = "const u = 'https://x.example/p'\nconst S = new Set(['total'])\n"
        assert "https://x.example/p" in _strip_js_comments(url)


class TestRowTypeEnumRegistration:
    """新增取值必须同步全部枚举登记处（memory 已记：unowned 曾漏两处）。"""

    def test_migrator_enum_registered(self) -> None:
        mod = _load(
            "scripts/migrate_disclosure_notes_to_v2.py", "migrator_for_expandable_guard"
        )
        assert EXPANDABLE in mod.VALID_ROW_TYPES

    def test_template_row_type_test_enum_registered(self) -> None:
        src = (
            BACKEND_ROOT / "tests" / "services" / "test_note_template_row_type.py"
        ).read_text(encoding="utf-8")
        m = re.search(r"VALID_ROW_TYPES\s*=\s*\{(.*?)\n\}", src, re.S)
        assert m, "未能解析 test_note_template_row_type.VALID_ROW_TYPES"
        assert f'"{EXPANDABLE}"' in m.group(1)

    def test_columns_coverage_guard_allows_it(self) -> None:
        src = (BACKEND_ROOT / "tests" / "test_note_columns_coverage.py").read_text(
            encoding="utf-8"
        )
        m = re.search(r"ALLOWED_ROW_TYPES\s*=\s*frozenset\((.*?)\)", src, re.S)
        assert m and EXPANDABLE in m.group(1)

# ===========================================================================
# Property 38: `row_type` 判据单一真源，禁任何写者硬编码 `data`
# ===========================================================================
#
# 缘由（2026-08-08 实测）：`row_type` 有多个写者 —— 本 spec 的
# `fix_note_expandable_rows.py`、共享行构造器 `_note_structure_kit.data_row()`、
# 以及若干 per-cycle 幂等脚本（`fix_note_h_policy_chapter_structure.py` 的
# `ADD_TABLES` 用 `tables[0] != want` **深比较整表**后整表重写 rows）。
# 判据分散 ⇒ 写者互相翻转：soe `四、生物资产` 的 4 行 `……` 被翻回 `data`。
#
# 🔴 判据必须能区分三种 marker 用法，否则会打红 7 个合法脚本：
#   ① 构造行            `{"label": "……", "row_type": "data"}`        → 冲突
#   ② 检测/删除集合      `PLACEHOLDER_ROW_LABELS = {"……", "..."}`      → 合法
#   ③ 打印截断           `print(f"{t[:40] + '…'}")`                    → 合法
# 故判据用 **AST 结构**（dict 的 label/row_type 键值对）而非字符串出现次数。

import ast as _ast  # noqa: E402

_SERVICE_REL = "app/services/note_expandable_markers.py"
_SERVICE_IMPORT = "app.services.note_expandable_markers"

#: service 必须导出的判据符号（存在性断言用）。
_JUDGE_FUNCS = (
    "match_marker",
    "match_label_marker",
    "label_candidates",
    "normalize_label",
    "row_type_for_label",
    "is_zero_visible_row",
)
_JUDGE_CONSTS = ("MARKERS", "LABEL_MARKERS", "LABEL_MARKER_EXCLUDED")

#: 「第二份声明」判据只查这些**专有名**。
#: 🔴 `normalize_label` 有意排除 —— 名字太通用会撞车：
#: `scripts/fix/remap_note_report_row_codes.py` 的同名函数是**报表行名归一**
#: （去 `△▲` / 章节序号 / `其中：` 前缀），与可扩位判据毫无关系。
_EXCLUSIVE_JUDGE_FUNCS = (
    "match_marker",
    "match_label_marker",
    "label_candidates",
    "row_type_for_label",
    "is_zero_visible_row",
)

#: 词表常量的「第二份声明」判据必须**按值形态**判 —— 只有「含 marker 字符串的
#: tuple/list/set/dict 字面量」才算副本。否则会撞车：
#: `mutate_note_text_hygiene_and_expandable.py` 的 `MARKERS = BACKEND / ... .py`
#: 是一个 `Path`（指向生成器文件），纯名字相同。
_MARKER_SAMPLE_STRINGS = ("……", "可无限量添加行", "......", "…", "预留")

#: 允许 re-export 判据符号（不算「第二份声明」）的模块 —— 保住既有 import 路径。
_REEXPORT_ALLOWED = {
    "app/services/note_sub_table_projector.py": (
        "note_word_exporter 从本模块取 EXPANDABLE_ROW_TYPE / is_zero_visible_row，"
        "改 import 路径会波及 17 个消费方；此处只 re-export、不声明第二份判据。"
    ),
    "scripts/diagnose/build_note_expandable_markers.py": (
        "生成器把词表写进 note_expandable_markers.json，需 re-export 供守卫与"
        "既有 `MARKERS_MOD.xxx` 调用形态复用。"
    ),
}


def _service_module():
    import app.services.note_expandable_markers as mod  # noqa: PLC0415

    return mod


def _iter_fix_scripts():
    for path in sorted((BACKEND_ROOT / "scripts" / "fix").glob("*.py")):
        yield path


def _dict_row_conflicts(tree: _ast.AST, is_marker) -> list[tuple[int, str]]:
    """形态 ①：dict 字面量同时含 `"label": <marker>` 与 `"row_type": "data"`。"""
    out: list[tuple[int, str]] = []
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Dict):
            continue
        label_val = None
        row_type_val = None
        for k, v in zip(node.keys, node.values):
            if not (isinstance(k, _ast.Constant) and isinstance(k.value, str)):
                continue
            if k.value == "label" and isinstance(v, _ast.Constant) and isinstance(v.value, str):
                label_val = v.value
            elif k.value == "row_type" and isinstance(v, _ast.Constant):
                row_type_val = v.value
        if label_val is not None and row_type_val == "data" and is_marker(label_val):
            out.append((node.lineno, label_val))
    return out


def _hardcoded_row_helpers(tree: _ast.AST) -> set[str]:
    """形态 ②的前半：本地行构造 helper（形参含 label，return dict 里 row_type 硬编码 data）。"""
    names: set[str] = set()
    for node in _ast.walk(tree):
        if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            continue
        arg_names = {a.arg for a in node.args.args}
        if "label" not in arg_names:
            continue
        for sub in _ast.walk(node):
            if not isinstance(sub, _ast.Dict):
                continue
            for k, v in zip(sub.keys, sub.values):
                if (
                    isinstance(k, _ast.Constant)
                    and k.value == "row_type"
                    and isinstance(v, _ast.Constant)
                    and v.value == "data"
                ):
                    names.add(node.name)
    return names


def _helper_call_conflicts(tree: _ast.AST, helpers: set[str], is_marker) -> list[tuple[int, str, str]]:
    """形态 ②的后半：用 marker 字面量调用了硬编码 helper。"""
    out: list[tuple[int, str, str]] = []
    if not helpers:
        return out
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, _ast.Name) else (fn.attr if isinstance(fn, _ast.Attribute) else "")
        if name not in helpers:
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(arg, _ast.Constant) and isinstance(arg.value, str) and is_marker(arg.value):
                out.append((node.lineno, name, arg.value))
    return out


def scan_row_type_conflicts(source: str, is_marker) -> list[str]:
    """返回该源码里的 `row_type` 双写者冲突（空 = 无冲突）。纯函数，供守卫与自检共用。"""
    tree = _ast.parse(source)
    problems = [
        "L%d dict 字面量硬编码：{'label': %r, 'row_type': 'data'}" % (ln, lab)
        for ln, lab in _dict_row_conflicts(tree, is_marker)
    ]
    helpers = _hardcoded_row_helpers(tree)
    problems += [
        "L%d 用 marker %r 调用硬编码 helper %s()" % (ln, lab, name)
        for ln, name, lab in _helper_call_conflicts(tree, helpers, is_marker)
    ]
    return problems


class TestRowTypeJudgeSingleSource:
    """Property 38：判据单一真源 + 全库禁硬编码。"""

    # ---------- 单一真源 ----------

    def test_service_module_exists_and_exports_judges(self) -> None:
        mod = _service_module()
        for fn in _JUDGE_FUNCS:
            assert callable(getattr(mod, fn, None)), f"service 缺判据函数 {fn}"
        for c in _JUDGE_CONSTS:
            assert getattr(mod, c, None), f"service 缺词表常量 {c}"
        assert mod.EXPANDABLE_ROW_TYPE == EXPANDABLE

    def test_judge_declared_only_once_in_backend(self) -> None:
        """判据函数/词表的**声明**只许出现在 service 层（re-export 需登记豁免）。"""
        offenders = self._scan_second_declarations()
        assert not offenders, (
            "判据必须只在 %s 声明一份（发现第二份声明）：\n  %s\n"
            "re-export 请写 `from %s import ...`，不要重新赋值。"
            % (_SERVICE_REL, "\n  ".join(offenders), _SERVICE_IMPORT)
        )

    @staticmethod
    def _is_marker_vocab_literal(node: _ast.AST) -> bool:
        """该赋值的**值**是否为「含 marker 字符串的容器字面量」（= 词表副本）。"""
        if not isinstance(node, (_ast.Tuple, _ast.List, _ast.Set, _ast.Dict)):
            return False
        items = list(node.keys) if isinstance(node, _ast.Dict) else list(node.elts)
        for it in items:
            if (
                isinstance(it, _ast.Constant)
                and isinstance(it.value, str)
                and it.value in _MARKER_SAMPLE_STRINGS
            ):
                return True
        return False

    @classmethod
    def _scan_second_declarations(cls) -> list[str]:
        offenders: list[str] = []
        for path in BACKEND_ROOT.rglob("*.py"):
            rel = str(path.relative_to(BACKEND_ROOT)).replace("\\", "/")
            if (
                rel == _SERVICE_REL
                or "__pycache__" in rel
                or rel.startswith("tests/")
                or path.name.startswith("_wip_")  # 本会话临时探针，收口时清理
            ):
                continue
            src = path.read_text(encoding="utf-8", errors="replace")
            if not any(w in src for w in (*_EXCLUSIVE_JUDGE_FUNCS, *_JUDGE_CONSTS)):
                continue
            try:
                tree = _ast.parse(src)
            except SyntaxError:
                continue
            for node in tree.body:  # 只看**顶层**声明
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    if node.name in _EXCLUSIVE_JUDGE_FUNCS:
                        offenders.append(f"{rel}:{node.lineno} def {node.name}")
                elif isinstance(node, (_ast.Assign, _ast.AnnAssign)):
                    targets = (
                        node.targets if isinstance(node, _ast.Assign) else [node.target]
                    )
                    for t in targets:
                        if (
                            isinstance(t, _ast.Name)
                            and t.id in _JUDGE_CONSTS
                            and node.value is not None
                            and cls._is_marker_vocab_literal(node.value)
                        ):
                            offenders.append(f"{rel}:{node.lineno} {t.id} = <词表副本>")
        return offenders

    def test_selfcheck_second_declaration_scan_is_not_vacuous(self) -> None:
        """反向自检：把 service 排除条件去掉后，扫描必须能抓到 service 自己。

        否则「offenders 为空」可能是解析失效而非真的没有第二份声明。
        """
        src = (BACKEND_ROOT / _SERVICE_REL).read_text(encoding="utf-8")
        tree = _ast.parse(src)
        found_fn, found_vocab = set(), set()
        for node in tree.body:
            if isinstance(node, _ast.FunctionDef) and node.name in _EXCLUSIVE_JUDGE_FUNCS:
                found_fn.add(node.name)
            if isinstance(node, (_ast.Assign, _ast.AnnAssign)):
                targets = node.targets if isinstance(node, _ast.Assign) else [node.target]
                for t in targets:
                    if (
                        isinstance(t, _ast.Name)
                        and t.id in _JUDGE_CONSTS
                        and node.value is not None
                        and self._is_marker_vocab_literal(node.value)
                    ):
                        found_vocab.add(t.id)
        assert found_fn == set(_EXCLUSIVE_JUDGE_FUNCS), (
            "扫描器抓不到 service 自己的判据函数（解析失效）：缺 %s"
            % sorted(set(_EXCLUSIVE_JUDGE_FUNCS) - found_fn)
        )
        assert {"MARKERS", "LABEL_MARKERS"} <= found_vocab, (
            "词表值形态判据失效（抓不到 service 自己的 MARKERS/LABEL_MARKERS）"
        )

    def test_selfcheck_path_assignment_is_not_flagged_as_vocab(self) -> None:
        """`MARKERS = BACKEND / "x.py"`（Path）不得被判成词表副本 —— 变异脚本就是这形态。"""
        node = _ast.parse('MARKERS = BACKEND / "scripts" / "x.py"\n').body[0]
        assert isinstance(node, _ast.Assign) and node.value is not None
        assert not self._is_marker_vocab_literal(node.value)
        vocab = _ast.parse('MARKERS = ("可无限量添加行", "……")\n').body[0]
        assert isinstance(vocab, _ast.Assign) and vocab.value is not None
        assert self._is_marker_vocab_literal(vocab.value)

    @pytest.mark.parametrize("rel,reason", sorted(_REEXPORT_ALLOWED.items()))
    def test_reexport_allowlist_is_not_stale(self, rel: str, reason: str) -> None:
        """登记的 re-export 模块必须真的 import service（否则条目过期，该移除）。"""
        assert len(reason) >= 20, "豁免必须写明理由"
        src = (BACKEND_ROOT / rel).read_text(encoding="utf-8")
        assert _SERVICE_IMPORT in src, f"{rel} 未 import service，re-export 豁免已过期"

    def test_kit_data_row_is_marker_aware(self) -> None:
        """共享行构造器必须 marker-aware —— 它是最多 per-cycle 脚本的公共入口。"""
        kit = _load("scripts/fix/_note_structure_kit.py", "kit_for_expandable_guard")
        assert kit.data_row("……")["row_type"] == EXPANDABLE
        assert kit.data_row("1、……")["row_type"] == EXPANDABLE
        assert kit.data_row("......")["row_type"] == EXPANDABLE
        assert kit.data_row("可无限量添加行")["row_type"] == EXPANDABLE
        # 反向边界：普通行、空行、示例行名不得被标成零可见内容
        assert kit.data_row("货币资金")["row_type"] == "data"
        assert kit.data_row()["row_type"] == "data"
        assert kit.data_row("项目1（可改名）")["row_type"] == "data"
        # 合计/小计语义不受影响
        assert kit.total_row()["row_type"] == "total"
        assert kit.subtotal_row("小计")["row_type"] == "subtotal"

    def test_kit_source_has_no_hardcoded_data_row_type(self) -> None:
        """源码级：kit 的 `data_row` 不得再硬编码 `"row_type": "data"`。"""
        src = (BACKEND_ROOT / "scripts" / "fix" / "_note_structure_kit.py").read_text(
            encoding="utf-8"
        )
        tree = _ast.parse(src)
        for node in _ast.walk(tree):
            if isinstance(node, _ast.FunctionDef) and node.name == "data_row":
                body = _ast.unparse(node)
                assert "row_type_for_label" in body, "kit.data_row 未走判据真源"
                assert "'data'" not in body and '"data"' not in body, (
                    "kit.data_row 仍硬编码 data"
                )
                return
        pytest.fail("未找到 kit.data_row —— 守卫解析失效（正则/AST 需更新）")

    # ---------- 全库禁硬编码 ----------

    def test_no_fix_script_hardcodes_marker_row_as_data(self) -> None:
        mod = _service_module()
        problems: dict[str, list[str]] = {}
        scanned = 0
        for path in _iter_fix_scripts():
            scanned += 1
            src = path.read_text(encoding="utf-8", errors="replace")
            try:
                hits = scan_row_type_conflicts(src, mod.match_label_marker)
            except SyntaxError:
                continue
            if hits:
                problems[path.name] = hits
        assert scanned >= 40, f"扫描面异常（只扫到 {scanned} 个 fix 脚本）"
        assert not problems, (
            "以下幂等脚本会把可扩位行写回 `data`（与 fix_note_expandable_rows.py 互相翻转）：\n"
            + "\n".join(
                "  %s\n    %s" % (k, "\n    ".join(v)) for k, v in sorted(problems.items())
            )
            + "\n判据真源 = app/services/note_expandable_markers.row_type_for_label()"
        )

    # ---------- 反向自检（判据有效性）----------

    def test_selfcheck_detects_dict_literal_conflict(self) -> None:
        mod = _service_module()
        bad = 'ROWS = [{"label": "……", "row_type": "data"}]\n'
        assert scan_row_type_conflicts(bad, mod.match_label_marker), "形态①未被检出"

    def test_selfcheck_detects_local_helper_conflict(self) -> None:
        mod = _service_module()
        bad = (
            "def _data(label):\n"
            '    return {"label": label, "row_type": "data"}\n'
            'ROWS = [_data("……"), _data("货币资金")]\n'
        )
        assert scan_row_type_conflicts(bad, mod.match_label_marker), "形态②未被检出"

    def test_selfcheck_ignores_detection_set(self) -> None:
        """②检测/删除集合是合法用法 —— 误判它会打红 4 个正确脚本。"""
        mod = _service_module()
        ok = (
            'PLACEHOLDER_ROW_LABELS = {"可无限量添加行", "......", "……", "…"}\n'
            'def check(row):\n'
            '    if str(row.get("label", "")).strip() in PLACEHOLDER_ROW_LABELS:\n'
            '        return "占位行"\n'
            '    return {"label": "货币资金", "row_type": "data"}\n'
        )
        assert scan_row_type_conflicts(ok, mod.match_label_marker) == []

    def test_selfcheck_ignores_print_ellipsis(self) -> None:
        """③打印截断里的 `…` 是合法用法 —— 误判它会打红 3 个正确脚本。"""
        mod = _service_module()
        ok = (
            "def report(t):\n"
            "    print(f\"文本删 {t[:40] + '…'}\")\n"
            '    return {"label": t, "row_type": "data"}\n'
        )
        assert scan_row_type_conflicts(ok, mod.match_label_marker) == []

    def test_selfcheck_marker_aware_helper_is_not_flagged(self) -> None:
        mod = _service_module()
        ok = (
            "from app.services.note_expandable_markers import row_type_for_label\n"
            "def _data(label):\n"
            '    return {"label": label, "row_type": row_type_for_label(label)}\n'
            'ROWS = [_data("……")]\n'
        )
        assert scan_row_type_conflicts(ok, mod.match_label_marker) == []

    # ---------- 冲突消解的验收判据 ----------

    def test_both_writers_report_zero_debt(self) -> None:
        """两个写者的 `--check` 必须同时 0 欠账 —— 这是「互不翻转」的唯一硬判据。"""
        import subprocess  # noqa: PLC0415

        for rel in (
            "scripts/fix/fix_note_expandable_rows.py",
            "scripts/fix/fix_note_h_policy_chapter_structure.py",
        ):
            r = subprocess.run(
                [sys.executable, str(BACKEND_ROOT / rel), "--check"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
            assert r.stdout is not None
            assert r.returncode == 0, (
                "%s --check 未通过（rc=%d）：\n%s\n%s"
                % (rel, r.returncode, (r.stdout or "")[-1500:], (r.stderr or "")[-800:])
            )
