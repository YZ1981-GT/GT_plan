"""F2 附注披露（上市 / 国企）—— 多区块导入导出。

与其它 F2 sheet 的差别：披露页不是单表，而是「多个表格区块 + 多个文本域」。
故 workbook 采用**一区块一 sheet**，文本域集中到「文本说明」sheet：

    编制说明            —— 使用指引（不参与导入）
    (1)存货分类(只读)    —— 跨 sheet 取数（F2-1），仅导出，导入时忽略
    (2)跌价准备变动      —— override map（键=披露分类 rowKey）
    (3)按组合计提-期末   —— rows 数组
    (3)按组合计提-期初   —— rows 数组
    (5)开发成本 / (6)开发产品 / (7)周转房 —— rows 数组（仅上市）
    (8)确认为存货的数据资源 —— DR 三来源列 map
    文本说明            —— 各文本域「区块 | 内容」两列

存储契约（与前端 `useF2Disclosure{Listed,Soe}.ts` 一致）：
- 全部披露 item 存在 **`remark`** 字段，`conclusion` 为 null
- item_id = `F2-note-{variant}-{suffix}`
- 派生列（净值/占比/计提比例/期末余额）不导出、不导入，由前端公式重算

Spec: .kiro/specs/f2-inventory-disclosure-template-alignment/ Task 13.4
"""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass, field as dc_field
from typing import Any, Literal

import sqlalchemy as sa
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession

from ._cycle_import_export_common import ROW_LIMIT, safe_float, safe_str

logger = logging.getLogger(__name__)

Variant = Literal["listed", "soe"]

SHEET_LISTED = "F2-note-listed"
SHEET_SOE = "F2-note-soe"

_HEADER_FILL = PatternFill("solid", fgColor="F0EDF5")
_SECTION_FILL = PatternFill("solid", fgColor="FFF8E6")


# ════════════════════════════════════════════════════════════════════
# 分类行镜像常量
#
# 🔴 双真源风险：以下三张表是前端常量的镜像，靠 `test_f2_disclosure_import_export.py`
# 的契约测试（直接正则读 .ts 源码逐条比对 rowKey/label）守住漂移。改前端务必同步此处。
#   listed → useF2DisclosureListed.ts  F2_LISTED_DISCLOSURE_CATEGORIES
#   soe    → useF2DisclosureSoe.ts     F2_SOE_DISCLOSURE_CATEGORIES
#   dr     → f2DataResourceInventory.ts ROW_DEFS
# ════════════════════════════════════════════════════════════════════

_LISTED_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("raw-materials", "原材料"),
    ("work-in-progress", "在产品"),
    # Sprint 8 新增：源 xlsx 注要求房地产开发企业增加「开发成本」「开发产品」种类
    ("dev-costs", "开发成本"),
    ("outsourced-processing", "委托加工物资"),
    ("finished-goods", "库存商品"),
    ("dev-products", "开发产品"),
    ("goods-in-transit", "发出商品"),
    ("revolving-materials", "周转材料"),
    ("contract-performance", "合同履约成本"),
    ("consumable-bio", "消耗性生物资产"),
    ("data-resources", "数据资源"),
)

_SOE_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("raw-combined", "原材料"),
    ("wip-combined", "自制半成品及在产品"),
    ("dev-costs", "其中：开发成本"),
    ("outsourced-processing", "委托加工物资"),
    ("fg-combined", "库存商品（产成品）"),
    ("dev-products", "其中：开发产品"),
    ("revolving-materials", "周转材料（包装物、低值易耗品等）"),
    ("goods-in-transit", "发出商品"),
    ("consumable-bio", "消耗性生物资产"),
    ("contract-performance", "合同履约成本"),
    ("data-resources", "数据资源"),
    ("other", "其他"),
    ("land-reserve", "其中：尚未开发的土地储备（由房地产开发企业填列）"),
)

# (rowKey, label, kind)；kind 为 section/derived 的行只展示不录入
_DR_ROW_DEFS: tuple[tuple[str, str, str], ...] = (
    ("gross-section", "一、账面原值", "section"),
    ("gross-open", "1.期初余额", "input"),
    ("gross-inc", "2.本期增加金额", "input"),
    ("gross-inc-purchase", "其中：购入", "sub"),
    ("gross-inc-collect", "采集加工", "sub"),
    ("gross-inc-other", "其他增加", "sub"),
    ("gross-dec", "3.本期减少金额", "input"),
    ("gross-dec-sale", "其中：出售", "sub"),
    ("gross-dec-invalid", "失效且终止确认", "sub"),
    ("gross-dec-other", "其他减少", "sub"),
    ("gross-end", "4.期末余额", "derived"),
    ("imp-section", "二、存货跌价准备", "section"),
    ("imp-open", "1.期初余额", "input"),
    ("imp-inc", "2.本期增加金额", "input"),
    ("imp-dec", "3.本期减少金额", "input"),
    ("imp-dec-reversal", "其中：转回", "sub"),
    ("imp-dec-writeoff", "转销", "sub"),
    ("imp-end", "4.期末余额", "derived"),
    ("nv-section", "三、账面价值", "section"),
    ("nv-end", "1.期末账面价值", "derived"),
    ("nv-open", "2.期初账面价值", "derived"),
)

_DR_SOE_LABEL_OVERRIDES = {"imp-section": "二、跌价准备"}

_DR_COL_KEYS: tuple[str, ...] = ("purchased", "selfProcessed", "other")
_DR_COL_LABELS: dict[str, str] = {
    "purchased": "外购的数据资源存货",
    "selfProcessed": "自行加工的数据资源存货",
    "other": "其他方式取得的数据资源存货",
}

# 🔴 DR 表**必须**按 rowKey 匹配，不能按行标签：三段骨架里「1.期初余额」/「2.本期增加金额」/
# 「3.本期减少金额」/「4.期末余额」在账面原值段与跌价准备段**同名重复**，按标签匹配会让后段
# 静默覆盖前段（已被 test_roundtrip_dr 抓出）。故导出首列写 rowKey，第二列才是可读标签。
_DR_KEY_HEADER = "行标识(勿改)"
_DR_LABEL_HEADER = "行项目"


# ════════════════════════════════════════════════════════════════════
# 区块定义
# ════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class _Block:
    """一个可导入区块 ↔ 一个 workbook sheet。"""

    sheet: str
    """workbook sheet 名（≤31 字符，禁 []:*?/\\）。"""
    suffix: str
    """item_id 后缀（完整 item_id = `F2-note-{variant}-{suffix}`）。"""
    kind: Literal["rows", "override", "dr"]
    headers: tuple[str, ...]
    keys: tuple[str, ...] = ()
    """与 headers 等长的字段名；`override` 的首列为主键列故 keys 少一个。"""
    numeric: frozenset[str] = dc_field(default_factory=frozenset)
    """需按数值解析的 key（不用公共启发式，避免 balance/opening/ending 被漏判）。"""
    note: str = ""
    """写入 sheet 首行的提示。"""


_S3_HEADERS = ("组合名称", "账面余额", "跌价准备", "计提标准")
_S3_KEYS = ("groupName", "balance", "impairment", "provisionStandard")
_S3_NUMERIC = frozenset({"balance", "impairment"})

_LISTED_BLOCKS: tuple[_Block, ...] = (
    _Block(
        sheet="(2)跌价准备变动",
        suffix="s2-overrides",
        kind="override",
        headers=("类别名", "本期计提", "本期其他增加", "本期转回", "本期其他减少"),
        keys=("incProvision", "incOther", "decReversal", "decOther"),
        numeric=frozenset({"incProvision", "incOther", "decReversal", "decOther"}),
        note=(
            "填数=手工覆盖，留空=沿用 F2-1 自动取数。"
            "本表为**整表覆盖**：请先「导出数据」再改，清空某行即撤销该类别的覆盖；"
            "若整表未填任何数则本表跳过（不会误清既有覆盖）。期末余额由公式重算，不在此填。"
        ),
    ),
    _Block(
        sheet="(3)按组合计提-期末",
        suffix="s3-end",
        kind="rows",
        headers=_S3_HEADERS,
        keys=_S3_KEYS,
        numeric=_S3_NUMERIC,
        note="账面价值/占比/计提比例为公式列，不导入。计提比例 = 跌价准备 ÷ 账面余额。",
    ),
    _Block(
        sheet="(3)按组合计提-期初",
        suffix="s3-prior",
        kind="rows",
        headers=_S3_HEADERS,
        keys=_S3_KEYS,
        numeric=_S3_NUMERIC,
        note="同「期末」表，本表为上年年末组合。",
    ),
    _Block(
        sheet="(5)开发成本",
        suffix="s5-rows",
        kind="rows",
        headers=(
            "项目名称", "开工时间", "预计竣工时间", "预计总投资",
            "期末余额", "上年年末余额", "期末跌价准备",
        ),
        keys=(
            "projectName", "startDate", "expectedCompleteDate", "estimatedInvestment",
            "endBalance", "priorBalance", "endImpairment",
        ),
        numeric=frozenset({"estimatedInvestment", "endBalance", "priorBalance", "endImpairment"}),
        note="房地产开发企业填列。时间列按文本导入（如 2025-03 或 2025年3月）。",
    ),
    _Block(
        sheet="(6)开发产品",
        suffix="s6-rows",
        kind="rows",
        headers=("项目名称", "竣工时间", "期初余额", "本期增加", "本期减少", "期末余额", "期末跌价准备"),
        keys=("projectName", "completeDate", "opening", "increase", "decrease", "ending", "endImpairment"),
        numeric=frozenset({"opening", "increase", "decrease", "ending", "endImpairment"}),
        note="期末余额可留空由公式算（期初+增加−减少）；填了以填写值为准。",
    ),
    _Block(
        sheet="(7)周转房",
        suffix="s7-rows",
        kind="rows",
        headers=("项目名称", "期初余额", "本期增加", "本期减少", "期末余额"),
        keys=("projectName", "opening", "increase", "decrease", "ending"),
        numeric=frozenset({"opening", "increase", "decrease", "ending"}),
        note="期末余额可留空由公式算（期初+增加−减少）。",
    ),
    _Block(
        sheet="(8)数据资源",
        suffix="s8-data-resource",
        kind="dr",
        headers=(_DR_KEY_HEADER, _DR_LABEL_HEADER, *(_DR_COL_LABELS[k] for k in _DR_COL_KEYS)),
        note=(
            "按「行标识」列匹配行，请勿修改或删除该列"
            "（三段中「1.期初余额」等标签重复，只能靠行标识区分）。"
            "段标题行与公式行（4.期末余额 / 账面价值）为只读，填了也不导入。"
        ),
    ),
)

_SOE_BLOCKS: tuple[_Block, ...] = (
    _Block(
        sheet="(2)跌价准备变动",
        suffix="s2-overrides",
        kind="override",
        headers=("类别名", "本期计提", "本期其他增加", "本期转回", "本期核销", "本期其他减少"),
        keys=("incProvision", "incOther", "decReversal", "decWriteOff", "decOther"),
        numeric=frozenset({"incProvision", "incOther", "decReversal", "decWriteOff", "decOther"}),
        note=(
            "填数=手工覆盖，留空=沿用 F2-1 自动取数。"
            "本表为**整表覆盖**：请先「导出数据」再改，清空某行即撤销该类别的覆盖；"
            "若整表未填任何数则本表跳过（不会误清既有覆盖）。期末余额由公式重算，不在此填。"
        ),
    ),
    _Block(
        sheet="(5)数据资源",
        suffix="s5-data-resource",
        kind="dr",
        headers=(_DR_KEY_HEADER, _DR_LABEL_HEADER, *(_DR_COL_LABELS[k] for k in _DR_COL_KEYS)),
        note=(
            "按「行标识」列匹配行，请勿修改或删除该列"
            "（三段中「1.期初余额」等标签重复，只能靠行标识区分）。"
            "段标题行与公式行（4.期末余额 / 账面价值）为只读，填了也不导入。"
        ),
    ),
)

# 文本域：(item 后缀, 区块名)。区块名即「文本说明」sheet 的首列，导入按它匹配。
_LISTED_TEXTS: tuple[tuple[str, str], ...] = (
    ("note-category", "(1) 存货分类说明"),
    ("note-nrv", "(2) 可变现净值确定依据及转回/转销原因"),
    ("note-provision", "(2) 存货跌价准备计提依据"),
    ("note-borrow", "(4) 借款费用资本化金额说明"),
    ("note-amort", "(4) 合同履约成本本期摊销金额说明"),
    ("note-re", "房地产开发企业补充披露说明"),
)

_SOE_TEXTS: tuple[tuple[str, str], ...] = (
    ("note-category", "(1) 存货分类说明"),
    ("land-note", "(1) 尚未开发土地储备说明"),
    ("note-borrow", "(3) 借款费用资本化金额说明"),
    ("note-amort", "(4) 合同履约成本本期摊销金额说明"),
    ("note", "(2) 跌价准备其他应披露事项"),
)

_GUIDE_SHEET = "编制说明"
_TEXT_SHEET = "文本说明"
_CLASS_SHEET = "(1)存货分类(只读)"

_TEXT_HEADERS = ("区块", "内容")
_CLASS_HEADERS = (
    "类别名", "期末账面余额", "期末跌价准备", "期末账面价值",
    "上年年末账面余额", "上年年末跌价准备", "上年年末账面价值",
)


def _variant_of(sheet: str) -> Variant:
    if sheet == SHEET_LISTED:
        return "listed"
    if sheet == SHEET_SOE:
        return "soe"
    raise ValueError(f"非披露 sheet: {sheet}")


def blocks_of(variant: Variant) -> tuple[_Block, ...]:
    return _LISTED_BLOCKS if variant == "listed" else _SOE_BLOCKS


def texts_of(variant: Variant) -> tuple[tuple[str, str], ...]:
    return _LISTED_TEXTS if variant == "listed" else _SOE_TEXTS


def categories_of(variant: Variant) -> tuple[tuple[str, str], ...]:
    return _LISTED_CATEGORIES if variant == "listed" else _SOE_CATEGORIES


def item_id_of(variant: Variant, suffix: str) -> str:
    return f"F2-note-{variant}-{suffix}"


def dr_rows_of(variant: Variant) -> tuple[tuple[str, str, str], ...]:
    """DR 21 行骨架（国企替换段标题用词）。"""
    if variant == "listed":
        return _DR_ROW_DEFS
    return tuple(
        (rk, _DR_SOE_LABEL_OVERRIDES.get(rk, label), kind) for rk, label, kind in _DR_ROW_DEFS
    )


# ════════════════════════════════════════════════════════════════════
# 读写 helper
# ════════════════════════════════════════════════════════════════════


async def _load_remarks(db: AsyncSession, wp_id: str, prefix: str) -> dict[str, str]:
    """一次取回该底稿下所有 `prefix%` 的 remark（item_id → remark）。"""
    result = await db.execute(
        sa.text(
            "SELECT item_id, remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE :pat"
        ),
        {"wp_id": wp_id, "pat": f"{prefix}%"},
    )
    return {r[0]: (r[1] or "") for r in result.all()}


def _parse_json(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


async def _load_class_rows(db: AsyncSession, wp_id: str, variant: Variant) -> list[list[Any]]:
    """复刻前端 `loadClassRow`：按 sourceKeys 合并 F2-1 逐字段取数。

    仅用于「(1)存货分类(只读)」导出，让用户导出后能核对期末/上年数。
    sourceKeys 由前端常量决定，此处只需 rowKey→sourceKeys 的映射。
    """
    source_map = _LISTED_SOURCE_KEYS if variant == "listed" else _SOE_SOURCE_KEYS
    fields = ("opening", "increase", "decrease", "adjustment")

    result = await db.execute(
        sa.text(
            "SELECT item_id, conclusion FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE 'F2-1-%'"
        ),
        {"wp_id": wp_id},
    )
    raw: dict[str, float] = {r[0]: safe_float(r[1]) for r in result.all()}

    def _sum(block: str, source_keys: tuple[str, ...], fld: str) -> float:
        return sum(raw.get(f"F2-1-{block}-{sk}-{fld}", 0.0) for sk in source_keys)

    out: list[list[Any]] = []
    for row_key, label in categories_of(variant):
        sks = source_map.get(row_key, (row_key,))
        vals: dict[str, dict[str, float]] = {}
        for block in ("gross", "impairment"):
            vals[block] = {f: _sum(block, sks, f) for f in fields}
        # 期末 = 期初 + 增加 − 减少 + 账项调整（与前端 loadClassRow 同口径）
        end_gross = (
            vals["gross"]["opening"] + vals["gross"]["increase"]
            - vals["gross"]["decrease"] + vals["gross"]["adjustment"]
        )
        end_imp = (
            vals["impairment"]["opening"] + vals["impairment"]["increase"]
            - vals["impairment"]["decrease"] + vals["impairment"]["adjustment"]
        )
        prior_gross = vals["gross"]["opening"]
        prior_imp = vals["impairment"]["opening"]
        out.append([
            label,
            round(end_gross, 2), round(end_imp, 2), round(end_gross - end_imp, 2),
            round(prior_gross, 2), round(prior_imp, 2), round(prior_gross - prior_imp, 2),
        ])
    return out


# rowKey → sourceKeys（镜像前端常量的 sourceKeys 字段，契约测试同步守）
_LISTED_SOURCE_KEYS: dict[str, tuple[str, ...]] = {
    "raw-materials": ("raw-materials", "material-in-transit"),
    # `work-in-progress` 作行标识保留，但不是审定表 rowKey（1404 是 semi-finished）→ 已从取数键删除
    "work-in-progress": ("semi-finished",),
    "dev-costs": ("dev-costs",),
    "outsourced-processing": ("outsourced-processing",),
    # 1412 商品进销差价是 1406 的备抵科目，上市版并入库存商品（国企版归「其他」）
    "finished-goods": ("finished-goods", "price-difference"),
    "dev-products": ("dev-products",),
    "goods-in-transit": ("goods-in-transit",),
    "revolving-materials": ("revolving-materials",),
    "contract-performance": ("contract-performance",),
    "consumable-bio": ("consumable-bio",),
    # 数据资源无对应存货科目 → 从 (8) 数据资源表联动，无取数键
    "data-resources": (),
}

_SOE_SOURCE_KEYS: dict[str, tuple[str, ...]] = {
    "raw-combined": ("raw-materials", "material-in-transit"),
    # 死键 `work-in-progress` 已删（1404 是 semi-finished）
    "wip-combined": ("semi-finished", "dev-costs"),
    "dev-costs": ("dev-costs",),
    "outsourced-processing": ("outsourced-processing",),
    "fg-combined": ("finished-goods", "dev-products"),
    "dev-products": ("dev-products",),
    "revolving-materials": ("revolving-materials",),
    "goods-in-transit": ("goods-in-transit",),
    "consumable-bio": ("consumable-bio",),
    "contract-performance": ("contract-performance",),
    # 数据资源无对应存货科目 → 从 (5) 数据资源表联动，无取数键
    "data-resources": (),
    # 死键 `other` 已删；「其他」行余量由 s1Overrides 手工录入
    "other": ("price-difference",),
    # 土地储备无对应科目 → 全靠 s1Overrides 手工录入
    "land-reserve": (),
}


# ════════════════════════════════════════════════════════════════════
# 导出
# ════════════════════════════════════════════════════════════════════


def _style_header(ws: Any, row_idx: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row_idx, column=c)
        cell.font = Font(bold=True)
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _autosize(ws: Any, ncols: int, *, wide_first: bool = True) -> None:
    for c in range(1, ncols + 1):
        width = 32 if (c == 1 and wide_first) else 16
        ws.column_dimensions[get_column_letter(c)].width = width


def _write_block_sheet(wb: Workbook, blk: _Block, data_rows: list[list[Any]]) -> None:
    ws = wb.create_sheet(blk.sheet)
    ncols = len(blk.headers)
    if blk.note:
        ws.append([f"提示：{blk.note}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
        ws.cell(row=1, column=1).font = Font(italic=True, color="8A6D3B")
        ws.cell(row=1, column=1).alignment = Alignment(wrap_text=True)
    ws.append(list(blk.headers))
    _style_header(ws, ws.max_row, ncols)
    header_row = ws.max_row
    for r in data_rows:
        ws.append(r)
    ws.freeze_panes = f"A{header_row + 1}"
    _autosize(ws, ncols)


def _guidance_lines(variant: Variant) -> list[str]:
    label = "上市公司" if variant == "listed" else "国有企业"
    lines = [
        f"F2 附注披露信息（{label}）—— 多区块导入导出",
        "",
        "一、每个业务区块对应一个工作表，表名前缀与底稿小节编号一致。",
        "二、导入按**工作表名**定位区块，缺失的工作表跳过（不清空原数据）。",
        "三、公式列（账面价值 / 占比 / 计提比例 / 期末余额 / 合计）不导出也不导入，由系统重算。",
        f"四、「{_CLASS_SHEET}」来自 F2-1 审定表跨表取数，**仅供核对，导入时忽略**。",
        f"五、「{_TEXT_SHEET}」按首列「区块」匹配文本域，区块名请勿改动。",
        f"六、每张表数据行上限 {ROW_LIMIT} 行，超出部分会被截断。",
        "",
        "区块清单：",
    ]
    for blk in blocks_of(variant):
        lines.append(f"  {blk.sheet} — {'覆盖值' if blk.kind == 'override' else '明细行' if blk.kind == 'rows' else '三来源列'}")
    lines.append(f"  {_TEXT_SHEET} — {len(texts_of(variant))} 个文本域")
    return lines


def _write_guide(wb: Workbook, variant: Variant) -> None:
    ws = wb.active
    ws.title = _GUIDE_SHEET
    for line in _guidance_lines(variant):
        ws.append([line])
    ws.cell(row=1, column=1).font = Font(bold=True, size=12)
    ws.column_dimensions["A"].width = 92


def _dr_data_rows(variant: Variant, values: dict[str, Any]) -> list[list[Any]]:
    """DR 表导出行：首列 rowKey（匹配键），次列可读标签；section/derived 值列留空表示只读。"""
    rows: list[list[Any]] = []
    for row_key, label, kind in dr_rows_of(variant):
        if kind in ("section", "derived"):
            rows.append([row_key, label, None, None, None])
            continue
        cell = values.get(row_key) or {}
        rows.append([
            row_key,
            label,
            *(round(safe_float(cell.get(k)), 2)
              if isinstance(cell, dict) and cell.get(k) is not None else None
              for k in _DR_COL_KEYS),
        ])
    return rows


def _override_data_rows(variant: Variant, store: dict[str, Any], blk: _Block) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for row_key, label in categories_of(variant):
        cell = store.get(row_key) or {}
        vals: list[Any] = []
        for k in blk.keys:
            v = cell.get(k) if isinstance(cell, dict) else None
            vals.append(round(safe_float(v), 2) if v is not None else None)
        rows.append([label, *vals])
    return rows


def _rows_data_rows(payload: Any, blk: _Block) -> list[list[Any]]:
    if not isinstance(payload, list):
        return []
    out: list[list[Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        row: list[Any] = []
        for k in blk.keys:
            v = item.get(k)
            if k in blk.numeric:
                row.append(round(safe_float(v), 2))
            else:
                row.append(safe_str(v))
        out.append(row)
    return out


def build_disclosure_workbook(
    variant: Variant,
    *,
    remarks: dict[str, str] | None = None,
    class_rows: list[list[Any]] | None = None,
) -> Workbook:
    """构造多区块 workbook。`remarks=None` 即模板（空表 + 预置标签行）。"""
    wb = Workbook()
    _write_guide(wb, variant)

    # (1) 分类只读表（模板也带表头，便于对齐）
    ws_cls = wb.create_sheet(_CLASS_SHEET)
    ws_cls.append([f"提示：本表来自 F2-1 审定表跨表取数，仅供核对，导入时忽略。"])
    ws_cls.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(_CLASS_HEADERS))
    ws_cls.cell(row=1, column=1).font = Font(italic=True, color="8A6D3B")
    ws_cls.append(list(_CLASS_HEADERS))
    _style_header(ws_cls, 2, len(_CLASS_HEADERS))
    for r in (class_rows or [[label] + [None] * 6 for _, label in categories_of(variant)]):
        ws_cls.append(r)
    ws_cls.freeze_panes = "A3"
    _autosize(ws_cls, len(_CLASS_HEADERS))

    for blk in blocks_of(variant):
        payload_raw = (remarks or {}).get(item_id_of(variant, blk.suffix))
        if blk.kind == "override":
            store = _parse_json(payload_raw, {}) if remarks is not None else {}
            data = _override_data_rows(variant, store, blk)
        elif blk.kind == "dr":
            store = _parse_json(payload_raw, {}) if remarks is not None else {}
            data = _dr_data_rows(variant, store)
        else:
            payload = _parse_json(payload_raw, []) if remarks is not None else []
            data = _rows_data_rows(payload, blk)
            if not data:
                data = [[None] * len(blk.headers) for _ in range(3)]
        _write_block_sheet(wb, blk, data)

    # 文本说明
    ws_txt = wb.create_sheet(_TEXT_SHEET)
    ws_txt.append(["提示：按首列「区块」匹配，请勿改动区块名；内容列支持多行文本。"])
    ws_txt.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
    ws_txt.cell(row=1, column=1).font = Font(italic=True, color="8A6D3B")
    ws_txt.append(list(_TEXT_HEADERS))
    _style_header(ws_txt, 2, 2)
    for suffix, block_name in texts_of(variant):
        content = "" if remarks is None else (remarks.get(item_id_of(variant, suffix)) or "")
        ws_txt.append([block_name, content])
        ws_txt.cell(row=ws_txt.max_row, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ws_txt.freeze_panes = "A3"
    ws_txt.column_dimensions["A"].width = 42
    ws_txt.column_dimensions["B"].width = 90
    return wb


async def export_disclosure_data(db: AsyncSession, wp_id: str, variant: Variant) -> Workbook:
    remarks = await _load_remarks(db, wp_id, f"F2-note-{variant}-")
    class_rows = await _load_class_rows(db, wp_id, variant)
    return build_disclosure_workbook(variant, remarks=remarks, class_rows=class_rows)


# ════════════════════════════════════════════════════════════════════
# 导入
# ════════════════════════════════════════════════════════════════════


def _find_header_row(ws: Any, expected_first: str, max_scan: int = 4) -> int | None:
    """在前 max_scan 行内找表头行（首格 == expected_first）。找不到返回 None。"""
    for r in range(1, min(max_scan, ws.max_row or 1) + 1):
        val = ws.cell(row=r, column=1).value
        if val is not None and str(val).strip() == expected_first:
            return r
    return None


def _header_index(ws: Any, header_row: int, ncols_hint: int) -> dict[str, int]:
    """表头名 → 1-based 列号（按名匹配，容忍列序变化与多余列）。"""
    out: dict[str, int] = {}
    width = max(ws.max_column or ncols_hint, ncols_hint)
    for c in range(1, width + 1):
        raw = ws.cell(row=header_row, column=c).value
        name = str(raw).strip() if raw is not None else ""
        if name and name not in out:
            out[name] = c
    return out


def _cell(ws: Any, row: int, col: int | None) -> Any:
    return None if not col else ws.cell(row=row, column=col).value


def _num_or_none(val: Any) -> float | None:
    """空/非数值 → None（表示"不覆盖"），数值 → float。"""
    if val is None or (isinstance(val, str) and not val.strip()):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _import_override(
    ws: Any, blk: _Block, variant: Variant,
) -> tuple[dict[str, dict[str, float]], list[str], int]:
    """**整表覆盖**语义：清空某行 = 撤销该类别的手工覆盖（回归 F2-1 自动取数）。

    与 rows 类区块一致（导入即以表内容为准）。若整张表一个数都没填（例如用户拿空
    模板只想导文本），返回 count=0 → 上层跳过写库，避免误清既有覆盖。
    """
    label_to_key = {label: rk for rk, label in categories_of(variant)}
    hdr_row = _find_header_row(ws, blk.headers[0])
    if hdr_row is None:
        return {}, [f"「{blk.sheet}」未找到表头「{blk.headers[0]}」，已跳过"], 0
    idx = _header_index(ws, hdr_row, len(blk.headers))
    store: dict[str, dict[str, float]] = {}
    warnings: list[str] = []
    filled = 0
    for r in range(hdr_row + 1, (ws.max_row or hdr_row) + 1):
        label = safe_str(_cell(ws, r, 1))
        if not label:
            continue
        row_key = label_to_key.get(label)
        if not row_key:
            warnings.append(f"「{blk.sheet}」未知类别「{label}」已跳过")
            continue
        cell: dict[str, float] = {}
        for header, key in zip(blk.headers[1:], blk.keys):
            num = _num_or_none(_cell(ws, r, idx.get(header)))
            if num is not None:
                cell[key] = num
        if cell:
            store[row_key] = cell
            filled += 1
        # cell 为空 → 不写入 store，即"撤销该类别覆盖"
    return store, warnings, filled


def _import_dr(ws: Any, blk: _Block, variant: Variant) -> tuple[dict[str, dict[str, float]], list[str], int]:
    """按「行标识」列（rowKey）匹配 —— 行标签在三段中重复，不能按标签匹配。"""
    editable = {rk for rk, _label, kind in dr_rows_of(variant) if kind in ("input", "sub")}
    known = {rk for rk, _label, _k in dr_rows_of(variant)}
    hdr_row = _find_header_row(ws, blk.headers[0])
    if hdr_row is None:
        return {}, [f"「{blk.sheet}」未找到表头「{blk.headers[0]}」，已跳过"], 0
    idx = _header_index(ws, hdr_row, len(blk.headers))
    key_col = idx.get(_DR_KEY_HEADER, 1)
    store: dict[str, dict[str, float]] = {}
    warnings: list[str] = []
    count = 0
    for r in range(hdr_row + 1, (ws.max_row or hdr_row) + 1):
        row_key = safe_str(_cell(ws, r, key_col))
        if not row_key:
            continue
        if row_key not in known:
            warnings.append(f"「{blk.sheet}」未知行标识「{row_key}」已跳过")
            continue
        if row_key not in editable:
            continue  # section/derived 行 → 静默跳过（本就是只读行）
        cell: dict[str, float] = {}
        for col_key in _DR_COL_KEYS:
            num = _num_or_none(_cell(ws, r, idx.get(_DR_COL_LABELS[col_key])))
            if num is not None:
                cell[col_key] = num
        if cell:
            store[row_key] = cell
            count += 1
    if not store:
        warnings.append(f"「{blk.sheet}」无有效数值行")
    return store, warnings, count


def _import_rows(ws: Any, blk: _Block) -> tuple[list[dict[str, Any]], list[str], int]:
    hdr_row = _find_header_row(ws, blk.headers[0])
    if hdr_row is None:
        return [], [f"「{blk.sheet}」未找到表头「{blk.headers[0]}」，已跳过"], 0
    idx = _header_index(ws, hdr_row, len(blk.headers))
    missing = [h for h in blk.headers if h not in idx]
    warnings: list[str] = []
    if missing:
        warnings.append(f"「{blk.sheet}」缺少列 {'、'.join(missing)}，缺列按空值导入")
    out: list[dict[str, Any]] = []
    truncated = False
    for r in range(hdr_row + 1, (ws.max_row or hdr_row) + 1):
        if len(out) >= ROW_LIMIT:
            truncated = True
            break
        raw_vals = [_cell(ws, r, idx.get(h)) for h in blk.headers]
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in raw_vals):
            continue
        item: dict[str, Any] = {"rowId": _new_row_id(blk.suffix)}
        for header, key in zip(blk.headers, blk.keys):
            v = _cell(ws, r, idx.get(header))
            item[key] = safe_float(v) if key in blk.numeric else safe_str(v)
        out.append(item)
    if truncated:
        warnings.append(f"「{blk.sheet}」数据行超过 {ROW_LIMIT} 行，已截断")
    return out, warnings, len(out)


def _new_row_id(suffix: str) -> str:
    from uuid import uuid4

    return f"{suffix}-{uuid4().hex[:12]}"


def _import_texts(ws: Any, variant: Variant) -> tuple[dict[str, str], list[str], int]:
    name_to_suffix = {name: suffix for suffix, name in texts_of(variant)}
    hdr_row = _find_header_row(ws, _TEXT_HEADERS[0])
    if hdr_row is None:
        return {}, [f"「{_TEXT_SHEET}」未找到表头「{_TEXT_HEADERS[0]}」，已跳过"], 0
    idx = _header_index(ws, hdr_row, len(_TEXT_HEADERS))
    content_col = idx.get(_TEXT_HEADERS[1], 2)
    out: dict[str, str] = {}
    warnings: list[str] = []
    count = 0
    for r in range(hdr_row + 1, (ws.max_row or hdr_row) + 1):
        name = safe_str(_cell(ws, r, 1))
        if not name:
            continue
        suffix = name_to_suffix.get(name)
        if not suffix:
            warnings.append(f"「{_TEXT_SHEET}」未知区块「{name}」已跳过")
            continue
        raw = _cell(ws, r, content_col)
        out[suffix] = "" if raw is None else str(raw)
        count += 1
    return out, warnings, count


async def _upsert_remark(db: AsyncSession, wp_id: str, project_id: str, item_id: str, remark: str) -> None:
    from uuid import uuid4

    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, updated_at, created_at)
            VALUES (:id, :project_id, :wp_id, :item_id, :remark, NOW(), NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET remark = :remark, updated_at = NOW()
        """),
        {
            "id": str(uuid4()),
            "project_id": project_id,
            "wp_id": wp_id,
            "item_id": item_id,
            "remark": remark,
        },
    )


async def import_disclosure_data(
    db: AsyncSession, wp_id: str, variant: Variant, content: bytes
) -> dict[str, Any]:
    """解析多区块 workbook 并逐区块 UPSERT 到 `remark`。

    缺失的 sheet 跳过（不清空原数据）；未知类别/区块名报 warning 并跳过。
    """
    proj = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id AND is_deleted = false"),
        {"wp_id": wp_id},
    )
    project_id = proj.scalar_one_or_none()
    if not project_id:
        return {"ok": False, "errors": ["底稿不存在"], "imported_count": 0}

    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception:  # noqa: BLE001
        return {"ok": False, "errors": ["无法解析 xlsx 文件"], "imported_count": 0}

    warnings: list[str] = []
    imported_blocks: list[str] = []
    total = 0

    try:
        for blk in blocks_of(variant):
            if blk.sheet not in wb.sheetnames:
                continue
            ws = wb[blk.sheet]
            if blk.kind == "override":
                store, warns, cnt = _import_override(ws, blk, variant)
                payload: Any = store
            elif blk.kind == "dr":
                store, warns, cnt = _import_dr(ws, blk, variant)
                payload = store
            else:
                rows, warns, cnt = _import_rows(ws, blk)
                payload = rows
            warnings.extend(warns)
            if cnt:
                await _upsert_remark(
                    db, wp_id, str(project_id),
                    item_id_of(variant, blk.suffix),
                    json.dumps(payload, ensure_ascii=False),
                )
                imported_blocks.append(blk.sheet)
                total += cnt

        if _TEXT_SHEET in wb.sheetnames:
            texts, warns, cnt = _import_texts(wb[_TEXT_SHEET], variant)
            warnings.extend(warns)
            for suffix, val in texts.items():
                await _upsert_remark(
                    db, wp_id, str(project_id), item_id_of(variant, suffix), val,
                )
            if cnt:
                imported_blocks.append(_TEXT_SHEET)
                total += cnt
    finally:
        wb.close()

    if not imported_blocks:
        return {
            "ok": False,
            "errors": ["未识别到任何可导入区块，请使用「导出模板」下载的文件"],
            "imported_count": 0,
            "warnings": warnings,
        }

    await db.commit()
    out: dict[str, Any] = {
        "ok": True,
        "imported_count": total,
        "imported_blocks": imported_blocks,
        "errors": [],
    }
    if warnings:
        out["warnings"] = warnings
    return out
