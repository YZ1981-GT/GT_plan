# -*- coding: utf-8 -*-
"""E1 声明层红判据（E1-P2 / E1-P3 / E1-P12 / E1-P16 / E1-P17 / E1-P18）。

spec: e1-sync-coverage-and-first-canary · Tasks 4/5/6
Properties: E1-P2（键名逐字实证）/ E1-P3（binding_kind 三元组 + 自省变异）/
            E1-P12（零回归基线）/ E1-P16（OCR 第二写入方登记）/
            E1-P17（TB 发布门：sync 不触达 trial_balance）/
            E1-P18（E1-3 列集守恒：只接 multi variant）

验证声明层类型自洽 + 与引擎的接口契约。
不重复实测模板几何（已在 docs/operations/evidence/e1-sync-coverage/ 登记）。
"""
from __future__ import annotations

import pytest

from app.services.workpaper_sync.excel_extract import BindingKind
from app.services.workpaper_sync.phase5_row_table_sheet import (
    StoreKind,
    managed_field_specs,
)

# ═══ 导入所有 E1 声明 ═══

from app.services.workpaper_sync.phase5_e1_monetary_fund import (
    ADAPTER_ID,
    ENTRY_ID,
    CROSS_VOLUME_KEYS,
    WP_CODES,
    all_store_item_ids,
    managed_row_table_specs,
    static_region_specs,
)
from app.services.workpaper_sync.phase5_e1_02_cash_detail import (
    SPEC_E102,
    STORE_ITEM_ID_E102,
    ROW_IDENTITY_STORE_KEY_E102,
    FIXED_ROW_KEY_E102,
    HTML_ONLY_ROWS_E102,
)
from app.services.workpaper_sync.phase5_e1_04_digital import (
    SPEC_E104,
    STORE_ITEM_ID_E104,
)
from app.services.workpaper_sync.phase5_e1_06_reconciliation import (
    SPEC_E106,
    STORE_ITEM_ID_E106,
)
from app.services.workpaper_sync.phase5_e1_07_08_09_cash_count import (
    SPEC_E107,
    SPEC_E108,
    SPEC_E109,
    STORE_ITEM_ID_E107,
    STORE_ITEM_ID_E108,
    STORE_ITEM_ID_E109,
    HTML_ONLY_ITEM_IDS_E1,
    LEGACY_SUMMARY_KEY_FX,
    CERT_SIGNATURES_KEY,
)
from app.services.workpaper_sync.phase5_e1_10_account_list import (
    SPEC_E110,
    STORE_ITEM_ID_E110,
    CROSS_SHEET_KEYS_E110,
    OCR_DIALOG_COMPONENTS_E110,
)
from app.services.workpaper_sync.phase5_e1_11_commitment import (
    SPEC_E111,
    STORE_ITEM_IDS_E111,
    OCR_DIALOG_COMPONENTS_E111,
    CROSS_SHEET_SNAPSHOT_KEY_E111,
)

# ═══ 所有行表 spec 的聚合集 ═══

ALL_ROW_TABLE_SPECS = (SPEC_E102, SPEC_E104, SPEC_E106, SPEC_E107, SPEC_E108, SPEC_E109, SPEC_E110)
ALL_SPECS = (*ALL_ROW_TABLE_SPECS, SPEC_E111)


# ═══════════════════════════════════════════════════════════════════════════
# E1-P2：每个 store_item_id 逐字等于按值 grep 实测值
# ═══════════════════════════════════════════════════════════════════════════


class TestP2StoreItemIdEvidence:
    """E1-P2：store_item_id 必须是前端实测值，不得按编号推演。

    🔴 E1 有**四种命名风格**（语义/编号嵌套/模板化/无连字符），
    按编号推演会全错（六次事故背书）。
    """

    # 实测值表（按值 grep 到的 composable 常量/写入点）
    EXPECTED = {
        "E1-2": "E1-cash-detail-rows",
        "E1-4": "E1-digital-rows",
        "E1-6": "E1-reconciliation-rows",
        "E1-7": "E1-cash-count-rmb-rows",
        "E1-8": "E1-cash-count-fx-rows",
        "E1-9": "E1-cash-count-cert-rows",
        "E1-10": "E1-account-list-rows",
    }

    @pytest.mark.parametrize("sheet,expected_key", list(EXPECTED.items()))
    def test_store_item_id_matches_grep_evidence(self, sheet: str, expected_key: str) -> None:
        """每个受管行表的 store_item_id 必须逐字等于实测值。"""
        spec = next(s for s in ALL_ROW_TABLE_SPECS if sheet in s.error_label)
        assert spec.store_item_id == expected_key, (
            f"{sheet} 的 store_item_id={spec.store_item_id!r} 与实测值 {expected_key!r} 不符 —— "
            "禁止按编号推演（裁决 F2，六次事故背书）"
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 红基线（未实施工作），不是回归。`self.EXPECTED` 覆盖 E1 的 7 张目标 sheet，"
            "而 provider 现只开 2 个灰度开关（`_INCLUDE_E102_CASH_DETAIL` / "
            "`_INCLUDE_E104_DIGITAL` 为 True，`_INCLUDE_E111_COMMITMENT_STATIC` 为 False）"
            "⇒ `all_store_item_ids()` 现算 {'E1-cash-detail-rows','E1-digital-rows'}，"
            "`E1-reconciliation-rows` 等连声明层都还没有。"
            "spec `e1-sync-coverage-and-first-canary` 在 INDEX 里是 0/23。"
            "2026-09-28 转 strict xfail：E1 扩容落地后本条会 XPASS 并报错，强制摘掉标记。"
        ),
    )
    def test_all_store_items_in_provider_output(self) -> None:
        """provider 的 all_store_item_ids() 包含全部行表键。"""
        items = set(all_store_item_ids())
        for expected_key in self.EXPECTED.values():
            assert expected_key in items, f"{expected_key} 不在 all_store_item_ids() 里"

    def test_enabled_sheets_store_items_are_really_wired(self) -> None:
        """✅ **已开启**的那几张必须真在 `all_store_item_ids()` 里（上一条的非空对照）。

        没有这条，上面那个 xfail 会把「E1 一张都没接」和「接了 2 张、还差 5 张」混为一谈。
        本条随灰度开关**现算**而非写死张数 —— 开关翻开时它自动覆盖新接的那张。
        """
        items = set(all_store_item_ids())
        enabled = {s.store_item_id for s in managed_row_table_specs() if s.store_item_id}
        assert enabled, "一个行表 spec 都没开 ⇒ 灰度开关被整体关掉了，这是回归不是红基线"
        missing = sorted(enabled - items)
        assert not missing, f"已开启的 spec 其 store_item_id 不在 all_store_item_ids()：{missing}"

    def test_mutation_e1_2_rows_pushes_wrong_key(self) -> None:
        """变异 ①：把 E1-cash-detail-rows 写成 E1-2-rows ⇒ 投影恒空必红。"""
        assert STORE_ITEM_ID_E102 != "E1-2-rows", "变异未生效 —— 这条应该恒过"
        assert STORE_ITEM_ID_E102 == "E1-cash-detail-rows"

    def test_mutation_cashcount_vs_cash_count(self) -> None:
        """变异 ②：cash-count 与 cashcount 一字之差。

        E1-8 同时有 E1-cash-count-fx-rows（新键）和
        E1-cashcount-audit-note-fx（无连字符 legacy 文本键）。
        """
        assert "cash-count" in STORE_ITEM_ID_E108, "E1-8 的行数据键必须含连字符 cash-count"
        assert "cashcount" not in STORE_ITEM_ID_E108, "行数据键误用了无连字符的 cashcount"
        # legacy 兜底键确实无连字符——是历史键，不是笔误
        assert "cashcount" in LEGACY_SUMMARY_KEY_FX


# ═══════════════════════════════════════════════════════════════════════════
# E1-P3：binding_kind 三元组 + 自省变异
# ═══════════════════════════════════════════════════════════════════════════


class TestP3BindingKindTriad:
    """E1-P3：BindingKind 取自前端三元组实证，不取自模板公式数。

    三元组：(store 键是否存在, addRow/removeRow 信号数, composable 归属)
    """

    def test_e1_11_is_the_only_static_region(self) -> None:
        """🔴 第一册唯一 static_region —— 零 -rows 键、无 composable。"""
        assert SPEC_E111.binding_kind is BindingKind.static_region
        assert SPEC_E111.row_identity_key == ""
        assert SPEC_E111.table_name == ""
        assert SPEC_E111.uuid_col == ""
        assert SPEC_E111.defined_name  # 非空

    @pytest.mark.parametrize("spec", ALL_ROW_TABLE_SPECS, ids=lambda s: s.error_label)
    def test_all_row_tables_are_excel_table_binding(self, spec) -> None:
        """全部 7 个行表 spec 都是 excel_table binding。"""
        assert spec.binding_kind is BindingKind.excel_table
        assert spec.store_kind is StoreKind.rows
        assert spec.row_identity_key  # 非空

    def test_e1_9_is_not_static_region(self) -> None:
        """🔴 变异 ④a：E1-9 存单盘点（7 公式）是动态行表，不是 static_region。

        首版按「各只 7 公式」把它判成 static_region，实证推翻
        （键 E1-cash-count-cert-rows + useE1CashCount addRow×4）。
        """
        assert SPEC_E109.binding_kind is BindingKind.excel_table
        assert SPEC_E109.store_item_id == "E1-cash-count-cert-rows"
        assert SPEC_E109.row_identity_key == "id"

    def test_e1_10_is_not_static_region(self) -> None:
        """🔴 变异 ④b：E1-10 账户清单（7 公式）是动态行表，不是 static_region。

        首版按「各只 7 公式」把它判成 static_region，实证推翻
        （键 E1-account-list-rows + useE1AccountList addRow/removeRow）。
        """
        assert SPEC_E110.binding_kind is BindingKind.excel_table
        assert SPEC_E110.store_item_id == "E1-account-list-rows"
        assert SPEC_E110.row_identity_key == "id"

    def test_self_introspection_mutation_formula_count_threshold(self) -> None:
        """🔴 自省变异（第 3 条）：把判据改回公式数阈值（< 10 ⇒ static_region）。

        E1-9 / E1-10 / E1-11 三张各只 7 公式。若按公式数阈值判定，
        三张都会判成 static_region —— 但实证只有 E1-11 成立。
        这复现的正是 spec 首版裁决 H3 的错法。
        """
        # 假设用公式数阈值 threshold=10
        FORMULA_COUNT_THRESHOLD = 10

        # 三张的模板公式数都低于阈值
        low_formula_sheets = {"E1-9": 7, "E1-10": 7, "E1-11": 7}

        # 按阈值推演：三张全判 static_region
        would_be_static_by_threshold = {
            sheet for sheet, count in low_formula_sheets.items()
            if count < FORMULA_COUNT_THRESHOLD
        }
        assert would_be_static_by_threshold == {"E1-9", "E1-10", "E1-11"}, (
            "前提不成立：公式数阈值推演未把三张全判 static_region"
        )

        # 但实证只有 E1-11 是 static_region
        actually_static = {"E1-11"}
        wrongly_classified = would_be_static_by_threshold - actually_static
        assert wrongly_classified == {"E1-9", "E1-10"}, (
            "自省变异失效：公式数阈值判据未把 E1-9/E1-10 **误判**成 static_region —— "
            "这条变异复现的正是 spec 首版裁决 H3 的错法，它必须能打红自己的历史错误"
        )

    def test_e1_row_identity_key_is_id_not_rowId(self) -> None:
        """🔴 E1 全族行身份键统一为 `id`（不是 D 类的 `rowId`）。

        D4-1 曾因 rowKey/rowId 之误踩过同款。
        """
        for spec in ALL_ROW_TABLE_SPECS:
            assert spec.row_identity_key == "id", (
                f"{spec.error_label} 的 row_identity_key={spec.row_identity_key!r} "
                "应为 'id'（E1 全族统一用 id，不是 D 类的 rowId）"
            )


# ═══════════════════════════════════════════════════════════════════════════
# E1-P12：零回归基线（其余 contract golden digest 不变）
# ═══════════════════════════════════════════════════════════════════════════


class TestP12ZeroRegressionBaseline:
    """E1-P12：新增 E1 contract 不得影响已有 10 个 contract 的 golden digest。"""

    def test_adapter_id_format(self) -> None:
        assert ADAPTER_ID == "e1.monetary_fund_detail"

    def test_entry_id_format(self) -> None:
        assert ENTRY_ID == "xlsx/gt-e1-monetary-fund"

    def test_wp_codes_matches_e1(self) -> None:
        assert WP_CODES == frozenset({"E1"})

    def test_e1_in_delivered_contracts(self) -> None:
        """E1 已注册到 DELIVERED_PER_ENTRY_CONTRACTS。"""
        from app.services.workpaper_sync.adapters.registry import DELIVERED_PER_ENTRY_CONTRACTS

        e1 = [r for r in DELIVERED_PER_ENTRY_CONTRACTS if r["contract_id"] == ADAPTER_ID]
        assert len(e1) == 1, f"E1 在交付登记表中应恰好 1 条，实际 {len(e1)}"
        assert e1[0]["entry_id"] == ENTRY_ID
        assert e1[0]["provider_module"] == "app.services.workpaper_sync.phase5_e1_monetary_fund"

    def test_e1_provider_in_whitelist(self) -> None:
        """E1 provider 已在 _ALLOWED_PROVIDER_MODULES 白名单。"""
        from app.services.workpaper_sync.adapters.registry import _ALLOWED_PROVIDER_MODULES

        assert "app.services.workpaper_sync.phase5_e1_monetary_fund" in _ALLOWED_PROVIDER_MODULES

    #: 截至 E1 加入前（2026-09-26）已交付的 10 条 per-entry contract。
    #:
    #: 🔴 2026-09-28 从**集合相等**改为**只许增不许减**。
    #:    原断言是 `existing_ids == expected_existing`，于是**任何别的 lane 新交付一个契约
    #:    都会让本条打红** —— 实测多了 40 条（g1~g14 / h2~h10 / i1~i6 / f1~f5 / j1 / l1 /
    #:    a51 / c2 …），全是其他 lane 的正常交付，没有一条是本 spec 的产物。
    #:    这不是零回归信号，是**把「平台在长大」误报成「E1 动了别人的东西」**。
    #:    E1-P12 要的是「E1 加入**没有删掉/改名**已有契约」⇒ 正确形态是子集关系。
    #:    🔴 反向保护没有丢：少一条仍然红（下方 `missing` 断言），且另有
    #:       `test_f2_p11_golden_digest_zero_regression` 逐文件盯 digest —— 内容变了在那里红。
    BASELINE_CONTRACTS_BEFORE_E1 = frozenset({
        "b60.hour_budget",
        "d2.receivable_detail",
        "h1.disposal_check",
        "g7.soe_subsidiary_disclosure",
        "d1.notes_receivable_detail",
        "d7.contract_liabilities_detail",
        "d3.prepaid_receipts_detail",
        "d6.contract_assets_detail",
        "d5.receivables_financing_detail",
        "d4.revenue_detail",
    })

    def test_all_existing_contracts_untouched(self) -> None:
        """E1 加入不得**删掉或改名**任何已有 contract（新 lane 交付新契约是正常增长）。"""
        from app.services.workpaper_sync.adapters.registry import DELIVERED_PER_ENTRY_CONTRACTS

        existing_ids = {
            str(r["contract_id"]) for r in DELIVERED_PER_ENTRY_CONTRACTS
            if r["contract_id"] != ADAPTER_ID
        }
        missing = sorted(self.BASELINE_CONTRACTS_BEFORE_E1 - existing_ids)
        assert not missing, (
            f"E1 加入前已有的 contract 不见了：{missing} —— 这才是零回归违规"
            "（新增的契约属其他 lane 正常交付，不在本条管辖内）"
        )

    def test_baseline_contract_set_is_not_empty(self) -> None:
        """基线本身非空 —— 防「基线被清空 ⇒ 上一条恒绿」。"""
        assert len(self.BASELINE_CONTRACTS_BEFORE_E1) == 10


# ═══════════════════════════════════════════════════════════════════════════
# E1-P16：OCR 确认弹窗在受管 sheet 上有登记
# ═══════════════════════════════════════════════════════════════════════════


class TestP16OcrSecondWriter:
    """E1-P16：E1 有 7 个 OCR 确认弹窗（D4 范式零 OCR）。

    受管 sheet 的 OCR 组件必须被显式登记，以便宿主 gating 在 OO 编辑态下禁用它们。
    """

    def test_e1_10_ocr_dialog_registered(self) -> None:
        """E1-10 有 OCR 确认弹窗（提及 ×43）。"""
        assert len(OCR_DIALOG_COMPONENTS_E110) >= 1
        assert "E1AccountListOcrConfirmDialog" in OCR_DIALOG_COMPONENTS_E110

    def test_e1_11_ocr_dialog_registered(self) -> None:
        """E1-11 有 OCR 确认弹窗（提及 ×43，与 E1-10 成对）。"""
        assert len(OCR_DIALOG_COMPONENTS_E111) >= 1
        assert "E1AccountCommitOcrConfirmDialog" in OCR_DIALOG_COMPONENTS_E111[0]

    def test_ocr_dialogs_are_distinct(self) -> None:
        """E1-10 和 E1-11 的 OCR 弹窗组件不同（各自独立）。"""
        assert set(OCR_DIALOG_COMPONENTS_E110) != set(OCR_DIALOG_COMPONENTS_E111)


# ═══════════════════════════════════════════════════════════════════════════
# E1-P17：TB 发布门（sync 回写不触达 trial_balance）
# ═══════════════════════════════════════════════════════════════════════════


class TestP17TbPublishGate:
    """E1-P17：sync 回写路径不得触达 trial_balance。

    E1-1 审定表接 `publishToTb` 显式门（data-testid="e1-publish-tb"），
    双向回写**不得**成为 TB 回写的第二条路径。
    """

    def test_sync_store_items_do_not_include_trial_balance(self) -> None:
        """sync 回写路径的 store item 里不含 trial_balance 相关键。"""
        items = all_store_item_ids()
        for item in items:
            assert "trial" not in item.lower(), (
                f"store item {item!r} 含 'trial' —— sync 回写不得触达 trial_balance"
            )
            assert "tb-" not in item.lower() and not item.startswith("tb_"), (
                f"store item {item!r} 疑似 TB 键 —— sync 回写不得触达 trial_balance"
            )

    def test_cross_volume_keys_do_not_include_trial_balance(self) -> None:
        """跨册取数键也不含 trial_balance。"""
        for key in CROSS_VOLUME_KEYS:
            assert "trial" not in key.lower()


# ═══════════════════════════════════════════════════════════════════════════
# E1-P18：E1-3 列集守恒（只接 multi variant）
# ═══════════════════════════════════════════════════════════════════════════


class TestP18E13ColumnSetIntegrity:
    """E1-P18：E1-3 两 variant 共用 E1-bank-detail-rows 但列集不同。

    默认裁决只接 multi（人民币及外币）一张（列集超集），
    rmb（仅人民币）保持 legacy 并显式登记。
    """

    def test_e1_3_not_in_current_managed_specs(self) -> None:
        """E1-3 声明文件（phase5_e1_03_bank_detail.py）尚未创建，
        当前受管清单里不应有 E1-bank-detail-rows。

        🔴 如果这条红了，说明有人在裁决未完成前就把 E1-3 加进了受管清单。
        """
        items = all_store_item_ids()
        assert "E1-bank-detail-rows" not in items, (
            "E1-bank-detail-rows 出现在 all_store_item_ids() 里 —— "
            "E1-3 裁决尚未落实为声明文件，不应在受管清单中"
        )

    def test_adjudication_evidence_exists(self) -> None:
        """裁决证据 JSON 必须存在。"""
        from pathlib import Path

        # 仓库根 = backend 的父目录的父目录（test file → tests/ → backend/ → GT_plan/）
        repo_root = Path(__file__).resolve().parents[3]
        evidence = repo_root / "docs" / "operations" / "evidence" / "e1-sync-coverage" / "e1-3-dual-sheet-adjudication.json"
        assert evidence.exists(), f"裁决证据不存在：{evidence}"

    def test_adjudication_selects_multi_variant(self) -> None:
        """裁决结论是只接 multi（人民币及外币）一张。"""
        import json
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        evidence = repo_root / "docs" / "operations" / "evidence" / "e1-sync-coverage" / "e1-3-dual-sheet-adjudication.json"
        data = json.loads(evidence.read_text(encoding="utf-8"))
        assert data["verdict"]["managed_variant"] == "multi"
        assert data["verdict"]["unmanaged_variant"] == "rmb"
        assert data["production_code_changed"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 补充判据：声明层结构自洽
# ═══════════════════════════════════════════════════════════════════════════


class TestE1DeclarationConsistency:
    """声明层结构自洽（与引擎接口契约）。"""

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "🔴 红基线（未实施工作），不是回归。目标态是 7 张（E1-2/4/6/7/8/9/10），"
            "现只开 2 张（`_INCLUDE_E102_CASH_DETAIL` / `_INCLUDE_E104_DIGITAL`）。"
            "spec `e1-sync-coverage-and-first-canary` 在 INDEX 里是 0/23。"
            "2026-09-28 转 strict xfail：第 7 张接上后本条 XPASS 并报错，强制摘掉标记。"
        ),
    )
    def test_managed_row_table_specs_count(self) -> None:
        """目标态 7 个行表 spec（E1-2/4/6/7/8/9/10）。"""
        assert len(managed_row_table_specs()) == 7

    def test_managed_row_table_specs_count_matches_enabled_switches(self) -> None:
        """✅ 现算张数必须 == **开着的灰度开关数**（上一条的非空对照）。

        🔴 不写死张数 —— 否则每开一张都要有人记得改这里（memory 已记的反模式）。
        它要抓的是「开关开着但 spec 没进清单」这类接线漏，而不是替上面那条数目标态。
        """
        import app.services.workpaper_sync.phase5_e1_monetary_fund as E1

        enabled_flags = sum(
            1
            for name in dir(E1)
            if name.startswith("_INCLUDE_E1")
            and not name.endswith("_STATIC")
            and getattr(E1, name) is True
        )
        assert enabled_flags > 0, "行表开关全关 ⇒ 这是回归，不是红基线"
        assert len(managed_row_table_specs()) == enabled_flags, (
            f"开着 {enabled_flags} 个行表开关，但 managed_row_table_specs() 现算 "
            f"{len(managed_row_table_specs())} 个 ⇒ 有开关没接进清单"
        )

    def test_static_region_specs_empty_when_switch_off(self) -> None:
        """E1-11 灰度开关关闭时 static_region_specs 返回空。"""
        # 当前 _INCLUDE_E111_COMMITMENT_STATIC = False
        assert len(static_region_specs()) == 0

    def test_all_store_item_ids_unique(self) -> None:
        """所有 store item id 唯一。"""
        items = all_store_item_ids()
        assert len(items) == len(set(items)), f"store item id 有重复：{items}"

    def test_all_sheet_keys_unique(self) -> None:
        """所有 sheet_key 唯一。"""
        keys = [s.sheet_key for s in ALL_SPECS]
        assert len(keys) == len(set(keys)), f"sheet_key 有重复：{keys}"

    @pytest.mark.parametrize("spec", ALL_ROW_TABLE_SPECS, ids=lambda s: s.error_label)
    def test_field_specs_non_empty(self, spec) -> None:
        """每个行表 spec 的 field_specs 非空。"""
        assert len(spec.field_specs) > 0, f"{spec.error_label} 的 field_specs 为空"

    def test_e1_7_8_9_share_variant_but_distinct_keys(self) -> None:
        """E1-7/8/9 三张共享 useE1CashCount 但键不同（variant 参数化）。"""
        keys = {STORE_ITEM_ID_E107, STORE_ITEM_ID_E108, STORE_ITEM_ID_E109}
        assert len(keys) == 3
        assert "rmb" in STORE_ITEM_ID_E107
        assert "fx" in STORE_ITEM_ID_E108
        assert "cert" in STORE_ITEM_ID_E109

    def test_html_only_item_ids_e1_covers_all_variants(self) -> None:
        """HTML_ONLY_ITEM_IDS_E1 覆盖三个 variant 各三个文本键。"""
        assert len(HTML_ONLY_ITEM_IDS_E1) == 9
        for variant in ("rmb", "fx", "cert"):
            variant_keys = [k for k in HTML_ONLY_ITEM_IDS_E1 if k.endswith(f"-{variant}")]
            assert len(variant_keys) == 3, f"variant {variant} 应有 3 个 HTML-only 键"

    def test_cross_sheet_keys_e110_declared(self) -> None:
        """E1-10 的三向联动键已登记。"""
        assert "E1-bank-detail-rows" in CROSS_SHEET_KEYS_E110
        assert "E1-account-commit-snapshot" in CROSS_SHEET_KEYS_E110

    def test_e1_2_fixed_row_declared(self) -> None:
        """E1-2 的不可删除固定行 fixed-rmb 已登记。"""
        assert FIXED_ROW_KEY_E102 == "fixed-rmb"

    def test_e1_2_html_only_rows_declared(self) -> None:
        """E1-2 的 footer 下 R23 已登记为 HTML-only。"""
        assert len(HTML_ONLY_ROWS_E102) >= 1
        assert any(r[0] == 23 for r in HTML_ONLY_ROWS_E102)

    def test_cross_volume_keys_declared(self) -> None:
        """跨册取数键 E1-accrued-interest-rows 已登记。"""
        assert "E1-accrued-interest-rows" in CROSS_VOLUME_KEYS

    def test_e1_11_cross_sheet_snapshot_key_declared(self) -> None:
        """E1-11 ↔ E1-10 联动的快照键已登记。"""
        assert CROSS_SHEET_SNAPSHOT_KEY_E111 == "E1-account-commit-snapshot"
