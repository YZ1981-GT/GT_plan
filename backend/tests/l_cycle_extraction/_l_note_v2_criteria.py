"""L 循环附注结构 v2 —— 判据层（常量 / 登记表 / 纯函数 / loader / fixture）。

从 `backend/tests/test_note_l_cycle_structure_v2.py` 拆出：原文件 954 行，
超过 pre-commit 的 800 行门禁。**不加 file_size_whitelist** —— 那张白名单
表头写明「仅历史大文件」，新增文件套用属滥用。

分层边界 = 「判据」与「用例」：本模块只放可复用的判据（含 openpyxl 直读源
xlsx 的取证函数），断言留在用例层。用例层的 import 清单由脚本按其实际引用
算出，不手写 —— 漏一个名字就是 collection error，会让整份守卫的断言零执行
而表面上「没有失败」。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__ = [
    "SourceTableFacts",
    "TargetSpec",
    "TARGET_SPECS",
    "CJK_RE",
    "PLATFORM_LABEL_KEY",
    "load_note_template",
    "load_source_sheet_cells",
    "index_sections_by_number",
    "find_table",
    "column_keys",
    "column_labels",
    "flat_flags",
    "label_flags",
    "group_of",
    "has_cjk",
    "evaluate_column_key_shape",
    "evaluate_flat_placement",
    "evaluate_two_level_group",
    "evaluate_label_column_count",
    "evaluate_text_sections_present",
    "evaluate_header_matches_source",
]

# ---------------------------------------------------------------------------
# 路径（从仓库根跑 pytest；本文件在 backend/tests/ 下）
# ---------------------------------------------------------------------------

# 🔴 parents[2]（不是 [1]）—— 本模块位于 backend/tests/l_cycle_extraction/，
# 比拆分前的 backend/tests/ 深一层。拆分时若沿用 [1] 会指向 backend/tests/，
# 于是所有模板/源 xlsx 路径都落到 backend/tests/data/ 与 backend/tests/wp_templates/，
# 表现为 9 个 fixture setup ERROR「附注模板不存在」。用锚点自校验钉死，
# 避免下次移动文件时再犯（路径推算依赖文件位置，是移动文件的高频坑）。
BACKEND_ROOT = Path(__file__).resolve().parents[2]
assert BACKEND_ROOT.name == "backend", (
    f"BACKEND_ROOT 推算错误：得到 {BACKEND_ROOT}，末级应为 backend —— "
    "本模块被移动过？请同步调整 parents[] 层数"
)
TEMPLATE_JSON = {
    "listed": BACKEND_ROOT / "data" / "note_template_listed.json",
    "soe": BACKEND_ROOT / "data" / "note_template_soe.json",
}
SOURCE_DIR = BACKEND_ROOT / "wp_templates" / "L"

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SNAKE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PLATFORM_LABEL_KEY = "label"

_CLASS_A = "【类 A 独立口径判据】"
_CLASS_B = "【类 B 被测实现】"
_WAVE1_RED = "这是预期的 Wave 1 打红结果（Wave 4 Task 10/11/12 修复）"

MIN_TARGET_COUNT = 5
MIN_SECTION_COUNT = 100


# ---------------------------------------------------------------------------
# 目标登记表：本 spec 负责的 5 处（按 (variant, 章节号, 表名) 精确定位）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceTableFacts:
    """源 xlsx 侧的列事实（该表表头行的逐格文字）。"""

    sheet: str
    header_row: int
    labels: tuple
    source_ref: str


@dataclass(frozen=True)
class TargetSpec:
    """一处待修目标。

    wp_code / source_sheet / source_header_row 指向源 xlsx 的裁决依据；
    expect_* 是 Wave 4 修完后应达到的状态（守卫按它判红/判绿）。
    """

    variant: str
    section_number: str
    table_name: str
    wp_code: str
    source_sheet: str
    source_header_row: int
    expect_keys: tuple
    expect_labels: tuple
    expect_groups: tuple  # 与 expect_keys 等长；None 表示该列不带 group
    expect_text_sections: bool
    evidence: str


# 源模板逐格实证（openpyxl 直读，2026-08-09）：
#   L3!附注披露（国企）信息核对!A21/B21/C21 = 借款类别 / 期末余额 / 期初余额
#   L4!附注披露信息核对（国企）!A17..E17    = 债券名称 / 面值 / 发行日期 / 债券期限 / 发行金额
#   L7!附注披露信息(国企)!A6/B6/C6         = 项目 / 年初余额 / 期末余额   <- 列序与列名双重不符模板
#   L4!附注披露信息核对（上市公司）!A63:I64 = 两级表头，4 组 x (数量/账面价值) = 9 列
TARGET_SPECS = (
    TargetSpec(
        variant="soe",
        section_number="八、45",
        table_name="（1）一年内到期的长期借款",
        wp_code="L3",
        source_sheet="附注披露（国企）信息核对",
        source_header_row=21,
        expect_keys=("label", "end_amount", "prior_amount"),
        expect_labels=("借款类别", "期末余额", "期初余额"),
        expect_groups=(None, None, None),
        expect_text_sections=False,
        evidence=(
            "列 key 现为中文字面量（项目 / 期末余额 / 期初余额），违反禁硬编码铁律，"
            "且 flat 标在每一列上（平台惯例只标标签列）。源 xlsx "
            "L3!附注披露（国企）信息核对!A21 的标签列文字是 借款类别 不是 项目。"
        ),
    ),
    TargetSpec(
        variant="soe",
        section_number="八、46",
        table_name="（2）一年内到期的应付债券",
        wp_code="L4",
        source_sheet="附注披露信息核对（国企）",
        source_header_row=17,
        expect_keys=("label", "face_value", "issue_date", "term", "issue_amount"),
        expect_labels=("债券名称", "面值", "发行日期", "债券期限", "发行金额"),
        expect_groups=(None, None, None, None, None),
        expect_text_sections=True,
        evidence=(
            "列 key 现为中文字面量，且 flat 标在每一列上。列名与源 xlsx "
            "L4!附注披露信息核对（国企）!A17..E17 一致，只需规范化 key 与 flat 位置。"
        ),
    ),
    TargetSpec(
        variant="soe",
        section_number="八、57",
        table_name="其他非流动负债",
        wp_code="L7",
        source_sheet="附注披露信息(国企)",
        source_header_row=6,
        expect_keys=("label", "begin_amount", "end_amount"),
        expect_labels=("项目", "年初余额", "期末余额"),
        expect_groups=(None, None, None),
        # 🔴 曾误写 True，与本条 evidence 自己的结论「如实登记为零」直接矛盾，
        # 使正确的数据被打红（假绿第③源的反向形态：守卫把错值当基线锁死）。
        # openpyxl 直读实证：该 sheet 仅 12 行 / 33 个非空格 —— 标题、表名
        # 「其他非流动负债」、表头行 6、5 行指向 明细表L7-2 的取数公式、合计行，
        # 无任何说明段。由 test_l7_soe_source_has_no_text_paragraph 钉死。
        expect_text_sections=False,
        evidence=(
            "源 xlsx L7!附注披露信息(国企)!A6/B6/C6 = 项目 / 年初余额 / 期末余额，"
            "而模板当前是 项目 / 期末余额 / 期初余额 —— 列序与列名双重不符"
            "（第 2 列源模板叫 年初余额 而非 期初余额）。listed 侧是 "
            "项目 / 期末数 / 上年年末数，两版本就不同构，禁为统一而对齐。"
            "另 text_sections 为 0，源 xlsx 该 sheet 无说明段故如实登记为零。"
        ),
    ),
    TargetSpec(
        variant="listed",
        section_number="五、46",
        table_name="期末发行在外的优先股、永续债等其他金融工具变动情况",
        wp_code="L4",
        source_sheet="附注披露信息核对（上市公司）",
        source_header_row=64,
        expect_keys=(
            "label",
            "begin_count",
            "begin_value",
            "increase_count",
            "increase_value",
            "decrease_count",
            "decrease_value",
            "end_count",
            "end_value",
        ),
        expect_labels=(
            "发行在外的金融工具",
            "数量",
            "账面价值",
            "数量",
            "账面价值",
            "数量",
            "账面价值",
            "数量",
            "账面价值",
        ),
        expect_groups=(
            None,
            "期初余额",
            "期初余额",
            "本期增加",
            "本期增加",
            "本期减少",
            "本期减少",
            "期末余额",
            "期末余额",
        ),
        expect_text_sections=True,
        evidence=(
            "源 xlsx L4!附注披露信息核对（上市公司）!A63:I64 是两级表头："
            "A63 发行在外的金融工具（A63:A64 纵向合并）+ B63/D63/F63/H63 四个父表头"
            "（期初余额/本期增加/本期减少/期末余额，各 colspan=2）+ 第 64 行八个叶子列"
            "（数量/账面价值 x 4）= 共 9 列。模板当前只有 5 列 "
            "（label/begin_count/increase_count/decrease_count/end_count）"
            "—— 丢的是 4 个 账面价值 列，不是丢了分组。故修法是先补 4 列再加 group，"
            "只加 group 会得到 5 列带 group 的错结构。"
        ),
    ),
    TargetSpec(
        variant="listed",
        section_number="五、52",
        table_name="其他非流动负债",
        wp_code="L7",
        source_sheet="附注披露信息（上市公司）",
        source_header_row=6,
        expect_keys=("label", "end_amount", "prior_amount"),
        expect_labels=("项目", "期末数", "上年年末数"),
        expect_groups=(None, None, None),
        expect_text_sections=False,
        evidence=(
            "列结构与源 xlsx L7!附注披露信息（上市公司）!A6/B6/C6 一致，无需改列；"
            "本条只登记 text_sections 为 0 —— 源 xlsx 该 sheet 确无说明段，"
            "故 expect_text_sections=False（如实登记为零，不得自造披露内容）。"
        ),
    ),
)


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text or ""))


def index_sections_by_number(template: dict) -> dict:
    """章节号 -> section 列表（同号可能多条，故返回 list）。"""
    out = {}
    for sec in template.get("sections") or []:
        num = str(sec.get("section_number") or "")
        if num:
            out.setdefault(num, []).append(sec)
    return out


def find_table(section: dict, table_name: str) -> dict | None:
    """在 section 内按表名精确取表。禁跨章节按表名全局索引。"""
    for tbl in section.get("tables") or []:
        if str(tbl.get("name") or "") == table_name:
            return tbl
    return None


def column_keys(table: dict) -> tuple:
    return tuple(str(c.get("key") or "") for c in table.get("columns") or [])


def column_labels(table: dict) -> tuple:
    return tuple(str(c.get("label") or "") for c in table.get("columns") or [])


def flat_flags(table: dict) -> tuple:
    return tuple(bool(c.get("flat")) for c in table.get("columns") or [])


def label_flags(table: dict) -> tuple:
    return tuple(bool(c.get("is_label")) for c in table.get("columns") or [])


def group_of(table: dict) -> tuple:
    return tuple(
        (str(c.get("group")) if c.get("group") else None) for c in table.get("columns") or []
    )


def evaluate_column_key_shape(table: dict) -> tuple:
    """Property 15：列 key 必须是 snake_case 标识符，不得含 CJK 字符。"""
    problems = []
    for idx, key in enumerate(column_keys(table)):
        if has_cjk(key):
            problems.append(
                f"columns[{idx}].key={key!r} 含中文字符，列 key 必须是 snake_case 标识符"
                "（中文字面量当 key 违反禁硬编码铁律，且改文案就会丢数据）"
            )
        elif not SNAKE_KEY_RE.match(key):
            problems.append(
                f"columns[{idx}].key={key!r} 不符 snake_case 形态 ^[a-z][a-z0-9_]*$"
            )
    return tuple(problems)


def evaluate_flat_placement(table: dict) -> tuple:
    """Property 16：flat 只许标在标签列（columns[0]）上。

    flat 标在任一列即对整表生效（_extract_column_groups 见 flat 即返 []），
    故"每列都标"虽然结果正确但形态与其余章节不一致，且会让后续想加 group 的人
    以为只要加 group 就行。
    """
    flats = flat_flags(table)
    if not flats:
        return ()
    problems = []
    extra = [i for i, f in enumerate(flats) if f and i != 0]
    if extra:
        problems.append(
            f"flat 出现在非标签列 columns{extra} 上；平台惯例只在 columns[0] 标 flat"
            f"（本表共 {len(flats)} 列，其中 {sum(flats)} 列带 flat）"
        )
    return tuple(problems)


def evaluate_two_level_group(table: dict, expect_groups: tuple) -> tuple:
    """Property 18：两级表头必须靠 group 表达，且标签列不得带 flat。

    这里同时校验两件事，因为它们互为前提：
      - group 声明齐备（每个数据列都归到正确的父表头）
      - 标签列没有 flat（有 flat 则整表 group 被打掉，加了也不生效）
    """
    if not any(expect_groups):
        return ()
    problems = []
    actual = group_of(table)
    if len(actual) != len(expect_groups):
        problems.append(
            f"列数 {len(actual)} 与期望 {len(expect_groups)} 不符，两级表头无法成立"
            "（本表源模板是两级 9 列，模板当前丢了 4 个 账面价值 列）"
        )
        return tuple(problems)
    for idx, (got, want) in enumerate(zip(actual, expect_groups)):
        if got != want:
            problems.append(
                f"columns[{idx}].group={got!r} 期望 {want!r}"
            )
    if flat_flags(table)[:1] == (True,):
        problems.append(
            "标签列 columns[0] 带 flat，而本表是两级表头；"
            "flat 标在任一列即让 _extract_column_groups 整表返回 []，group 会被永久打掉"
        )
    return tuple(problems)


def evaluate_label_column_count(table: dict) -> tuple:
    """两侧 is_label 列数必须恰为 1。

    is_label 表态不一致会让 group 索引整体偏移一位（_extract_column_groups 跳过
    is_label 列且 header_idx 从 1 起），表现为父子对应关系整体错开而列名列数都对。
    """
    flags = label_flags(table)
    if not flags:
        return ()
    n = sum(flags)
    if n != 1:
        return (
            f"is_label 列数为 {n}（应恰为 1）；表态不一致会让两级表头的 group "
            "索引整体偏移一位，症状是父子对应关系错开而列名列数看着都对",
        )
    if not flags[0]:
        return (
            f"is_label 不在 columns[0] 上（实际在 columns[{flags.index(True)}]）",
        )
    return ()


def evaluate_text_sections_present(section: dict, expect: bool) -> tuple:
    """Property 19：应有说明段的章节 text_sections 必须非空。"""
    texts = section.get("text_sections") or []
    if expect and not texts:
        return (
            "text_sections 为 0，而源模板该 sheet 有说明段，必须补齐"
            "（补的段落不得是裸表名 —— 裸表名会被当披露正文渲染）",
        )
    if not expect and texts:
        return (
            f"text_sections 有 {len(texts)} 段，而本条登记为"
            "「源 xlsx 无说明段、如实登记为零」；若确有真源请先改登记表并写明依据",
        )
    return ()


def evaluate_header_matches_source(
    table: dict, source: SourceTableFacts, expect_labels: tuple
) -> tuple:
    """三向比对的第三条边：模板 headers 必须与源 xlsx 表头行一致。

    源 xlsx 是唯一裁决者。两级表头时源侧取的是叶子行，故 expect_labels 里
    数量/账面价值 会重复出现，这是正确的（父表头由 group 承载）。
    """
    problems = []
    headers = tuple(str(h) for h in (table.get("headers") or []))
    if headers != expect_labels:
        problems.append(
            f"headers={list(headers)} 与源模板 {source.source_ref} 的表头 "
            f"{list(expect_labels)} 不一致"
        )
    labels = column_labels(table)
    if labels and labels != expect_labels:
        problems.append(
            f"columns[].label={list(labels)} 与源模板 {source.source_ref} 的表头 "
            f"{list(expect_labels)} 不一致"
        )
    return tuple(problems)


# ---------------------------------------------------------------------------
# 数据加载（生产模块与三方库一律函数内 import）
# ---------------------------------------------------------------------------


def _ensure_backend_on_path() -> None:
    root = str(BACKEND_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def load_note_template(variant: str) -> dict:
    path = TEMPLATE_JSON.get(variant)
    if path is None:
        pytest.fail(f"{_CLASS_A} 未知 variant {variant!r}，应为 listed 或 soe")
    if not path.exists():
        pytest.fail(f"{_CLASS_A} 附注模板不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"{_CLASS_A} 附注模板解析失败 {path}: {exc!r}")


def load_source_sheet_cells(wp_code: str, sheet: str) -> dict:
    """openpyxl 直读源 xlsx 某 sheet 的逐格文字（不带公式求值）。

    返回 {(row, col): text}。sheet 名必须精确相等（不 strip）——
    源模板有首尾带空格的真实 tab 名，strip 会把它判成不存在。
    """
    if not SOURCE_DIR.is_dir():
        pytest.fail(f"{_CLASS_A} L 类源模板目录不存在: {SOURCE_DIR}")
    try:
        from openpyxl import load_workbook
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"{_CLASS_A} 无法 import openpyxl: {exc!r}")

    matches = [
        p
        for p in sorted(SOURCE_DIR.glob("*.xlsx"))
        if not p.name.startswith("~$") and p.stem.split(" ", 1)[0].strip() == wp_code
    ]
    if not matches:
        pytest.fail(f"{_CLASS_A} 源模板目录里找不到 wp_code={wp_code} 的 xlsx")

    wb = load_workbook(matches[0], data_only=False)
    try:
        if sheet not in wb.sheetnames:
            pytest.fail(
                f"{_CLASS_A} {wp_code} 源 xlsx 无 sheet {sheet!r}；"
                f"实际 tab 名: {wb.sheetnames}"
            )
        ws = wb[sheet]
        if ws.sheet_state != "visible":
            pytest.fail(
                f"{_CLASS_A} {wp_code}!{sheet} 是 {ws.sheet_state} sheet，"
                "hidden sheet 不属于底稿集合，不得作为判据"
            )
        cells = {}
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    cells[(cell.row, cell.column)] = str(cell.value).strip()
        return cells
    finally:
        wb.close()


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def templates() -> dict:
    return {v: load_note_template(v) for v in ("listed", "soe")}


@pytest.fixture(scope="module")
def section_index(templates) -> dict:
    return {v: index_sections_by_number(t) for v, t in templates.items()}


def _resolve_section(section_index: dict, spec: TargetSpec) -> dict:
    hits = section_index[spec.variant].get(spec.section_number) or []
    if not hits:
        pytest.fail(
            f"{_CLASS_A} {spec.variant} 模板里找不到章节号 {spec.section_number!r}；"
            "注意 20 个章节号在两份模板间撞号，按章节号查必须先由 variant 定位"
        )
    if len(hits) > 1:
        titles = [s.get("section_title") for s in hits]
        pytest.fail(
            f"{_CLASS_A} {spec.variant} 的章节号 {spec.section_number!r} 命中 "
            f"{len(hits)} 个 section（{titles}），二元组索引不再唯一"
        )
    return hits[0]


def _resolve_table(section_index: dict, spec: TargetSpec) -> dict:
    sec = _resolve_section(section_index, spec)
    tbl = find_table(sec, spec.table_name)
    if tbl is None:
        names = [t.get("name") for t in sec.get("tables") or []]
        pytest.fail(
            f"{_CLASS_A} {spec.variant} {spec.section_number} 里找不到表 "
            f"{spec.table_name!r}；实际表名: {names}"
        )
    return tbl


def _fail_class_b(title: str, offenders: dict) -> None:
    lines = [f"{_CLASS_B} {title}", f"{_WAVE1_RED}。", f"命中处数: {len(offenders)}"]
    for key in sorted(offenders):
        lines.append(f"  - {key}")
        for msg in offenders[key]:
            lines.append(f"      {msg}")
    pytest.fail("\n".join(lines))


def _target_key(spec: TargetSpec) -> str:
    return f"{spec.variant} {spec.section_number} / {spec.table_name}"


# ===========================================================================
# 类 A：独立口径判据（现在就应全绿）
# ===========================================================================


