"""Tests for G-cycle prefill_formula_mapping.json extension (Sprint 2 Task 2.27)

Validates: Requirements G-F10
- G-cycle 总 cells ≥ 134（baseline 74 + 新增 ≥ 60，Sprint 0.X 降级目标 ≥ 60）
- 4-arg AUX 校验：=AUX 公式必须有 4 个参数（account, aux_type, aux_code, column）
- 真实 sheet 名校验：明细表G7-2 / 明细表G1-2 / 明细表G6-2 等（design.md ADR-G4 实测）
- **G7 禁止**硬编码项目专属客户码的 =AUX（原「唯一保留真实链路」已反转，见
  :class:`TestG7AuxLinkage` docstring）；逐户明细改由 render 侧动态归集
- **G7 禁止**点号子科目 ``TB('1511.0x',...)``（恒返 0 且不报错，改 PLACEHOLDER）
- G6 使用 ``1506``（其他债权投资），**不是** 1505（= 债权投资减值准备，report_config
  BS-022 偏移错码）
- G1/G4/G8/G11/G13/G14 全部使用 =TB / =LEDGER / =WP / =ADJ / =PREV（无 =AUX）
- 各 sheet cell 数**精确**锁死（双向），被删错码 cell 配 stale 检测

Spec: workpaper-g-investment-cycle / Sprint 2 / Task 2.27
      + g-cycle-extraction-mapping-and-disclosure-alignment（2026-08-08 修正过时断言）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


DATA_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "prefill_formula_mapping.json"
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def mappings() -> list[dict]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["mappings"]


@pytest.fixture(scope="module")
def g_entries(mappings) -> list[dict]:
    """所有 wp_code 以 G 开头的 entry"""
    return [e for e in mappings if (e.get("wp_code") or "").startswith("G")]


@pytest.fixture(scope="module")
def g_cells(g_entries) -> list[dict]:
    """所有 G entry 的 cells 平铺"""
    out = []
    for entry in g_entries:
        for c in entry.get("cells", []):
            out.append({
                "wp_code": entry["wp_code"],
                "sheet": entry["sheet"],
                **c,
            })
    return out


# ─── Test 1: G cycle 总 cell 数 ≥ 134 (74 baseline + ≥ 60 new) ───────────────


class TestGCycleCellCounts:
    def test_total_g_cells_at_least_134(self, g_cells):
        """G 循环总 cell 数 ≥ 134（Sprint 0.X 降级目标：74 + ≥ 60）"""
        assert len(g_cells) >= 134, (
            f"Expected ≥134 G cells, got {len(g_cells)}"
        )

    def test_g_entries_at_least_24(self, g_entries):
        """G entry 数 ≥ 24（baseline 16 + 至少 8 个新 (wp_code, sheet) 组合）"""
        assert len(g_entries) >= 24, (
            f"Expected ≥24 G entries, got {len(g_entries)}"
        )


# ─── Test 2: 真实 sheet 名验证（design.md ADR-G4 openpyxl 实测）──────────────


class TestRealSheetNames:
    """sheet 名必须用 openpyxl 实测的真实名称（铁律：禁止臆造）"""

    EXPECTED_SHEETS = {
        # design.md ADR-G4 实测真实 sheet 名（task 0x.2 落地）
        "明细表G1-2",
        "明细表G4-2",
        "明细表G6-2",
        "明细表G7-2",
        "明细表G8-2",
        # G11/G13/G14 明细分析 (Sprint 2 Task 2.25 创建)
        "明细分析表G11-2",
        "明细分析表G13-2",
        "明细分析表G14-2",
    }

    def test_real_sheet_names_present(self, g_entries):
        """新增 entry 的 sheet 名应在 design.md ADR-G4 实测清单内"""
        actual_sheets = {e["sheet"] for e in g_entries}
        missing = self.EXPECTED_SHEETS - actual_sheets
        assert not missing, (
            f"design.md ADR-G4 实测 sheet 名缺失: {missing}"
        )

    def test_no_invented_sheet_names(self, g_entries):
        """sheet 名不应含臆造 placeholder（如 'TBD' / 'placeholder'）"""
        for e in g_entries:
            sheet = e["sheet"].lower()
            assert "tbd" not in sheet, f"placeholder sheet 名: {e['sheet']}"
            assert "placeholder" not in sheet, f"placeholder sheet 名: {e['sheet']}"


# ─── Test 3: 4-arg =AUX 校验（强制铁律）───────────────────────────────────────


class TestAuxFormulaArgCount:
    """=AUX 公式必须严格 4-arg（account_code, aux_type, aux_code, column）"""

    def test_aux_formulas_have_exactly_4_args(self, g_cells):
        """=AUX(arg1,arg2,arg3,arg4) — 逗号数必须 == 3 → 4 个参数"""
        aux_cells = [c for c in g_cells if c["formula"] and c["formula"].startswith("=AUX(")]
        for c in aux_cells:
            formula = c["formula"]
            # 提取 () 内部字符串，按逗号计数
            inner = formula[len("=AUX("):].rsplit(")", 1)[0]
            arg_count = len([a.strip() for a in inner.split(",") if a.strip()])
            assert arg_count == 4, (
                f"=AUX 必须 4 args, 实际 {arg_count} args: "
                f"wp_code={c['wp_code']}, sheet={c['sheet']}, "
                f"cell_ref={c['cell_ref']}, formula={formula}"
            )

    def test_aux_args_quoted_strings(self, g_cells):
        """=AUX 各参数必须用单引号包裹（与现有 D2 客户明细表风格一致）"""
        aux_cells = [c for c in g_cells if c["formula"] and c["formula"].startswith("=AUX(")]
        for c in aux_cells:
            formula = c["formula"]
            inner = formula[len("=AUX("):].rsplit(")", 1)[0]
            args = [a.strip() for a in inner.split(",")]
            for arg in args:
                assert arg.startswith("'") and arg.endswith("'"), (
                    f"=AUX 参数应单引号包裹: {formula}"
                )


# ─── Test 4: G7 唯一保留 =AUX 真实链路（≥ 5 个 1511.01 客户 aux_code）────────


class TestG7AuxLinkage:
    """G7 的 ``=AUX`` 链路契约。

    🔴 2026-08-08 断言方向反转（原断言锁定的是**已被正确删除**的旧行为）
    ------------------------------------------------------------------
    早期版本给 G7 ``明细表G7-2`` 预设了 5 条 ``=AUX('1511.01','客户','007960',...)``，
    aux_code 是**某个真实项目的具体客户编号**。它们已由
    ``backend/scripts/fix/fix_g_cycle_prefill_presets.py`` 删除，依据是平台铁律
    「避免硬编码」—— 项目专属客户编码写进**跨项目共享**的预设文件后：

    1. 在别的项目上该公式恒空（客户码不存在），与「该客户余额为 0」不可区分；
    2. 客户编码是客户账套的私有标识，属数据污染（同 H2 已修的
       ``AUX('1604','项目名称','B510003',...)`` 范式）。

    逐户明细的正解 = render 侧按 ``tb_aux_balance`` 的 ``aux_type='客户'`` 动态归集
    （灰度 ``G7_FOUR_TABLE_EXTRACTION_ENABLED``），不在预设里写死任何客户码。

    故原 ``test_g7_has_aux_cells``（要求 ≥5 条）与 ``test_g7_aux_codes_are_real_samples``
    （要求 ≥5 个 aux_code 命中实测样本集）**都是在要求把污染写回来**，已反转为禁令。
    """

    #: 早期预设里写死过的项目专属客户编码 —— 现在是**禁止出现**的黑名单。
    #: 保留常量是为了让反转后的断言能精确指名，而不是笼统禁所有 AUX。
    FORBIDDEN_PROJECT_AUX_CODES = {
        "007960", "014127", "014747", "019378", "050645",
    }

    def test_g7_has_no_hardcoded_project_aux_codes(self, g_cells):
        """G7 预设不得出现项目专属客户编码（跨项目共享文件禁硬编码）。"""
        offenders: list[str] = []
        for c in g_cells:
            if c["wp_code"] != "G7":
                continue
            blob = f"{c.get('formula') or ''} {c.get('description') or ''}"
            for code in self.FORBIDDEN_PROJECT_AUX_CODES:
                if f"'{code}'" in blob:
                    offenders.append(
                        f"{c['sheet']}/{c['cell_ref']}: {c.get('formula')}"
                    )
                    break
        assert not offenders, (
            "G7 预设含项目专属客户编码（应由 render 侧 tb_aux_balance 动态归集）:\n  "
            + "\n  ".join(offenders)
        )

    def test_forbidden_aux_code_blacklist_is_not_empty(self):
        """反向自检：黑名单非空，否则上一条断言退化为空转。"""
        assert len(self.FORBIDDEN_PROJECT_AUX_CODES) >= 5

    def test_g7_aux_uses_1511_01(self, g_cells):
        """G7 =AUX 必须使用 account_code='1511.01'"""
        g7_aux = [
            c for c in g_cells
            if c["wp_code"] == "G7"
            and c["formula"]
            and c["formula"].startswith("=AUX(")
        ]
        for c in g7_aux:
            assert "'1511.01'" in c["formula"], (
                f"G7 =AUX 应使用 '1511.01' account_code: {c['formula']}"
            )

    def test_g7_aux_uses_kehu_aux_type(self, g_cells):
        """G7 =AUX 必须使用 aux_type='客户'（Sprint 0.X 实测唯一可用维度）"""
        g7_aux = [
            c for c in g_cells
            if c["wp_code"] == "G7"
            and c["formula"]
            and c["formula"].startswith("=AUX(")
        ]
        for c in g7_aux:
            assert "'客户'" in c["formula"], (
                f"G7 =AUX 应使用 '客户' aux_type: {c['formula']}"
            )

    def test_g7_detail_sheet_has_no_dot_subaccount_tb(self, g_cells):
        """G7 明细表不得用 ``TB('1511.0x', ...)`` 取数（恒返 0 且不报错）。

        实证：``formula_engine._handle_tb`` 从 ``ctx.tb_data`` 按**标准码**取值
        （余额来自 ``trial_balance``），而 ``trial_balance`` 的 151x 段只有
        ``1511`` / ``1512`` / ``1519`` —— 点号子科目只存在于 ``tb_balance``
        （客户原始码体系）⇒ 键查不到返 0；且「期末余额」是已注册列故不进
        ``errors``，使「取不到」与「余额确实为 0」不可区分。
        真源 = render 的 ``tb_leaf_categories`` / ``adjudication_prefill``。
        """
        offenders: list[str] = []
        for c in g_cells:
            if c["wp_code"] != "G7":
                continue
            f = c.get("formula") or ""
            if re.search(r"=TB\('\d+\.\d+'", f):
                offenders.append(f"{c['sheet']}/{c['cell_ref']}: {f}")
        assert not offenders, (
            "G7 预设含点号子科目 TB() 取数（恒返 0 且不报错，须改 PLACEHOLDER）:\n  "
            + "\n  ".join(offenders)
        )

    def test_g7_detail_placeholder_cells_present(self, g_cells):
        """正向锁死：那 7 个格子必须是 ``PLACEHOLDER`` 且 description 写明真源。"""
        expected = {
            "子科目_1511_01_期初",
            "子科目_1511_01_期末",
            "子科目_1511_02_期末",
            "子科目_1511_03_期末",
            "子科目_1511_04_期末",
            "子科目_1511_04_01_期末",
            "子科目_1511_04_02_期末",
        }
        found: dict[str, dict] = {
            c["cell_ref"]: c
            for c in g_cells
            if c["wp_code"] == "G7" and c["sheet"] == "明细表G7-2"
            and c["cell_ref"] in expected
        }
        missing = expected - set(found)
        assert not missing, f"明细表G7-2 缺失子科目格: {missing}"
        for ref, cell in sorted(found.items()):
            assert cell.get("formula_type") == "PLACEHOLDER", (
                f"{ref} formula_type 应为 PLACEHOLDER，实际 {cell.get('formula_type')}"
            )
            desc = str(cell.get("description") or "")
            assert "tb_leaf_categories" in desc, (
                f"{ref} description 必须写明真源 tb_leaf_categories（防 PLACEHOLDER 变逃逸阀）"
            )
            assert len(desc) >= 40, f"{ref} description 过短（{len(desc)} 字），须含实证依据"


# ─── Test 5: G6 不再含 =AUX（2026-08-01 纠错：1531 是长期应收款非 G6 科目）───


class TestG6PartialAux:
    """G6 科目码契约，旧 1531.02 AUX 硬编码已删除。

    🔴 2026-08-08 修正：原 ``test_g6_uses_1505`` 锁定的是**错码**。
    ``report_config`` 的 ``BS-022/BS-025/BS-026`` 连续偏移一位（平台在 1504 与 1506
    之间插了 ``1505 债权投资减值准备``），实证：
    ``1505`` = 债权投资减值准备（**G4 的备抵**）/ ``1506`` = 其他债权投资（**G6 原值**）。
    幂等脚本 ``fix_g_cycle_prefill_presets.py`` 的 ``CODE_REMAP['G6'] = {'1505': '1506'}``
    已纠正，本断言随之改为要求 ``1506``（并反向禁止 ``1505`` 回潮）。
    """

    def test_g6_has_no_aux(self, g_cells):
        g6_aux = [
            c for c in g_cells
            if c["wp_code"] == "G6"
            and c["formula"]
            and c["formula"].startswith("=AUX(")
        ]
        assert len(g6_aux) == 0, (
            f"G6 不应含 =AUX cell（1531 是长期应收款非 G6 科目）, 实际 {len(g6_aux)}"
        )

    def test_g6_uses_1506_not_1505(self, g_cells):
        g6_tb = [
            c for c in g_cells
            if c["wp_code"] == "G6"
            and c["formula"]
            and c["formula"].startswith("=TB(")
        ]
        assert g6_tb, "G6 应有 =TB 预设（若为 0 则本断言空转）"
        for c in g6_tb:
            assert "'1505'" not in c["formula"], (
                f"G6 不得用 '1505'（= 债权投资减值损失/G4 备抵，report_config BS-022 偏移错码）: "
                f"{c['formula']}"
            )
            assert "'1506'" in c["formula"], (
                f"G6 =TB 应使用 '1506'（其他债权投资）: {c['formula']}"
            )


# ─── Test 6: G1/G4/G8/G11/G13/G14 不含 =AUX（仅 =TB/=LEDGER/=WP/=ADJ/=PREV）─


class TestNonG7G6CyclesNoAux:
    """G1/G4/G8/G11/G13/G14 子循环（无 aux 数据）不应含 =AUX 公式"""

    NO_AUX_WP_CODES = {"G1", "G4", "G8", "G11", "G13", "G14"}

    def test_no_aux_in_other_g_cycles(self, g_cells):
        """1101/1501/1521-1527 均无 tb_aux_balance 数据，prefill 必须降级为 =TB/=LEDGER/=WP"""
        for c in g_cells:
            if c["wp_code"] in self.NO_AUX_WP_CODES:
                if c["formula"] is not None:
                    assert not c["formula"].startswith("=AUX("), (
                        f"{c['wp_code']} 不应含 =AUX cell（Sprint 0.X 实测无 aux 数据）: "
                        f"sheet={c['sheet']}, cell_ref={c['cell_ref']}, formula={c['formula']}"
                    )


# ─── Test 7: 各 sheet 最低 cell 数（task 2.25 子任务声明）────────────────────


class TestPerSheetMinimums:
    """各 sheet cell 数**双向锁死**（原为单向 ``≥ min``）。

    🔴 2026-08-08 基线按实测重算 + 改双向
    ----------------------------------
    原 ``min_cells`` 是 task 2.25 落地时的数，而幂等脚本
    ``fix_g_cycle_prefill_presets.py`` 依据源 xlsx + DB 实证删掉了若干**错码 cell**，
    于是三条断言长期红（属「测试镜像已修好的 bug」，会被当噪声跳过）：

    - ``明细表G4-2`` 6 → **5**：删 ``应计利息_期末``（``TB('1501.03')``，1501 是
      旧准则「持有至到期投资」，取数恒空）
    - ``明细表G7-2`` 15 → **14**：删 5 条 ``=AUX('1511.01','客户','0079xx',...)``
      项目专属客户码（见 :class:`TestG7AuxLinkage` docstring）
    - ``明细表G8-2`` 6 → **3**：删 ``FVOCI_1525/1526/1527_期末``（投资性房地产
      累计折旧 / 累计摊销 / 减值准备，是 **H3** 的科目族）

    ⚠️ 改为 ``exact``（精确相等）而非 ``≥``：单向下限挡不住「删错 cell」也挡不住
    「把数字改小让它绿」。精确值使**任何**增删都打红 —— 合法新增时同步改这里，
    并在下方 ``_REMOVED_CELL_EVIDENCE`` 登记理由，比静默放宽安全。
    """

    #: 被幂等脚本正确删除的 cell 及其依据（stale 检测：这些 cell_ref 不得回潮）
    _REMOVED_CELL_EVIDENCE: dict[str, tuple[str, str]] = {
        "应计利息_期末": ("明细表G4-2", "TB('1501.03') —— 1501 是旧准则持有至到期投资，取数恒空"),
        "FVOCI_1525_期末": ("明细表G8-2", "1525 投资性房地产累计折旧，属 H3 科目族"),
        "FVOCI_1526_期末": ("明细表G8-2", "1526 投资性房地产累计摊销，属 H3 科目族"),
        "FVOCI_1527_期末": ("明细表G8-2", "1527 投资性房地产减值准备，属 H3 科目族"),
    }

    @pytest.mark.parametrize("sheet,exact_cells,description", [
        ("明细表G1-2", 10, "G1 交易性金融资产明细表"),
        ("明细表G4-2", 5, "G4 债权投资明细表 + ECL 测试参数（原 6，删 1 条 1501 错码）"),
        ("明细表G6-2", 5, "G6 其他债权投资明细表"),
        ("明细表G7-2", 14, "G7 长期股权投资明细表（原 19，删 5 条项目专属客户码 AUX）"),
        ("明细表G8-2", 3, "G8 其他权益工具投资明细表（原 6，删 3 条 H3 科目族错码）"),
    ])
    def test_sheet_cell_count_exact(self, g_cells, sheet, exact_cells, description):
        actual = sum(1 for c in g_cells if c["sheet"] == sheet)
        assert actual == exact_cells, (
            f"{description}: 实际 {actual} != 期望 {exact_cells}。\n"
            f"变少 ⇒ 有 cell 被误删；变多 ⇒ 新增了 cell，请核对合法性后同步改本断言。"
        )

    def test_removed_cells_do_not_reappear(self, g_cells):
        """stale 检测：被正确删除的错码 cell 不得回潮。"""
        present = {(c["sheet"], c["cell_ref"]) for c in g_cells}
        offenders = [
            f"{sheet}/{ref}（{why}）"
            for ref, (sheet, why) in self._REMOVED_CELL_EVIDENCE.items()
            if (sheet, ref) in present
        ]
        assert not offenders, "已删除的错码 cell 回潮:\n  " + "\n  ".join(offenders)

    def test_removed_cell_evidence_is_documented(self):
        """反向自检：每条登记必须写明依据（防登记表变成空壳）。"""
        for ref, (sheet, why) in self._REMOVED_CELL_EVIDENCE.items():
            assert sheet.startswith("明细表"), f"{ref} sheet 名可疑: {sheet}"
            assert len(why) >= 15, f"{ref} 删除依据过短: {why!r}"

    def test_g11_aggregation_meets_minimum(self, g_cells):
        """G11 投资收益汇总（=WP 跨 sheet）≥ 6 cell"""
        actual = sum(1 for c in g_cells if c["sheet"] == "明细分析表G11-2")
        assert actual >= 6, (
            f"G11 投资收益汇总 ≥ 6 cell: 实际 {actual}"
        )

    def test_g13_g14_aggregation_meets_minimum(self, g_cells):
        """G13 公允价值变动 + G14 信用减值汇总（=WP 跨 sheet）≥ 7 cell 合计"""
        g13 = sum(1 for c in g_cells if c["sheet"] == "明细分析表G13-2")
        g14 = sum(1 for c in g_cells if c["sheet"] == "明细分析表G14-2")
        assert g13 + g14 >= 7, (
            f"G13+G14 汇总 ≥ 7 cell 合计: 实际 G13={g13} + G14={g14} = {g13+g14}"
        )


# ─── Test 8: formula_type 枚举合法性 ────────────────────────────────────────


class TestFormulaTypeValidity:
    VALID_FORMULA_TYPES = {
        "TB", "TB_SUM", "TB_AUX", "AUX",
        "ADJ", "PREV", "WP",
        "LEDGER", "PLACEHOLDER",
    }

    def test_formula_types_in_enum(self, g_cells):
        for c in g_cells:
            ft = c.get("formula_type") or ""
            assert ft in self.VALID_FORMULA_TYPES, (
                f"非法 formula_type {ft!r} in "
                f"{c['wp_code']}/{c['sheet']}/{c['cell_ref']}"
            )

    def test_formula_matches_type(self, g_cells):
        """formula 前缀应与 formula_type 匹配"""
        for c in g_cells:
            ft = c.get("formula_type")
            f = c.get("formula")
            if f is None:
                continue
            if ft == "TB":
                assert f.startswith("=TB("), f"{c['cell_ref']}: {f}"
            elif ft == "TB_SUM":
                assert f.startswith("=TB_SUM("), f"{c['cell_ref']}: {f}"
            elif ft == "TB_AUX":
                assert f.startswith("=TB_AUX("), f"{c['cell_ref']}: {f}"
            elif ft == "AUX":
                assert f.startswith("=AUX("), f"{c['cell_ref']}: {f}"
            elif ft == "ADJ":
                assert f.startswith("=ADJ("), f"{c['cell_ref']}: {f}"
            elif ft == "PREV":
                assert f.startswith("=PREV("), f"{c['cell_ref']}: {f}"
            elif ft == "WP":
                assert f.startswith("=WP("), f"{c['cell_ref']}: {f}"
            elif ft == "LEDGER":
                assert f.startswith("=LEDGER("), f"{c['cell_ref']}: {f}"
