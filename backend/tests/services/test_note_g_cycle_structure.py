"""附注 G 循环披露章节结构守卫（对齐源模板后不得漂移）。

配套幂等脚本：``backend/scripts/fix/fix_note_g_cycle_structure.py``
（``--check`` 供 CI；本文件从**模板落盘结果**正向断言，两者互为兜底）。

覆盖 spec `disclosure-sync-path-buildout` 批 1 已对齐的 G8 / G9 / G12：

- 表名不是表头首格（`项  目` / `种  类`）→ 否则附注 TAB 页签显示列名，且与前端
  子表名常量错位产出孤儿子表
- 每张表 `columns` 齐备且**显式表态 flat**（源模板均为单级表头；不表态会让 seed
  路径被 `_infer_groups_from_headers` 塞凭空父表头）
- `columns[0].label == headers[0]`（标签列头错位 → 同步后表头整体右移）
- 每张表有 `guidance`（附注 TAB 编制提示）
- 无 `row_type == header_label` 的假数据行（md 重建脚本压扁第二行表头的残留）
- 前端子表名常量与模板 `tables[].name` 逐字一致（读 `.ts` 源码，防双真源漂移）

spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.4 / 2.5 / 2.8
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent
DATA_DIR = _BACKEND / "data"
COMPOSABLES = (
    _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"
)

TEMPLATE = {
    "listed": DATA_DIR / "note_template_listed.json",
    "soe": DATA_DIR / "note_template_soe.json",
}

_G4_LISTED_STAGES = [
    "期末处于第一阶段的债权投资的减值准备",
    "期末处于第二阶段的债权投资的减值准备",
    "期末处于第三阶段的债权投资的减值准备",
    "上年年末处于第一阶段的债权投资的减值准备",
    "上年年末处于第二阶段的债权投资的减值准备",
    "上年年末处于第三阶段的债权投资的减值准备",
]
_G6_LISTED_STAGES = [s.replace("债权投资", "其他债权投资") for s in _G4_LISTED_STAGES]

# (cycle, variant, section_number, [表名...])  —— 顺序即模板 tables 顺序
EXPECTED: list[tuple[str, str, str, list[str]]] = [
    ("G4", "listed", "五、14", [
        "债权投资",
        "债权投资减值准备本期变动情况",
        "期末重要的债权投资",
        "期末重要的债权投资（续：上年年末余额）",
        *_G4_LISTED_STAGES,
        "本期计提、收回或转回的减值准备情况",
        "本期实际核销的债权投资",
        "重要的债权投资核销情况（逐项披露）",
    ]),
    ("G4", "soe", "八、15", [
        "债权投资情况",
        "期末重要的债权投资",
        "期末，处于第一阶段的债权投资的减值准备",
        "期末，处于第二阶段的债权投资的减值准备",
        "期末，处于第三阶段的债权投资的减值准备",
        "本期计提、收回或转回的减值准备情况",
    ]),
    ("G5", "listed", "五、16", [
        "长期应收款按性质披露",
        "坏账准备计提情况",
        "按单项计提坏账准备",
        "按单项计提坏账准备（续：上年年末余额）",
        "组合计提项目：XXX",
        "本期计提、收回或转回的坏账准备情况",
        "本期实际核销的长期应收款",
        "重要的长期应收款核销情况（逐项披露）",
    ]),
    ("G5", "soe", "八、17", [
        "长期应收款按性质披露",
        "终止确认的长期应收款",
        "转移长期应收款且继续涉入形成的资产、负债的金额",
    ]),
    ("G6", "listed", "五、15", [
        "其他债权投资",
        "其他债权投资情况",
        "其他债权投资减值准备本期变动情况",
        "期末重要的其他债权投资",
        "期末重要的其他债权投资（续：上年年末余额）",
        *_G6_LISTED_STAGES,
        "本期计提、收回或转回的减值准备情况",
        "本期实际核销的其他债权投资",
        "重要的其他债权投资核销情况（逐项披露）",
    ]),
    ("G6", "soe", "八、16", ["其他债权投资情况", "期末重要的其他债权投资"]),
    ("G8", "listed", "五、19", ["其他权益工具投资", "期末其他权益工具投资情况"]),
    ("G8", "soe", "八、19", ["其他权益工具投资情况", "期末其他权益工具投资情况"]),
    ("G9", "listed", "五、20", ["其他非流动金融资产"]),
    ("G9", "soe", "八、20", ["其他非流动金融资产"]),
    ("G12", "listed", "五、70", ["净敞口套期收益"]),
    ("G12", "soe", "八、71", ["净敞口套期收益"]),
]

# 源模版本就是**两级**表头的表（其余一律单级 → 必须标 flat）
GROUP_TABLES: dict[tuple[str, str], set[str]] = {
    ("G4", "listed"): {
        "债权投资",
        "期末重要的债权投资",
        "期末重要的债权投资（续：上年年末余额）",
        "本期计提、收回或转回的减值准备情况",
    },
    ("G4", "soe"): {"债权投资情况", "本期计提、收回或转回的减值准备情况"},
    ("G5", "listed"): {
        "长期应收款按性质披露",
        "坏账准备计提情况",
        "按单项计提坏账准备",
        "按单项计提坏账准备（续：上年年末余额）",
        "组合计提项目：XXX",
    },
    ("G5", "soe"): {"长期应收款按性质披露"},
    ("G6", "listed"): {
        "期末重要的其他债权投资",
        "期末重要的其他债权投资（续：上年年末余额）",
        "本期计提、收回或转回的减值准备情况",
    },
}

# 被 seed 拿来当表名的表头首格 / 裸续表名（禁止再出现在上述章节里）
FORBIDDEN_TABLE_NAMES = {
    "项  目", "项目", "种  类", "种类", "类  别", "类别", "名  称", "名称",
    "续：", "续:", "债权投资（表6）",
}

_docs: dict[str, dict] = {}


def _doc(variant: str) -> dict:
    if variant not in _docs:
        _docs[variant] = json.loads(TEMPLATE[variant].read_text(encoding="utf-8"))
    return _docs[variant]


def _section(variant: str, number: str) -> dict:
    for sec in _doc(variant).get("sections", []):
        if str(sec.get("section_number", "")) == number:
            return sec
    pytest.fail(f"{TEMPLATE[variant].name} 缺章节 {number}")


def _table(variant: str, number: str, name: str) -> dict:
    for tbl in _section(variant, number).get("tables") or []:
        if str(tbl.get("name", "")) == name:
            return tbl
    names = [t.get("name") for t in _section(variant, number).get("tables") or []]
    pytest.fail(f"{variant} §{number} 缺表「{name}」；现有：{names}")


_ALL_TABLES = [
    pytest.param(cycle, variant, number, name, id=f"{cycle}-{variant}-{name}")
    for cycle, variant, number, names in EXPECTED
    for name in names
]


@pytest.mark.parametrize(("cycle", "variant", "number", "names"), [
    pytest.param(c, v, n, ns, id=f"{c}-{v}") for c, v, n, ns in EXPECTED
])
def test_section_tables_exact(cycle: str, variant: str, number: str, names: list[str]) -> None:
    """章节内表名齐备、顺序一致、无重复。"""
    actual = [str(t.get("name", "")) for t in _section(variant, number).get("tables") or []]
    assert actual == names, f"{cycle}/{variant} §{number} 表集合漂移"
    assert len(set(actual)) == len(actual), "表名重复会让按 name 建键的同步互相覆盖丢表"


@pytest.mark.parametrize(("cycle", "variant", "number", "name"), _ALL_TABLES)
def test_table_name_not_header_cell(cycle: str, variant: str, number: str, name: str) -> None:
    assert name not in FORBIDDEN_TABLE_NAMES, (
        f"{cycle}/{variant} 表名「{name}」是表头首格 / 裸续表名 → TAB 页签显示列名"
    )


def _is_group_table(cycle: str, variant: str, name: str) -> bool:
    return name in GROUP_TABLES.get((cycle, variant), set())


@pytest.mark.parametrize(("cycle", "variant", "number", "name"), _ALL_TABLES)
def test_columns_declared_state(cycle: str, variant: str, number: str, name: str) -> None:
    """列元数据齐备 + 三态明确表态：单级标 `flat`，两级用 `group` + `_column_groups`。"""
    tbl = _table(variant, number, name)
    cols = tbl.get("columns") or []
    headers = tbl.get("headers") or []
    assert cols, f"{name} 缺 columns → seed 路径会前缀反猜父表头"
    assert len(cols) == len(headers), f"{name} columns={len(cols)} ≠ headers={len(headers)}"

    has_flat = any(c.get("flat") for c in cols)
    has_group = any(c.get("group") for c in cols)
    assert not (has_flat and has_group), f"{name} flat 与 group 并存（表态冲突）"
    assert has_flat or has_group, f"{name} columns 未表态（既无 flat 也无 group）"

    if _is_group_table(cycle, variant, name):
        assert has_group, f"{name} 源模版是两级表头，应用 group 声明"
        assert tbl.get("_column_groups"), f"{name} 缺 _column_groups"
        assert not cols[0].get("group"), f"{name} 标签列不得带 group"
    else:
        assert has_flat, f"{name} 源模版是单级表头，应标 flat"
        assert not tbl.get("_column_groups"), f"{name} 单级表头却残留 _column_groups"


@pytest.mark.parametrize(("cycle", "variant", "number", "name"), _ALL_TABLES)
def test_column_groups_self_consistent(cycle: str, variant: str, number: str, name: str) -> None:
    """`_column_groups` 与 `columns.group` 同源；区间不越界、不重叠。"""
    if not _is_group_table(cycle, variant, name):
        pytest.skip("单级表头")
    tbl = _table(variant, number, name)
    cols = tbl["columns"]
    headers = tbl["headers"]

    want: list[dict[str, object]] = []
    idx = 1
    for col in cols[1:]:
        group = col.get("group")
        if not group:
            idx += 1
            continue
        last = want[-1] if want else None
        if last and last["group"] == group and int(last["start"]) + int(last["span"]) == idx:
            last["span"] = int(last["span"]) + 1
        else:
            want.append({"group": group, "start": idx, "span": 1})
        idx += 1
    assert tbl.get("_column_groups") == want, f"{name} _column_groups 与 columns.group 漂移"

    occupied: set[int] = set()
    for g in tbl["_column_groups"]:
        start, span = int(g["start"]), int(g["span"])
        assert start >= 1, f"{name} 分组「{g['group']}」start={start} 覆盖了标签列"
        assert start + span <= len(headers), f"{name} 分组「{g['group']}」越界"
        rng = set(range(start, start + span))
        assert not (rng & occupied), f"{name} 分组「{g['group']}」区间重叠"
        occupied |= rng


@pytest.mark.parametrize(("cycle", "variant", "number", "name"), _ALL_TABLES)
def test_no_duplicate_label_within_group(
    cycle: str, variant: str, number: str, name: str
) -> None:
    """同一父表头下列名不得重复（否则附注侧两列同名无法区分）。"""
    cols = _table(variant, number, name)["columns"]
    by_group: dict[str, list[str]] = {}
    for col in cols[1:]:
        by_group.setdefault(str(col.get("group") or ""), []).append(str(col["label"]))
    for group, labels in by_group.items():
        dup = sorted({x for x in labels if labels.count(x) > 1})
        assert not dup, f"{name} 分组「{group or '(无)'}」内列名重复：{dup}"


@pytest.mark.parametrize(("cycle", "variant", "number", "name"), _ALL_TABLES)
def test_label_column_matches_first_header(
    cycle: str, variant: str, number: str, name: str
) -> None:
    tbl = _table(variant, number, name)
    cols = tbl.get("columns") or []
    headers = tbl.get("headers") or []
    assert str(cols[0].get("label", "")) == str(headers[0]), (
        f"{name} 标签列头与 headers[0] 不一致 → 同步后表头错位"
    )
    assert cols[0].get("is_label") is True, f"{name} 首列未标 is_label"


@pytest.mark.parametrize(("cycle", "variant", "number", "name"), _ALL_TABLES)
def test_headers_clean(cycle: str, variant: str, number: str, name: str) -> None:
    headers = _table(variant, number, name).get("headers") or []
    assert headers, f"{name} 无 headers"
    assert all(str(h).strip() for h in headers), f"{name} headers 含空串：{headers}"
    assert not any("<" in str(h) for h in headers), (
        f"{name} headers 含 HTML（el-table-column 与 Word 导出都不解析）：{headers}"
    )


@pytest.mark.parametrize(("cycle", "variant", "number", "name"), _ALL_TABLES)
def test_guidance_present(cycle: str, variant: str, number: str, name: str) -> None:
    guidance = str(_table(variant, number, name).get("guidance") or "")
    assert guidance.strip(), f"{name} 缺 guidance（附注 TAB 编制提示）"
    assert len(guidance) >= 20, f"{name} guidance 过短（{len(guidance)} 字），易诱导自造披露内容"


@pytest.mark.parametrize(("cycle", "variant", "number", "name"), _ALL_TABLES)
def test_no_header_label_rows(cycle: str, variant: str, number: str, name: str) -> None:
    rows = _table(variant, number, name).get("rows") or []
    offenders = [i for i, r in enumerate(rows) if str(r.get("row_type", "")) == "header_label"]
    assert not offenders, f"{name} 第 {offenders} 行是压扁的第二行表头残留（假数据行）"


def test_g9_soe_keeps_four_category_rows() -> None:
    """国企 G9 行骨架取源 xlsx 的 4 个分类（附注模版 md 的空行是简写）。"""
    rows = _table("soe", "八、20", "其他非流动金融资产").get("rows") or []
    labels = [str(r.get("label", "")) for r in rows]
    assert labels == [
        "债务工具投资",
        "权益工具投资",
        "指定为以公允价值计量且其变动计入当期损益的金融资产",
        "其他",
        "合计",
    ]


def test_g12_soe_keeps_two_source_rows() -> None:
    rows = _table("soe", "八、71", "净敞口套期收益").get("rows") or []
    labels = [str(r.get("label", "")) for r in rows]
    assert labels == [
        "净敞口套期下被套期项目累计公允价值变动转入当期损益的金额",
        "净敞口套期下现金流量套期储备转入当期损益的金额",
        "合计",
    ]


# ────────────────── 前端常量 ↔ 模板 表名逐字一致（防双真源漂移） ──────────────────

def _read_ts(name: str) -> str:
    path = COMPOSABLES / name
    assert path.exists(), f"缺前端映射文件 {path}"
    return path.read_text(encoding="utf-8")


def _resolve_ident(src: str, ident: str) -> str | None:
    """解析 `export const X = '…'` 形态的标识符引用（G8/G9 用别名声明 soe 章节号）。"""
    m = re.search(rf"const {re.escape(ident)}\s*=\s*['\"]([^'\"]+)['\"]", src)
    return m.group(1) if m else None


def _ts_record_values(src: str, const_name: str) -> dict[str, str]:
    """从 `export const X = { listed: '…', soe: X_SOE_… }` 抽出 variant → 值（含别名解析）。"""
    m = re.search(rf"export const {const_name}\s*=\s*\{{(.*?)\}}\s*as const", src, re.S)
    assert m, f"未找到常量 {const_name}"
    body = m.group(1)
    out: dict[str, str] = {}
    for key, literal, ident in re.findall(
        r"(listed|soe)\s*:\s*(?:['\"]([^'\"]+)['\"]|([A-Za-z_][\w]*))", body
    ):
        if literal:
            out[key] = literal
        elif ident:
            resolved = _resolve_ident(src, ident)
            assert resolved, f"{const_name}.{key} 引用的 {ident} 解析不到字面量"
            out[key] = resolved
    return out


@pytest.mark.parametrize(
    ("file_name", "const_name", "expected"),
    [
        ("g9NoteSectionMap.ts", "G9_MAIN_SUBTABLE",
         {"listed": "其他非流动金融资产", "soe": "其他非流动金融资产"}),
        ("g8NoteSectionMap.ts", "G8_MAIN_SUBTABLE",
         {"listed": "其他权益工具投资", "soe": "其他权益工具投资情况"}),
        ("g12NoteSectionMap.ts", "G12_NOTE_SECTION",
         {"listed": "五、70", "soe": "八、71"}),
        ("g9NoteSectionMap.ts", "G9_NOTE_SECTION",
         {"listed": "五、20", "soe": "八、20"}),
        ("g8NoteSectionMap.ts", "G8_NOTE_SECTION",
         {"listed": "五、19", "soe": "八、19"}),
    ],
)
def test_frontend_constants_match(
    file_name: str, const_name: str, expected: dict[str, str]
) -> None:
    got = _ts_record_values(_read_ts(file_name), const_name)
    assert got == expected, f"{file_name}::{const_name} 与模板/章节矩阵漂移"


def test_g8_detail_subtable_constant() -> None:
    src = _read_ts("g8NoteSectionMap.ts")
    m = re.search(r"export const G8_DETAIL_SUBTABLE\s*=\s*['\"]([^'\"]+)['\"]", src)
    assert m, "缺 G8_DETAIL_SUBTABLE"
    assert m.group(1) == "期末其他权益工具投资情况"


def test_g12_main_subtable_constant() -> None:
    src = _read_ts("g12DisclosureSyncPayload.ts")
    m = re.search(r"export const G12_MAIN_SUBTABLE\s*=\s*['\"]([^'\"]+)['\"]", src)
    assert m, "缺 G12_MAIN_SUBTABLE"
    assert m.group(1) == "净敞口套期收益"


@pytest.mark.parametrize("file_name", [
    "g8NoteSectionMap.ts", "g9NoteSectionMap.ts", "g12NoteSectionMap.ts",
])
def test_sheet_name_is_real_tab_name(file_name: str) -> None:
    """sheet_name 必须是源 xlsx 中文 tab 名（非合成标识、非短名）。"""
    src = _read_ts(file_name)
    m = re.search(r"_DISCLOSURE_SHEET_NAME\s*=\s*\{(.*?)\}\s*as const", src, re.S)
    assert m, f"{file_name} 缺 sheet 名常量"
    values = dict(re.findall(r"(listed|soe)\s*:\s*['\"]([^'\"]+)['\"]", m.group(1)))
    assert values.get("listed") == "附注披露信息（上市公司）"
    assert values.get("soe") == "附注披露信息（国企）"


# ────────────── G4/G5/G6 压扁表头重建的定点回归 ──────────────

def test_g4_listed_main_table_is_seven_columns() -> None:
    """曾被压扁成 3 列（只留第一行表头），源模版是 7 列两级。"""
    tbl = _table("listed", "五、14", "债权投资")
    assert tbl["headers"] == [
        "项目", "账面余额", "减值准备", "账面价值", "账面余额", "减值准备", "账面价值",
    ]
    assert tbl["_column_groups"] == [
        {"group": "期末余额", "start": 1, "span": 3},
        {"group": "上年年末余额", "start": 4, "span": 3},
    ]


def test_g4_important_bond_tables_are_six_columns() -> None:
    """曾被压扁成 2 列；续表由裸「续：」改名，两版父表头不同。"""
    end = _table("listed", "五、14", "期末重要的债权投资")
    cont = _table("listed", "五、14", "期末重要的债权投资（续：上年年末余额）")
    for tbl in (end, cont):
        assert tbl["headers"] == ["项目", "面值", "票面利率", "实际利率", "到期日", "逾期本金"]
    assert end["_column_groups"] == [{"group": "期末余额", "start": 1, "span": 5}]
    assert cont["_column_groups"] == [{"group": "上年年末余额", "start": 1, "span": 5}]


@pytest.mark.parametrize(("variant", "number"), [("listed", "五、14"), ("soe", "八、15")])
def test_stage_movement_table_two_level(variant: str, number: str) -> None:
    """三阶段迁移表：父表头第一/二/三阶段，合计列为独立列（不进分组）。"""
    tbl = _table(variant, number, "本期计提、收回或转回的减值准备情况")
    assert tbl["headers"][0] == "减值准备"
    assert tbl["headers"][-1] == "合计"
    assert tbl["_column_groups"] == [
        {"group": "第一阶段", "start": 1, "span": 1},
        {"group": "第二阶段", "start": 2, "span": 1},
        {"group": "第三阶段", "start": 3, "span": 1},
    ]
    labels = [r["label"] for r in tbl["rows"]]
    assert labels[0] == "期初余额"
    assert labels[-1] == "期末余额"
    assert len(labels) == 12


def test_g4_soe_table6_renamed_from_placeholder() -> None:
    """seed 曾生成占位表名「债权投资（表6）」。"""
    names = [t["name"] for t in _section("soe", "八、15")["tables"]]
    assert "债权投资（表6）" not in names
    assert "本期计提、收回或转回的减值准备情况" in names


def test_g5_listed_provision_table_projects_three_levels_into_two() -> None:
    """源模版三级（期末>账面余额>金额）→ 平台两级：父取期间，子用限定名。"""
    tbl = _table("listed", "五、16", "坏账准备计提情况")
    assert tbl["headers"] == [
        "类别",
        "账面余额-金额", "账面余额-比例(%)", "坏账准备-金额", "坏账准备-预期信用损失率(%)", "账面价值",
        "账面余额-金额", "账面余额-比例(%)", "坏账准备-金额", "坏账准备-预期信用损失率(%)", "账面价值",
    ]
    assert tbl["_column_groups"] == [
        {"group": "期末余额", "start": 1, "span": 5},
        {"group": "上年年末余额", "start": 6, "span": 5},
    ]


def test_g5_listed_portfolio_table_deduplicated() -> None:
    """源模版有 5 张同名「组合计提项目：XXX」占位表 → 只留 1 张骨架。"""
    names = [t["name"] for t in _section("listed", "五、16")["tables"]]
    assert names.count("组合计提项目：XXX") == 1
    tbl = _table("listed", "五、16", "组合计提项目：XXX")
    # 源模版首格留空 → 统一取「账龄」，避免空列头
    assert tbl["headers"][0] == "账龄"
    assert [r["label"] for r in tbl["rows"]] == ["1年以内", "1至2年", "2至3年", "合计"]


def test_g5_listed_nature_table_drops_placeholder_row() -> None:
    """「可无限量添加行」是占位说明，不是披露数据行。

    🔴 行集合以**权威模板**（`backend/wp_templates/G/G5 长期应收款.xlsx`）为准：
    只有 3 类性质（各带「其中：未实现融资收益」）+ 3 个空行 + 小计/减/合计。
    参考副本 `基础数据/…` 里的「应收保证金 / 应收关联方款项 / 其他」三行在权威版**已删除**，
    2026-07-30 曾因先读参考副本而误加，此处反向锁死。
    """
    labels = [r["label"] for r in _table("listed", "五、16", "长期应收款按性质披露")["rows"]]
    assert "可无限量添加行" not in labels
    assert labels[-3:] == ["小计", "减：1年内到期的长期应收款", "合计"]
    assert labels[:6] == [
        "融资租赁款", "其中：未实现融资收益",
        "分期收款销售商品", "其中：未实现融资收益",
        "分期收款提供劳务", "其中：未实现融资收益",
    ]
    for stale in ("应收保证金", "应收关联方款项"):
        assert stale not in labels, f"{stale} 来自已落后的参考副本，权威模板已删除"


def test_g5_soe_nature_table_rows_follow_authoritative_template() -> None:
    labels = [r["label"] for r in _table("soe", "八、17", "长期应收款按性质披露")["rows"]]
    assert labels[:4] == [
        "融资租赁款", "其中：未实现融资收益", "分期收款销售商品", "分期收款提供劳务",
    ]
    assert "其他" in labels
    for stale in ("应收保证金", "应收关联方款项"):
        assert stale not in labels


@pytest.mark.parametrize(("variant", "number", "account"), [
    ("listed", "五、14", "债权投资"),
    ("listed", "五、15", "其他债权投资"),
])
def test_listed_first_stage_uses_reason_others_use_basis(
    variant: str, number: str, account: str
) -> None:
    """🔴 只有「期末第一阶段」末列是「理由」，其余 5 张是「划分依据」（权威模板逐格核对）。"""
    first = _table(variant, number, f"期末处于第一阶段的{account}的减值准备")
    assert first["headers"][-1] == "理由"
    for name in (
        f"期末处于第二阶段的{account}的减值准备",
        f"期末处于第三阶段的{account}的减值准备",
        f"上年年末处于第一阶段的{account}的减值准备",
        f"上年年末处于第二阶段的{account}的减值准备",
        f"上年年末处于第三阶段的{account}的减值准备",
    ):
        assert _table(variant, number, name)["headers"][-1] == "划分依据", name


def test_g4_soe_stage_rows_use_impairment_wording() -> None:
    """G4 国企权威模板编制说明第 2 条：三阶段用语统一为「减值准备」（旧副本写「坏账准备」）。"""
    for name in (
        "期末，处于第一阶段的债权投资的减值准备",
        "期末，处于第二阶段的债权投资的减值准备",
        "期末，处于第三阶段的债权投资的减值准备",
    ):
        labels = [r["label"] for r in _table("soe", "八、15", name)["rows"]]
        assert "按单项计提减值准备" in labels, name
        assert "按组合计提减值准备" in labels, name
        assert not any("坏账准备" in x for x in labels), name


def test_g6_listed_provision_movement_keeps_other_row() -> None:
    """权威模板该表有「其他（如有）」行（旧副本为空行）。"""
    labels = [
        r["label"] for r in _table("listed", "五、15", "其他债权投资减值准备本期变动情况")["rows"]
    ]
    assert labels == ["", "", "其他（如有）", "合计"]


def test_g5_listed_movement_table_has_label_header() -> None:
    """源模版首格留空导致只剩 1 个表头 → 补「项目」标签列。"""
    tbl = _table("listed", "五、16", "本期计提、收回或转回的坏账准备情况")
    assert tbl["headers"] == ["项目", "坏账准备金额"]


def test_g5_soe_has_no_provision_tables() -> None:
    """🔴 宁缺勿造：国企附注模版对「坏账准备计提情况」只有交叉引用，无表。

    源 xlsx 的 坏账准备/按单项/5×组合 系列表属**底稿侧**审计明细，不进附注。
    """
    names = [t["name"] for t in _section("soe", "八、17")["tables"]]
    assert names == [
        "长期应收款按性质披露",
        "终止确认的长期应收款",
        "转移长期应收款且继续涉入形成的资产、负债的金额",
    ]
    assert not any("坏账准备" in n or "组合计提" in n for n in names)


def test_g5_soe_strips_html_from_headers() -> None:
    """md 里的 `账面<br/>余额` / `与终止确认相关的<br/>利得或损失` 必须去 HTML。"""
    for name in (
        "长期应收款按性质披露",
        "终止确认的长期应收款",
    ):
        headers = _table("soe", "八、17", name)["headers"]
        assert not any("<" in h for h in headers), f"{name} headers 含 HTML：{headers}"
    assert "与终止确认相关的利得或损失" in _table("soe", "八、17", "终止确认的长期应收款")["headers"]


def test_g6_listed_main_table_is_single_level() -> None:
    """G6 主表源模版就是 3 列单级（与 G4 的 7 列两级不同，勿套用）。"""
    tbl = _table("listed", "五、15", "其他债权投资")
    assert tbl["headers"] == ["项目", "期末余额", "上年年末余额"]
    assert any(c.get("flat") for c in tbl["columns"])
    assert not tbl.get("_column_groups")


def test_g6_soe_only_two_tables() -> None:
    """国企侧减值准备参照八、15 披露 → 不加表。"""
    names = [t["name"] for t in _section("soe", "八、16")["tables"]]
    assert names == ["其他债权投资情况", "期末重要的其他债权投资"]


@pytest.mark.parametrize(("variant", "number", "name"), [
    ("listed", "五、14", "债权投资"),
    ("listed", "五、15", "其他债权投资"),
    ("listed", "五、16", "长期应收款按性质披露"),
    ("soe", "八、17", "长期应收款按性质披露"),
])
def test_subtotal_then_deduction_then_total(variant: str, number: str, name: str) -> None:
    """「小计 → 减：一年内到期 → 合计」三行结构不得丢（合计 ≠ 明细之和）。"""
    rows = _table(variant, number, name)["rows"]
    labels = [r["label"] for r in rows]
    assert labels[-3] == "小计"
    assert labels[-2].startswith("减：")
    assert labels[-1] == "合计"
    assert rows[-3].get("row_type") == "subtotal"
    assert rows[-1].get("row_type") == "total"
