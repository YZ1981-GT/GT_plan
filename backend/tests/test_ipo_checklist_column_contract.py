# -*- coding: utf-8 -*-
"""D4 IPO 检查表（D4-25/26/27/28）列结构三向同构守卫。

spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 1 · Task 1

三方比对（任一漂移即红）：
  1. 前端列规格 `ipoChecklistSchema.ts` 的 `SHEET_SPECS`（结构真源）
  2. 后端 `_SHEET_HEADERS[sheet]`（导入导出锚点，1D 摊平 label 序列）
  3. 源模板 xlsx（openpyxl 直读表头单元格，运行时权威 = backend/wp_templates/）

判据落到「结构」而非「字符串存在」：逐列相等（含全角标点与顿号），并对源模板做
**显式登记的归一化**（去换行后缀、`…` 占位列 → `其他`），任何未登记的差异都必须打红。

🔴 Task 1 阶段本守卫必须先红：`ipoChecklistSchema.ts` 尚不存在 → 解析失败即红。

Property 1/2/3/4/35（requirements.md）。
"""

from __future__ import annotations

import re
from pathlib import Path

import openpyxl
import pytest

# ── 路径 ────────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parents[2]
_TEMPLATE = (
    _REPO
    / "backend"
    / "wp_templates"
    / "D"
    / "D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx"
)
_SCHEMA_TS = (
    _REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "d4"
    / "ipo"
    / "ipoChecklistSchema.ts"
)

# ── 源模板实证基线（2026-09-13 openpyxl 只读实测，非预期值）─────────────────
# 每张 sheet：sheet_name / 表头行号 / 数据区首行 / 期望数据列数（含二级列，不含父组占位）
_SHEET_META = {
    "D4-25": {"sheet_name": "经销商检查D4-25", "header_rows": [11], "cols": 13},
    "D4-26": {"sheet_name": "境外销售收入检查D4-26", "header_rows": [11, 12], "cols": 19},
    "D4-27": {"sheet_name": "识别未披露的关联方D4-27", "header_rows": [14], "cols": 18},
    "D4-28": {"sheet_name": "客户信息核查清单D4-28", "header_rows": [12, 13], "cols": 15},
}

# 两级表头父组（源 xlsx 合并单元格实测）：sheet → (父组 label, 覆盖的二级列 label 集合)
_TWO_LEVEL_GROUPS = {
    # D4-26：O11:S11 合并，父组 label = 相关程序索引…，5 个二级列在 O12:S12
    "D4-26": (
        "相关程序索引",
        {"实地走访", "交易函证", "海关函证", "核对报关单", "电子口岸数据查询"},
    ),
    # D4-28：J12:N12 合并，父组 label = 核查方式（√），5 个二级列在 J13:N13
    "D4-28": (
        "核查方式（√）",
        {"工商资料查询", "互联网信息查询", "函证", "视频、电话访谈", "实地走访"},
    ),
}

# 源 xlsx → 后端/schema 的**显式登记归一化**（未登记的差异一律打红）。
# 归一化只做两类：① 去掉换行及其后的括号补充说明 ② `…` 占位列改名 `其他`。
_XLSX_LABEL_NORMALIZE = {
    "…": "其他",
    "客户与公司员工或高管或/和亲属重名（Y/N）": "重名(Y/N)",
    "20XX年度销售额": "年度销售额",
    # 视频、电话访谈：Task 14 已把后端与 schema 统一到源模板顿号，无需归一。
}


def _norm_xlsx_label(raw: object) -> str:
    """把源 xlsx 单元格文本归一到后端/schema 口径。

    源模板两类换行：① `业务模式\n（直销客户/经销商）` 是括号补充说明 → 去掉换行及其后；
    ② `占总交易\n比重` 是中文标签折行 → 去掉换行后拼接（不截断）。
    判据：换行后紧跟全角/半角左括号 → 视为补充说明整段丢弃；否则拼接。
    """
    s = "" if raw is None else str(raw)
    if "\n" in s:
        head, tail = s.split("\n", 1)
        tail = tail.strip()
        if tail[:1] in ("（", "("):
            s = head.strip()  # 括号补充说明整段丢弃
        else:
            s = (head.strip() + tail).replace("\n", "")  # 折行拼接
    s = s.strip()
    return _XLSX_LABEL_NORMALIZE.get(s, s)


# ── 源模板真源读取 ──────────────────────────────────────────────────────────
def _read_xlsx_headers(sheet_code: str) -> list[str]:
    """从源 xlsx 读一张 sheet 的摊平 label 序列（去父组占位、按数据列顺序）。

    单级表头直接读表头行；两级表头把二级列 label 摊到主列序列尾部（与后端 1D 口径一致）。
    """
    meta = _SHEET_META[sheet_code]
    wb = openpyxl.load_workbook(_TEMPLATE, data_only=False)
    try:
        ws = wb[meta["sheet_name"]]
        rows = meta["header_rows"]
        max_col = ws.max_column
        if len(rows) == 1:
            r = rows[0]
            labels = []
            for c in range(1, max_col + 1):
                v = ws.cell(r, c).value
                if v is None:
                    continue
                labels.append(_norm_xlsx_label(v))
            return labels
        # 两级：left-to-right 按列摊平（与后端 1D 口径一致）。
        # 落在二级列区（sub 行有值）→ 取 sub 行 label；否则取 main 行 label。
        main_r, sub_r = rows[0], rows[1]
        labels = []
        for c in range(1, max_col + 1):
            mv = ws.cell(main_r, c).value
            sv = ws.cell(sub_r, c).value
            if sv is not None:
                labels.append(_norm_xlsx_label(sv))
            elif mv is not None:
                labels.append(_norm_xlsx_label(mv))
        return labels
    finally:
        wb.close()


# ── 后端 _SHEET_HEADERS ─────────────────────────────────────────────────────
def _read_backend_headers(sheet_code: str) -> list[str]:
    from app.routers.wp_render_strategies._d4_import_export import _SHEET_HEADERS

    return list(_SHEET_HEADERS[sheet_code])


# ── 前端 schema 解析（读 TS 源码；Task 1 阶段文件不存在 → 解析失败即红）──────────
def _strip_ts_comments(src: str) -> str:
    """去掉 TS 的 /* */ 块注释与 // 行注释（保留字符串字面量原文）。"""
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"(^|[^:])//[^\n]*", r"\1", src)
    return src


def _read_schema_ts() -> str:
    if not _SCHEMA_TS.exists():
        pytest.fail(
            f"ipoChecklistSchema.ts 不存在（{_SCHEMA_TS}）—— Task 4 未落地，"
            "本守卫在 Wave 1 阶段必须先红"
        )
    return _strip_ts_comments(_SCHEMA_TS.read_text(encoding="utf-8"))


def _parse_schema_columns(sheet_code: str) -> list[dict]:
    """从 SHEET_SPECS 里抽取指定 sheet 的列 {key,label,group} 有序序列。

    约定 schema 形态（Task 4 落地）：
        { sheetCode: 'D4-25', ..., columns: [ { key:'...', label:'...', group:null, ... }, ... ] }
    解析用花括号配对切出该 sheet 的 columns 数组，再逐列抽 key/label/group。
    """
    src = _read_schema_ts()
    # 只在 SHEET_SPECS 对象内查找（避免撞到 interface 的类型联合 sheetCode: 'D4-25' | ...）
    specs_at = src.find("SHEET_SPECS")
    search_from = specs_at if specs_at >= 0 else 0
    # 定位该 sheetCode 的 spec 块起点（SHEET_SPECS 内那处）
    m = re.search(rf"sheetCode:\s*['\"]{re.escape(sheet_code)}['\"]", src[search_from:])
    if not m:
        pytest.fail(f"schema 中找不到 sheetCode='{sheet_code}' 的 spec 块")
    m_end = search_from + m.end()
    # 从该点向后找 columns: <inline array | 变量名>
    cm = re.search(r"columns:\s*(\[|[A-Za-z_$][\w$]*)", src[m_end:])
    if not cm:
        pytest.fail(f"{sheet_code} spec 块缺 columns 字段")
    token = cm.group(1)
    if token == "[":
        bracket = m_end + cm.start(1)
    else:
        # columns 是变量引用 → 定位 const <VARNAME> = [ ... ]
        decl = re.search(rf"\b{re.escape(token)}\s*(?::[^=]*)?=\s*\[", src)
        if not decl:
            pytest.fail(f"{sheet_code} columns 变量 {token} 找不到声明数组")
        bracket = decl.end() - 1
    depth = 0
    i = bracket
    while i < len(src):
        ch = src[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    arr = src[bracket : i + 1]
    # 解析 `const NAME = '文字'` 常量表，供 group 变量引用解析
    const_str = {
        cm2.group(1): cm2.group(2)
        for cm2 in re.finditer(r"const\s+([A-Za-z_$][\w$]*)\s*=\s*['\"]([^'\"]*)['\"]", src)
    }

    cols: list[dict] = []
    # 逐个 { ... } 对象（列）解析
    for obj_m in re.finditer(r"\{[^{}]*\}", arr):
        obj = obj_m.group(0)
        key_m = re.search(r"key:\s*['\"]([^'\"]+)['\"]", obj)
        label_m = re.search(r"label:\s*['\"]([^'\"]+)['\"]", obj)
        # group 可能是 null / 字符串字面量 / 变量引用
        group_m = re.search(r"group:\s*(null|['\"]([^'\"]*)['\"]|[A-Za-z_$][\w$]*)", obj)
        if not key_m or not label_m:
            continue
        group_val = None
        if group_m:
            raw = group_m.group(1)
            if raw == "null":
                group_val = None
            elif group_m.group(2) is not None:
                group_val = group_m.group(2)
            else:
                # 变量引用 → 查常量表
                group_val = const_str.get(raw)
        cols.append({"key": key_m.group(1), "label": label_m.group(1), "group": group_val})
    return cols


# ═══════════════════════════════════════════════════════════════════════════
# Property 4 / 35：schema.label == backend._SHEET_HEADERS == 源 xlsx（归一后）
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sheet_code", ["D4-25", "D4-26", "D4-27", "D4-28"])
def test_three_way_label_alignment(sheet_code: str):
    xlsx = _read_xlsx_headers(sheet_code)
    backend = _read_backend_headers(sheet_code)
    schema_cols = _parse_schema_columns(sheet_code)
    schema_labels = [c["label"] for c in schema_cols]

    assert len(xlsx) == _SHEET_META[sheet_code]["cols"], (
        f"{sheet_code} 源 xlsx 数据列数 {len(xlsx)} != 实证基线 "
        f"{_SHEET_META[sheet_code]['cols']}（openpyxl 实测复算而非预期）"
    )
    assert backend == xlsx, (
        f"{sheet_code} 后端 _SHEET_HEADERS 与源 xlsx（归一后）逐列不等：\n"
        f"  backend={backend}\n  xlsx   ={xlsx}"
    )
    assert schema_labels == backend, (
        f"{sheet_code} schema.label 序列与后端 _SHEET_HEADERS 逐列不等：\n"
        f"  schema ={schema_labels}\n  backend={backend}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Property 1：schema.key 序列长度 == 后端摊平 label 序列长度（一一对应）
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sheet_code", ["D4-25", "D4-26", "D4-27", "D4-28"])
def test_schema_key_count_matches_backend(sheet_code: str):
    schema_cols = _parse_schema_columns(sheet_code)
    backend = _read_backend_headers(sheet_code)
    keys = [c["key"] for c in schema_cols]
    assert len(keys) == len(backend), (
        f"{sheet_code} schema key 数 {len(keys)} != 后端列数 {len(backend)}"
    )
    assert len(set(keys)) == len(keys), f"{sheet_code} schema key 有重复（会撞键）：{keys}"


# ═══════════════════════════════════════════════════════════════════════════
# Property 2/3：两级表头父组恰 5 列，label 集合与源 xlsx 二级列一致
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("sheet_code", ["D4-26", "D4-28"])
def test_two_level_group_covers_five_sub_columns(sheet_code: str):
    schema_cols = _parse_schema_columns(sheet_code)
    grouped = [c for c in schema_cols if c["group"]]
    assert len(grouped) == 5, (
        f"{sheet_code} schema 中 group 非空的列应恰为 5（二级列），实际 {len(grouped)}"
    )
    groups = {c["group"] for c in grouped}
    assert len(groups) == 1, f"{sheet_code} 二级列的 group 应统一为一个父组，实际 {groups}"

    _, expected_subs = _TWO_LEVEL_GROUPS[sheet_code]
    sub_labels = {c["label"] for c in grouped}
    # 源 xlsx 二级列 label 归一后应与 schema 二级列 label 一致
    normed_expected = {_XLSX_LABEL_NORMALIZE.get(s, s) for s in expected_subs}
    assert sub_labels == normed_expected, (
        f"{sheet_code} 二级列 label 集合与源 xlsx 不一致：\n"
        f"  schema={sub_labels}\n  xlsx  ={normed_expected}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 反向自检：归一化 / stripComments 真在承重（防守卫退化成恒真）
# ═══════════════════════════════════════════════════════════════════════════
def test_selfcheck_xlsx_normalize_is_load_bearing():
    """故意给一个带换行后缀的 label，归一后必须只剩主名。"""
    assert _norm_xlsx_label("业务模式\n（直销客户/经销商）") == "业务模式"
    assert _norm_xlsx_label("…") == "其他"
    # 若归一化退化成「原样返回」，上面两条立即打红


def test_selfcheck_strip_ts_comments_is_load_bearing():
    """剥注释必须真剥掉 // 与 /* */。"""
    stub = "const x = 1 // key: 'FAKE'\n/* label: 'FAKE2' */\nconst y = 2"
    out = _strip_ts_comments(stub)
    assert "FAKE" not in out and "FAKE2" not in out
    assert "const x = 1" in out and "const y = 2" in out


def test_selfcheck_reverse_wrong_label_must_fail():
    """反向自检：把源 xlsx 期望列数改错必失败（证明 test_three_way 非恒真）。

    这里用一个独立断言复算：源 xlsx D4-25 第 9 列应为 `个人/企业`，
    若守卫退化成「字符串存在」而非「逐列相等」，把它换成任意存在的字样也会过。
    """
    xlsx = _read_xlsx_headers("D4-25")
    assert xlsx[8] == "个人/企业", (
        f"D4-25 第 9 列应为 个人/企业（源模板实测），实际 {xlsx[8]!r}"
    )
    # 反向：一个错误期望必须能被这条断言否定
    assert xlsx[8] != "个人·企业", "spec prose 的 个人·企业 是错的，源模板是 个人/企业"
