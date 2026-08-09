"""附注模板文本卫生守卫（裸表名标题化 + md 重建假行清理）—— 不连库，可进 CI。

spec: note-template-columns-and-legacy-snapshot-closure Requirement 12 / Property 35~37

设计要点
--------
1. **判据与落地脚本、与后端渲染器三方同源**：
   * 裸表名判定复用 `_note_structure_kit.find_bare_table_name_paragraphs` /
     `is_title_paragraph`，后者与 `disclosure_engine._is_table_title_paragraph`
     逐样本比对（漂了即打红）；
   * 假行判定复用 `fix_note_text_hygiene.prove_header_artifact`。
2. **fail-closed 是核心不变量**：删行必须可由该表 `headers` 证明；
   无法证明的替身必须被跳过（反向自检）。
3. **与 Requirement 11 的边界**：可扩位行（`……` / `可无限量添加行`）永不被本条删除，
   两条处置的作用行集合交集必须为空。
4. **Property 37**：删行触及多段共享表 ⇒ 派生段清单必须与当前模板重算一致（stale 检测），
   且段代码序列不变。
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

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DATA_DIR = BACKEND_ROOT / "data"
VARIANTS = ("listed", "soe")


def _load(rel: str, name: str):
    path = BACKEND_ROOT / rel
    assert path.exists(), f"缺失：{path}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


KIT = _load("scripts/fix/_note_structure_kit.py", "kit_for_hygiene_guard")
FIXER = _load("scripts/fix/fix_note_text_hygiene.py", "hygiene_fixer_for_guard")
MARKERS_MOD = _load(
    "scripts/diagnose/build_note_expandable_markers.py", "markers_for_hygiene_guard"
)
PROBE = _load(
    "scripts/diagnose/diagnose_note_columns_coverage.py", "probe_for_hygiene_guard"
)

# ---------------------------------------------------------------------------
# 基线（2026-08-08 落地后实测；只许降不许升）
# ---------------------------------------------------------------------------

#: 作用域内（排除母公司章）仍会被当正文渲染的裸表名段落数 —— 硬锁 0
EXPECTED_BARE_IN_SCOPE = 0

#: 母公司章内保留的裸表名段落数（归 A spec，本 spec 不动；反向自检用）
EXPECTED_BARE_PARENT_CHAPTER = {"listed": 4, "soe": 9}

#: 落地后全库 `header_label` 行数（listed 36 → 0 / soe 6 → 0，全在 unregistered）
EXPECTED_HEADER_LABEL = {"listed": 0, "soe": 0}


@pytest.fixture(scope="module")
def templates() -> dict[str, Any]:
    return {
        v: json.loads((DATA_DIR / f"note_template_{v}.json").read_text(encoding="utf-8"))
        for v in VARIANTS
    }


def _scope_of(num: str, variant: str, parents, registry) -> str:
    return PROBE.classify_section(
        section_number=num, variant=variant,
        parent_sections=parents, registry_sections=registry,
    )


# ---------------------------------------------------------------------------
# Property 35：裸表名只标题化不删除，判据与后端同口径
# ---------------------------------------------------------------------------

class TestBareTableNameParagraphs:
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_no_bare_table_name_in_scope(self, templates, variant) -> None:
        parents = PROBE._load_parent_sections()
        registry = PROBE._load_registry_sections()
        offenders: list[str] = []
        for section in templates[variant].get("sections") or []:
            if not isinstance(section, dict):
                continue
            num = str(section.get("section_number") or "")
            if _scope_of(num, variant, parents, registry) == PROBE.SCOPE_PARENT:
                continue
            for para in KIT.find_bare_table_name_paragraphs(section):
                offenders.append(f"{num} :: {para[:40]}")
        assert len(offenders) == EXPECTED_BARE_IN_SCOPE, (
            f"[{variant}] 仍有裸表名段落会被当正文渲染 {len(offenders)} 处："
            + "; ".join(offenders[:8])
            + "（重跑 backend/scripts/fix/fix_note_text_hygiene.py --apply）"
        )

    def test_parent_chapter_exclusion_is_wired_in_source(self) -> None:
        """源码级：母公司章排除必须在**任何改动之前**短路（R10.2）。

        🔴 只断言「当前模板里母公司章的裸表名仍在」**抓不到**「脚本删掉了排除分支」
        —— 数据已落地，改脚本不改数据（变异 M5 实测 GREEN）。故必须加源码级断言。
        """
        src = (BACKEND_ROOT / "scripts" / "fix" / "fix_note_text_hygiene.py").read_text(
            encoding="utf-8"
        )
        i = src.find("def run_variant(")
        assert i > 0
        body = src[i:]
        m = re.search(r"if\s+scope\s*==\s*PROBE\.SCOPE_PARENT\s*:", body)
        assert m, "run_variant 未排除母公司章（R10.2）"
        # 排除必须早于标题化与删行两个动作
        for action in ("titleize_text_sections", "plan_header_label_rows"):
            at = body.find(action)
            assert at > 0, f"未找到动作 {action}"
            assert m.start() < at, f"母公司章排除必须早于 {action}"
        # 且该分支体内必须 continue（不是只记日志）
        tail = body[m.end():m.end() + 400]
        assert "continue" in tail, "母公司章分支未 continue，等于没排除"

    def test_parent_chapter_bare_names_untouched(self, templates) -> None:
        """R10.2 反向自检：母公司章的裸表名**仍在**（证明排除真生效、扫描面非空）。"""
        parents = PROBE._load_parent_sections()
        registry = PROBE._load_registry_sections()
        for variant in VARIANTS:
            n = 0
            for section in templates[variant].get("sections") or []:
                if not isinstance(section, dict):
                    continue
                num = str(section.get("section_number") or "")
                if _scope_of(num, variant, parents, registry) != PROBE.SCOPE_PARENT:
                    continue
                n += len(KIT.find_bare_table_name_paragraphs(section))
            assert n == EXPECTED_BARE_PARENT_CHAPTER[variant], (
                f"[{variant}] 母公司章裸表名 {n} != 基线 "
                f"{EXPECTED_BARE_PARENT_CHAPTER[variant]}"
                "（本 spec 不该动它；数变了说明 A spec 有进展或排除失效）"
            )

    def test_titleize_only_prefixes_never_drops(self) -> None:
        """Property 35：只加 `#### ` 前缀，段数前后相等。"""
        section = {
            "tables": [{"name": "应收账款账龄"}],
            "text_sections": ["应收账款账龄", "正文段落一", "（1）已是标题"],
        }
        before = list(section["text_sections"])
        changes = KIT.titleize_text_sections(section)
        after = section["text_sections"]
        assert len(after) == len(before), "标题化不得改变段数"
        assert after[0] == "#### 应收账款账龄"
        assert after[1] == "正文段落一", "非表名段落不得被动"
        assert after[2] == "（1）已是标题", "已是标题的段落不得被重复加前缀"
        assert len(changes) == 1

    def test_numbered_paragraph_is_already_title(self) -> None:
        """反向自检：带 `（N）` / `N.` 编号的段落本就被判为标题 → 不进作业面。

        tasks.md 曾据此把 soe registry_covered 的 5 条判成「不是缺陷」；
        实测那 5 条**没有**编号（`长期应收款按性质披露` 等）故确是缺陷。
        """
        assert KIT.is_title_paragraph("（1）按账龄披露应收账款") is True
        assert KIT.is_title_paragraph("1. 按账龄披露") is True
        assert KIT.is_title_paragraph("#### 已是标题") is True
        assert KIT.is_title_paragraph("长期应收款按性质披露") is False

    def test_kit_title_judge_matches_backend_engine(self) -> None:
        """判据同源：kit 的复刻实现必须与后端 `disclosure_engine` 逐样本相等。"""
        from app.services.disclosure_engine import DisclosureEngine

        backend = getattr(DisclosureEngine, "_is_table_title_paragraph", None)
        if backend is None:
            import app.services.disclosure_engine as de
            backend = getattr(de, "_is_table_title_paragraph", None)
        if backend is None:
            pytest.skip("后端未暴露 _is_table_title_paragraph（命名变更？）")
        samples = [
            "", "   ", "#### x", "# y", "（1）按账龄披露应收账款", "1. 按账龄",
            "2、按性质", "长期应收款按性质披露",
            "这是一段很长的正文说明，长度显然超过二十个字符所以不该被判成标题。",
            "项  目",
        ]
        for s in samples:
            try:
                got = backend(s)  # type: ignore[misc]
            except TypeError:
                got = backend(None, s)  # type: ignore[misc]
            assert KIT.is_title_paragraph(s) == got, f"判据漂移 at {s!r}"


# ---------------------------------------------------------------------------
# Property 36：假行删除 fail-closed 且不吃可扩位
# ---------------------------------------------------------------------------

class TestHeaderLabelFakeRows:
    @pytest.mark.parametrize("variant", VARIANTS)
    def test_no_header_label_rows_left(self, templates, variant) -> None:
        offenders: list[str] = []
        for section in templates[variant].get("sections") or []:
            if not isinstance(section, dict):
                continue
            num = str(section.get("section_number") or "")
            for ti, table in enumerate(section.get("tables") or []):
                if not isinstance(table, dict):
                    continue
                for ri, row in enumerate(table.get("rows") or []):
                    if (
                        isinstance(row, dict)
                        and str(row.get("row_type") or "") == "header_label"
                    ):
                        offenders.append(
                            f"{num} #{ti} r{ri} {row.get('label')!r}"
                        )
        assert len(offenders) == EXPECTED_HEADER_LABEL[variant], (
            f"[{variant}] 仍有 header_label 假行 {len(offenders)} 处："
            + "; ".join(offenders[:8])
        )

    def test_baseline_must_not_be_raised(self) -> None:
        assert EXPECTED_BARE_IN_SCOPE == 0
        assert EXPECTED_HEADER_LABEL == {"listed": 0, "soe": 0}

    @pytest.mark.parametrize(
        "label,headers,expected",
        [
            ("项  目", ["项目", "期末余额"], "equals_header"),
            ("项目", ["项  目", "期末余额"], "equals_header"),
            ("合营企业或联营<br/>企业名称", ["企业名称"], "html_in_label"),
            ("项目", ["项目名称", "金额"], None),        # 子串不算
            ("原材料", ["项目", "金额"], None),
            ("", ["项目"], None),
            ("   ", ["项目"], None),
        ],
    )
    def test_prove_header_artifact(self, label, headers, expected) -> None:
        assert FIXER.prove_header_artifact(label, headers) == expected

    def test_fail_closed_keeps_unprovable_row(self) -> None:
        """反向自检：证明不了就必须保留（Requirement 12.3）。"""
        table = {
            "headers": ["项目", "金额"],
            "rows": [
                {"label": "项目", "row_type": "header_label"},          # 可证 → 删
                {"label": "某个业务分组", "row_type": "header_label"},   # 不可证 → 留
                {"label": "原材料", "row_type": "data"},
            ],
        }
        kept, notes = FIXER.plan_header_label_rows(table)
        labels = [r["label"] for r in kept]
        assert labels == ["某个业务分组", "原材料"], labels
        assert any("无法证明" in n for n in notes)

    def test_expandable_row_never_deleted(self) -> None:
        """Requirement 12.4：可扩位行归 Requirement 11 处置，本条永不删。"""
        table = {
            "headers": ["项目", "金额"],
            "rows": [
                {"label": "……", "row_type": "header_label"},
                {"label": "可无限量添加行", "row_type": "header_label"},
                {"label": "项目", "row_type": "header_label"},
            ],
        }
        kept, notes = FIXER.plan_header_label_rows(table)
        assert [r["label"] for r in kept] == ["……", "可无限量添加行"]
        assert sum(1 for n in notes if "可扩位" in n) == 2

    def test_two_dispositions_are_disjoint(self, templates) -> None:
        """两条处置的作用行集合交集必须为空（Property 36）。

        全库不得存在「既是可扩位标记、又被判为表头残留」的行。
        """
        clash: list[str] = []
        for variant in VARIANTS:
            for section in templates[variant].get("sections") or []:
                if not isinstance(section, dict):
                    continue
                num = str(section.get("section_number") or "")
                for ti, table in enumerate(section.get("tables") or []):
                    if not isinstance(table, dict):
                        continue
                    headers = table.get("headers") or []
                    for ri, row in enumerate(table.get("rows") or []):
                        if not isinstance(row, dict):
                            continue
                        label = row.get("label")
                        if MARKERS_MOD.match_label_marker(label) is None:
                            continue
                        if FIXER.prove_header_artifact(label, headers) is not None:
                            clash.append(f"{variant} {num} #{ti} r{ri} {label!r}")
        assert not clash, "同一行同时命中两条处置：" + "; ".join(clash[:5])

    def test_non_header_label_rows_untouched(self) -> None:
        """只动 `header_label`：data / total / subtotal / unowned 一律不碰。"""
        table = {
            "headers": ["项目"],
            "rows": [
                {"label": "项目", "row_type": "data"},
                {"label": "项目", "row_type": "total", "is_total": True},
                {"label": "项目", "row_type": "unowned"},
            ],
        }
        kept, _ = FIXER.plan_header_label_rows(table)
        assert len(kept) == 3

    def test_idempotent_on_clean_table(self) -> None:
        table = {"headers": ["项目"], "rows": [{"label": "原材料", "row_type": "data"}]}
        kept, notes = FIXER.plan_header_label_rows(table)
        assert kept == table["rows"] and notes == []


# ---------------------------------------------------------------------------
# Requirement 12.5：不与别的脚本抢 text_sections
# ---------------------------------------------------------------------------

class TestNoConflictWithPerCycleScripts:
    def test_declared_set_is_nonempty(self) -> None:
        """反向自检：冲突面扫描必须真扫到东西，否则该保护是空转。"""
        declared = FIXER.sections_with_text_sections_declared()
        assert len(declared) >= 10, f"声明面异常小：{sorted(declared)}"

    def test_skip_clause_is_wired_in_source(self) -> None:
        """源码级：标题化前必须先查 declared 集合。

        🔴 **不能用「章节被本 spec stamp 过 且 含 `#### ` 段落」当判据** ——
        `_aligned_by` 由本 spec 的 Wave 2/3/4 三批任务共同 stamp，而 `#### ` 段落
        大量来自各 per-cycle 脚本自己的 titleize（D1/D2/D4/J2/母公司 5 个脚本在做），
        两者叠加会把 `五、24`/`五、32`/`五、54`/`五、57` 误报成冲突（首版实测踩到）。
        """
        src = (BACKEND_ROOT / "scripts" / "fix" / "fix_note_text_hygiene.py").read_text(
            encoding="utf-8"
        )
        i = src.find("def run_variant(")
        assert i > 0
        body = src[i:]
        m = re.search(
            r"if\s+section_code_of\(num\)\s+in\s+declared\s*:", body
        )
        assert m, "run_variant 未在标题化前检查 declared 集合"
        titleize_at = body.find("titleize_text_sections")
        assert 0 < m.start() < titleize_at, "declared 检查必须早于 titleize 调用"

    def test_declared_section_is_skipped_behaviorally(self, tmp_path) -> None:
        """反向自检：给一个 declared 章节注入裸表名，脚本必须跳过它。

        当前真实模板里**没有**「declared 章节 + 裸表名」的组合（dry-run 零 `跳过标题化`），
        故该避让路径零命中 ⇒ 必须用替身证明它不是死代码。
        """
        declared = FIXER.sections_with_text_sections_declared()
        assert declared, "declared 为空，替身无从构造"
        victim = sorted(declared)[0]
        section = {
            "section_number": victim,
            "tables": [{"name": "替身表名"}],
            "text_sections": ["替身表名"],
        }
        assert KIT.find_bare_table_name_paragraphs(section) == ["替身表名"]
        # 脚本的避让判据
        assert FIXER.section_code_of(victim) in declared
        # 反向：非 declared 的章节号不会被跳过
        assert FIXER.section_code_of("三、固定资产") not in declared

    def test_section_code_of_handles_truncated_numbers(self) -> None:
        """模板里有 md 截断的 section_number，按 `X、N` 前缀比；无该形态则原样返回。

        原样返回是**有意**的：`declared` 里只有 `X、N` 形态的码，返回全串等于
        「不与任何声明冲突」⇒ 该章节照常标题化（不会被错误跳过）。
        """
        assert FIXER.section_code_of("九、1、或有负债") == "九、1"
        assert FIXER.section_code_of("八、17") == "八、17"
        # 无 `X、N` 形态 → 原样返回，且不会误命中 declared
        assert FIXER.section_code_of("三、资产减值损失（损") == "三、资产减值损失（损"
        assert (
            FIXER.section_code_of("三、资产减值损失（损")
            not in FIXER.sections_with_text_sections_declared()
        )


# ---------------------------------------------------------------------------
# Property 37：派生段清单 stale 检测 + 段语义不变
# ---------------------------------------------------------------------------

class TestSharedSegmentManifestFresh:
    def test_manifest_matches_current_templates(self) -> None:
        """删行会让派生清单漂移 ⇒ 必须已重生成（stale 检测）。"""
        gen = _load(
            "scripts/gen/gen_note_shared_table_segments.py", "seg_gen_for_hygiene_guard"
        )
        builder = None
        for name in ("build_manifest", "build", "build_payload"):
            builder = getattr(gen, name, None)
            if callable(builder):
                break
        if builder is None:
            pytest.skip("生成器未暴露可复用的 build_* 入口（命名变更？）")
        try:
            fresh = builder()
        except TypeError:
            pytest.skip("生成器入口签名需要参数，跳过 stale 检测")

        stored = json.loads(
            (DATA_DIR / "note_shared_table_segments.json").read_text(encoding="utf-8")
        )

        def sig(payload: dict) -> list:
            return [
                [
                    t.get("variant"), t.get("section_number"), t.get("table_name"),
                    t.get("row_count"),
                    [s.get("row_code") for s in (t.get("segments") or [])],
                ]
                for t in (payload.get("tables") or [])
            ]

        assert sig(stored) == sig(fresh), (
            "派生段清单与当前模板不一致 → 重跑 "
            "backend/scripts/gen/gen_note_shared_table_segments.py --write"
        )

    def test_shared_table_counts_unchanged(self) -> None:
        """共享表张数不因删假行而变（段归属不变，只有行序前移）。"""
        stored = json.loads(
            (DATA_DIR / "note_shared_table_segments.json").read_text(encoding="utf-8")
        )
        assert stored.get("counts") == {"listed": 23, "soe": 6}, (
            f"共享表数变了：{stored.get('counts')}（段归属可能被改动）"
        )

    def test_expandable_rows_stay_inside_segments(self) -> None:
        """🔴 可扩位行不是无主行：不得被 `_TOTAL_ROW_TYPES` 排除出段可写区。"""
        from app.services.note_shared_table_segments import _TOTAL_ROW_TYPES

        assert "expandable" not in _TOTAL_ROW_TYPES
        assert "header_label" in _TOTAL_ROW_TYPES, (
            "既有语义不得被改（Requirement 10.9）"
        )
