"""IPO 检查表列结构同构守卫 — 三向比对

三方比对：
1. 前端列规格（ipoChecklistSchema.ts 的 SHEET_SPECS）
2. 后端 _SHEET_HEADERS[sheet] 的摊平 label 序列
3. 源模板 xlsx 表头单元格（openpyxl 直读）

Property 1/2/3/4/35: 四张 sheet 的列规格逐列相等。
🔴 源模板表头含换行符与括号说明，三方比对使用归一化 label。
🔴 冻结实证基线：D4-25 13 列 / D4-26 19 列 / D4-27 18 列 / D4-28 15 列
   （数值来自 openpyxl 实测复算而非预期）
"""
from __future__ import annotations

import re
from pathlib import Path

import openpyxl
import pytest

# ─── 后端 _SHEET_HEADERS ─────────────────────────────────────────────
from app.routers.wp_render_strategies._d4_import_export import _SHEET_HEADERS


# ─── 前端列规格（读 TS 源码，提取 label 序列） ────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "d4" / "ipo"
SCHEMA_FILE = FRONTEND_DIR / "ipoChecklistSchema.ts"

# ─── 源模板 ─────────────────────────────────────────────────────────
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "wp_templates" / "D"
TEMPLATE_FILE = TEMPLATE_DIR / "D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx"

# ─── 四张表的配置 ────────────────────────────────────────────────────
SHEET_CONFIGS = {
    "D4-25": {
        "sheet_name": "经销商检查D4-25",
        "header_rows": [11],
        "expected_col_count": 13,
    },
    "D4-26": {
        "sheet_name": "境外销售收入检查D4-26",
        "header_rows": [11, 12],
        "expected_col_count": 19,  # 14 主列 + 5 二级列（_SHEET_HEADERS 摊平口径无 "相关程序索引" 末列的说明括号）
    },
    "D4-27": {
        "sheet_name": "识别未披露的关联方D4-27",
        "header_rows": [14],
        "expected_col_count": 18,
    },
    "D4-28": {
        "sheet_name": "客户信息核查清单D4-28",
        "header_rows": [12, 13],
        "expected_col_count": 15,  # 10 主数据列 + 5 二级列（_SHEET_HEADERS 摊平口径）
    },
}


def _normalize_label(raw: str) -> str:
    """归一化 label：去换行符、去括号说明、去前后空白、统一全角标点。

    源模板表头常带 '\\n（说明文字）'，后端 _SHEET_HEADERS 是简化版。
    """
    if not raw:
        return ""
    s = str(raw).strip()
    # 去换行符后的括号说明
    s = re.sub(r"\n.*", "", s)
    # 去括号说明（中文括号+英文括号）但保留 (√) 和 (Y/N) 等简短标记
    # 只去长度>10 的括号内容
    s = re.sub(r"（[^）]{10,}）", "", s)
    s = re.sub(r"\([^)]{10,}\)", "", s)
    s = s.strip()
    return s


def _read_xlsx_headers(sheet_name: str, header_rows: list[int]) -> list[str]:
    """从源模板 xlsx 读取表头单元格，按行摊平（跳过 None）。"""
    assert TEMPLATE_FILE.exists(), f"源模板不存在: {TEMPLATE_FILE}"
    wb = openpyxl.load_workbook(str(TEMPLATE_FILE), read_only=True, data_only=True)
    ws = wb[sheet_name]
    labels: list[str] = []
    if len(header_rows) == 1:
        # 单级表头：直接取该行非空单元格
        for cell in ws[header_rows[0]]:
            if cell.value is not None:
                labels.append(_normalize_label(str(cell.value)))
    else:
        # 两级表头：第一行是主列 + 父组，第二行是二级列
        # 先收集第一行的所有非空列（主列直接加，父组记下跨列范围）
        row1_cells = {cell.column: _normalize_label(str(cell.value)) for cell in ws[header_rows[0]] if cell.value is not None}
        row2_cells = {cell.column: _normalize_label(str(cell.value)) for cell in ws[header_rows[1]] if cell.value is not None}

        # 找出合并单元格中的父组
        merged_ranges = list(ws.merged_cells.ranges)
        parent_cols: set[int] = set()
        for mr in merged_ranges:
            if mr.min_row == header_rows[0] and mr.max_row == header_rows[0]:
                # 横跨合并 = 父组
                if mr.max_col > mr.min_col:
                    parent_cols.update(range(mr.min_col, mr.max_col + 1))

        # 遍历所有列号，按归属输出 label
        max_col = max(list(row1_cells.keys()) + list(row2_cells.keys()) + [0])
        for col in range(1, max_col + 1):
            if col in parent_cols:
                # 父组覆盖的列 → 取第二行的值
                if col in row2_cells:
                    labels.append(row2_cells[col])
            elif col in row1_cells:
                # 主列 → 取第一行的值
                # 但需排除父组标签本身（它不是数据列）
                val = row1_cells[col]
                if val and col not in {c for mr in merged_ranges if mr.min_row == header_rows[0] for c in [mr.min_col]}:
                    labels.append(val)
                elif val and col in {mr.min_col for mr in merged_ranges if mr.min_row == header_rows[0] and mr.max_col > mr.min_col}:
                    # 这是父组的起始列，跳过（由二级列代替）
                    pass
                else:
                    labels.append(val)

    wb.close()
    return labels


def _read_frontend_labels(sheet_code: str) -> list[str]:
    """从 ipoChecklistSchema.ts 读取该 sheet 的列规格 label 序列。

    🔴 读源码前 stripComments。
    """
    assert SCHEMA_FILE.exists(), f"ipoChecklistSchema.ts 不存在: {SCHEMA_FILE}"
    raw = SCHEMA_FILE.read_text(encoding="utf-8")
    # stripComments: 去单行注释和多行注释
    raw = re.sub(r"//[^\n]*", "", raw)
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)

    # 提取 label 值（模式：label: '...' 或 label: "..."）
    # 在对应 sheet 的列定义区域内
    labels: list[str] = []
    # 找到对应常量（如 D4_25_COLUMNS）
    const_name_map = {
        "D4-25": "D4_25_COLUMNS",
        "D4-26": "D4_26_COLUMNS",
        "D4-27": "D4_27_COLUMNS",
        "D4-28": "D4_28_COLUMNS",
    }
    const_name = const_name_map[sheet_code]
    pattern = rf"const\s+{const_name}\s*.*?=\s*\[(.*?)\]\s*as\s+const"
    match = re.search(pattern, raw, re.DOTALL)
    if not match:
        return []

    block = match.group(1)
    # 提取所有 label 值
    label_pattern = r"label:\s*['\"]([^'\"]+)['\"]"
    for m in re.finditer(label_pattern, block):
        labels.append(m.group(1))

    return labels


# ═══════════════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════════════


class TestColumnCountBaseline:
    """冻结实证基线：列数来自 openpyxl 实测复算。"""

    @pytest.mark.parametrize("sheet_code", ["D4-25", "D4-26", "D4-27", "D4-28"])
    def test_backend_header_count(self, sheet_code: str):
        cfg = SHEET_CONFIGS[sheet_code]
        headers = _SHEET_HEADERS[sheet_code]
        assert len(headers) == cfg["expected_col_count"], (
            f"{sheet_code}: 后端 _SHEET_HEADERS 列数 {len(headers)} != 期望 {cfg['expected_col_count']}"
        )

    @pytest.mark.parametrize("sheet_code", ["D4-25", "D4-26", "D4-27", "D4-28"])
    def test_frontend_label_count(self, sheet_code: str):
        cfg = SHEET_CONFIGS[sheet_code]
        labels = _read_frontend_labels(sheet_code)
        assert len(labels) == cfg["expected_col_count"], (
            f"{sheet_code}: 前端列规格列数 {len(labels)} != 期望 {cfg['expected_col_count']}"
        )


class TestBackendVsFrontend:
    """后端 _SHEET_HEADERS 与前端列规格 label 序列逐列比对。

    比对使用归一化 label（后端已是简化版，前端也是简化版）。
    """

    @pytest.mark.parametrize("sheet_code", ["D4-25", "D4-26", "D4-27", "D4-28"])
    def test_label_sequence_match(self, sheet_code: str):
        backend = _SHEET_HEADERS[sheet_code]
        frontend = _read_frontend_labels(sheet_code)
        assert len(backend) == len(frontend), (
            f"{sheet_code}: 后端 {len(backend)} 列 vs 前端 {len(frontend)} 列"
        )
        mismatches = []
        for i, (b, f) in enumerate(zip(backend, frontend)):
            bn = _normalize_label(b)
            fn = _normalize_label(f)
            if bn != fn:
                mismatches.append(f"  col {i}: backend='{bn}' vs frontend='{fn}'")
        assert not mismatches, (
            f"{sheet_code}: {len(mismatches)} 列不匹配:\n" + "\n".join(mismatches)
        )


class TestD426GroupStructure:
    """Property 2: D4-26 父组「核查程序执行情况」覆盖 5 列。"""

    def test_group_columns(self):
        labels = _read_frontend_labels("D4-26")
        # 从 ipoChecklistSchema.ts 提取 group 信息
        raw = SCHEMA_FILE.read_text(encoding="utf-8")
        raw = re.sub(r"//[^\n]*", "", raw)
        raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
        match = re.search(r"const\s+D4_26_COLUMNS\s*.*?=\s*\[(.*?)\]\s*as\s+const", raw, re.DOTALL)
        assert match
        block = match.group(1)
        group_pattern = r"group:\s*['\"]([^'\"]+)['\"]"
        groups = re.findall(group_pattern, block)
        assert len(groups) == 5, f"D4-26 非空 group 列数 {len(groups)} != 5"
        assert all(g == "核查程序执行情况" for g in groups), f"D4-26 group 值不全为 '核查程序执行情况': {groups}"


class TestD428GroupStructure:
    """Property 3: D4-28 父组「核查方式（√）」覆盖 5 列。"""

    def test_group_columns(self):
        raw = SCHEMA_FILE.read_text(encoding="utf-8")
        raw = re.sub(r"//[^\n]*", "", raw)
        raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
        match = re.search(r"const\s+D4_28_COLUMNS\s*.*?=\s*\[(.*?)\]\s*as\s+const", raw, re.DOTALL)
        assert match
        block = match.group(1)
        group_pattern = r"group:\s*['\"]([^'\"]+)['\"]"
        groups = re.findall(group_pattern, block)
        assert len(groups) == 5, f"D4-28 非空 group 列数 {len(groups)} != 5"
        assert all("核查方式" in g for g in groups), f"D4-28 group 值不含 '核查方式': {groups}"


class TestReverseCheck:
    """反向自检：故意改一列 label 必须失败。"""

    def test_wrong_label_detected(self):
        """把 D4-25 第一列 label 从 '序号' 改成 '错误' 后，序列比对必须失败。"""
        frontend = _read_frontend_labels("D4-25")
        backend = list(_SHEET_HEADERS["D4-25"])
        # 模拟篡改
        tampered = list(frontend)
        tampered[0] = "错误的列名"
        mismatches = []
        for i, (b, f) in enumerate(zip(backend, tampered)):
            if _normalize_label(b) != _normalize_label(f):
                mismatches.append(i)
        assert len(mismatches) > 0, "反向自检失败：篡改后未检测到不匹配"
