# -*- coding: utf-8 -*-
"""G2 canary 判据 GF-P10~P16：几何 · payload 列 · 键收敛 · 状态 · TB 红线。

spec: `g-cycle-sync-foundation-and-first-canary` · Tasks 11~14 / 17
　　　Requirements 4.1 / 4.2 / 4.3 / 4.4 / 4.5 / 4.6 / 4.9

「另起文件」的理由同 `test_g_foundation_p1_p3_fc_reinterpretation.py` 模块头。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import openpyxl
import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import (  # noqa: E402
    phase5_g2_interest_receivable as G2,
)
from app.services.workpaper_sync.phase5_g2_02_detail import (  # noqa: E402
    FIELD_SPECS_G202,
    FORMULA_TEMPLATES_G202,
    SPEC_G202,
)

FRONTEND = _REPO / "audit-platform" / "frontend" / "src"
COMPOSABLES = FRONTEND / "components" / "workpaper" / "composables"
TPL = _BACKEND / "wp_templates" / "G" / "G2 应收利息.xlsx"


@pytest.fixture(scope="module")
def ws():
    wb = openpyxl.load_workbook(TPL)
    try:
        yield wb["明细表G2-2"]
    finally:
        wb.close()


# ═══════════════════════════════════════════════════════════════════════════
# GF-P10：canary 几何逐格一致
# ═══════════════════════════════════════════════════════════════════════════


class TestGfP10CanaryGeometry:
    """Validates: 4.1"""

    def test_single_level_header_at_row_9(self, ws) -> None:
        """🔴 **单级**表头 R9 —— 变异「声明两级 R9/R10」⇒ 数据区起点错位。

        正向证据：R9 的 A..M 十三格全是标题文本；R10 的 A..M **没有**任何标题，
        且 E10/H10/J10 已经是数据行公式 ⇒ R10 属数据区不属表头。
        """
        assert SPEC_G202.header_row == 9
        assert SPEC_G202.header_group_row is None and SPEC_G202.header_leaf_row is None, (
            "声明了两级表头 ⇒ 与 R10 已是数据行（带 =C10+D10 等公式）的实测矛盾"
        )
        headers = [ws.cell(9, c).value for c in range(1, 14)]
        assert all(isinstance(h, str) and h.strip() for h in headers), headers
        assert headers[0] == "投资种类" and headers[12] == "发函或期后收款情况"
        row10 = [ws.cell(10, c).value for c in range(1, 14)]
        texts = [v for v in row10 if isinstance(v, str) and not v.startswith("=")]
        assert texts == [], f"R10 出现非公式文本 {texts} ⇒ 它可能是第二级表头，须重核"

    def test_data_rows_and_footer(self, ws) -> None:
        assert (SPEC_G202.first_data_row, SPEC_G202.last_data_row) == (10, 15)
        assert SPEC_G202.footer_row == 16
        assert SPEC_G202.footer_marker == "合计"
        assert ws.cell(16, 1).value == "合计", ws.cell(16, 1).value
        # footer 带合计公式 ⇒ carries_total_formula 必须为 True
        assert ws.cell(16, 3).value == "=SUM(C10:C15)"
        assert SPEC_G202.footer_carries_total_formula is True

    def test_formula_columns_and_templates_match_template_verbatim(self, ws) -> None:
        """公式列 E/H/J 与模板逐行逐字一致（6 行 × 3 列 = 18 格）。"""
        assert SPEC_G202.formula_columns == ("E", "H", "J")
        assert set(FORMULA_TEMPLATES_G202) == {"E", "H", "J"}
        for r in range(10, 16):
            for col in ("E", "H", "J"):
                want = FORMULA_TEMPLATES_G202[col].format(r=r)
                got = ws[f"{col}{r}"].value
                assert got == want, f"{col}{r}: 模板 {got!r} != 声明 {want!r}"

    def test_no_other_formula_in_data_rows(self, ws) -> None:
        """数据区**只有** E/H/J 三列有公式 —— 否则声明漏了 formula 列（FC-7）。"""
        extra: list[str] = []
        for r in range(10, 16):
            for c in range(1, 14):
                cell = ws.cell(r, c)
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    if cell.column_letter not in ("E", "H", "J"):
                        extra.append(f"{cell.coordinate}={cell.value}")
        assert not extra, f"数据区出现未声明的公式格: {extra}"

    def test_thirteen_effective_columns_and_uuid_col_is_n(self, ws) -> None:
        """有效内容列 13（A-M）；UUID 列 = N（有效列 +1），且 N/O/P 全空。"""
        assert len(FIELD_SPECS_G202) == 13
        assert [f[1] for f in FIELD_SPECS_G202] == list("ABCDEFGHIJKLM")
        assert SPEC_G202.uuid_col == "N"
        for col in ("N", "O", "P"):
            vals = [
                ws[f"{col}{r}"].value
                for r in range(1, ws.max_row + 1)
                if ws[f"{col}{r}"].value is not None
            ]
            assert vals == [], f"{col} 列非空 {vals} ⇒ 写 UUID 会覆盖内容，须换列"

    def test_cell_protection_agrees_with_formula_columns(self, ws) -> None:
        """模板的单元格锁定与公式列自洽 —— `merge._protection` 的格级判定据此。

        数据行里恰好 E/H/J 三列 locked、其余十列 unlocked；footer 整行 locked。
        """
        for r in range(10, 16):
            locked = {
                ws.cell(r, c).column_letter
                for c in range(1, 14)
                if ws.cell(r, c).protection.locked
            }
            assert locked == {"E", "H", "J"}, f"R{r} locked 列 = {sorted(locked)}"
        footer_unlocked = [
            ws.cell(16, c).column_letter
            for c in range(1, 14)
            if not ws.cell(16, c).protection.locked
        ]
        assert footer_unlocked == [], f"footer R16 有未锁列: {footer_unlocked}"

    def test_header_texts_are_taken_from_template_not_frontend_labels(self, ws) -> None:
        """🔴 FC-5「以模板为权威」：`header_text` 逐字取模板 R9，**不取**前端 label。

        L / M 两列的措辞在模板与前端不同（`预计收取日期`↔`原计收项目期` /
        `发函或期后收款情况`↔`流通或期后收款情况`）。本判据锁住取的是模板那一侧，
        并正向断言「前端确实用了另一套措辞」——否则这条差异记录已失真。
        """
        for key, col, _mode, _vt, _json, header, _grp in FIELD_SPECS_G202:
            idx = openpyxl.utils.column_index_from_string(col)
            assert header == ws.cell(9, idx).value, (
                f"{key}({col}) 的 header_text {header!r} 与模板 R9 的 "
                f"{ws.cell(9, idx).value!r} 不逐字相等"
            )
        tab = (
            FRONTEND
            / "components/workpaper/g2-interest-receivable/G2TabDetail.vue"
        ).read_text(encoding="utf-8")
        assert "原计收项目期" in tab and "流通或期后收款情况" in tab, (
            "前端不再用另一套措辞 ⇒ 模块 docstring 里那张模板/前端对照表已失真，须更新"
        )


# ═══════════════════════════════════════════════════════════════════════════
# GF-P11：G2 payload 判定为 remark_only（**剔占位后**）
# ═══════════════════════════════════════════════════════════════════════════

#: 字面 null / undefined 占位（GC-5：判 mode 前必须剔掉）。
_NULL_PLACEHOLDER = re.compile(
    r"\b(conclusion|remark)\s*:\s*(null|undefined)\b"
)
#: 真写入（键后跟非 null 的值表达式）。
_REAL_WRITE = re.compile(r"\b(conclusion|remark)\s*:\s*(?!null\b|undefined\b)\S")


def _payload_mode_of(src: str) -> str:
    """剔除字面 null 占位后判 payload 列形态（GC-5 的口径）。"""
    stripped = _NULL_PLACEHOLDER.sub("", src)
    cols = {m.group(1) for m in _REAL_WRITE.finditer(stripped)}
    if cols == {"remark"}:
        return "remark_only"
    if cols == {"conclusion"}:
        return "conclusion_only"
    if cols == {"remark", "conclusion"}:
        return "dual_write_remark_and_conclusion"
    return f"unknown({sorted(cols)})"


class TestGfP11PayloadColumnRemarkOnly:
    """Validates: 4.3"""

    def test_provider_declares_remark_only(self) -> None:
        assert G2.PAYLOAD_COLUMN == "remark"
        assert G2.PAYLOAD_COLUMN_MODE == "remark_only"

    def test_contract_html_store_points_at_remark(self) -> None:
        payload = G2.build_contract_payload()
        hs = payload["review"]["html_store"]
        assert hs["payload_column"] == "remark", hs
        assert hs["payload_column_mode"] == "remark_only", hs
        assert hs["null_placeholder_column"] == "conclusion", hs
        assert hs["item_ids"] == ["G2-2-detail-rows"], hs

    def test_mode_is_remark_only_after_stripping_null_placeholder(self) -> None:
        """核心判据：对 `useG2Detail.ts` 现算，**剔占位后**判定为 `remark_only`。"""
        src = (COMPOSABLES / "useG2Detail.ts").read_text(encoding="utf-8")
        assert _payload_mode_of(src) == "remark_only", (
            f"剔占位后判为 {_payload_mode_of(src)}（应为 remark_only）"
        )

    def test_mutation_not_stripping_placeholder_misjudges_as_dual_write(self) -> None:
        """🔴 自省变异：**不剔**占位就会把 G2 判成 `dual_write`。

        这正是 Task 49 首轮守卫翻车的形态 —— 本条把「必须剔」这件事证成，
        而不是靠注释声称。
        """
        src = (COMPOSABLES / "useG2Detail.ts").read_text(encoding="utf-8")
        naive = {m.group(1) for m in re.finditer(r"\b(conclusion|remark)\s*:", src)}
        assert naive == {"conclusion", "remark"}, naive
        assert _payload_mode_of(src) != "dual_write_remark_and_conclusion", (
            "剔占位后仍判 dual_write ⇒ 剔除逻辑没起作用"
        )

    def test_null_placeholder_write_site_really_exists(self) -> None:
        """双向锁①：声称有 null 占位的写入点**真有**（不是凭空放宽判据）。"""
        src = (COMPOSABLES / "useG2Detail.ts").read_text(encoding="utf-8")
        assert re.search(r"conclusion\s*:\s*null", src), (
            "useG2Detail.ts 里找不到 `conclusion: null` ⇒ null 占位子形态的前提不成立"
        )
        assert re.search(r"remark\s*:\s*JSON\.stringify", src), (
            "找不到 `remark: JSON.stringify(...)` ⇒ remark 承载行数组的前提不成立"
        )

    def test_g2_managed_table_write_site_carries_the_placeholder(self) -> None:
        """G2 的**主受管表**写入点逐字是 `{item_id, conclusion: null, remark: JSON.stringify}`。

        定位方式：找 `allResponses.value.set(<主表键常量>, {...})` 这个对象字面量本身，
        **不是**全文搜 `conclusion: null` —— 后者会把「审计说明/结论文本键」的写入也算进来
        （见下一条判据的实测）。
        """
        src = (COMPOSABLES / "useG2Detail.ts").read_text(encoding="utf-8")
        m = re.search(
            r"allResponses\.value\.set\(\s*STORAGE_KEY\s*,\s*\{(?P<body>[^}]*)\}",
            src,
            re.DOTALL,
        )
        assert m, "找不到主受管表的写入点（`allResponses.value.set(STORAGE_KEY, {...})`）"
        body = m.group("body")
        assert re.search(r"conclusion\s*:\s*null", body), body
        assert re.search(r"remark\s*:\s*JSON\.stringify", body), body

    def test_null_placeholder_on_managed_table_is_unique_to_g2(self) -> None:
        """双向锁②：G 循环**其余** entry 的**主受管表**写入点没有 null 占位子形态。

        🔴 口径必须限定在**主受管表**。本轮实测：全文搜会误报 ——
        `useG6MainDetail.ts` 确有两处 `conclusion: null`，但它们在
        **`NOTE_KEY`（审计说明）/ `CONCLUSION_KEY`（审计结论）** 两个**自由文本** store item
        上（L634 / L641），不是主受管表 `G6-2-rows`。把它们算进来会得出
        「slice 的『全 slice 仅 G2 一条』不成立」的**错**结论。
        （G6-main 在 FD-1 里登记为 `dual_write_remark_and_conclusion`，
        指的是它主表的双写，与这两处文本键无关。）
        """
        others = {
            "G1": ("useG1Detail.ts", "G1-2-rows"),
            "G3": ("useG3Detail.ts", "G3-2-detail-rows"),
            "G4-main": ("useG4MainDetail.ts", "G4-2-rows"),
            "G5": ("useG5BalanceDetail.ts", "G5-2-rows"),
            "G6-main": ("useG6MainDetail.ts", "G6-2-rows"),
            "G8": ("useG8Detail.ts", "G8-detail-rows"),
            "G9": ("useG9Detail.ts", "G9-detail-rows"),
            "G10": ("useG10Detail.ts", "G10-detail-rows"),
            "G12": ("useG12HedgeDetail.ts", "G12-hedge-detail-rows"),
            "G13": ("useG13Detail.ts", "G13-detail-rows"),
        }
        scanned = 0
        hits: list[str] = []
        for label, (name, managed_key) in others.items():
            p = COMPOSABLES / name
            if not p.exists():
                continue
            scanned += 1
            src = p.read_text(encoding="utf-8")
            # 主表键的常量名（该键的字面量声明所在行的常量名）
            km = re.search(
                rf"""(?:const|let)\s+(\w+)\s*(?::[^=]+)?=\s*['"]{re.escape(managed_key)}['"]""",
                src,
            )
            key_tokens = [managed_key] + ([km.group(1)] if km else [])
            for token in key_tokens:
                for wm in re.finditer(
                    rf"""\.set\(\s*{re.escape(token)}\s*,\s*\{{(?P<body>[^}}]*)\}}""",
                    src,
                    re.DOTALL,
                ):
                    if re.search(r"conclusion\s*:\s*null", wm.group("body")):
                        hits.append(f"{label}/{name}（主表键 {token}）")
        assert scanned >= 8, f"只扫到 {scanned} 个对照 composable ⇒ 判据分母不足"
        assert not hits, (
            "以下 entry 的**主受管表**写入点也有 `conclusion: null` 占位 ⇒ "
            f"slice 的「全 slice 仅 G2 一条」不成立，FD-1 的登记须扩: {hits}"
        )

    def test_g6_main_text_keys_have_placeholder_but_are_not_the_sub_form(self) -> None:
        """正向锁住上一条的区分依据：G6-main 的两处占位确实在**文本键**上。

        这条存在的意义是防止有人把上一条的口径改回「全文搜」——
        那会复现本轮实测过的假红。
        """
        src = (COMPOSABLES / "useG6MainDetail.ts").read_text(encoding="utf-8")
        assert len(re.findall(r"conclusion\s*:\s*null", src)) >= 2, (
            "G6-main 不再有 `conclusion: null` ⇒ 本区分依据失效，上一条判据的注释须改"
        )
        for token in ("NOTE_KEY", "CONCLUSION_KEY"):
            assert re.search(
                rf"\.set\(\s*{token}\s*,\s*\{{[^}}]*conclusion\s*:\s*null",
                src,
                re.DOTALL,
            ), f"G6-main 的 {token} 写入点没有 conclusion:null ⇒ 区分依据须重核"


# ═══════════════════════════════════════════════════════════════════════════
# GF-P12：`store_item_id` 取真键 + 声明收敛为单一真源
# ═══════════════════════════════════════════════════════════════════════════

STORAGE_CONTRACT = COMPOSABLES / "g2StorageContract.ts"
#: 原本各写一份声明的五个模块（RG-9 实测）。
FORMER_DECLARERS: tuple[str, ...] = (
    "g2CrossHelpers.ts",
    "useG2Detail.ts",
    "useG2DisclosureListed.ts",
    "useG2DisclosureSoe.ts",
    "useG2InterestCalc.ts",
)


class TestGfP12StoreItemIdConverged:
    """Validates: 4.4"""

    def test_store_item_id_is_the_real_key(self) -> None:
        assert SPEC_G202.store_item_id == "G2-2-detail-rows"
        assert G2.STORE_ITEM_ID == "G2-2-detail-rows"
        assert G2.all_store_item_ids() == ("G2-2-detail-rows",)

    def test_mutation_wrong_key_projects_empty(self) -> None:
        """变异 `G2-2-detail-rows → G2-2-rows`（不存在）⇒ 投影恒空。

        真跑引擎：把载荷挂在错键下，`_spec_of_store_item` 直接抛（不静默返回空）——
        比「返回空投影」更强：错键在注册期就被拒。
        """
        with pytest.raises(G2.EntrySelectionError, match="不在 G2 受管清单"):
            G2.build_store_projection(
                "[]", contract=G2.load_contract_from_disk(), store_item_id="G2-2-rows"
            )

    def test_single_source_declaration_and_derived_aliases(self) -> None:
        """🔴 生产源码里 `'G2-2-detail-rows'` 字面量**只有一处**声明。

        范式照 BP-10 的正面样本 `g6CrossHelpers.G6_11_ROWS_KEY = G6_ITEM_IDS.G6_11_ROWS`：
        真源在 `g2StorageContract.G2_ITEM_IDS`，其余五处改派生别名（原常量名保留，零回归）。
        """
        assert STORAGE_CONTRACT.is_file(), "g2StorageContract.ts 不存在"
        literal = re.compile(r"""['"]G2-2-detail-rows['"]""")
        decl_files: list[str] = []
        for p in FRONTEND.rglob("*.ts"):
            rel = p.relative_to(FRONTEND).as_posix()
            if "__tests__" in rel:
                # 🔴 测试文件里保留字面量是**有意**的：测试若也派生同一常量，
                #    改名时测试跟着变、就抓不住改名了。
                continue
            if literal.search(p.read_text(encoding="utf-8")):
                decl_files.append(rel)
        assert decl_files == [
            "components/workpaper/composables/g2StorageContract.ts"
        ], f"生产源码里该字面量出现在多处: {decl_files}"

    def test_former_declarers_now_derive_from_single_source(self) -> None:
        """原五处声明方现在都 import 真源并派生（不是各留一份字面量）。"""
        missing: list[str] = []
        for name in FORMER_DECLARERS:
            src = (COMPOSABLES / name).read_text(encoding="utf-8")
            if "G2_ITEM_IDS" not in src or "g2StorageContract" not in src:
                missing.append(name)
        assert not missing, f"以下模块未接单一真源: {missing}"

    def test_provider_and_frontend_agree_on_the_key(self) -> None:
        """后端 provider 的 `store_item_id` 与前端真源逐字相等（三边锁的一条边）。"""
        src = STORAGE_CONTRACT.read_text(encoding="utf-8")
        m = re.search(r"G2_2_DETAIL_ROWS:\s*'([^']+)'", src)
        assert m, "g2StorageContract 里找不到 G2_2_DETAIL_ROWS"
        assert m.group(1) == G2.STORE_ITEM_ID, (
            f"前端 {m.group(1)!r} != provider {G2.STORE_ITEM_ID!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# GF-P13：发布链状态（migration_state）
# ═══════════════════════════════════════════════════════════════════════════


class TestGfP13MigrationState:
    """Validates: 4.5, 4.6

    🔴 **2026-09-30 状态已翻转，本类判据按原指引改写**。原文断言「现状仍是 legacy」
    并在翻转后以 `pytest.fail` 给出改写指引 —— 那条指引已被执行：
    overlay 裁决 13 条 G 主入口为 bidirectional、`approved_source_digest` 门经复核后
    批准、生成器 `--apply` 重生成 manifest ⇒ G2 现为
    `capability=bidirectional` + `adapter_id=g2.interest_receivable_detail`
    + `migration_state=adapter_registered`。
    判据因此反向钉死：**状态不得退回 legacy**（退回即 manifest 被手改或重生成漂移）。
    """

    def test_manifest_state_is_adapter_registered_and_capability_is_open(self) -> None:
        """按原判据的 `pytest.fail` 指引改写：断言 capability + adapter_id + state 三者一致。"""
        from app.services.workpaper_sync.entry_profile import (  # type: ignore
            load_entry_manifest,
            manifest_entries_by_id,
        )

        load_entry_manifest.cache_clear()
        entry = manifest_entries_by_id(load_entry_manifest())[G2.ENTRY_ID]
        assert entry.get("capability") == "bidirectional", (
            f"G2 capability 退回 {entry.get('capability')!r} ⇒ manifest 被手改或重生成漂移"
        )
        assert entry.get("adapter_id") == "g2.interest_receivable_detail", entry.get("adapter_id")
        assert entry.get("migration_state") == "adapter_registered", entry.get("migration_state")
        # 🔴 三处状态必须一致：manifest 字段 与 provider 的 capability 门不得分叉
        assert G2.manifest_capability_enabled() is True, (
            "manifest 已是 bidirectional 但 provider 的 capability 门仍关 ⇒ 两处状态不一致"
        )

    def test_attach_short_circuits_while_the_capability_gate_is_closed(self) -> None:
        """capability 门关着时 `attach_pilot_adapters` 返回空 —— 不抛、不伪造。

        🔴 **2026-09-30 改写说明**：原判据名为 `…when_supply_missing`，靠「门本来是关的」
        来取得空元组，并传 `session=None`。门放开后它会一路走到读库那一步而抛
        `AttributeError: 'NoneType' object has no attribute 'execute'` —— 那是**正确行为**
        （同族先例见 `test_task42_h1_grouped_dynamic_pilot.py` 的同类改写）。
        要测的属性始终是「门关着时短路」，所以把门显式按关来构造，而不是依赖全局现状。
        """
        import asyncio

        from app.services.workpaper_sync.adapters.registry import (  # type: ignore
            WorkpaperSyncAdapterRegistry,
        )

        # 变异自证：不打桩时门是开的（否则本判据会退化成「门恒关」的恒真式）
        assert G2.manifest_capability_enabled() is True, (
            "未打桩时 capability 门就是关的 ⇒ 本判据无区分力，先查 manifest 状态"
        )

        reg = WorkpaperSyncAdapterRegistry(manifest={"entries": []})
        original = G2.manifest_capability_enabled
        try:
            G2.manifest_capability_enabled = lambda **_kw: False  # type: ignore[assignment]
            got = asyncio.run(G2.attach_pilot_adapters(reg, session=None))
        finally:
            G2.manifest_capability_enabled = original  # type: ignore[assignment]
        assert got == (), f"门关着却返回 {got} ⇒ 伪造了注册"
        assert G2.manifest_capability_enabled() is True, "打桩未复原"

    @pytest.mark.skip(
        reason=(
            "2026-09-30：capability 门已放开 ⇒ 「门开着且供给缺位时返回空」这条属性需要"
            "真 session（传 None 会在读库处抛 AttributeError，那是正确行为而非被测属性）。"
            "待真栈环境（PG + 已落 representation 的 G2 项目）后改为真跑并断言空元组。"
        )
    )
    def test_attach_returns_empty_when_supply_missing_with_gate_open(self) -> None:  # pragma: no cover
        raise NotImplementedError("需真 session，见 skip reason")

    def test_contract_is_delivered_and_matches_source(self) -> None:
        """发布链第①环已交付：磁盘契约与模块现算 payload 一致（双向锁）。"""
        contract = G2.assert_contract_file_matches_source()
        assert contract.contract_id == "g2.interest_receivable_detail"
        assert [s.sheet_key for s in contract.sheets] == ["g202-managed"]
        table = contract.sheets[0].tables[0]
        assert table.table_key == "interest_detail_rows"
        assert len(table.fields) == 13
        assert table.row_identity.json_pointer == "/rows/*/id"
        assert table.formula_mask == ("E10:E15", "H10:H15", "J10:J15")


# ═══════════════════════════════════════════════════════════════════════════
# GF-P16：canary 受管后 sync 路径对 trial_balance 写次数为 0（FC-9 红线）
# ═══════════════════════════════════════════════════════════════════════════

#: 被禁的 TB 写入端点字面量（带路径分隔符 —— 裸词会命中中文提示文案）。
_TB_WRITE_ENDPOINTS: tuple[str, ...] = (
    "trial-balance/writeback",
    "/trial_balance",
)
#: 唯一合法的显式发布门端点。
_PUBLISH_ENDPOINT = "audit-determination/publish-to-tb"


#: sync 路径上被禁的 TB 写入形态（端点 + 发布门函数名）。
_TB_RED_LINE_PATTERNS: tuple[str, ...] = (
    *_TB_WRITE_ENDPOINTS,
    "publishToTb",
    "publish_to_tb",
)


def _strip_python_comments_and_docstrings(src: str) -> str:
    """只留**代码**：剔掉整行 `#` 注释与三引号块。

    存在的理由：本 spec 的 provider / 薄声明 docstring 里为解释 FC-9 逐字提到过
    `publish-to-tb` 等词，裸 `in` 会把解释文字当成违规调用（自造红）。
    """
    code = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )
    return re.sub(r'"""(?:.|\n)*?"""', "", code)


def _tb_red_line_violations(src: str, *, label: str) -> list[str]:
    """返回 `src` 里命中 TB 红线的形态清单（空 = 合规）。

    抽成函数是为了让**变异检验**能直接喂一段被污染的源码进来 —— 判据必须能证明
    「往 sync 路径塞一行 publishToTb 会打红」，而不是只在真实源码上恒绿。
    """
    code = _strip_python_comments_and_docstrings(src)
    return [f"{label}: {pat}" for pat in _TB_RED_LINE_PATTERNS if pat in code]


def _strip_vue_comments(src: str) -> str:
    """剔掉 `<!-- -->` / `//` / `/* */`，只留 SFC 的可执行部分。"""
    code = re.sub(r"<!--(?:.|\n)*?-->", "", src)
    code = re.sub(r"/\*(?:.|\n)*?\*/", "", code)
    return "\n".join(
        line for line in code.splitlines() if not line.strip().startswith("//")
    )


class TestGfP16TbRedLine:
    """Validates: 4.9"""

    def test_provider_module_never_writes_trial_balance(self) -> None:
        """sync 路径（provider + 薄声明）对 `trial_balance` 写次数为 **0**。"""
        violations: list[str] = []
        for name in (
            "phase5_g2_interest_receivable.py",
            "phase5_g2_02_detail.py",
        ):
            src = (
                _BACKEND / "app" / "services" / "workpaper_sync" / name
            ).read_text(encoding="utf-8")
            violations += _tb_red_line_violations(src, label=name)
        assert not violations, f"sync 路径出现 TB 写入形态 ⇒ 违反 FC-9 红线：{violations}"

    def test_mutation_publish_to_tb_in_sync_path_makes_red_line_fire(self) -> None:
        """🔴 变异（Task 17 原文「sync 回写里调 publishToTb 必红」）：判据要有牙齿。

        往 provider 的**代码区**注入一行发布门调用 ⇒ 红线扫描必须报出来。
        对照：真实源码扫描结果为空（上一条判据）。不做这一条，`not in` 形态的红线
        判据无法区分「真的没有」和「扫描口径写错了永远扫不到」。
        """
        src = (
            _BACKEND
            / "app"
            / "services"
            / "workpaper_sync"
            / "phase5_g2_interest_receivable.py"
        ).read_text(encoding="utf-8")
        assert _tb_red_line_violations(src, label="real") == []
        # 变异①：sync 回写路径里直接调发布门。
        mutated = src + "\n\ndef _mutant(session):\n    return publish_to_tb(session)\n"
        assert _tb_red_line_violations(mutated, label="mut") == [
            "mut: publish_to_tb"
        ], "注入 publish_to_tb 后红线未报 ⇒ 扫描口径失效"
        # 变异②：绕过发布门直接打 legacy writeback 端点。
        mutated2 = src + '\n\nTB = "trial-balance/writeback"\n'
        assert "mut2: trial-balance/writeback" in _tb_red_line_violations(
            mutated2, label="mut2"
        ), "注入 legacy writeback 端点后红线未报"

    def test_bridged_host_sync_path_carries_no_tb_write(self) -> None:
        """Task 15 接桥后的**宿主**同样在红线内：syncBridge 一侧不得碰 TB。

        为什么单列一条：Task 15 给 `GtG2InterestReceivable.vue` 加了 `flushHtml` /
        `reloadHtml` 两个回调 —— 它们是 sync 路径在宿主侧的**新落点**。把 TB 写入塞进
        `flushHtml` 是最自然的错误写法（「反正都要 flush，一起把审定数推到 TB」），
        provider 侧的红线扫描覆盖不到它。
        """
        host = (
            FRONTEND / "components" / "workpaper" / "GtG2InterestReceivable.vue"
        ).read_text(encoding="utf-8")
        code = _strip_vue_comments(host)
        for pat in ("publishToTb", "trial-balance/writeback", "publish-to-tb"):
            assert pat not in code, (
                f"宿主代码出现 {pat!r} ⇒ sync 路径在宿主侧越界写 TB（FC-9 红线）"
            )
        # 已移除的 legacy 监听器不得复活（spec tb-writeback-explicit-publish-gate Task 12）
        assert "g2:writeback-trial-balance" not in code, (
            "legacy 事件监听器 `g2:writeback-trial-balance` 复活 ⇒ 绕过显式确认门"
        )
        # 正向锁：接桥后的两个 sync 回调确实存在（否则上面三条是空分母重言式）
        assert "flushHtml" in code and "reloadHtml" in code, (
            "宿主没有 sync 回调 ⇒ 本判据无对象，须先确认 Task 15 接桥仍在"
        )

    def test_publish_gate_remains_the_only_entrance(self) -> None:
        """G2 的显式发布门仍在、且仍是唯一入口（科目 1132、余额口径）。"""
        adj = COMPOSABLES / "useG2Adjudication.ts"
        src = adj.read_text(encoding="utf-8")
        assert src.count("publishToTb") == 3, (
            f"useG2Adjudication 的 publishToTb 计数 = {src.count('publishToTb')}（基线 3）"
        )
        # 门的真实端点必须在某一层的代码里
        found = [
            p.relative_to(FRONTEND).as_posix()
            for p in FRONTEND.rglob("*")
            if p.is_file()
            and p.suffix in (".ts", ".vue")
            and "__tests__" not in p.as_posix()
            and re.search(r"(^|/)(useG2|G2Tab|GtG2)", p.relative_to(FRONTEND).as_posix())
            and _PUBLISH_ENDPOINT in p.read_text(encoding="utf-8", errors="replace")
        ]
        assert found, f"G2 四层里找不到 {_PUBLISH_ENDPOINT!r} ⇒ 显式发布门不存在了"

    def test_legacy_dual_tb_keys_are_both_kept(self) -> None:
        """🔴 需求 4.9：G2 的 TB 键是 legacy 双键 —— 契约只声明主键，读回退**不得删**。"""
        src = (COMPOSABLES / "useG2Adjudication.ts").read_text(encoding="utf-8")
        assert "G2-1-tb" in src, "主键 `G2-1-tb` 消失"
        assert "G2-1-adj-tb-1132" in src, (
            "legacy 回退键 `G2-1-adj-tb-1132` 被删 ⇒ 已有项目的 TB 核对数据读不回来"
        )
        # 契约不得声明 TB 键（审定表 G2-1 归后置 spec）
        payload = json.dumps(G2.build_contract_payload(), ensure_ascii=False)
        for key in ("G2-1-tb", "G2-1-adj-tb-1132"):
            assert key not in payload, f"契约里出现 TB 键 {key!r} ⇒ 越界到审定表作业面"

    def test_account_code_is_1132_and_balance_caliber(self) -> None:
        """科目 1132 + **余额**口径（G2 是资产类，不是 `PL_CYCLES` 成员）。"""
        from tests.four_table.test_g_cycle_formula_presets import (  # type: ignore
            G_ACCOUNT_CODES,
            PL_CYCLES,
        )

        assert G_ACCOUNT_CODES["G2"] == "1132"
        assert "G2" not in PL_CYCLES, "G2 被当成损益类 ⇒ 口径会错成本期发生额"
        items = (COMPOSABLES / "g2AdjudicationItems.ts").read_text(encoding="utf-8")
        assert "'1132'" in items, "g2AdjudicationItems 的科目码不再是 1132"

    def test_adjudication_sheet_is_deferred_not_silently_managed(self) -> None:
        """GF-H5：审定表 G2-1 归后置 spec ⇒ 本 provider 的 adjudication_spec 恒 None。"""
        assert G2.adjudication_spec() is None
        assert G2.all_managed_sheet_names() == ("明细表G2-2",)


# ═══════════════════════════════════════════════════════════════════════════
# GF-P15：真栈验收不 seed，但**必须先断言载荷非空**（Task 16）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么要一条静态判据：真栈跑不跑取决于环境（start-dev.bat + OO + 真 PG），
#    而「不 seed 却不检载荷」这个缺陷是**写在文件里**的，静态就能守。
#    空表往返会让三谓词（confirm / durable ack / store 镜像）全部成立而什么都没验证 ——
#    这是 D4 lane 真实踩过的假绿形态。故本组判据锁：
#      ① fixture 声明了 `min_row_count ≥ 1` 且 `must_assert_before_skip`；
#      ② e2e spec 里前置断言**出现在** adapter skip 之前（位置判据，不是存在判据）；
#      ③ 前置断言**不带** `pending_adapter` 跳过条件（否则它会跟着一起被跳掉）；
#      ④ 裁决 GF-H2 落成「无 seed 脚本」：仓库里不存在 G2 canary 的 seed 脚本。

_E2E_DIR = FRONTEND.parent / "e2e"
_G2_FIXTURE = _E2E_DIR / "fixtures" / "g2-l2-cases.json"
_G2_SPEC = _E2E_DIR / "g2-l2-oo-to-html-all.spec.ts"


class TestGfP15RealStackPreconditions:
    """Validates: 4.8"""

    def test_fixture_and_spec_exist(self) -> None:
        assert _G2_FIXTURE.is_file(), f"缺 fixture：{_G2_FIXTURE}"
        assert _G2_SPEC.is_file(), f"缺真栈用例：{_G2_SPEC}"

    def test_fixture_declares_non_empty_precondition(self) -> None:
        """fixture 必须声明「行数 ≥ 1」的前置，且标明要在 skip 之前断言。"""
        data = json.loads(_G2_FIXTURE.read_text(encoding="utf-8"))
        pre = data["preconditions"]
        assert pre["store_item_id"] == "G2-2-detail-rows"
        assert int(pre["min_row_count"]) >= 1, (
            f"min_row_count={pre['min_row_count']} ⇒ 0 行也算通过，P15 失效"
        )
        assert pre["must_assert_before_skip"] is True

    def test_fixture_seed_policy_matches_real_db_evidence(self) -> None:
        """裁决 GF-H2 的证据必须是**现测数字**，不是「大概有数据」。"""
        data = json.loads(_G2_FIXTURE.read_text(encoding="utf-8"))
        policy = data["seed_policy"]
        assert policy["decision"] == "no_seed"
        assert policy["adjudication"] == "GF-H2"
        ev = policy["evidence"]
        # 2026-09-27 对真 PG 现查：475 B / jsonb 数组 1 行
        assert ev["store_item_id"] == "G2-2-detail-rows"
        assert int(ev["remark_bytes"]) == 475
        assert int(ev["row_count"]) == 1
        assert ev["wp_code"] == "G2"
        # wp_id / project_id 必须是可复查的 UUID，不能留占位
        for key in ("wp_id", "project_id"):
            assert re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                str(ev[key]),
            ), f"{key} 不是 UUID：{ev[key]!r} ⇒ 证据无法复查"
        assert policy["evidence_sql"].strip().upper().startswith("SELECT"), (
            "没留可复跑的 SQL ⇒ 下一个人无法复核 475 B / 1 行这两个数"
        )

    def test_no_seed_script_was_delivered(self) -> None:
        """GF-H2「不交付 seed」要能被证伪：仓库里不存在 G2 canary 的 seed 脚本。"""
        candidates = [
            p.relative_to(_BACKEND.parent).as_posix()
            for p in (_BACKEND / "scripts").rglob("*.py")
            if re.search(r"seed.*g2|g2.*seed", p.name, re.IGNORECASE)
        ]
        assert candidates == [], (
            f"出现 G2 seed 脚本 {candidates} ⇒ 与裁决 GF-H2 冲突；"
            "若确需 seed，请改裁决并同步 fixture 的 seed_policy"
        )

    def test_precondition_assertion_precedes_the_adapter_skip(self) -> None:
        """🔴 位置判据：前置断言必须在 `pending_adapter` 跳过**之前**。

        只断言「文件里有 min_row_count 检查」是不够的 —— 若它写在 skip 之后（或写进
        被 skip 的那个 test 体内），整条就跟着被跳掉，P15 等于没有。
        """
        src = _G2_SPEC.read_text(encoding="utf-8")
        pre_pos = src.find("toBeGreaterThanOrEqual")
        # 🔴 口径：定位**可执行的**跳过谓词，不是文档里提到的 `pending_adapter` 字样。
        #    本文件头部的 docstring 为解释「为什么当前 pending_adapter」逐字用了该词，
        #    裸 `find('pending_adapter')` 会命中注释（实测 556 < 3140，判据自造红）——
        #    与仓库反复登记的「符号名 grep 会误报」同类。
        skip_match = re.search(
            r"c\.result_enum\s*===\s*'pending_adapter'", src
        )
        assert pre_pos > 0, "spec 里没有行数下界断言 ⇒ P15 未落地"
        assert skip_match is not None, (
            "spec 里没有 `c.result_enum === 'pending_adapter'` 跳过谓词 ⇒ 请核对 adapter 供给状态"
        )
        skip_pos = skip_match.start()
        assert pre_pos < skip_pos, (
            "行数断言出现在 pending_adapter 跳过之后 ⇒ 它会被一起跳掉，空表假绿的洞没堵上"
        )

    def test_precondition_test_is_not_itself_skippable_by_adapter_gap(self) -> None:
        """前置那条 test 的函数体内不得含 adapter 相关的 `test.skip`。"""
        src = _G2_SPEC.read_text(encoding="utf-8")
        start = src.find("P15 前置")
        assert start > 0, "找不到 P15 前置用例 ⇒ 判据无对象"
        # 前置用例体 = 从它的标题到下一个 `test(` 之间
        nxt = src.find("\n  for (const c of cases.cases)", start)
        body = src[start : nxt if nxt > 0 else len(src)]
        assert "pending_adapter" not in body, (
            "前置用例体内引用了 pending_adapter ⇒ 它会随 adapter 缺位一起被跳过"
        )
        assert "test.skip" not in body, (
            "前置用例体内有 test.skip ⇒ P15 可被静默跳过。环境缺位应让它**红**（诚实失败），"
            "而不是绿着跳过"
        )

    def test_fixture_is_loaded_in_a_form_playwright_can_actually_load(self) -> None:
        """🔴 fixture 必须用 `readFileSync` 读，不得用 `import … from '*.json'`。

        实测：Playwright 的 Node ESM 加载器对裸 JSON import 抛
        `needs an import attribute of "type: json"`，**整个 spec 文件加载失败**，
        `--list` 得到 `Total: 0 tests in 0 files` —— 一条用例都跑不起来，而 CI 上看不出
        区别（本来就 skip）。`f1-l2-oo-to-html-all.spec.ts` 现在正是这个形态（既存缺陷，
        属 f1 lane，不在本 spec 修改范围，见收口证据登记）。

        本判据锁住 G2 lane 用的是可加载形态，防「照 F1 抄回去」。
        """
        src = _G2_SPEC.read_text(encoding="utf-8")
        assert not re.search(r"^import\s+cases\s+from\s+'.*\.json'", src, re.M), (
            "用了裸 JSON import ⇒ Playwright 加载该 spec 会整体失败（Total: 0 tests）"
        )
        assert "readFileSync" in src, "未用 readFileSync 读 fixture"
        assert "fixtures/g2-l2-cases.json" in src, "spec 没指向 G2 的 fixture"

    def test_f1_lane_fixture_import_stays_loadable(self) -> None:
        """🔴 **2026-09-30 登记已按其自身指引解除并反转为回归锁**。

        原判据断言「F1 lane 的同类文件**仍是**坏形态（裸 JSON import）」，并在修好后打红
        提示移除登记。现算确认缺陷**确已清**（三项独立证据，均非本轮改动）：
          ① `audit-platform/frontend/e2e/` 下两个 f1 spec（`f1-l2-oo-to-html-all.spec.ts` /
             `f-cycle-f1-prepayment.spec.ts`）均已无 `^import cases from '*.json'`；
          ② 两文件工作树**干净**，最近提交是他人的 `121939f3d chore: 批量更新 — e2e 测试适配…`；
          ③ golden digest 基线里 f1 条目有完整真实 digest（contract_payload / sheet_digests /
             store_projection / instrumentation 四项非 null），门禁现算「零跳过」。

        ⇒ 判据反转为**回归锁**：F1 不得退回裸 JSON import（Playwright 会整体 Total: 0 tests）。
        同时保留「照 F1 抄回去」这层防护的本意 —— 对象从「登记缺陷」变成「守住已修状态」。
        """
        targets = sorted(_E2E_DIR.glob("*f1*.spec.ts"))
        assert targets, "F1 lane 的 e2e spec 全部消失 ⇒ 本回归锁失去对象，须重新指认"
        broken = [
            p.name for p in targets
            if re.search(r"^import\s+\w+\s+from\s+'.*\.json'", p.read_text(encoding="utf-8"), re.M)
        ]
        assert not broken, (
            f"F1 lane 退回裸 JSON import：{broken} ⇒ Playwright 加载该 spec 会整体失败"
            "（Total: 0 tests），须改回 readFileSync"
        )

    def test_spec_documents_workers_one(self) -> None:
        """`--workers=1` 与串行模式都要在文件里显式落地（同 wp 的 room/revision 是串行资源）。"""
        src = _G2_SPEC.read_text(encoding="utf-8")
        assert "--workers=1" in src, "未记载 --workers=1 跑法"
        assert "mode: 'serial'" in src, "未声明 serial 模式 ⇒ 并行会抢同一 wp 的 revision"


# ═══════════════════════════════════════════════════════════════════════════
# GF-P19：引擎层整册往返（Task 18「整册 materialize/verify」在 G2 上的可跑部分）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 **诚实边界**：Task 18 原文要求「整册 materialize/verify」。生产那条链
#    （`excel_materialize.materialize_projection` + `excel_extract.verify_unmanaged_regions`）
#    需要 `FrozenEntryDefinitions` + `ExcelIdentityBinding`，两者只能由
#    registry/resolution 从**已注册 adapter**取 —— G2 的 manifest capability 仍是
#    `single_onlyoffice`（BP-1~BP-3 平台级欠账），`attach_pilot_adapters` 走 capability 门
#    返回空 ⇒ 那条链在 G2 上**不可达**，与 Task 14 第③环、Task 16 真栈同一阻塞。
#    参照：`scripts/e2e/verify_d4_full_book_real_stack.py` 的注释明确「D4 是 D 循环唯一
#    adapter_registered=True 的 entry，故也是唯一能真跑这条的」。
#
#    可跑且有意义的那一半是**引擎层往返**：store 载荷 → `build_store_projection` →
#    `merge_projection_into_store_rows` → 回到 store 行。它证明本 spec 声明的几何与
#    13 个字段规格能**无损**承载真库载荷 —— 声明漏一列、json_path 写错、账龄组展开错，
#    往返后都会丢值。下面用**真库录制的载荷**（非编造）跑这条。

#: 真库录制载荷（2026-09-27 现查）。
#: `SELECT remark FROM checklist_responses WHERE item_id='G2-2-detail-rows'
#:   AND wp_id='ede443da-3848-4a3f-af21-848559aa0e25'` —— 475 B / 1 行。
#: 🔴 逐字录制，不精简、不编造：账龄双组（`agingPrior` / `agingAudited`）与
#:    `eclStage`/`indexRef` 这些真实键是判据的一半价值所在（编造的载荷不会带它们）。
RECORDED_REAL_PAYLOAD: str = (
    '[{"id":"detail-1784433008253-e6b7a1","seq":1,"investType":"","investTarget":"",'
    '"openingUnadjusted":0,"openingAdjustment":0,"debit":0,"credit":0,'
    '"closingAdjustment":0,"interestDueDate":"","accrualPeriod":"",'
    '"collectionStatus":"","faceValue":0,"couponRate":0,"accrualStart":"",'
    '"accrualEnd":"","receivedInterest":0,"eclStage":"Stage1",'
    '"agingPrior":{"within1":0,"y1to2":0,"y2to3":0,"over3":0},'
    '"agingAudited":{"within1":0,"y1to2":0,"y2to3":0,"over3":0},'
    '"remark":"","indexRef":""}]'
)


class TestGfP19EngineLevelRoundTrip:
    """Validates: 4.1, 4.3（Task 18 的可跑部分）"""

    def test_recorded_payload_is_the_real_db_shape(self) -> None:
        """录制载荷的形态自洽：单行数组、带行身份、账龄双组齐全。"""
        rows = json.loads(RECORDED_REAL_PAYLOAD)
        assert isinstance(rows, list) and len(rows) == 1
        row = rows[0]
        assert row["id"].startswith("detail-"), "行身份前缀不是 generateId() 的 `detail-`"
        for group in ("agingPrior", "agingAudited"):
            assert set(row[group]) == {"within1", "y1to2", "y2to3", "over3"}, (
                f"{group} 的档位键与 spec 声明不符：{sorted(row[group])}"
            )
        assert len(RECORDED_REAL_PAYLOAD.encode("utf-8")) == 475, (
            "录制载荷字节数不再是 475 ⇒ 录制过程改动了内容，不能当真库证据"
        )

    def test_store_to_projection_to_store_round_trip_is_lossless(self) -> None:
        """store → projection → store 无损：13 字段 + 账龄双组逐值回得来。"""
        from app.services.workpaper_sync.phase5_row_table_sheet import (  # type: ignore
            build_store_projection as engine_build,
            merge_projection_into_store_rows as engine_merge,
        )

        contract = G2.load_contract_from_disk()
        base_rows = json.loads(RECORDED_REAL_PAYLOAD)
        projection = engine_build(SPEC_G202, RECORDED_REAL_PAYLOAD, contract=contract)
        assert projection.values, "投影为空 ⇒ 字段声明与载荷键对不上（键名或 json_path 错）"
        assert SPEC_G202.table_key in projection.row_keys, (
            f"投影缺 table_key={SPEC_G202.table_key!r} 的 row_keys ⇒ 下游 materialize 判不了行增删"
        )
        # `row_keys` 的值是 tuple（引擎口径），逐元素比不按容器类型比
        assert list(projection.row_keys[SPEC_G202.table_key]) == [base_rows[0]["id"]], (
            "投影的行身份与载荷不一致 ⇒ 行身份取的不是 `id`"
        )

        merged, *_ = engine_merge(
            SPEC_G202, projection=projection, base_rows=json.loads(RECORDED_REAL_PAYLOAD)
        )
        assert merged == base_rows, (
            "往返后行内容变了 ⇒ 存在字段丢失/覆盖。"
            f"\n原: {json.dumps(base_rows, ensure_ascii=False)}"
            f"\n后: {json.dumps(merged, ensure_ascii=False)}"
        )

    def test_mutation_dropping_a_declared_field_breaks_the_round_trip(self) -> None:
        """🔴 变异：载荷里抽掉一个受管字段 ⇒ 往返后该键缺失（证明判据能看见丢值）。

        不改 spec、只改输入 —— 证明「往返无损」不是恒真：投影只搬它声明的字段，
        输入缺列时合并回来也缺，于是与原载荷不等。
        """
        from app.services.workpaper_sync.phase5_row_table_sheet import (  # type: ignore
            build_store_projection as engine_build,
            merge_projection_into_store_rows as engine_merge,
        )

        contract = G2.load_contract_from_disk()
        rows = json.loads(RECORDED_REAL_PAYLOAD)
        rows[0].pop("faceValue")
        mutated = json.dumps(rows, ensure_ascii=False)
        projection = engine_build(SPEC_G202, mutated, contract=contract)
        merged, *_ = engine_merge(
            SPEC_G202, projection=projection, base_rows=json.loads(mutated)
        )
        assert merged != json.loads(RECORDED_REAL_PAYLOAD), (
            "抽掉一个受管字段后往返结果仍与原载荷相等 ⇒ 上一条的「无损」是恒真装饰"
        )

    def test_capability_gate_is_open_and_real_stack_run_is_the_remaining_step(
        self,
    ) -> None:
        """🔴 **2026-09-30 按原判据的指引改写**：capability 门已放开，剩下的是真栈整册跑。

        原判据断言「门仍关着 ⇒ 整册 materialize/verify 不可达」，并在门放开后打红提示
        「请改跑生产整册 materialize/verify（照 `scripts/e2e/verify_d4_full_book_real_stack.py`），
        并移除本登记判据」。门确实已放开（overlay 裁决 + digest 门复核批准 + 生成器
        `--apply`），但**真栈整册跑需要 PG + OnlyOffice 容器与已落 representation 的 G2 项目**，
        不在本轮环境内。

        ⇒ 本判据因此如实转为两条可证伪的事实，而不是删掉了事：
          ① 门**确实**已开（退回即红 —— 防 manifest 被手改或重生成漂移）
          ② 真栈脚本**确实存在**且是下一步的执行对象（文件消失即红 —— 防「下一步」指向空气）
        真栈跑完后请把本判据替换为真实的 materialize/verify 断言。
        """
        assert G2.manifest_capability_enabled() is True, (
            "capability 门又关上了 ⇒ manifest 可能被手改或重生成漂移，"
            "先核 `generate_workpaper_sync_manifest.py --check`"
        )
        runner = _BACKEND / "scripts" / "e2e" / "verify_d4_full_book_real_stack.py"
        assert runner.is_file(), (
            f"真栈整册跑的参照脚本不存在：{runner} ⇒ "
            "本判据指向的「下一步」已失效，须重新指认执行对象"
        )
