# -*- coding: utf-8 -*-
r"""I 循环规划期登记的缺陷 —— **已修复，且必须保持修复**。

spec: `i1-i3-disclosure-positional-identity-and-classification-source`（Task 3~9）
      `i-cycle-sync-foundation-and-first-canary`（Task 21）

═══ 为什么从 Task 51 搬到这里（与 H 循环 `test_h_cycle_registered_defects_fixed.py` 同款）═══

`test_task51_i_cycle_migration.py` 是**规划期**快照，判据是「实测命中 == 登记」——
缺陷**还在**才绿。2026-09-27 那轮 lane 1 的修复正是被它锁死才回滚的。本轮修了两条：

  · **BP-6** I1/I3 披露层 8 个位置化行身份 site（族 A′ 1 / 族 B 5 / 族 D 2）；
  · **BP-10** I6 宿主首处挂 AC 1.4 提示（I 循环此前 6 宿主 0 挂载）。

判据于是**翻面**：slice 登记保持原值（append-only，那是修复前的历史事实，改成 0 让判据
自洽同样打红）+ 现算为零 + 修复手法真在源码里。运行期语义（删中间行 / 同毫秒批量 /
grandfather）由 vitest `i3DisclosureRowIdentity.spec.ts` 真跑 composable 覆盖——这里只做
静态防回退，**不**拿源码文本冒充运行期证据。

🔴 扫描口径共用 Task 51 的实现，不另抄一份（两个扫描器各自漂移正是要防的东西）。
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.workpaper_sync.test_task51_i_cycle_migration import (
    COMPOSABLES,
    MANIFEST_SLICE_PATH,
    NOTICE_COMPONENT_NAME,
    ROOT,
    WP_COMPONENTS,
    _POSITIONAL_IDENTITY_TOKEN,
    _gate_anchor,
    _i_cycle_files,
    _load,
    _positional_identity_hits,
    _resolve_repo,
    _strip_ts_comments,
    _toolbar_block,
    _value_expr_after_key,
    _vue_template,
)

I3_DISCLOSURE = COMPOSABLES / "useI3Disclosure.ts"
I1_ENHANCE = COMPOSABLES / "i1DisclosureEnhance.ts"
I3_RECOVERABLE_VUE = WP_COMPONENTS / "i3" / "impairment" / "I3TabRecoverableTest.vue"
RUNTIME_SPEC = COMPOSABLES / "__tests__" / "i3DisclosureRowIdentity.spec.ts"
NOTICE_TS = WP_COMPONENTS / "sync" / "workpaperEntrySyncNotice.ts"

I6_ENTRY = "xlsx/gt-i6-research-development-expense"

#: 🔴 族 D 形态：`${added}` 计数器（slice 的 token 没有这支 ⇒ 只用 slice 口径会漏 site #7/#8）。
_FAMILY_D_TOKEN = re.compile(r"\$\{\s*added\s*\}")


def _extended_hits(files: list[pathlib.Path]) -> list[tuple[str, int, str]]:
    """slice 口径 ∪ 族 D：`(相对路径, 行号, 表达式)`。"""
    out = [(rel, no, expr) for rel, no, _k, expr in _positional_identity_hits(files)]
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        for no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("*", "//")):
                continue
            expr = _value_expr_after_key(line, "rowId")
            if expr is not None and _FAMILY_D_TOKEN.search(expr):
                out.append((rel, no, expr.strip()))
    return out


@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def i_files() -> list[pathlib.Path]:
    return _i_cycle_files()


class TestBp6PositionalIdentityStaysFixed:
    """**Validates: ID-P1 / ID-P2 / ID-P4 / ID-P19**"""

    #: 修复前 8 个 site 的原始表达式（design ID-1 表；变异样本：扫描器必须全部命中）。
    _OLD_FORMS = (
        "`cgu-${i}`,",
        "`bv-${r.rowId || i}`,",
        "`imp-${r.rowId || i}`,",
        "`perf-${r.rowId || i}`,",
        "String(r.rowId || `cgu-${idx}`),",
        "`tc-i18-${r.rowId || i}`,",
        "`perf-${Date.now()}-${added}`,",
        "`ap-${Date.now()}-${added}`,",
    )
    #: 修复后的形态（变异样本：扫描器必须全部**不**命中，否则判据把修复报成缺陷）。
    _NEW_FORMS = (
        "reuseCgu(name, 'cgu'),",
        "r.rowId ? `bv-${r.rowId}` : reuseBv(investee, 'bv'),",
        "r.rowId ? `perf-${r.rowId}` : _stableRowId('perf'),",
        "String(r.rowId || legacyCguRowId(cguName, occurrence)),",
        "_stableRowId('ap'),",
    )

    def test_slice_registration_keeps_its_pre_fix_values(self, manifest_slice: dict) -> None:
        """slice 是修复前快照：6 / 1 / 4 原值保留（有人改成 0 想让判据自洽 ⇒ 打红）。"""
        inv = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        assert inv["total_hits"] == 6
        assert inv["family_a_pure_index_persisted"]["count"] == 1
        assert inv["family_b_index_as_fallback"]["count"] == 4
        assert inv["family_c_display_ordinal_must_not_be_flagged"]["count"] == 20

    def test_scanner_detects_every_old_form_and_none_of_the_new(self) -> None:
        """🔴 双向变异：旧 8 形态全命中、新形态全不命中 —— 否则下面的「现算为零」不可信。"""
        def flagged(expr: str) -> bool:
            return bool(_POSITIONAL_IDENTITY_TOKEN.search(expr) or _FAMILY_D_TOKEN.search(expr))

        missed = [e for e in self._OLD_FORMS if not flagged(e)]
        assert not missed, f"扫描器漏判修复前形态：{missed}"
        false_pos = [e for e in self._NEW_FORMS if flagged(e)]
        assert not false_pos, f"扫描器把修复后形态误报为位置化：{false_pos}"
        # 只用 slice 口径（不含 `${added}`）必漏族 D 两处 —— 这正是扩口径的理由
        slice_only_missed = [e for e in self._OLD_FORMS if not _POSITIONAL_IDENTITY_TOKEN.search(e)]
        assert len(slice_only_missed) == 2 and all("added" in e for e in slice_only_missed)

    def test_scan_scope_includes_the_vue_site(self, i_files: list[pathlib.Path]) -> None:
        """🔴 ID-P2：site #5 在 `.vue` 里；分母限定 composables/ 会漏它。"""
        assert I3_RECOVERABLE_VUE in i_files
        assert any(p.suffix == ".vue" and COMPOSABLES not in p.parents for p in i_files)

    def test_no_positional_identity_left_in_i_cycle(self, i_files: list[pathlib.Path]) -> None:
        """① 现算为零（slice 口径 ∪ 族 D），新引入任何一处即打红。"""
        hits = _extended_hits(i_files)
        assert hits == [], "I 循环又出现位置化行身份：\n" + "\n".join(
            f"  {rel}#L{no}: {expr[:90]}" for rel, no, expr in hits
        )

    def test_fix_method_is_really_in_source(self) -> None:
        """② 修复手法：同文件生成器 + 按业务值复用（grandfather）；生成器签名无下标参数。"""
        body = _strip_ts_comments(I3_DISCLOSURE.read_text(encoding="utf-8"))
        sig = re.search(r"export function _stableRowId\s*\(([^)]*)\)", body)
        assert sig, "useI3Disclosure.ts 缺 _stableRowId"
        assert sig.group(1).strip() == "prefix: string", f"生成器签名变了：{sig.group(1)!r}"
        assert re.search(r"Date\.now\(\)\.toString\(36\)", body) and "Math.random()" in body
        assert re.search(r"export function _rowIdReuser", body), "缺按值复用器 ⇒ grandfather 没了"
        assert re.search(
            r"LEGACY_POSITIONAL_ROW_ID_RE\s*=\s*/\^\(cgu\|bv\|imp\|perf\|ap\|tc-i18\)-\\d\+\$/", body
        ), "旧格式正则与 design ID-1 不符"
        # 复用池必须在覆盖式重建**之前**取（之后取到的是新行，复用即失效）
        pull = body[body.index("function pullFromDetailRows"):]
        assert pull.index("_rowIdReuser(bookValueRows.value") < pull.index("bookValueRows.value = detail.map")
        assert pull.index("_rowIdReuser(sectionRows.value.cgu_allocation") < pull.index(
            "sectionRows.value.cgu_allocation = "
        )
        vue = _strip_ts_comments(I3_RECOVERABLE_VUE.read_text(encoding="utf-8"))
        vsig = re.search(r"function legacyCguRowId\s*\(([^)]*)\)", vue)
        assert vsig and not re.search(r"\b(i|idx|index)\s*:", vsig.group(1)), (
            "legacyCguRowId 缺失或签名出现下标参数"
        )

    def test_family_a_persist_chain_unchanged(self) -> None:
        """③ 唯一确证真落库的 site：修复不得顺手改落库键（改了 = 历史数据错位）。"""
        body = I3_DISCLOSURE.read_text(encoding="utf-8")
        assert "_persistSection('cgu_allocation')" in body
        assert re.search(r"options\?\.onSave\?\.\(\s*`\$\{prefix\}-\$\{sectionKey\}-rows`", body)
        for const, value in (("ITEM_PREFIX_LISTED", "I3-disc-listed"), ("ITEM_PREFIX_SOE", "I3-disc-soe")):
            assert re.search(r"\b" + const + r"\s*=\s*['\"]" + re.escape(value) + r"['\"]", body)

    def test_runtime_judgements_exist_and_cover_the_combo(self) -> None:
        """④ 运行期判据在 vitest：ID-6 删中间行 / 族 D 同毫秒 / grandfather `cgu-3`。"""
        spec = RUNTIME_SPEC.read_text(encoding="utf-8")
        for needle in ("ID-6", "filter((_, k) => k !== 2)", "mockReturnValue", "'cgu-3'", "draftTitleRowsFromI18"):
            assert needle in spec, f"运行期判据缺 {needle!r}"


class TestBp10NoticeFirstMountInI6:
    """**Validates: IF-P15**（foundation Task 21）"""

    def test_slice_still_registers_bp10(self, manifest_slice: dict) -> None:
        assert "BP-10" in {bp["id"] for bp in manifest_slice["blocking_preconditions"]}

    def test_i6_mounts_notice_inside_its_toolbar_with_three_elements(self, manifest_slice: dict) -> None:
        entry = next(e for e in manifest_slice["independent_entries"] if e["entry_id"] == I6_ENTRY)
        source = (WP_COMPONENTS / entry["host"]).read_text(encoding="utf-8")
        code = _strip_ts_comments(source)
        assert re.search(
            r"import\s+GtEntrySyncCapabilityNotice\s+from\s+'\./sync/GtEntrySyncCapabilityNotice\.vue'", code
        ), "I6 宿主未 import 提示组件"
        block = _toolbar_block(_vue_template(source), _gate_anchor(entry))
        assert f'<{NOTICE_COMPONENT_NAME} entry-id="{I6_ENTRY}"' in block, (
            "提示组件不在 i6-header-toolbar 区块内或 entry-id 绑定不对"
        )
        for ref in entry["ui_gate_source_refs"]:
            assert _resolve_repo(ref).exists()

    def test_notice_text_is_not_inlined_in_the_host(self, manifest_slice: dict) -> None:
        """🔴 文案真源唯一：宿主出现任一句提示中文 ⇒ 内联副本，打红。"""
        notice_src = NOTICE_TS.read_text(encoding="utf-8")
        # `\s` 跨行：SUMMARY 的字面量在下一行
        phrases = set(re.findall(r"ENTRY_SYNC_NOTICE_(?:LABEL|SUMMARY)\s*=\s*'([^']+)'", notice_src))
        assert len(phrases) == 2, f"提示文案常量抽取失败（判据防空转）：{phrases}"
        entry = next(e for e in manifest_slice["independent_entries"] if e["entry_id"] == I6_ENTRY)
        host = (WP_COMPONENTS / entry["host"]).read_text(encoding="utf-8")
        inlined = [p for p in phrases if p in host]
        assert not inlined, f"I6 宿主内联了提示文案：{inlined}"

    def test_other_i_hosts_still_unmounted(self, manifest_slice: dict) -> None:
        """其余 5 宿主仍未挂（lane 1 Task 16 断言 I1/I3 notice==0；挂了须同步改那边）。"""
        mounted = []
        for entry in manifest_slice["independent_entries"]:
            if entry["entry_id"] == I6_ENTRY:
                continue
            code = _strip_ts_comments((WP_COMPONENTS / entry["host"]).read_text(encoding="utf-8"))
            if NOTICE_COMPONENT_NAME in code:
                mounted.append(entry["entry_id"])
        assert mounted == [], f"非 I6 宿主挂了提示：{mounted}"


I1_SOE_MODEL = COMPOSABLES / "i1SoeDisclosureModel.ts"
I1_CATEGORY_SCOPE = COMPOSABLES / "i1CategoryScope.ts"
I1_SOE_RUNTIME_SPEC = COMPOSABLES / "__tests__" / "iCycleDynamicRows.spec.ts"


class TestBp7SoeClassificationConvergedToSingleSource:
    """BP-7（lane1 Task 11a，2026-10-01）：I1 国企披露分类**已收敛到单一真源**，且必须保持收敛。

    **Validates: BP-7 / CD-1 单一真源收敛**

    规划期 slice 的 CD-2 把 `I1_SOE_CATEGORIES` 登记为 12 条写死数组 / verdict=MISMATCH
    （软件第 1 带「其中：」、房屋使用权、特许权、采矿权+探矿权分列），与三方一致的权威源
    （`底稿目录!A9:A19` == `附注披露信息（国有企业）!A9:A19` == `note_template_soe.json`，11 条）
    及平台单一真源 `i1CategoryScope.ts#I1_DEFAULT_CATEGORIES` 分叉 —— 属 CD-1 收敛 listed 侧时
    漏掉的 soe 侧遗留。本轮把它收敛为**派生自单一真源**。

    判据翻面（与 BP-6 同款）：slice 保持修复前快照（append-only），这里断言「已收敛」。
    运行期的 11 条有序等值 / 软件第 8 / 无 exploration 由 vitest `iCycleDynamicRows.spec.ts`
    真跑 composable 覆盖——这里只做静态防回退。
    """

    def test_slice_cd2_keeps_its_pre_fix_mismatch_snapshot(self, manifest_slice: dict) -> None:
        """slice 是修复前快照：CD-2 仍是 12 条 / MISMATCH（有人改成已修想让判据自洽 ⇒ 打红）。"""
        decs = manifest_slice["classification_row_model_derivation"]["declarations"]
        cd2 = next(d for d in decs if d["id"] == "CD-2")
        assert cd2["entry_id"] == "xlsx/gt-i1-intangible-assets"
        assert cd2["impl_constant"] == "I1_SOE_CATEGORIES"
        assert cd2["verdict"] == "MISMATCH"
        assert len(cd2["impl_labels"]) == 12

    def test_soe_categories_now_derive_from_the_single_source(self) -> None:
        """① `I1_SOE_CATEGORIES` 不再是写死数组，而是 `.map()` 派生自 `I1_DEFAULT_CATEGORIES`。"""
        body = _strip_ts_comments(I1_SOE_MODEL.read_text(encoding="utf-8"))
        # 从单一真源 import（收敛的硬证据）
        assert re.search(
            r"import\s*\{[^}]*\bI1_DEFAULT_CATEGORIES\b[^}]*\bI1_STANDARD_TO_LEGACY\b[^}]*\}\s*from\s*'\./i1CategoryScope'",
            body,
        ) or re.search(
            r"import\s*\{[^}]*\bI1_STANDARD_TO_LEGACY\b[^}]*\bI1_DEFAULT_CATEGORIES\b[^}]*\}\s*from\s*'\./i1CategoryScope'",
            body,
        ), "i1SoeDisclosureModel 未从单一真源 i1CategoryScope import"
        # 赋值右侧是对单一真源的 .map()，不是数组字面量（变异：改回 `= [` 应打红）
        m = re.search(r"\bI1_SOE_CATEGORIES\b[^=\n]*=\s*(.+)", body)
        assert m, "找不到 I1_SOE_CATEGORIES 声明"
        rhs = m.group(1).lstrip()
        assert rhs.startswith("I1_DEFAULT_CATEGORIES.map("), (
            f"I1_SOE_CATEGORIES 不是派生自单一真源：{rhs[:60]!r}"
        )
        assert not rhs.startswith("["), "I1_SOE_CATEGORIES 退回写死数组字面量 ⇒ 收敛被回退"
        # 收敛后不得再出现旧的分叉**写死标签字面量**（带 label/shortLabel 结构）。
        # 🔴 不裸查「采矿权」等中文：收敛后 label 来自单一真源不在本文件、且
        # mapToI1SoeCategoryKey 的正则含「采矿/探矿/矿权」匹配模式会误命中；只查带结构的旧字面量。
        for stale in ("label: '其中：软件'", "label: '房屋使用权'", "shortLabel: '采矿权'", "shortLabel: '探矿权'"):
            assert stale not in body, f"i1SoeDisclosureModel 残留收敛前写死标签 {stale!r}"

    def test_map_to_soe_key_merges_mining_and_exploration(self) -> None:
        """② 采矿/探矿/矿权统一归 `mining`（矿产权），不再有独立 `exploration` 分支。"""
        body = _strip_ts_comments(I1_SOE_MODEL.read_text(encoding="utf-8"))
        func = body[body.index("function mapToI1SoeCategoryKey"):]
        func = func[: func.index("\n}") + 2]
        assert "return 'exploration'" not in func, "mapToI1SoeCategoryKey 仍把探矿权单列 exploration"
        assert re.search(r"/[^/]*采矿[^/]*探矿[^/]*/\.test\(s\)\s*\)\s*return 'mining'", func) or (
            "采矿" in func and "探矿" in func and "return 'mining'" in func
        ), "采矿/探矿未统一归 mining"

    def test_single_source_still_has_the_eleven_authoritative_categories(self) -> None:
        """③ 单一真源 `i1CategoryScope.ts#I1_DEFAULT_CATEGORIES` 仍是三方一致的 11 条（基准成立）。"""
        body = _strip_ts_comments(I1_CATEGORY_SCOPE.read_text(encoding="utf-8"))
        keys = re.findall(r"key:\s*'([^']+)'", body[body.index("I1_DEFAULT_CATEGORIES"):])
        # 取声明体内前 11 个 key（后面还有 legacy map 的 key，用软件第 8 位 + 条数锚定）
        head = keys[:11]
        assert head == [
            "land_use_right", "housing_use_right", "patent", "patent_free_tech",
            "trademark", "copyright", "franchise", "software", "mining_right",
            "data_resource", "other",
        ], f"单一真源 11 条权威分类漂移：{head}"

    def test_runtime_ordered_equality_is_covered_by_vitest(self) -> None:
        """④ 运行期 11 条有序等值 / 软件第 8 / 无 exploration 由 vitest 覆盖（不拿源码文本冒充）。"""
        spec = I1_SOE_RUNTIME_SPEC.read_text(encoding="utf-8")
        for needle in ("toHaveLength(11)", "'software', 'mining', 'data', 'other'", "exploration"):
            assert needle in spec, f"运行期有序等值判据缺 {needle!r}"
