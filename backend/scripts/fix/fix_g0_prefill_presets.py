"""G0 公式预设纠偏 —— sheet 名 / 科目族 / cell_ref 锚点三处

spec: g0-confirmation-source-alignment，Task 18（Requirement 9.1~9.6）

背景（逐项实证）
-----------------
``backend/data/prefill_formula_mapping.json`` 的 G0 块（``mappings`` 内唯一一处）有三处错：

1. ``sheet`` 写 ``审定表G0-1``，而源 xlsx ``backend/wp_templates/G/G0 投资循环函证.xlsx``
   的真实 tab 名是 ``函证结果汇总表G0-1``（openpyxl 直读 ``wb.sheetnames`` 实证，
   全册 10 张 sheet 无 ``审定表G0-1``）。
2. 公式用跨科目族区间 ``TB_SUM('1101~1511', ...)`` —— 该区间把 ``1121 应收票据`` /
   ``1122 应收账款`` / ``1123 预付款项`` / ``1221 其他应收款`` / ``14xx 存货`` 全部
   扫进投资循环。**正解是 8 条 ``PLACEHOLDER``**（见下「裁决」；``BOOK_AMOUNT_SPECS``
   的科目码降级为展示/筛选用的参考码，运行态不据此取数）。
3. ``cell_ref`` 用 ``期初余额`` / ``未审数`` 两个审定表锚点，而 G0-1 是**函证结果汇总表**、
   没有审定表的双期结构 → 这两个锚点在 G0-1 上不存在。正解是下区矩阵的品种账面金额键。

🔴 裁决：8 条 ``PLACEHOLDER`` 而非 8 条按码 ``TB()``（2026-08-04，与 H0 口径统一）
--------------------------------------------------------------------------------
首版把 2 条区间公式改成 8 条离散 ``TB('{code}','期末余额')``。**已推翻**，两条 AC 判据：

- **R4.3** 明文要求「缺失时返回 ``undefined``（非 0），使『本项目无此科目』与
  『余额为 0』可区分」。``TB()`` 的数据源是 ``trial_balance.standard_account_code``，
  **取不到时返 0** → 恰好把两者混同。
- **R3.5** 手工值优先于自动取数。而 ``cell_ref`` 指向的
  ``G0-1-matrix-{品种}-book_amount`` 是**手工覆盖键** → 让预设公式写它，等于让「按码
  取到的 0」伪装成审计师手填值，压住语义定位拿到的 ``undefined``。

旁证（postgres 只读实测 ``trial_balance``，9 个项目）：``1504`` / ``1506`` / ``1507`` /
``1519`` / ``2101`` **全库零非零行**（有该行的项目 5/5/5/3/5，非零行数全为 0）；
只有 ``1511`` 有 5 行非零、``1101`` 与 ``1531`` 各 1 行。``account_chart`` 侧 8 个码虽
**全部一码一名**（科目名与品种名逐字相同、无一码两义），但 client 侧 ``1504``/``1506``/
``1507`` **零命中**、``2101`` 仅 1/8、``1519`` standard 侧仅 4/10。

另有 memory 铁律旁证：「render 的 seed 回退标量必须与 Tier A 预设同口径，否则用户停用
公式后假差异复活」（D1 实证）—— 预设按码 vs 运行时按名，正是该铁律警告的口径分叉。

→ 运行态真源 = 相邻 ``{wpCode}`` 审定表 render-config 的 ``project_context.tb_amount``
（走 ``semantic_account_resolver`` 按科目名在**本项目**科目表定位 + 叶子聚合），由前端
``g0MatrixDataSources.loadG0MatrixSources`` 并行拉取。形态与
``backend/scripts/fix/fix_h0_prefill_presets.py`` 保持一致（H0 是 2 条、G0 逐品种 8 条 ——
更细是有意的：G0 品种↔相邻循环一一对应，能逐条写清真源 wp_code）。

🔴 cell_ref 键名真源
--------------------
``audit-platform/frontend/src/components/workpaper/g0-confirmation/g0MatrixDataSources.ts``
的 ``g0MatrixOverrideItemId(category, metric)`` → ``G0-1-matrix-{品种}-book_amount``
（Task 7 已交付，由 ``__tests__/g0SummaryMatrix.spec.ts`` 56 例钉死）。

design.md §Data Models 立项时写的 ``G0-1-lower-book-amount-{category}`` **已作废** ——
账面金额手工值就是 ``book_amount`` 这个可编辑指标的覆盖值，不另立键。照旧值写 cell_ref
= 预设指向没人读的键 = 死配置（「additive 注入即死代码」同族）。

故本脚本**不写死键名字面量**，而是读 TS 源码抽出模板串再拼接（``read_ts_cell_ref_template``），
TS 侧改规则时脚本立即 exit 2 而不是静默产出旧键。

🔴 三条不做的事
---------------
1. **只动 ``wp_code == 'G0'`` 的块**，其余 mappings 条目逐字节不变（``--dry-run``
   会显式打印比对结果）。
2. **不动 ``wp_name``**（``投资循环函证`` 与源模板一致）。
3. **不新增块级字段**：``convert_prefill_presets`` 只读 ``wp_code`` + ``cells``，
   纠偏依据写在 ``cells[].description`` 里（守卫按 Req 9.5 只扫语义字段，
   故描述里如实写出被纠正的反例不会打红）。

用法
----
    python backend/scripts/fix/fix_g0_prefill_presets.py --check
    python backend/scripts/fix/fix_g0_prefill_presets.py --dry-run
    python backend/scripts/fix/fix_g0_prefill_presets.py --apply

退出码：0 = 无欠账 / 1 = 有欠账（--check）/ 2 = 自检失败（不写盘）
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_JSON_PATH = _REPO_ROOT / "backend" / "data" / "prefill_formula_mapping.json"
_CHART_PATH = _REPO_ROOT / "backend" / "data" / "standard_account_chart.json"
_XLSX_PATH = _REPO_ROOT / "backend" / "wp_templates" / "G" / "G0 投资循环函证.xlsx"
_TS_PATH = (
    _REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "g0-confirmation"
    / "g0MatrixDataSources.ts"
)
_TS_MATRIX_PATH = _TS_PATH.with_name("g0SummaryMatrix.ts")

WP_CODE = "G0"

#: 源 xlsx 真实 tab 名（``wb.sheetnames`` 实证；``审定表G0-1`` 不存在）
EXPECTED_SHEET = "函证结果汇总表G0-1"

#: 唯一可手工覆盖的矩阵指标 key（源模板该行无公式）—— 与 TS ``EDITABLE_METRIC`` 同值
EDITABLE_METRIC = "book_amount"

#: 期末口径列名。🔴 只出现在 ``description`` 里说明口径 —— 8 条 formula 已是
#: ``PLACEHOLDER``，不再按码取数（见文件头「裁决」）。
PERIOD_COLUMN = "期末余额"

#: PLACEHOLDER 标签模板（与 H0 侧 ``=PLACEHOLDER('函证品种账面金额（期末未审）')`` 同形）
PLACEHOLDER_LABEL = "{category}本期（期末）账面金额"


@dataclass(frozen=True)
class BookAmountSpec:
    """一个投资品种的账面金额取数口径。

    顺序 = TS ``G0_MATRIX_CATEGORIES`` 顺序（源模板 ``G0-1!E20:H20`` 三格 + ``G0A!B7``
    程序 1 明列的品种全集）。``row_code``/``account_code`` 与
    ``backend/app/services/four_table/g_cycle_specs.py`` 的 G 循环规格逐条对齐。

    🔴 ``row_code`` / ``account_code`` **仅作展示与筛选**（写进 ``description`` 与块级
    ``account_codes``），运行态不据此取数（R4.4）—— 取数走 ``wp_code`` 指向的相邻审定表
    render-config 的语义定位结果。
    """

    category: str
    row_code: str
    account_code: str
    wp_code: str


BOOK_AMOUNT_SPECS: tuple[BookAmountSpec, ...] = (
    BookAmountSpec("交易性金融资产", "BS-003", "1101", "G1"),
    BookAmountSpec("长期股权投资", "BS-024", "1511", "G7"),
    BookAmountSpec("债权投资", "BS-021", "1504", "G4"),
    BookAmountSpec("长期应收款", "BS-023", "1531", "G5"),
    BookAmountSpec("其他债权投资", "BS-022", "1506", "G6"),
    BookAmountSpec("其他权益工具投资", "BS-025", "1507", "G8"),
    BookAmountSpec("其他非流动金融资产", "BS-026", "1519", "G9"),
    BookAmountSpec("交易性金融负债", "BS-042", "2101", "G10"),
)

#: 被纠正的反例（如实写进首条 description，供审计师理解口径变更）。
#: 🔴 守卫按 Req 9.5 只扫语义字段，故此串出现在 description 里不会打红。
LEGACY_RANGE_NOTE = (
    "纠偏：原 TB_SUM('1101~1511','期末余额') 是跨科目族区间，"
    "会把 1121 应收票据 / 1122 应收账款 / 1123 预付款项 / 1221 其他应收款 / 14xx 存货"
    "一并扫进投资循环"
)

#: 第二轮裁决的反例（2026-08-04）：连「按码 TB()」也不适用。同样只进 description。
LEGACY_TB_CODE_NOTE = (
    "按码 TB() 亦不适用 —— 实测 trial_balance 中 1504/1506/1507/1519/2101 全库零非零行，"
    "且 TB() 取不到时返 0 会让「无此科目」与「余额为 0」不可区分（R4.3）；"
    "cell_ref 又是手工覆盖键，写 TB() 等于让按码取到的 0 伪装成审计师手填值、"
    "压住语义定位拿到的 undefined（R3.5）"
)


# ── cell_ref 键名：读 TS 源码抽模板串，不写死字面量 ──────────────────────────


def read_ts_cell_ref_template(ts_source: str | None = None) -> str:
    """从 ``g0MatrixDataSources.ts`` 抽 ``g0MatrixOverrideItemId`` 的模板串。

    返回形如 ``G0-1-matrix-${category}-${metric}``。抽不到即抛错（宁可打红也不静默
    回退字面量 —— 静默回退会让 TS 侧改规则后脚本继续产出旧键 = 死配置）。
    """
    src = ts_source if ts_source is not None else _TS_PATH.read_text(encoding="utf-8")
    m = re.search(
        r"export\s+function\s+g0MatrixOverrideItemId\s*\([^)]*\)\s*:\s*string\s*\{"
        r"\s*return\s*`([^`]+)`",
        src,
    )
    if not m:
        raise SystemExit(
            "[FATAL] 无法从 g0MatrixDataSources.ts 抽出 g0MatrixOverrideItemId 的模板串，"
            "TS 侧签名或实现已变，请复核 spec Task 7 后再跑本脚本"
        )
    return m.group(1)


def render_cell_ref(template: str, category: str, metric: str = EDITABLE_METRIC) -> str:
    """按 TS 模板串拼 cell_ref（复刻 ``g0MatrixOverrideItemId`` 的拼接规则）。"""
    out = template.replace("${category}", category).replace("${metric}", metric)
    if "${" in out:
        raise SystemExit(f"[FATAL] cell_ref 模板含未知占位符，无法安全拼接: {template!r}")
    return out


def read_ts_matrix_categories(ts_source: str | None = None) -> list[tuple[str, str, str]]:
    """从 ``g0SummaryMatrix.ts`` 抽 ``G0_MATRIX_CATEGORIES`` 的 (品种, rowCode, wpCode)。

    用于交叉锁死本脚本的 ``BOOK_AMOUNT_SPECS`` —— 两侧任一漂移即 exit 2。
    """
    src = ts_source if ts_source is not None else _TS_MATRIX_PATH.read_text(encoding="utf-8")
    start = src.find("G0_MATRIX_CATEGORIES")
    if start < 0:
        raise SystemExit("[FATAL] g0SummaryMatrix.ts 未找到 G0_MATRIX_CATEGORIES")
    end = src.find("G0_CATEGORY_NAMES", start)
    block = src[start : end if end > start else len(src)]
    out: list[tuple[str, str, str]] = []
    for m in re.finditer(
        r"name:\s*'([^']+)'\s*,\s*book:\s*\{\s*rowCode:\s*'([^']+)'\s*,\s*wpCode:\s*'([^']+)'",
        block,
    ):
        out.append((m.group(1), m.group(2), m.group(3)))
    if not out:
        raise SystemExit("[FATAL] 从 G0_MATRIX_CATEGORIES 抽取品种为空（正则失效）")
    return out


# ── 期望块 ────────────────────────────────────────────────────────────────────


def build_expected_cells(template: str) -> list[dict]:
    cells: list[dict] = []
    for idx, spec in enumerate(BOOK_AMOUNT_SPECS):
        label = PLACEHOLDER_LABEL.format(category=spec.category)
        desc = (
            f"品种「{spec.category}」本期（期末）账面金额。"
            f"取数真源 = 相邻 {spec.wp_code} 审定表 render-config 的 "
            f"`project_context.tb_amount`（走 semantic_account_resolver 按科目名在"
            f"**本项目**科目表定位 + 叶子聚合，{PERIOD_COLUMN}口径），"
            f"由前端 `g0MatrixDataSources.loadG0MatrixSources` 并行拉取。"
            f"报表行 {spec.row_code}、参考科目码 {spec.account_code} "
            f"**仅作展示与筛选，运行态不据此取数**（R4.4）。"
            f"本项目无该科目时显示「本项目无此科目」而非 0（R4.3）。"
        )
        if idx == 0:
            desc = f"{desc}{LEGACY_RANGE_NOTE}；{LEGACY_TB_CODE_NOTE}。"
        cells.append(
            {
                "cell_ref": render_cell_ref(template, spec.category),
                "formula": f"=PLACEHOLDER('{label}')",
                "formula_type": "PLACEHOLDER",
                "description": desc,
            }
        )
    return cells


def build_expected_block(existing: dict, template: str) -> dict:
    """在既有块上做最小改动：只改 sheet / account_codes / cells，其余键原样保留。"""
    out = dict(existing)
    out["sheet"] = EXPECTED_SHEET
    out["account_codes"] = [s.account_code for s in BOOK_AMOUNT_SPECS]
    out["cells"] = build_expected_cells(template)
    return out


# ── 定位与计划 ────────────────────────────────────────────────────────────────


def find_g0_indexes(data: dict) -> list[int]:
    mappings = data.get("mappings")
    if not isinstance(mappings, list):
        raise SystemExit("[FATAL] `mappings` 不是数组，源数据结构已变")
    return [i for i, m in enumerate(mappings) if isinstance(m, dict) and m.get("wp_code") == WP_CODE]


def plan(data: dict, template: str) -> tuple[int, list[str]]:
    """返回 (G0 块索引, 变更清单)。变更清单为空 = 无欠账。"""
    idx_list = find_g0_indexes(data)
    if len(idx_list) != 1:
        raise SystemExit(
            f"[FATAL] 期望 mappings 内恰好 1 处 wp_code=='{WP_CODE}'，实为 {len(idx_list)} 处"
            f"（索引 {idx_list}）—— 并发会话可能改过结构，请先人工复核"
        )
    idx = idx_list[0]
    cur = data["mappings"][idx]
    exp = build_expected_block(cur, template)

    changes: list[str] = []
    if cur.get("sheet") != exp["sheet"]:
        changes.append(f"sheet: {cur.get('sheet')!r} → {exp['sheet']!r}")
    if list(cur.get("account_codes") or []) != exp["account_codes"]:
        changes.append(
            f"account_codes: {list(cur.get('account_codes') or [])} → {exp['account_codes']}"
        )

    cur_cells = list(cur.get("cells") or [])
    exp_cells = exp["cells"]
    cur_refs = [c.get("cell_ref") for c in cur_cells]
    exp_refs = [c["cell_ref"] for c in exp_cells]
    for ref in cur_refs:
        if ref not in exp_refs:
            old = next(c for c in cur_cells if c.get("cell_ref") == ref)
            changes.append(f"cells- 删除 cell_ref={ref!r}  formula={old.get('formula')!r}")
    for cell in exp_cells:
        old = next((c for c in cur_cells if c.get("cell_ref") == cell["cell_ref"]), None)
        if old is None:
            changes.append(
                f"cells+ 新增 cell_ref={cell['cell_ref']!r}  formula={cell['formula']!r}"
            )
        elif old != cell:
            diffs = [k for k in cell if old.get(k) != cell[k]]
            line = f"cells~ 修改 cell_ref={cell['cell_ref']!r}  字段 {diffs}"
            if "formula" in diffs:
                line += (
                    f"\n         formula      {old.get('formula')!r} → {cell['formula']!r}"
                    f"\n         formula_type {old.get('formula_type')!r}"
                    f" → {cell['formula_type']!r}"
                )
            changes.append(line)
    if cur_refs != exp_refs and not any(c.startswith(("cells+", "cells-")) for c in changes):
        changes.append(f"cells 顺序: {cur_refs} → {exp_refs}")
    return idx, changes


def apply_plan(data: dict, idx: int, template: str) -> None:
    data["mappings"][idx] = build_expected_block(data["mappings"][idx], template)


def non_g0_snapshot(data: dict, g0_idx: int) -> list[tuple[int, str]]:
    """其余 mappings 条目的规范化快照，用于证明「零变更」。"""
    return [
        (i, json.dumps(m, ensure_ascii=False, sort_keys=True))
        for i, m in enumerate(data.get("mappings") or [])
        if i != g0_idx
    ]


# ── 自检 ──────────────────────────────────────────────────────────────────────


def selfcheck_roundtrip(raw: str, data: dict) -> str | None:
    """``json.dumps`` 必须逐字复现原文，否则整文件写回会造成全文件重排。

    实测本文件形态 = ``indent=2`` + 默认分隔符 + 尾部换行（273737 字节逐字命中）。
    返回错误串，None = 通过。
    """
    reproduced = json.dumps(data, indent=2, ensure_ascii=False) + ("\n" if raw.endswith("\n") else "")
    if reproduced != raw:
        n = min(len(reproduced), len(raw))
        at = next((i for i in range(n) if reproduced[i] != raw[i]), n)
        return (
            "round-trip 自检失败：json.dumps(indent=2, ensure_ascii=False) 无法逐字复现原文"
            f"（{len(reproduced)} vs {len(raw)} 字节，首处差异 offset={at}），拒绝写盘"
        )
    return None


@lru_cache(maxsize=1)
def source_sheetnames() -> tuple[str, ...]:
    """openpyxl 直读源 xlsx 的 tab 名（缓存 —— 该工作簿加载约 10s）。"""
    import warnings

    import openpyxl

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(_XLSX_PATH)
    return tuple(wb.sheetnames)


def selfcheck_sheet_name() -> str | None:
    """源 xlsx 交叉比对：EXPECTED_SHEET 必须在 wb.sheetnames 内，旧值必须不在。"""
    if not _XLSX_PATH.exists():
        print(f"[WARN] 源模板缺失，跳过 sheet 名交叉比对: {_XLSX_PATH}", file=sys.stderr)
        return None
    names = list(source_sheetnames())
    if EXPECTED_SHEET not in names:
        return f"EXPECTED_SHEET={EXPECTED_SHEET!r} 不在源 xlsx sheetnames 内: {names}"
    if "审定表G0-1" in names:
        return "源 xlsx 竟含 `审定表G0-1` —— 纠偏前提不成立，请复核 spec R9.1"
    return None


def selfcheck_account_codes() -> str | None:
    """标准科目表交叉比对：8 个码都在表内，且科目名与品种名逐字相同。"""
    if not _CHART_PATH.exists():
        return f"标准科目表缺失: {_CHART_PATH}"
    chart = json.loads(_CHART_PATH.read_text(encoding="utf-8"))
    by_code = {a["code"]: a["name"] for a in chart.get("accounts") or []}
    bad: list[str] = []
    for spec in BOOK_AMOUNT_SPECS:
        name = by_code.get(spec.account_code)
        if name is None:
            bad.append(f"{spec.account_code} 不在标准科目表内（品种 {spec.category}）")
        elif name != spec.category:
            bad.append(f"{spec.account_code} 标准科目名 {name!r} ≠ 品种名 {spec.category!r}")
    return "；".join(bad) if bad else None


def selfcheck_ts_categories() -> str | None:
    """与前端 G0_MATRIX_CATEGORIES 交叉锁死（品种名 / rowCode / wpCode 逐条相等）。"""
    if not _TS_MATRIX_PATH.exists():
        print(f"[WARN] 前端矩阵定义缺失，跳过交叉锁死: {_TS_MATRIX_PATH}", file=sys.stderr)
        return None
    ts = read_ts_matrix_categories()
    mine = [(s.category, s.row_code, s.wp_code) for s in BOOK_AMOUNT_SPECS]
    if ts != mine:
        return f"与前端 G0_MATRIX_CATEGORIES 不一致：\n  TS   = {ts}\n  脚本 = {mine}"
    return None


def selfcheck_no_range_formula(data: dict, idx: int) -> str | None:
    """语义字段级断言：G0 块 formula 不得含跨科目族区间 ``TB_SUM('a~b')``。"""
    pat = re.compile(r"TB_SUM\(\s*'[^']*~[^']*'")
    bad = [
        c.get("cell_ref")
        for c in data["mappings"][idx].get("cells") or []
        if pat.search(str(c.get("formula") or ""))
    ]
    return f"G0 块仍有跨科目族区间公式: {bad}" if bad else None


def selfcheck_no_account_code_in_formula(data: dict, idx: int) -> str | None:
    """语义字段级断言：8 条 ``formula`` 不得出现任何科目码字面量（R4.4 / Property 11）。

    科目码只许出现在 ``description``（展示与溯源）与块级 ``account_codes``（筛选）里。
    公式一旦写码就等于回到「按码取数」，与语义定位口径分叉。
    """
    bad: list[str] = []
    for cell in data["mappings"][idx].get("cells") or []:
        formula = str(cell.get("formula") or "")
        hits = sorted(set(re.findall(r"\d{4,}", formula)))
        if hits:
            bad.append(f"cell_ref={cell.get('cell_ref')!r} 的 formula 含科目码字面量 {hits}")
    return "；".join(bad) if bad else None


def _run_selfchecks(raw: str, data: dict) -> int:
    """跑全部前置自检；返回 0 通过 / 2 失败。"""
    for err in (
        selfcheck_roundtrip(raw, data),
        selfcheck_sheet_name(),
        selfcheck_account_codes(),
        selfcheck_ts_categories(),
    ):
        if err:
            print(f"[FATAL] {err}", file=sys.stderr)
            return 2
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="G0 公式预设纠偏（幂等）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="只报欠账，有欠账 exit 1")
    g.add_argument("--dry-run", action="store_true", help="打印变更清单，不写盘")
    g.add_argument("--apply", action="store_true", help="写盘")
    args = ap.parse_args()

    raw = _JSON_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)

    rc = _run_selfchecks(raw, data)
    if rc:
        return rc
    print("[OK] 前置自检通过：round-trip / 源 xlsx sheet 名 / 标准科目表 / 前端矩阵定义")

    template = read_ts_cell_ref_template()
    print(f"[OK] cell_ref 模板取自 g0MatrixDataSources.ts: {template!r}")

    idx, changes = plan(data, template)
    print(f"[INFO] G0 块位于 mappings[{idx}]，全文件共 {len(data['mappings'])} 条 mapping")

    before = non_g0_snapshot(data, idx)
    after_data = copy.deepcopy(data)
    apply_plan(after_data, idx, template)
    after = non_g0_snapshot(after_data, idx)
    if before != after:
        moved = [i for (i, a), (_, b) in zip(before, after) if a != b]
        print(f"[FATAL] 其余 mappings 条目被改动（索引 {moved}），拒绝继续", file=sys.stderr)
        return 2
    print(
        f"[OK] 其余 mappings 条目 0 变更：{len(before)}/{len(before)} 条逐字节相同"
        f"（仅 mappings[{idx}] 在变更范围内）"
    )

    for err in (
        selfcheck_no_range_formula(after_data, idx),
        selfcheck_no_account_code_in_formula(after_data, idx),
    ):
        if err:
            print(f"[FATAL] {err}", file=sys.stderr)
            return 2

    if not changes:
        print(f"[OK] G0 预设已修正（sheet={EXPECTED_SHEET}，8 条 PLACEHOLDER），0 项欠账")
        return 0

    print(f"[PLAN] {len(changes)} 项变更：")
    for line in changes:
        print(f"  {line}")

    if args.check:
        print(f"[FAIL] {len(changes)} 项欠账", file=sys.stderr)
        return 1
    if args.dry_run:
        print("[DRY-RUN] 未写盘")
        return 0

    apply_plan(data, idx, template)
    out = json.dumps(data, indent=2, ensure_ascii=False) + ("\n" if raw.endswith("\n") else "")
    _JSON_PATH.write_text(out, encoding="utf-8")
    print(f"[APPLIED] 已写入 {_JSON_PATH}")

    again_raw = _JSON_PATH.read_text(encoding="utf-8")
    again_data = json.loads(again_raw)
    if err := selfcheck_roundtrip(again_raw, again_data):
        print(f"[FATAL] 写盘后 {err}", file=sys.stderr)
        return 2
    _, again = plan(again_data, template)
    if again:
        print(f"[FATAL] 幂等自检失败：写盘后仍有 {len(again)} 项欠账", file=sys.stderr)
        return 2
    print("[OK] 幂等自检通过（再次计划 0 项）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
