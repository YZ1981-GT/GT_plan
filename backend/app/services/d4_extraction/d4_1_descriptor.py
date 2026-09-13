"""D4-1 营业收入审定表的模板 descriptor（单一真源）。

spec: d4-1-adjudication-bidirectional-writeback-and-formula-io / Task 1.1~1.2 (DEC1 模板先行)

由 `backend/scripts/diagnose/diagnose_d4_1_template.py` openpyxl 直读权威模板
`backend/wp_templates/D/D4-1至D4-4 …xlsx` 核定；证据见 spec `evidence/d4_1_descriptor.md`
与 `evidence/d4_1_template_facts.json`。**禁止**在 render/OO/导入导出里另写死 tab/列/行。

契约测试 `backend/tests/d4_extraction/test_d4_1_descriptor.py` 用 openpyxl 直读源 xlsx
与本模块交叉比对（三向 + 反向自检）；模板漂移或本模块被改坏即打红。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def d4_1_template_path() -> Path:
    """D4-1 审定表册权威 xlsx 的绝对路径（运行时权威 = `backend/wp_templates/D/`）。

    🔴 用「D4-1至」精确定位——`D4-1*` 会误命中「D4-12 营业收入-合同检查…」。
    """
    # app/services/d4_extraction/xxx.py -> backend/
    backend_root = Path(__file__).resolve().parents[3]
    d_dir = backend_root / "wp_templates" / "D"
    for p in sorted(d_dir.glob("D4-1至*.xlsx")):
        if p.name.startswith("~$"):  # WPS/Excel 锁文件
            continue
        return p
    raise FileNotFoundError(f"未找到 D4-1 审定表册（D4-1至*.xlsx）于 {d_dir}")


#: D4-1 审定表的真实 tab 名（不是裸 `D4-1`）。render/OO 定位用此。
D4_1_SHEET_NAME = "营业收入审定表D4-1"

#: 索引号单元格值（I3）。
D4_1_INDEX_CODE = "D4-1"

#: 同册 sheet 名（D4-1~D4-4 同册，核定实证）。
D4_1_WORKBOOK_SHEETS: tuple[str, ...] = (
    "底稿目录",
    "营业收入审计程序表D4A",
    "主营业务收入审计程序表D4A（修订前）",
    "营业收入审定表D4-1",
    "附注披露信息（上市公司）",
    "附注披露信息（国企）",
    "主营业务收入明细表D4-2",
    "其他业务收入明细表D4-3",
    "营业收入调整分录汇总D4-4",
    "GT_Custom",
)


@dataclass(frozen=True)
class D4_1_ColumnSpec:
    """一个受管金额列的坐标与语义键。"""

    col: str  # Excel 列字母
    field: str  # 前端 per-field 键（D4_ADJ_VALUE_FIELDS 之一）
    period: str  # "current" | "prior"
    label: str  # 表头文案（R6）


#: 受管输入列（B/C/D/F/G/H 六列），与前端 `D4_ADJ_VALUE_FIELDS` 一一对应。
#: E/I 审定数是派生公式列，不在此列（见 :data:`D4_1_FORMULA_COLUMNS`）。
D4_1_INPUT_COLUMNS: tuple[D4_1_ColumnSpec, ...] = (
    D4_1_ColumnSpec("B", "currentUnadjusted", "current", "未审数"),
    D4_1_ColumnSpec("C", "currentAje", "current", "账项调整"),
    D4_1_ColumnSpec("D", "currentRje", "current", "重分类调整"),
    D4_1_ColumnSpec("F", "priorUnadjusted", "prior", "未审数"),
    D4_1_ColumnSpec("G", "priorAje", "prior", "账项调整"),
    D4_1_ColumnSpec("H", "priorRje", "prior", "重分类调整"),
)

#: 审定数派生列（E=本期、I=上期）。公式 = SUM(该期三输入列)。
D4_1_AUDITED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("E", "current"),
    ("I", "prior"),
)

#: 段（section）标题行与其可扩明细行区段（1-based 行号，含端点）。
@dataclass(frozen=True)
class D4_1_Section:
    key: str  # 前端 sectionKey
    title: str  # A 列段标题文案
    title_row: int
    detail_rows: tuple[int, ...]  # 空白可扩明细行
    subtotal_row: int  # 小计行


D4_1_SECTIONS: tuple[D4_1_Section, ...] = (
    D4_1_Section("main-revenue", "主营业务收入：", 7, (8, 9, 10, 11), 12),
    D4_1_Section("other-revenue", "其他业务收入：", 13, (14, 15, 16, 17), 18),
)

#: 汇总/核对结构行。
D4_1_TOTAL_ROW = 19  # 合计
D4_1_TB_CHECK_ROW = 20  # 试算平衡表数
D4_1_DIFF_ROW = 21  # 差异数

#: 表头行。
D4_1_HEADER_TOP_ROW = 5  # 项目 / 本期数 / 上期数
D4_1_HEADER_SUB_ROW = 6  # 未审数 / 账项调整 / 重分类调整 / 审定数

#: 公式列字母集（OO formula mask 保护对象）——审定数 + 小计/合计/差异所在列。
#: 审定=E/I；小计/合计/差异横跨 B..I。核定实证 48 个公式格全部落在这些列。
D4_1_FORMULA_COLUMNS: tuple[str, ...] = ("B", "C", "D", "E", "F", "G", "H", "I")

#: 表头文案真源（R5 顶层）。
D4_1_HEADER_TOP: dict[str, str] = {
    "A5": "项目",
    "B5": "本期数",
    "F5": "上期数",
}

#: 表头文案真源（R6 子层）。
D4_1_HEADER_SUB: dict[str, str] = {
    "B6": "未审数", "C6": "账项调整", "D6": "重分类调整", "E6": "审定数",
    "F6": "未审数", "G6": "账项调整", "H6": "重分类调整", "I6": "审定数",
}


@dataclass(frozen=True)
class D4_1_Descriptor:
    """D4-1 审定表 descriptor 聚合视图（供 render / OO / 导入导出统一消费）。"""

    sheet_name: str = D4_1_SHEET_NAME
    index_code: str = D4_1_INDEX_CODE
    input_columns: tuple[D4_1_ColumnSpec, ...] = D4_1_INPUT_COLUMNS
    audited_columns: tuple[tuple[str, str], ...] = D4_1_AUDITED_COLUMNS
    sections: tuple[D4_1_Section, ...] = D4_1_SECTIONS
    total_row: int = D4_1_TOTAL_ROW
    tb_check_row: int = D4_1_TB_CHECK_ROW
    diff_row: int = D4_1_DIFF_ROW
    formula_columns: tuple[str, ...] = D4_1_FORMULA_COLUMNS


def d4_1_descriptor() -> D4_1_Descriptor:
    return D4_1_Descriptor()


__all__ = [
    "d4_1_template_path",
    "D4_1_SHEET_NAME",
    "D4_1_INDEX_CODE",
    "D4_1_WORKBOOK_SHEETS",
    "D4_1_ColumnSpec",
    "D4_1_INPUT_COLUMNS",
    "D4_1_AUDITED_COLUMNS",
    "D4_1_Section",
    "D4_1_SECTIONS",
    "D4_1_TOTAL_ROW",
    "D4_1_TB_CHECK_ROW",
    "D4_1_DIFF_ROW",
    "D4_1_HEADER_TOP_ROW",
    "D4_1_HEADER_SUB_ROW",
    "D4_1_FORMULA_COLUMNS",
    "D4_1_HEADER_TOP",
    "D4_1_HEADER_SUB",
    "D4_1_Descriptor",
    "d4_1_descriptor",
]
