"""G5 公式预设守卫 — 科目码一致 / sheet 名一致 / 语法合法.

验证 prefill_formula_mapping.json 中 G5 块：
- account_codes 全部为 ['1531']
- 所有 TB()/ADJ() 公式引用的科目码 ∈ {1531, 1531.*}
- wp_name 正确
- sheet 名与源 xlsx tab 名一致
"""
import json
import re
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MAPPING_PATH = DATA_DIR / "prefill_formula_mapping.json"

G5_CORRECT_ACCOUNT = "1531"
G5_CORRECT_WP_NAMES = {"长期应收款审定表", "长期应收款明细表", "长期应收款附注披露（上市）", "长期应收款附注披露（国企）"}
# 源 xlsx 真实 tab 名
G5_VALID_SHEET_NAMES = {
    "审定表G5-1",
    "余额明细表G5-2",
    "附注披露信息（上市公司）",
    "附注披露信息（国企）",
    "坏账准备明细表G5-3",
    "调整分录汇总G5-4",
    "未实现融资收益测算表（租赁）G5-5",
    "未实现融资收益测算表（销售）G5-6",
    "长期应收款保理核查表G5-7",
    "信用减值损失会计政策检查G5-8",
    "长期应收款三阶段划分G5-9",
    "长期应收款坏账准备测算G5-10",
    "减值准备转回（收回）、核销检查表G5-11",
    "凭证检查表G5-12",
    "长期应收款实质性程序表G5A",
}

# 从公式中提取科目码的正则
TB_PATTERN = re.compile(r"TB\(\s*'([^']+)'")
ADJ_PATTERN = re.compile(r"ADJ\(\s*'([^']+)'")


@pytest.fixture(scope="module")
def g5_blocks() -> list[dict]:
    """加载 G5 的所有公式预设块."""
    with open(MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)
    all_blocks = data.get("mappings", data) if isinstance(data, dict) else data
    return [b for b in all_blocks if isinstance(b, dict) and b.get("wp_code") == "G5"]


class TestG5FormulaPresets:
    """G5 公式预设正确性."""

    def test_has_blocks(self, g5_blocks: list[dict]):
        """G5 至少有 1 个块."""
        assert len(g5_blocks) >= 1

    def test_account_codes_correct(self, g5_blocks: list[dict]):
        """所有块的 account_codes 都是 ['1531']."""
        for block in g5_blocks:
            codes = block.get("account_codes", [])
            assert codes == [G5_CORRECT_ACCOUNT], (
                f"块 '{block.get('wp_name')}' 的 account_codes={codes}，"
                f"应为 ['{G5_CORRECT_ACCOUNT}']"
            )

    def test_wp_names_correct(self, g5_blocks: list[dict]):
        """wp_name 在合法集合内."""
        for block in g5_blocks:
            name = block.get("wp_name", "")
            assert name in G5_CORRECT_WP_NAMES, (
                f"块 wp_name='{name}' 不在合法集合内：{G5_CORRECT_WP_NAMES}"
            )

    def test_sheet_names_valid(self, g5_blocks: list[dict]):
        """sheet 名在源 xlsx tab 名集合内."""
        for block in g5_blocks:
            sheet = block.get("sheet", "")
            assert sheet in G5_VALID_SHEET_NAMES, (
                f"块 '{block.get('wp_name')}' 的 sheet='{sheet}' "
                f"不在源 xlsx tab 名集合内"
            )

    def test_tb_formulas_reference_correct_account(self, g5_blocks: list[dict]):
        """所有 TB() 公式引用的科目码以 1531 开头."""
        for block in g5_blocks:
            for cell in block.get("cells", []):
                formula = cell.get("formula", "")
                for match in TB_PATTERN.finditer(formula):
                    code = match.group(1)
                    assert code.startswith(G5_CORRECT_ACCOUNT), (
                        f"块 '{block.get('wp_name')}' cell '{cell.get('cell_ref')}' "
                        f"的 TB 公式引用科目 '{code}'，应以 '{G5_CORRECT_ACCOUNT}' 开头"
                    )

    def test_adj_formulas_reference_correct_account(self, g5_blocks: list[dict]):
        """所有 ADJ() 公式引用的科目码以 1531 开头."""
        for block in g5_blocks:
            for cell in block.get("cells", []):
                formula = cell.get("formula", "")
                for match in ADJ_PATTERN.finditer(formula):
                    code = match.group(1)
                    assert code.startswith(G5_CORRECT_ACCOUNT), (
                        f"块 '{block.get('wp_name')}' cell '{cell.get('cell_ref')}' "
                        f"的 ADJ 公式引用科目 '{code}'，应以 '{G5_CORRECT_ACCOUNT}' 开头"
                    )

    def test_no_1503_remains(self, g5_blocks: list[dict]):
        """不得残留旧科目 1503."""
        for block in g5_blocks:
            raw = json.dumps(block, ensure_ascii=False)
            assert "1503" not in raw, (
                f"块 '{block.get('wp_name')}' 残留旧科目 1503"
            )

    def test_formula_syntax_valid(self, g5_blocks: list[dict]):
        """公式语法基本合法（以 = 开头，包含已知函数名）."""
        VALID_FUNCS = {"TB", "ADJ", "PREV", "WP", "TB_SUM", "LEDGER", "LEDGER_DETAIL"}
        for block in g5_blocks:
            for cell in block.get("cells", []):
                formula = cell.get("formula", "")
                if not formula:
                    continue
                assert formula.startswith("="), (
                    f"公式不以 '=' 开头：{formula}"
                )
                func_name = re.match(r"=(\w+)\(", formula)
                if func_name:
                    assert func_name.group(1) in VALID_FUNCS, (
                        f"未知函数 '{func_name.group(1)}' in '{formula}'"
                    )


class TestReverseValidation:
    """反向自检."""

    def test_mapping_file_exists(self):
        assert MAPPING_PATH.exists()

    def test_g5_blocks_count(self, g5_blocks: list[dict]):
        """G5 应有 4 个块（审定表 + 明细表 + 上市披露 + 国企披露）."""
        assert len(g5_blocks) == 4, f"G5 块数={len(g5_blocks)}，期望 4"
