"""附注 K 系复杂类（批 3：K1 其他应收款 / K6 持有待售）章节结构守卫。

对应 `backend/scripts/fix/fix_note_k_complex_structure.py`（幂等脚本）。
只读 `backend/data/note_template_{listed,soe}.json` + 源 xlsx，不连库。

守住的实质欠账（详见脚本 docstring）：
  · 37 + 11 张表的 `columns` 齐备且在 `group` / `flat` 之间明确表态
  · 两级表头用 `group` + **叶子列名**（不是带期别前缀的压平串），`_column_groups` 自洽
  · 无 `header_label` 假数据行 / 无占位说明行 / 无裸续表名 `续：`
  · 三阶段快照 6 表含第 6 列「理由」
  · K6 上市 `tables[1]` 的 name↔rows 错位已修，5 张垃圾表名已正名
  · `sheet_name` 常量与源 xlsx tab 名逐字一致（K1 上市是**前半角后全角**）

含**反向自检**：确认守卫真的能打红（防正则/路径失效导致空转）。
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "backend" / "scripts" / "fix" / "fix_note_k_complex_structure.py"
LISTED = REPO / "backend" / "data" / "note_template_listed.json"
SOE = REPO / "backend" / "data" / "note_template_soe.json"
FRONTEND = REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"

PLACEHOLDER_ROWS = {"可无限量添加行", "......", "……", "项  目", "子公司A", "分公司B"}


def _load_script() -> Any:
    """按文件路径加载脚本（无包上下文，与 CI 的调用方式一致）。"""
    spec = importlib.util.spec_from_file_location("fix_note_k_complex_structure", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def script() -> Any:
    return _load_script()


def _section(path: Path, number: str) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")).strip() == number:
            return sec
    raise AssertionError(f"{path.name} 缺章节 {number}")


SECTION_KEYS = [
    ("k1-listed", LISTED, "五、8"),
    ("k1-soe", SOE, "八、9"),
    ("k6-listed", LISTED, "五、11"),
    ("k6-soe", SOE, "八、12"),
    ("k6-soe-liab", SOE, "八、43"),
]


# ─────────────────── 脚本自身：--check 必须为 0 欠账 ───────────────────

def test_all_sections_aligned(script: Any) -> None:
    """`--check` 等价断言：5 个章节全部对齐（幂等脚本已跑过）。"""
    for key in script.SPECS:
        _changes, warnings, errs = script._runner(key, dry_run=True, check=True)
        assert not errs, f"{key} 结构欠账：{errs}"
        assert not warnings, f"{key} 告警：{warnings}"


def test_script_is_idempotent(script: Any) -> None:
    """dry-run 应报 0 处变更（已应用过 → 幂等空操作）。"""
    for key in script.SPECS:
        changes, warnings, errs = script._runner(key, dry_run=True, check=False)
        assert not changes, f"{key} 仍有待修变更（脚本非幂等或模板被回退）：{changes}"
        assert not errs, f"{key} 校验失败：{errs}"
        assert not warnings, f"{key} 告警：{warnings}"


def test_sections_stamped(script: Any) -> None:
    for _key, path, number in SECTION_KEYS:
        sec = _section(path, number)
        assert sec.get("_aligned_by") == script.ALIGNED_BY, f"{number} 缺 _aligned_by 标记"


# ─────────────────── 通用结构：columns / 表态 / 假行 ───────────────────

@pytest.mark.parametrize("key,path,number", SECTION_KEYS)
def test_every_table_has_columns_and_guidance(key: str, path: Path, number: str) -> None:
    sec = _section(path, number)
    tables = sec.get("tables") or []
    assert tables, f"{number} 没有表"
    for tbl in tables:
        name = tbl.get("name")
        cols = tbl.get("columns") or []
        headers = tbl.get("headers") or []
        assert cols, f"{number}/{name} 缺 columns"
        assert len(cols) == len(headers), f"{number}/{name} columns≠headers"
        assert [str(c["label"]) for c in cols] == [str(h) for h in headers], (
            f"{number}/{name} columns.label 与 headers 不同形"
        )
        assert str(tbl.get("guidance") or "").strip(), f"{number}/{name} 缺 guidance"
        assert cols[0].get("is_label") is True, f"{number}/{name} 首列未标 is_label"
        has_flat = any(c.get("flat") for c in cols)
        has_group = any(c.get("group") for c in cols)
        assert not (has_flat and has_group), f"{number}/{name} flat 与 group 并存"
        assert has_flat or has_group, f"{number}/{name} 未表态"
        assert not cols[0].get("group"), f"{number}/{name} 标签列不得带 group"


@pytest.mark.parametrize("key,path,number", SECTION_KEYS)
def test_no_fake_rows(key: str, path: Path, number: str) -> None:
    """无 `header_label` 压扁表头残留、无占位说明行。"""
    sec = _section(path, number)
    for tbl in sec.get("tables") or []:
        name = tbl.get("name")
        for i, row in enumerate(tbl.get("rows") or []):
            assert str(row.get("row_type", "")) != "header_label", (
                f"{number}/{name} 第 {i} 行仍是 header_label 假数据行"
            )
            label = str(row.get("label", "")).strip()
            assert label not in PLACEHOLDER_ROWS, (
                f"{number}/{name} 第 {i} 行是占位说明「{label}」，应改空白录入行"
            )


@pytest.mark.parametrize("key,path,number", SECTION_KEYS)
def test_column_groups_consistent(key: str, path: Path, number: str) -> None:
    """`_column_groups` 与 `columns[].group` 自洽（后端 `_extract_column_groups` 同口径）。"""
    script_mod = _load_script()
    derive = script_mod.derive_column_groups
    sec = _section(path, number)
    for tbl in sec.get("tables") or []:
        name = tbl.get("name")
        cols = tbl.get("columns") or []
        want = derive(cols)
        if want:
            assert tbl.get("_column_groups") == want, f"{number}/{name} _column_groups 不自洽"
            for g in want:
                assert g["start"] >= 1, f"{number}/{name} 分组 start<1"
                assert g["start"] + g["span"] <= len(cols), f"{number}/{name} 分组越界"
        else:
            assert "_column_groups" not in tbl, f"{number}/{name} 单级表头残留 _column_groups"


@pytest.mark.parametrize("key,path,number", SECTION_KEYS)
def test_headers_plaintext(key: str, path: Path, number: str) -> None:
    sec = _section(path, number)
    for tbl in sec.get("tables") or []:
        for h in tbl.get("headers") or []:
            assert "<" not in str(h), f"{number}/{tbl.get('name')} headers 含 HTML：{h}"
            assert str(h).strip(), f"{number}/{tbl.get('name')} headers 含空串"


@pytest.mark.parametrize("key,path,number", SECTION_KEYS)
def test_no_duplicate_table_names(key: str, path: Path, number: str) -> None:
    names = [str(t.get("name", "")) for t in (_section(path, number).get("tables") or [])]
    assert len(names) == len(set(names)), f"{number} 表名重复：{names}"


# ─────────────────── K1 专项 ───────────────────

def test_k1_soe_bare_continuation_renamed() -> None:
    """裸续表名 `续：` 已正名（跨章节撞键 + 附注 TAB 看不出续的是哪张表）。"""
    names = [str(t.get("name")) for t in (_section(SOE, "八、9").get("tables") or [])]
    assert "续：" not in names
    assert "按坏账准备计提方法分类披露其他应收款项（续：期初余额）" in names


def test_k1_listed_stage_tables_have_reason_column() -> None:
    """三阶段快照 6 表第 6 列必须是「理由」（源 xlsx F32/F41/F51/F63/F72/F82）。"""
    sec = _section(LISTED, "五、8")
    by_name = {str(t.get("name")): t for t in (sec.get("tables") or [])}
    stage_names = [
        "期末处于第一阶段的坏账准备",
        "期末处于第二阶段的坏账准备",
        "期末处于第三阶段的坏账准备",
        "上年年末处于第一阶段的坏账准备",
        "上年年末处于第二阶段的坏账准备",
        "上年年末处于第三阶段的坏账准备",
    ]
    for name in stage_names:
        tbl = by_name.get(name)
        assert tbl is not None, f"模板缺表 {name}"
        headers = tbl.get("headers") or []
        assert len(headers) == 6, f"{name} 应 6 列，实为 {len(headers)}"
        assert headers[5] == "理由", f"{name} 末列应为「理由」"
    # ECL 率表头按阶段不同
    assert "未来12个月" in (by_name[stage_names[0]].get("headers") or [])[2]
    assert "整个存续期" in (by_name[stage_names[1]].get("headers") or [])[2]


def test_k1_listed_nature_is_two_level_with_leaf_labels() -> None:
    """按款项性质披露 = 两级表头，叶子列名不得带期别前缀（压平即杜撰）。"""
    tbl = next(
        t for t in (_section(LISTED, "五、8").get("tables") or [])
        if t.get("name") == "按款项性质披露"
    )
    assert (tbl.get("headers") or []) == [
        "项  目", "账面余额", "坏账准备", "账面价值", "账面余额", "坏账准备", "账面价值",
    ]
    groups = [c.get("group") for c in (tbl.get("columns") or [])]
    assert groups == [None, "期末金额", "期末金额", "期末金额",
                      "上年年末金额", "上年年末金额", "上年年末金额"]
    # key 仍是既有中文数据键（改 key 会让整表数据丢落点）
    assert [c.get("key") for c in (tbl.get("columns") or [])] == [
        "label", "期末账面余额", "期末坏账准备", "期末账面价值",
        "上年年末账面余额", "上年年末坏账准备", "上年年末账面价值",
    ]


def test_k1_soe_method_tables_split_top_level_period() -> None:
    """三级表头按「主表 + 续表」拆顶层期别（D1/D6 同款范式），剩两级用 group。"""
    sec = _section(SOE, "八、9")
    by_name = {str(t.get("name")): t for t in (sec.get("tables") or [])}
    for name in ["按坏账准备计提方法分类披露其他应收款项",
                 "按坏账准备计提方法分类披露其他应收款项（续：期初余额）"]:
        tbl = by_name[name]
        assert (tbl.get("headers") or []) == [
            "类  别", "金额", "比例(%)", "金额", "预期信用损失率(%)", "账面价值",
        ], name
        assert tbl.get("_column_groups") == [
            {"group": "账面余额", "start": 1, "span": 2},
            {"group": "坏账准备", "start": 3, "span": 2},
        ], name
        # 「账面价值」是 rowspan=2 的独立列 → 不给 group（混合分组）
        assert (tbl.get("columns") or [])[5].get("group") is None, name


# ─────────────────── K6 专项 ───────────────────

def test_k6_listed_table_names_fixed() -> None:
    """5 张垃圾表名已正名，且 name↔rows 错位已修。"""
    tables = _section(LISTED, "五、11").get("tables") or []
    names = [str(t.get("name")) for t in tables]
    assert names == [
        "持有待售资产和持有待售负债",
        "持有待售负债",
        "持有待售资产减值准备",
        "持有待售的非流动资产",
        "持有待售的处置组",
    ], names
    for garbage in ["期末，持有待售资产的情况：", "子公司A", "分公司B", "项  目"]:
        assert garbage not in names, f"垃圾表名「{garbage}」未清理"
    # 错位修复实证：`持有待售负债` 表的行必须是负债行，不是减值准备行
    liab = tables[1]
    assert "负债" in str((liab.get("rows") or [])[0].get("label"))


def test_k6_main_table_two_level_six_value_columns() -> None:
    """主表两级表头 6 个值列（压扁成 3 列时校验预设 F11-4 无从落地）。"""
    for path, number, groups in [
        (LISTED, "五、11", ("期末余额", "上年年末余额")),
        (SOE, "八、12", ("期末数", "期初数")),
    ]:
        tbl = (_section(path, number).get("tables") or [])[0]
        assert (tbl.get("headers") or []) == [
            "项目", "账面余额", "减值准备", "账面价值", "账面余额", "减值准备", "账面价值",
        ], number
        assert tbl.get("_column_groups") == [
            {"group": groups[0], "start": 1, "span": 3},
            {"group": groups[1], "start": 4, "span": 3},
        ], number


def test_k6_impairment_table_splits_decrease() -> None:
    """「本期减少」下辖「本期转回」「本期出售」（源 D32:E32 / D22:E22 合并）。"""
    for path, number, prior in [(LISTED, "五、11", "上年年末数"), (SOE, "八、12", "期初数")]:
        tbl = next(
            t for t in (_section(path, number).get("tables") or [])
            if t.get("name") == "持有待售资产减值准备"
        )
        assert (tbl.get("headers") or []) == [
            "项目", prior, "本期增加", "本期转回", "本期出售", "期末数",
        ], number
        assert tbl.get("_column_groups") == [{"group": "本期减少", "start": 3, "span": 2}], number


def test_k6_soe_liability_is_separate_section() -> None:
    """国企持有待售负债是独立章节 八、43（上市并入 五、11）。"""
    sec = _section(SOE, "八、43")
    tables = sec.get("tables") or []
    assert len(tables) == 1
    assert str(tables[0].get("name")) == "持有待售负债"
    assert (tables[0].get("headers") or []) == [
        "项目", "期末账面价值", "期末公允价值", "预计处置费用", "时间安排",
    ]
    # 上市侧同一张表用「预计出售费用」（源模板用语不同，不可共享常量）
    listed_nc = next(
        t for t in (_section(LISTED, "五、11").get("tables") or [])
        if t.get("name") == "持有待售的非流动资产"
    )
    assert "预计出售费用" in (listed_nc.get("headers") or [])


# ─────────────────── sheet_name 与源 xlsx tab 名逐字一致 ───────────────────

def _ts_const(file: str, name: str) -> dict[str, str]:
    """从前端 `.ts` 抽 `export const NAME = { listed: '..', soe: '..' }`。"""
    src = (FRONTEND / file).read_text(encoding="utf-8")
    m = re.search(rf"export const {re.escape(name)} = \{{(.*?)\}} as const", src, re.S)
    assert m, f"{file} 找不到常量 {name}"
    body = m.group(1)
    out: dict[str, str] = {}
    for key, val in re.findall(r"(\w+):\s*'([^']*)'", body):
        out[key] = val
    assert out, f"{file}.{name} 抽取为空（正则失效）"
    return out


@pytest.mark.parametrize("wp_file,ts_file,const_name", [
    ("K1 其他应收款.xlsx", "k1NoteSectionMap.ts", "K1_DISCLOSURE_SHEET_NAME"),
    ("K6 持有待售资产和负债.xlsx", "k6NoteSectionMap.ts", "K6_DISCLOSURE_SHEET_NAME"),
])
def test_sheet_name_matches_source_xlsx(wp_file: str, ts_file: str, const_name: str) -> None:
    """🔴 `disclosureSheetNameRegistry.spec.ts` 只比对「常量 ↔ registry」，
    查不出与 xlsx 的漂移 → 这里直接 openpyxl 读 `wb.sheetnames`。

    K1 上市 tab 名是**前半角后全角** `附注披露信息(上市公司）`，
    K6 国企是 `附注披露信息(国企）` —— 源模板即如此，勿"修正"。
    """
    openpyxl = pytest.importorskip("openpyxl")
    path = REPO / "backend" / "wp_templates" / "K" / wp_file
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        tabs = set(wb.sheetnames)
    finally:
        wb.close()
    consts = _ts_const(ts_file, const_name)
    for variant, sheet in consts.items():
        assert sheet in tabs, (
            f"{const_name}.{variant} = {sheet!r} 不在源 xlsx tab 名里；实际：{sorted(tabs)}"
        )


# ─────────────────── 反向自检（防守卫空转） ───────────────────

def test_guard_detects_regression(script: Any) -> None:
    """把一张表的 columns 抹掉 / 塞回 header_label 假行，校验器必须打红。"""
    sec = json.loads(json.dumps(_section(LISTED, "五、8"), ensure_ascii=False))
    expected = script.K1_LISTED_EXPECTED

    assert not script.validate_section(sec, expected), "基线应为 0 欠账"

    broken = json.loads(json.dumps(sec, ensure_ascii=False))
    broken["tables"][0].pop("columns")
    assert script.validate_section(broken, expected), "抹掉 columns 后未打红"

    broken2 = json.loads(json.dumps(sec, ensure_ascii=False))
    broken2["tables"][0]["rows"].insert(0, {"label": "项目", "row_type": "header_label"})
    assert script.validate_section(broken2, expected), "塞回 header_label 假行后未打红"

    broken3 = json.loads(json.dumps(sec, ensure_ascii=False))
    for col in broken3["tables"][6]["columns"]:
        col.pop("group", None)
    assert script.validate_section(broken3, expected), "两级表头退化成未表态后未打红"


def test_ts_const_extractor_self_check() -> None:
    """`_ts_const` 抽取器自检：改写法导致抽空时必须失败而非静默通过。"""
    consts = _ts_const("k6NoteSectionMap.ts", "K6_DISCLOSURE_SHEET_NAME")
    assert set(consts) == {"listed", "soe"}
    assert consts["soe"] == "附注披露信息(国企）"
    with pytest.raises(AssertionError):
        _ts_const("k6NoteSectionMap.ts", "K6_NO_SUCH_CONSTANT")
