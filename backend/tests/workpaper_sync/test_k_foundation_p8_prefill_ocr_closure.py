# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 1 Task 16 + 18~19：prefill / OCR / 四条收口。

spec: k-cycle-sync-foundation-and-first-canary
Task 16: KC-17 prefill 一致性断言（干净点，方向是「保持」）
Task 18: KC-19 OCR 两形态登记
Task 19: KC-20 + KC-21 + KC-22 + KC-23 四条收口
Property: KF-P38, KF-P40, KF-P41, KF-P42, KF-P57, KF-P63

═══ 本组的两个反向结论 ═══

1. ✅ **KC-17 是 K 的干净点**：51 条 prefill 的 sheet 名与模板真名
   **逐字一致 51/51**，含全部四类字符缺陷（带空格 / 半全混 / 全半角）。
   与 J 的「`审定表J1-1` 缺尾部空格必失配」形成鲜明对比 ⇒ 判据方向是
   **断言保持一致**，不是修。

2. 🔴 **KC-23 判据必须按资产负债 / 损益分支**：统一要求 `select_leaves`
   会假红 6 条损益 entry（K8~K13 走 `render_pl_cycle` → `pl_occurrence`）。
   且 42 个 `_k*.py` 须按「是否 import `k_cycle_specs`」筛，**不能按文件名前缀**
   （slice 首轮即因此把 `_k0_confirmation.py` 当损益侧 entry 打红）。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest
from openpyxl import load_workbook

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    BP5_INDEXES,
    BP6_INDEXES,
    DATA,
    K_INDEXES,
    NON_CONTRACT_FILES_IN_CONTRACT_DIR,
    ROOT,
    WP_COMPOSABLES,
    contract_dir_split,
    endpoint_index,
    k_domain_files,
    literal_hits,
)

K_TEMPLATE_DIR = ROOT / "backend" / "wp_templates" / "K"
PREFILL_PATH = DATA / "prefill_formula_mapping.json"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
RENDER_STRATEGY_DIR = ROOT / "backend" / "app" / "routers" / "wp_render_strategies"

EP_OCR_NO_WPID = "/api/d4/contract-ocr"
EP_OCR_WITH_WPID = "/api/workpapers/{X}/d4/contract-ocr"


@pytest.fixture(scope="module")
def k_files() -> list[pathlib.Path]:
    return k_domain_files()


@pytest.fixture(scope="module")
def prefill() -> dict:
    return json.loads(PREFILL_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def k_prefill_entries(prefill: dict) -> list[dict]:
    return [
        m for m in prefill["mappings"]
        if str(m.get("wp_code", "")).startswith("K")
    ]


@pytest.fixture(scope="module")
def template_sheet_names() -> dict[str, set[str]]:
    """{K0..K13: sheet 名集合}。"""
    out: dict[str, set[str]] = {}
    for f in sorted(K_TEMPLATE_DIR.iterdir()):
        if f.suffix != ".xlsx" or f.name.startswith("~$"):
            continue
        m = re.match(r"^(K\d+)", f.name)
        if not m:
            continue
        wb = load_workbook(f, read_only=True, data_only=True)
        out[m.group(1)] = set(wb.sheetnames)
        wb.close()
    return out


# ════════════════════════════════════════════════════════════════════════════
# Task 16 / KF-P38：prefill 一致性（K 的干净点）
# ════════════════════════════════════════════════════════════════════════════
class TestKFP38PrefillConsistency:
    """✅ KC-17：sheet 名 51/51 逐字一致 —— 方向是「断言保持」不是修。"""

    def test_k_prefill_entry_count_is_51(
        self, k_prefill_entries: list[dict]
    ) -> None:
        assert len(k_prefill_entries) == 51, (
            f"K 前缀 prefill 条目期望 51，实得 {len(k_prefill_entries)}"
        )

    def test_composition_is_13_adjudication_26_disclosure_12_other(
        self, k_prefill_entries: list[dict]
    ) -> None:
        """13 审定表 + 26 披露表（13 entry × 2 变体）+ 12 其他。"""
        adj = [m for m in k_prefill_entries if "审定表" in str(m.get("sheet", ""))]
        disc = [m for m in k_prefill_entries if "附注披露" in str(m.get("sheet", ""))]
        other = len(k_prefill_entries) - len(adj) - len(disc)
        assert len(adj) == 13, f"审定表期望 13，实得 {len(adj)}"
        assert len(disc) == 26, f"披露表期望 26（13×2 变体），实得 {len(disc)}"
        assert other == 12, f"其他期望 12，实得 {other}"

    def test_sheet_names_match_template_byte_for_byte(
        self,
        k_prefill_entries: list[dict],
        template_sheet_names: dict[str, set[str]],
    ) -> None:
        """🔴 KC-17 的核心：51/51 与模板真名**逐字一致**（含全部字符缺陷）。"""
        mismatch: list[tuple[str, str]] = []
        for m in k_prefill_entries:
            code = str(m.get("wp_code", ""))
            sheet = str(m.get("sheet", ""))
            book = re.match(r"^(K\d+)", code)
            if not book:
                continue
            bk = book.group(1)
            if bk in template_sheet_names and sheet not in template_sheet_names[bk]:
                mismatch.append((code, sheet))
        assert mismatch == [], (
            f"sheet 名失配 {len(mismatch)} 条：{mismatch[:5]}"
            " ⇒ K 的干净点失效，判据方向须从「保持」改为「修」"
        )

    def test_defective_sheet_names_are_carried_verbatim(
        self, k_prefill_entries: list[dict]
    ) -> None:
        """🔴 四类字符缺陷在 prefill 里**原样保留**（证明一致性不是靠归一化）。"""
        sheets = [str(m.get("sheet", "")) for m in k_prefill_entries]
        # 带半角空格
        with_space = [s for s in sheets if " " in s]
        assert with_space, "prefill 里没有带空格的 sheet 名 ⇒ 缺陷未原样保留"
        # 半/全角括号混用
        mixed = [
            s for s in sheets
            if ("(" in s and "）" in s) or ("（" in s and ")" in s)
        ]
        assert mixed, "prefill 里没有半/全混括号的 sheet 名 ⇒ 缺陷未原样保留"
        # K7 的「国有企业」
        guoyou = [s for s in sheets if "国有企业" in s]
        assert guoyou, "prefill 里没有「国有企业」⇒ K7 的独有形态未保留"

    def test_two_dead_cells_configs_are_registered(
        self, k_prefill_entries: list[dict]
    ) -> None:
        """🔴 2 条 `cells` 为空的死配置（K1 / K3 的明细表）。"""
        dead = [
            (str(m.get("wp_code")), str(m.get("wp_name")))
            for m in k_prefill_entries
            if not m.get("cells")
        ]
        assert len(dead) == 2, f"cells 为空的条目期望 2，实得 {len(dead)}：{dead}"
        codes = {c for c, _n in dead}
        assert codes == {"K1", "K3"}, f"死配置归属期望 K1/K3，实得 {sorted(codes)}"

    def test_k4_has_three_empty_account_codes(
        self, k_prefill_entries: list[dict]
    ) -> None:
        """🔴 K4 三条 `account_codes` 为空。"""
        empty = [
            str(m.get("wp_code"))
            for m in k_prefill_entries
            if not m.get("account_codes")
        ]
        assert len(empty) == 3, f"account_codes 空的期望 3 条，实得 {len(empty)}"
        assert set(empty) == {"K4"}, f"空科目码归属期望全 K4，实得 {sorted(set(empty))}"

    def test_account_codes_per_entry_match_design(
        self, k_prefill_entries: list[dict]
    ) -> None:
        """KC-17 的科目码现算（抽查几条关键的）。"""
        by_code: dict[str, set[str]] = {}
        for m in k_prefill_entries:
            code = str(m.get("wp_code", ""))
            for a in (m.get("account_codes") or []):
                by_code.setdefault(code, set()).add(str(a))
        expected = {
            "K2": {"1901"}, "K3": {"2241"}, "K5": {"2801"}, "K7": {"2401"},
            "K8": {"6601"}, "K9": {"6602"}, "K10": {"6117"}, "K11": {"6701"},
            "K12": {"6301"}, "K13": {"6711"},
        }
        for code, exp in expected.items():
            actual = by_code.get(code, set())
            assert exp <= actual, (
                f"{code}: 期望科目码含 {sorted(exp)}，实得 {sorted(actual)}"
            )


# ════════════════════════════════════════════════════════════════════════════
# Task 18 / KF-P40：OCR 两种 URL 形态（本身就是缺陷）
# ════════════════════════════════════════════════════════════════════════════
class TestKFP40OcrTwoUrlForms:
    """🔴 KC-19：同一能力两个契约面 ⇒ 缺陷，须统一。"""

    #: 🔴 改造前基线（append-only）。lane 2 已在其 Task 16 把本 lane 的 5 处
    #: 无 wpId 调用统一到含 wpId 形态 —— 那 5 处后端**没有注册路由**，是 404。
    BASELINE_NO_WPID_FILES = 7
    BASELINE_WITH_WPID_FILES = 3
    #: 已收敛（lane 2 的 5 个文件：K8 ×2 · K12 ×2 · K13 ×1）
    CONVERGED_FILES = 5

    def test_no_wpid_form_follows_the_convergence_ledger(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """现算 == 基线 7 − 已收敛 5 == 2（余下 2 处在 lane 1，归其 spec）。"""
        by_file, _hits = endpoint_index(k_files)
        live = len(by_file.get(EP_OCR_NO_WPID, set()))
        expected = self.BASELINE_NO_WPID_FILES - self.CONVERGED_FILES
        assert live == expected, (
            f"无 wpId 段：基线 {self.BASELINE_NO_WPID_FILES} − 已收敛 "
            f"{self.CONVERGED_FILES} = {expected}，实得 {live}"
        )

    def test_with_wpid_form_grew_by_the_converged_count(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 守恒：含 wpId 的涨幅 == 无 wpId 的降幅（是**迁移**不是删调用）。"""
        by_file, _ = endpoint_index(k_files)
        live = len(by_file.get(EP_OCR_WITH_WPID, set()))
        expected = self.BASELINE_WITH_WPID_FILES + self.CONVERGED_FILES
        assert live == expected, (
            f"含 wpId 段：基线 {self.BASELINE_WITH_WPID_FILES} + 已迁入 "
            f"{self.CONVERGED_FILES} = {expected}，实得 {live}"
        )

    def test_two_forms_total_is_conserved(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """两形态文件数合计恒等于基线合计 10（迁移不增不减）。"""
        by_file, _ = endpoint_index(k_files)
        total = len(by_file.get(EP_OCR_NO_WPID, set())) + len(
            by_file.get(EP_OCR_WITH_WPID, set())
        )
        assert total == self.BASELINE_NO_WPID_FILES + self.BASELINE_WITH_WPID_FILES
        assert total == 10

    def test_the_bare_form_has_no_backend_route(self) -> None:
        """🔴 收敛依据留档：无 wpId 形态后端从未注册 ⇒ 基线里那 7 处有 5 处是 404。"""
        routers = ROOT / "backend" / "app" / "routers"
        declared: list[str] = []
        for p in routers.rglob("*.py"):
            declared += re.findall(
                r"""@router\.post\(\s*['"]([^'"]*d4/contract-ocr)['"]""",
                p.read_text(encoding="utf-8", errors="ignore"),
            )
        assert declared, "后端找不到任何 d4/contract-ocr 路由"
        assert all("{wp_id}" in d for d in declared), (
            f"存在不带 wp_id 的注册 {declared} ⇒ 404 判定须复核"
        )

    def test_wide_caliber_is_12_files(self, k_files: list[pathlib.Path]) -> None:
        """宽口径 `contract-ocr` 12 文件（比两形态合计 10 多 2）。"""
        wide = literal_hits(k_files, "contract-ocr")
        assert len(wide) == 12, f"宽口径期望 12 文件，实得 {len(wide)}"

    def test_two_forms_are_disjoint(self, k_files: list[pathlib.Path]) -> None:
        """两形态的文件集合不相交（同一文件不会两种都用）。"""
        by_file, _ = endpoint_index(k_files)
        a = by_file.get(EP_OCR_NO_WPID, set())
        b = by_file.get(EP_OCR_WITH_WPID, set())
        assert a & b == set(), f"两形态共用文件：{sorted(a & b)}"

    def test_run_ocr_and_ocr_confirm_calibers(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """`runOcr` 4 文件 / `OcrConfirm` 0 文件。"""
        assert len(literal_hits(k_files, "runOcr")) == 4
        assert len(literal_hits(k_files, "OcrConfirm")) == 0

    def test_inconsistency_itself_is_the_defect(
        self, k_files: list[pathlib.Path]
    ) -> None:
        """🔴 两种 URL 形态并存本身是缺陷（同一能力两个契约面）。"""
        by_file, _ = endpoint_index(k_files)
        a = by_file.get(EP_OCR_NO_WPID, set())
        b = by_file.get(EP_OCR_WITH_WPID, set())
        assert a and b, (
            "只剩一种形态 ⇒ KC-19 的缺陷已被统一，登记须更新"
        )
        assert len(a) + len(b) == 10


# ════════════════════════════════════════════════════════════════════════════
# Task 19 / KF-P41：KC-20 per-row 孤儿键判据（缺陷归 lane 1）
# ════════════════════════════════════════════════════════════════════════════
class TestKFP41OrphanPerRowKeyCriterion:
    """KC-20：per-row 键的 rowId 集合 SHALL ⊆ 主键载荷 rowId 集合。"""

    def test_criterion_is_a_subset_relation(self) -> None:
        """判据形状：子集关系（可对任意载荷复算）。"""
        primary = {"r-ls0ldh", "r-5ac9vk"}
        per_row = {"r-ls0ldh", "r-5ac9vk", "r-ryx6og", "r-yqfa02"}
        orphans = per_row - primary
        assert orphans == {"r-ryx6og", "r-yqfa02"}, (
            "孤儿判据的示例计算不符 ⇒ 判据形状写错了"
        )
        assert not (per_row <= primary), "示例应违反子集关系"

    def test_k2_adjudication_sheet_exists_as_the_carrier(
        self, template_sheet_names: dict[str, set[str]]
    ) -> None:
        """`审定表K2-1` 存在（孤儿键的宿主表）。"""
        assert "K2" in template_sheet_names
        assert any("审定表K2-1" in s for s in template_sheet_names["K2"]), (
            f"找不到审定表K2-1：{sorted(template_sheet_names['K2'])}"
        )

    def test_cleanup_must_not_delete_valued_keys(self) -> None:
        """🔴 清理动作不得误删有值的 4 个键（真库实测金额）。"""
        valued = {
            "K2-1-r-ls0ldh-begin": "-732505.4",
            "K2-1-r-ls0ldh-unadj": "-1312178.93",
            "K2-1-r-5ac9vk-begin": "-377709.19",
            "K2-1-r-5ac9vk-unadj": "-406014.85",
        }
        empty = {
            "K2-1-r-ryx6og-begin": "",
            "K2-1-r-ryx6og-unadj": "",
            "K2-1-r-yqfa02-begin": "",
            "K2-1-r-yqfa02-unadj": "",
        }
        # 判据：只删值为空串且 rowId 不在主键载荷里的
        assert all(v for v in valued.values()), "有值的 4 键示例不应为空"
        assert all(not v for v in empty.values()), "孤儿的 4 键示例应为空串"
        assert set(valued) & set(empty) == set()


# ════════════════════════════════════════════════════════════════════════════
# Task 19 / KF-P42：KC-21 审定表K2-1 是纯派生表
# ════════════════════════════════════════════════════════════════════════════
class TestKFP42K2AdjudicationIsPurelyDerived:
    """🔴 KC-21：OO 侧无任何用户输入位 ⇒ 写回方向空转，不得作 canary。"""

    @pytest.fixture(scope="class")
    def k2_sheet(self):
        wb = load_workbook(
            K_TEMPLATE_DIR / "K2 其他流动资产.xlsx", read_only=False, data_only=False
        )
        sn = next((s for s in wb.sheetnames if "审定表K2-1" in s), None)
        assert sn, f"找不到审定表K2-1：{wb.sheetnames}"
        yield wb[sn]
        wb.close()

    def test_geometry_is_r23_c16_merged9(self, k2_sheet) -> None:
        assert k2_sheet.max_row == 23, f"r 期望 23，实得 {k2_sheet.max_row}"
        assert k2_sheet.max_column == 16, f"c 期望 16，实得 {k2_sheet.max_column}"
        assert len(k2_sheet.merged_cells.ranges) == 9, (
            f"merged 期望 9，实得 {len(k2_sheet.merged_cells.ranges)}"
        )

    def test_data_rows_r7_to_r13_have_formula_even_in_column_a(
        self, k2_sheet
    ) -> None:
        """🔴 数据区 R7:R13 **连 A 列项目名都是** `='明细表K2-2'!A{n}`。"""
        for r in range(7, 14):
            v = k2_sheet.cell(row=r, column=1).value
            assert isinstance(v, str) and v.startswith("="), (
                f"A{r} 不是公式：{v!r} ⇒ 「连 A 列都是公式」的登记失效"
            )
            assert "明细表K2-2" in v, (
                f"A{r} 的公式不引明细表K2-2：{v!r}"
            )
            assert re.match(r"^='明细表K2-2'!A\d+$", v), (
                f"A{r} 公式形态不符：{v!r}"
            )

    def test_r5_headers_contain_in_cell_newlines(self, k2_sheet) -> None:
        """🔴 R5 的 J5/L5 含**单元格内换行符** ⇒ 三边比对须逐格字节。"""
        for col, coord in ((10, "J5"), (12, "L5")):
            v = k2_sheet.cell(row=5, column=col).value
            assert isinstance(v, str), f"{coord} 不是字符串：{v!r}"
            assert "\n" in v, (
                f"{coord} 不含换行符：{v!r}"
                " ⇒ 「禁 strip、禁全半角归一」的依据失效"
            )

    def test_r14_is_blank_and_r15_sum_includes_it(self, k2_sheet) -> None:
        """R14 空行 + R15 `=SUM(B7:B14)` 含空行 ⇒ KC-12 正常形态不是缺陷。"""
        assert k2_sheet.cell(row=14, column=2).value is None, (
            "R14 的 B 列非空 ⇒ 「空行预留」的登记失效"
        )
        b15 = k2_sheet.cell(row=15, column=2).value
        assert isinstance(b15, str) and "SUM(" in b15.upper()
        m = re.search(r"SUM\(B(\d+):B(\d+)\)", b15)
        assert m, f"B15 的 SUM 区间解析失败：{b15!r}"
        lo, hi = int(m.group(1)), int(m.group(2))
        assert lo <= 14 <= hi, (
            f"SUM 区间 B{lo}:B{hi} 不含空行 14 ⇒ 与登记矛盾"
        )

    def test_no_user_input_cell_in_data_region(self, k2_sheet) -> None:
        """🔴 数据区无任何用户输入位（全是公式或空）⇒ 写回方向空转。"""
        non_formula: list[str] = []
        for r in range(7, 14):
            for c in range(1, 17):
                cell = k2_sheet.cell(row=r, column=c)
                v = cell.value
                if v is None:
                    continue
                if isinstance(v, str) and v.startswith("="):
                    continue
                non_formula.append(f"{cell.coordinate}={v!r}")
        assert non_formula == [], (
            f"数据区有非公式非空单元格 {non_formula[:5]}"
            " ⇒ 「OO 侧无输入位」的登记失效，可能可作 canary"
        )

    def test_must_not_be_chosen_as_canary(self) -> None:
        """🔴 不得选此类表作 canary（这是否决 K2-1-rows 的第三条理由）。"""
        # canary 的 entry 是 K10，不是 K2
        slice_doc = json.loads(
            (DATA / "workpaper_sync_k_cycle_manifest_slice.json").read_text(
                encoding="utf-8"
            )
        )
        k2 = next(
            e for e in slice_doc["independent_entries"]
            if e["entry_id"] == "xlsx/gt-k2-other-current-assets"
        )
        # K2 属 BP-5 组（lane 1），不是 foundation 的 canary entry
        assert "BP-5" in k2["capability_target_blocked_by"], (
            "K2 不属 BP-5 组 ⇒ 切分表须复核"
        )


# ════════════════════════════════════════════════════════════════════════════
# Task 19 / KF-P57：KC-22③ 契约与 adapter 分母分开算
# ════════════════════════════════════════════════════════════════════════════
class TestKFP57ContractVsAdapterDenominators:
    """🔴 KC-22③：「契约已发」≠「adapter 已注册」，两个分母混用必算错。"""

    def test_contract_directory_counts(self) -> None:
        """🔴 口径勘误：契约目录里的文件**不全是契约**。

        原判据写 `reviewed + candidate == len(files)`，前提是「目录里每个 `*.json`
        都是契约」。现算该前提不成立 —— 并发的 L 循环 spec 把一张键映射表
        （无 `review_status`、不是任何 `{adapter_id}.json`）放进了同一目录。
        生产侧不受影响（按精确文件名取 / 按 `review_status` 筛），但按「全是契约」
        写的判据会被它打红，而红的原因与 K 循环无关。

        ⇒ 分母改为「契约文件」而非「目录文件」，差集用可伪证白名单锁住。
        """
        files = sorted(CONTRACT_DIR.glob("*.json"))
        assert files, "契约目录为空 ⇒ 分母塌了"
        contracts, others = contract_dir_split()
        reviewed = sum(
            1 for d in contracts.values() if d.get("review_status") == "reviewed"
        )
        candidate = sum(
            1 for d in contracts.values() if d.get("review_status") == "candidate"
        )
        assert candidate >= 1, (
            "candidate 反例分母为空 ⇒ 「candidate 不得进生产」这条判据没有对象"
        )
        assert reviewed >= 20, f"reviewed 契约只有 {reviewed} 份 ⇒ 分母异常"
        assert reviewed + candidate == len(contracts), (
            f"契约文件的 review_status 既非 reviewed 也非 candidate："
            f"{sorted(set(contracts) - {k for k, v in contracts.items() if v.get('review_status') in ('reviewed', 'candidate')})}"
        )
        assert len(contracts) + len(others) == len(files), "两类之和不等于目录文件数"

    def test_non_contract_whitelist_is_exact_and_falsifiable(self) -> None:
        """🔴 白名单必须可伪证：成员真的不是契约 + 名单里没有失效条目。

        只写一句理由的名单 = 加一行就变绿的后门（方法论铁律 ㉗⑤）。这里对每个成员
        实打实验三件事：① 真的没有 `review_status` ② 真的不是任何 adapter 的
        `{adapter_id}.json`（`load_contract` 取不到）③ 文件真的还在。
        """
        from app.services.workpaper_sync.contracts import load_contract

        _contracts, others = contract_dir_split()
        assert set(others) == set(NON_CONTRACT_FILES_IN_CONTRACT_DIR), (
            f"非契约文件集变了：多 {sorted(set(others) - set(NON_CONTRACT_FILES_IN_CONTRACT_DIR))}，"
            f"少 {sorted(set(NON_CONTRACT_FILES_IN_CONTRACT_DIR) - set(others))}"
        )
        for name in NON_CONTRACT_FILES_IN_CONTRACT_DIR:
            p = CONTRACT_DIR / name
            assert p.exists(), f"白名单条目 {name} 已不存在 ⇒ 名单须删该行"
            doc = json.loads(p.read_text(encoding="utf-8"))
            assert doc.get("review_status") is None, (
                f"{name} 现在有 review_status 了 ⇒ 它成了契约，须移出白名单"
            )
            with pytest.raises(Exception):
                load_contract(name.removesuffix(".json"))

    def test_the_whitelist_is_not_vacuous(self) -> None:
        """🔴 反向：白名单非空且**确实**在起作用（去掉它判据就会红）。"""
        assert len(NON_CONTRACT_FILES_IN_CONTRACT_DIR) >= 1, (
            "白名单为空 ⇒ 若目录里真没有非契约文件，应把本组判据删掉而不是留空名单"
        )
        _contracts, others = contract_dir_split()
        assert others, "目录里已无非契约文件 ⇒ 白名单与本判据一并删除"

    def test_adapter_id_non_null_count_is_smaller_than_reviewed(self) -> None:
        """🔴 adapter_id 非空的 entry 数**远小于** reviewed 契约数。"""
        manifest = json.loads(FULL_MANIFEST_PATH.read_text(encoding="utf-8"))
        non_null = [e["entry_id"] for e in manifest["entries"] if e.get("adapter_id")]
        files = sorted(CONTRACT_DIR.glob("*.json"))
        reviewed = sum(
            1 for p in files
            if json.loads(p.read_text(encoding="utf-8")).get("review_status") == "reviewed"
        )
        assert len(non_null) < reviewed, (
            f"adapter_id 非空 {len(non_null)} 不小于 reviewed 契约 {reviewed}"
            " ⇒ 「契约已发 ≠ adapter 已注册」这条登记须撤"
        )
        assert len(non_null) >= 5, f"adapter_id 非空只有 {len(non_null)} 条 ⇒ 分母异常"

    def test_manifest_has_no_adapter_registered_field(self) -> None:
        """🔴 manifest **根本没有** `adapter_registered` 字段 ⇒ 按它判会恒得 0。"""
        manifest = json.loads(FULL_MANIFEST_PATH.read_text(encoding="utf-8"))
        has_field = [
            e["entry_id"] for e in manifest["entries"]
            if "adapter_registered" in e
        ]
        assert has_field == [], (
            f"manifest 出现了 adapter_registered 字段：{has_field[:3]}"
            " ⇒ 判据可改用该字段，本条登记须更新"
        )

    def test_no_k_entry_has_an_adapter(self) -> None:
        """K 循环 adapter_id 非空的 entry **恰好**等于晋级账本（2026-10-01 起 5 条）。"""
        from tests.workpaper_sync.k_foundation_facts import (
            k_expected_manifest_adapters,
            k_manifest_adapters,
        )

        manifest = json.loads(FULL_MANIFEST_PATH.read_text(encoding="utf-8"))
        assert k_manifest_adapters(manifest) == k_expected_manifest_adapters()


# ════════════════════════════════════════════════════════════════════════════
# Task 19 / KF-P63：KC-23 科目四表判据按资产负债 / 损益分支
# ════════════════════════════════════════════════════════════════════════════
class TestKFP63FourTableBranchByBalanceOrPl:
    """🔴 KC-23：统一要求 `select_leaves` 会假红 6 条损益 entry。"""

    @pytest.fixture(scope="class")
    def k_strategies(self) -> list[pathlib.Path]:
        return sorted(RENDER_STRATEGY_DIR.glob("_k*.py"))

    def test_42_k_strategy_files(self, k_strategies: list[pathlib.Path]) -> None:
        assert len(k_strategies) == 42, (
            f"_k*.py 期望 42 个，实得 {len(k_strategies)}"
        )

    def test_13_main_strategies_import_k_cycle_specs(
        self, k_strategies: list[pathlib.Path]
    ) -> None:
        """🔴 按「是否 import `k_cycle_specs`」筛出 13 个主策略，**不按文件名前缀**。"""
        with_specs = [
            p.name for p in k_strategies
            if "k_cycle_specs" in p.read_text(encoding="utf-8")
        ]
        assert len(with_specs) == 13, (
            f"import k_cycle_specs 的期望 13 个，实得 {len(with_specs)}：{with_specs}"
        )

    def test_k0_strategies_do_not_import_k_cycle_specs(
        self, k_strategies: list[pathlib.Path]
    ) -> None:
        """🔴 3 个 K0 策略不 import `k_cycle_specs`（按文件名前缀筛会把它们打红）。"""
        k0 = [p for p in k_strategies if p.name.startswith("_k0")]
        assert len(k0) == 3, f"K0 策略期望 3 个，实得 {[p.name for p in k0]}"
        for p in k0:
            assert "k_cycle_specs" not in p.read_text(encoding="utf-8"), (
                f"{p.name} import 了 k_cycle_specs ⇒ 它会被误当损益侧 entry"
            )

    def test_balance_side_7_entries_use_select_leaves(
        self, k_strategies: list[pathlib.Path]
    ) -> None:
        """资产负债侧 K1~K7（7 条）用 `select_leaves`。"""
        with_sl = {
            p.name for p in k_strategies
            if "select_leaves" in p.read_text(encoding="utf-8")
        }
        assert len(with_sl) == 7, (
            f"含 select_leaves 的期望 7 个，实得 {sorted(with_sl)}"
        )
        # 逐条对应 K1~K7
        for n in BP5_INDEXES:
            matched = [f for f in with_sl if re.match(rf"^_k{n}(?![0-9])_", f)]
            assert matched, f"K{n} 的策略不含 select_leaves"

    def test_pl_side_6_entries_use_render_pl_cycle(
        self, k_strategies: list[pathlib.Path]
    ) -> None:
        """🔴 损益侧 K8~K13（6 条）走 `render_pl_cycle` / `pl_occurrence`。

        它们的 `select_leaves` 命中 **0 是正确的** —— 统一要求会假红。
        """
        with_pl = {
            p.name for p in k_strategies
            if "render_pl_cycle" in p.read_text(encoding="utf-8")
            or "pl_occurrence" in p.read_text(encoding="utf-8")
        }
        assert len(with_pl) == 6, (
            f"含 render_pl_cycle/pl_occurrence 的期望 6 个，实得 {sorted(with_pl)}"
        )
        for n in BP6_INDEXES:
            matched = [f for f in with_pl if re.match(rf"^_k{n}(?![0-9])_", f)]
            assert matched, f"K{n} 的策略不含 render_pl_cycle/pl_occurrence"

    def test_unified_select_leaves_criterion_would_falsely_red_6_pl_entries(
        self, k_strategies: list[pathlib.Path]
    ) -> None:
        """🔴 反证：统一要求 `select_leaves` 的假红集合恰好是 6 条损益 entry。"""
        main = [
            p for p in k_strategies
            if "k_cycle_specs" in p.read_text(encoding="utf-8")
        ]
        assert len(main) == 13
        failing = [
            p.name for p in main
            if "select_leaves" not in p.read_text(encoding="utf-8")
        ]
        assert len(failing) == 6, (
            f"假红集合应恰好 6 条损益 entry，实得 {len(failing)}：{failing}"
            " —— 这条反证保证 KC-23 的分支判据不是多余的"
        )

    def test_balance_and_pl_partition_the_13(
        self, k_strategies: list[pathlib.Path]
    ) -> None:
        """7 + 6 == 13，且两集合不相交。"""
        with_sl = {
            p.name for p in k_strategies
            if "select_leaves" in p.read_text(encoding="utf-8")
        }
        with_pl = {
            p.name for p in k_strategies
            if "render_pl_cycle" in p.read_text(encoding="utf-8")
            or "pl_occurrence" in p.read_text(encoding="utf-8")
        }
        assert with_sl & with_pl == set(), (
            f"两侧共用策略：{sorted(with_sl & with_pl)}"
        )
        assert len(with_sl) + len(with_pl) == 13

    def test_13_frontend_account_scope_files_exist(self) -> None:
        """13 个 `k{n}AccountScope.ts` 全存。"""
        scopes = sorted(WP_COMPOSABLES.glob("k*AccountScope.ts"))
        names = {p.name for p in scopes}
        assert len(names) == 13, f"AccountScope 期望 13 个，实得 {sorted(names)}"
        for n in K_INDEXES:
            assert f"k{n}AccountScope.ts" in names, f"缺 k{n}AccountScope.ts"

    def test_account_scope_uses_tb_source_codes_at_runtime(self) -> None:
        """范式：运行态取 render 下发的 `tb_source_codes.gross_standard`。"""
        p = WP_COMPOSABLES / "k2AccountScope.ts"
        assert p.exists()
        src = p.read_text(encoding="utf-8")
        assert "tb_source_codes" in src or "gross_standard" in src, (
            "k2AccountScope.ts 不引 tb_source_codes/gross_standard ⇒ 范式登记须更新"
        )
