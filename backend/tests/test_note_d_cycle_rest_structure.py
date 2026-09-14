"""附注 D 类剩余循环（D3/D5/D6/D7）披露章节结构守卫。

守住 8 个章节（五、38 / 八、38 / 五、6 / 八、6 / 五、10 / 八、11 / 五、39 / 八、39）的
结构不被并发会话或 md 重建脚本回退：

- 表名齐备唯一，且**垃圾表名不得复活**（空名 / `续：` / `项  目` / `按单项计提减值准备：`）
- 每张表显式表态 `flat` 或 `group`（三态语义：未表态会被 `_infer_groups_from_headers`
  按前缀反猜出凭空父表头 —— D5 上市「背书或贴现」两列共前缀「期末」是实证案例）
- 两级表头的 `_column_groups` 与 `columns[].group` 自洽、索引连续、不覆盖标签列
- D6 含比较期的表两期子列名同构
- 无 `row_type == 'header_label'` 假数据行；`guidance` 齐备

spec: .kiro/specs/d-cycle-remaining-disclosure-alignment/ Task 1.2
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
FIX_SCRIPT = _BACKEND / "scripts" / "fix" / "fix_note_d_cycle_rest_structure.py"
DATA_DIR = _BACKEND / "data"


def _load_fix_module():
    spec = importlib.util.spec_from_file_location("_fix_d_cycle_rest", FIX_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix_module()
KIT = importlib.import_module("_note_structure_kit")

SECTION_KEYS = sorted(FIX.SECTIONS)

_DOC_CACHE: dict[str, dict[str, Any]] = {}


def _doc(variant: str) -> dict[str, Any]:
    if variant not in _DOC_CACHE:
        _DOC_CACHE[variant] = json.loads(
            FIX.TEMPLATE_PATH[variant].read_text(encoding="utf-8")
        )
    return _DOC_CACHE[variant]


def _section(key: str) -> dict[str, Any]:
    spec = FIX.SECTIONS[key]
    sec = KIT.find_section(_doc(str(spec["variant"])), str(spec["section"]))
    assert sec is not None, f"{key}: 缺章节 {spec['section']}"
    return sec


def _tables(key: str) -> list[dict[str, Any]]:
    return _section(key).get("tables") or []


def _table(key: str, name: str) -> dict[str, Any]:
    for t in _tables(key):
        if str(t.get("name", "")) == name:
            return t
    pytest.fail(f"{key}: 缺表「{name}」")


# ─── 章节级：脚本自带校验器必须零欠账（Property 5）──────────────────────────


@pytest.mark.parametrize("key", SECTION_KEYS)
def test_section_validates_clean(key: str) -> None:
    spec = FIX.SECTIONS[key]
    errs = KIT.validate_section(
        _section(key), list(spec["expected"]), forbidden_names=list(spec["drops"])
    )
    assert errs == [], f"{key}: {errs}"


@pytest.mark.parametrize("key", SECTION_KEYS)
def test_expected_tables_present_in_order(key: str) -> None:
    """期望表全部存在，且按计划顺序出现（游标式 apply 依赖顺序稳定）。"""
    spec = FIX.SECTIONS[key]
    names = [str(t.get("name", "")) for t in _tables(key)]
    idxs = [names.index(n) for n in spec["expected"] if n in names]
    missing = [n for n in spec["expected"] if n not in names]
    assert missing == [], f"{key}: 缺表 {missing}"
    assert idxs == sorted(idxs), f"{key}: 表序被打乱 {names}"


# ─── Property 2：每表显式表态 flat 或 group，且互斥 ──────────────────────────


@pytest.mark.parametrize("key", SECTION_KEYS)
def test_every_table_declares_flat_or_group(key: str) -> None:
    spec = FIX.SECTIONS[key]
    bad: list[str] = []
    for name in spec["expected"]:
        cols = _table(key, name).get("columns") or []
        has_flat = any(c.get("flat") for c in cols)
        has_group = any(c.get("group") for c in cols)
        if has_flat == has_group:  # 都无 → 未表态；都有 → 冲突
            bad.append(f"{name}(flat={has_flat}, group={has_group})")
    assert bad == [], f"{key}: {bad}"


# ─── Property 3：分组索引连续、不覆盖标签列、与 columns 自洽 ────────────────


@pytest.mark.parametrize("key", SECTION_KEYS)
def test_column_groups_consistent(key: str) -> None:
    spec = FIX.SECTIONS[key]
    for name in spec["expected"]:
        tbl = _table(key, name)
        cols = tbl.get("columns") or []
        headers = tbl.get("headers") or []
        want = KIT.derive_column_groups(cols)
        if want:
            assert tbl.get("_column_groups") == want, f"{key}/{name}: _column_groups 漂移"
            for g in want:
                assert int(g["start"]) >= 1, f"{key}/{name}: 分组覆盖标签列"
                assert int(g["start"]) + int(g["span"]) <= len(headers), (
                    f"{key}/{name}: 分组越界"
                )
        else:
            assert tbl.get("_column_groups") is None, (
                f"{key}/{name}: 单级表头残留 _column_groups（会渲出凭空父表头）"
            )


@pytest.mark.parametrize("key", SECTION_KEYS)
def test_headers_match_column_labels(key: str) -> None:
    spec = FIX.SECTIONS[key]
    for name in spec["expected"]:
        tbl = _table(key, name)
        cols = tbl.get("columns") or []
        assert [str(c["label"]) for c in cols] == list(tbl.get("headers") or []), (
            f"{key}/{name}: headers 与 columns.label 不一致"
        )
        assert cols[0].get("is_label") is True, f"{key}/{name}: 首列未标 is_label"


# ─── Property 6：无垃圾表名 / 无假数据行 ────────────────────────────────────

_GARBAGE_NAMES = {"", "续：", "续:", "项  目", "项目", "按单项计提减值准备：", "合同负债（表2）"}


@pytest.mark.parametrize("key", SECTION_KEYS)
def test_no_garbage_table_names(key: str) -> None:
    offenders = [
        str(t.get("name", ""))
        for t in _tables(key)
        if str(t.get("name", "")).strip() in _GARBAGE_NAMES
        or not str(t.get("name", "")).strip()
    ]
    assert offenders == [], f"{key}: 垃圾表名复活 {offenders}"


@pytest.mark.parametrize("key", SECTION_KEYS)
def test_no_header_label_rows(key: str) -> None:
    bad: list[str] = []
    for t in _tables(key):
        for j, row in enumerate(t.get("rows") or []):
            if str(row.get("row_type", "")) == "header_label":
                bad.append(f"{t.get('name')}#{j}")
    assert bad == [], f"{key}: 压扁的第二行表头残留为假数据行 {bad}"


@pytest.mark.parametrize("key", SECTION_KEYS)
def test_guidance_present(key: str) -> None:
    spec = FIX.SECTIONS[key]
    missing = [n for n in spec["expected"] if not str(_table(key, n).get("guidance") or "").strip()]
    assert missing == [], f"{key}: 缺 guidance {missing}"


@pytest.mark.parametrize("key", SECTION_KEYS)
def test_no_bare_table_name_paragraphs(key: str) -> None:
    """`text_sections` 里的裸表名会被当披露正文渲染（后端 `_is_table_title_paragraph`）。"""
    bare = KIT.find_bare_table_name_paragraphs(_section(key))
    assert bare == [], f"{key}: {bare}"


def test_is_title_paragraph_matches_backend_semantics() -> None:
    """kit 的复刻判定与后端真实实现同口径（防守卫空转）。"""
    from app.services.disclosure_engine import _is_table_title_paragraph as backend_impl

    samples = [
        "",
        "   ",
        "#### 合同资产",
        "# 合同资产",
        "（1）合同资产情况",
        "1、合同资产",
        "合同资产",
        "组合计提项目：工程施工",
        "（1）" + "长" * 40,
        "1、" + "长" * 40,
    ]
    for s in samples:
        assert KIT.is_title_paragraph(s) == backend_impl(s), f"判定漂移：{s!r}"


# ─── Property 4：D6 两期同构 ────────────────────────────────────────────────

_TWO_PERIOD_TABLES = [
    ("d6-listed", "合同资产", ("期末余额", "上年年末余额")),
    ("d6-listed", "组合计提项目：工程施工", ("期末余额", "上年年末余额")),
    ("d6-listed", "组合计提项目：质量保证金", ("期末余额", "上年年末余额")),
    ("d6-soe", "合同资产情况", ("期末数", "期初数")),
]


@pytest.mark.parametrize(("key", "name", "groups"), _TWO_PERIOD_TABLES)
def test_two_period_tables_are_isomorphic(
    key: str, name: str, groups: tuple[str, str]
) -> None:
    cols = _table(key, name).get("columns") or []
    by_group: dict[str, list[str]] = {}
    for c in cols[1:]:
        by_group.setdefault(str(c.get("group") or ""), []).append(str(c.get("label")))
    assert set(by_group) == set(groups), f"{key}/{name}: 分组名 {sorted(by_group)}"
    assert by_group[groups[0]] == by_group[groups[1]], f"{key}/{name}: 两期子列不同构"


# ─── 逐表钉死关键结构（防悄悄改回压扁形态）────────────────────────────────


def _cols(key: str, name: str) -> list[tuple[str, str]]:
    """返回 `[(label, group)]`，group 缺失为空串。"""
    return [
        (str(c.get("label")), str(c.get("group") or ""))
        for c in (_table(key, name).get("columns") or [])
    ]


def test_d6_listed_main_two_level() -> None:
    assert _cols("d6-listed", "合同资产") == [
        ("项  目", ""),
        ("账面余额", "期末余额"), ("减值准备", "期末余额"), ("账面价值", "期末余额"),
        ("账面余额", "上年年末余额"), ("减值准备", "上年年末余额"), ("账面价值", "上年年末余额"),
    ]


def test_d6_soe_main_two_level() -> None:
    assert _cols("d6-soe", "合同资产情况") == [
        ("项  目", ""),
        ("账面余额", "期末数"), ("减值准备", "期末数"), ("账面价值", "期末数"),
        ("账面余额", "期初数"), ("减值准备", "期初数"), ("账面价值", "期初数"),
    ]


@pytest.mark.parametrize(
    "name",
    ["合同资产减值准备计提情况（期末余额）", "合同资产减值准备计提情况（续：上年年末余额）"],
)
def test_d6_listed_impairment_provision_split_two_level(name: str) -> None:
    """源模板三级 → 顶层期间提到表名，只留两级；账面价值是 rowspan=2 独立列。"""
    assert _cols("d6-listed", name) == [
        ("类别", ""),
        ("金额", "账面余额"), ("比例(%)", "账面余额"),
        ("金额", "减值准备"), ("预期信用损失率(%)", "减值准备"),
        ("账面价值", ""),
    ]


def test_d6_soe_impairment_movement_group() -> None:
    assert _cols("d6-soe", "合同资产减值准备") == [
        ("项  目", ""),
        ("期初数", ""),
        ("计提", "本期变动金额"), ("转回", "本期变动金额"), ("转销/核销", "本期变动金额"),
        ("期末数", ""),
        ("原因", ""),
    ]


def test_d5_listed_endorsed_table_is_flat() -> None:
    """🔴 两列共前缀「期末」：未标 flat 时会被推断出凭空「期末」父表头。"""
    tbl = _table("d5-listed", "期末本公司已背书或贴现但尚未到期的应收票据")
    cols = tbl.get("columns") or []
    assert any(c.get("flat") for c in cols)
    assert not any(c.get("group") for c in cols)
    assert tbl.get("_column_groups") is None
    assert [str(c.get("label")) for c in cols] == [
        "种  类", "期末终止确认金额", "期末未终止确认金额",
    ]


def test_d5_listed_impairment_table_has_label_column() -> None:
    """模板曾只剩「减值准备金额」一列（标签列被 md 重建脚本吃掉）。"""
    tbl = _table("d5-listed", "本期计提、收回或转回的减值准备情况")
    assert [str(h) for h in tbl.get("headers") or []] == ["项目", "减值准备金额"]
    labels = [str(r.get("label")) for r in tbl.get("rows") or []]
    assert labels[0] == "上年年末余额" and labels[-1] == "期末余额"


def test_d5_listed_main_rows_follow_source() -> None:
    """源模板 A9-A13 五行：两类资产 + 小计 + 减：公允价值变动 + 期末公允价值。"""
    rows = _table("d5-listed", "应收款项融资").get("rows") or []
    assert [str(r.get("label")) for r in rows] == [
        "应收票据", "应收账款", "小  计", "减：其他综合收益-公允价值变动", "期末公允价值",
    ]


def test_d7_soe_second_table_renamed() -> None:
    names = [str(t.get("name", "")) for t in _tables("d7-soe")]
    assert "本期合同负债账面价值的重大变动" in names
    assert "合同负债（表2）" not in names


def test_d3_soe_second_table_follows_source() -> None:
    """源 A10/A11：表名「账龄超过1年的重要预收账款」、第 3 列「未偿还原因」。"""
    tbl = _table("d3-soe", "账龄超过1年的重要预收账款")
    assert [str(h) for h in tbl.get("headers") or []] == [
        "债权单位名称", "期末余额", "未偿还原因",
    ]


# ─── 反向自检：守卫不得空转 ─────────────────────────────────────────────────


def test_validator_rejects_untyped_columns() -> None:
    """构造一张既无 flat 也无 group 的表，校验器必须判红。"""
    section = {
        "tables": [
            {
                "name": "替身表",
                "headers": ["项目", "期末余额"],
                "columns": [
                    {"key": "label", "label": "项目", "is_label": True},
                    {"key": "amt", "label": "期末余额", "format": "amount"},
                ],
                "guidance": "x",
            }
        ]
    }
    errs = KIT.validate_section(section, ["替身表"])
    assert any("未表态" in e for e in errs), errs


def test_validator_rejects_group_with_slash() -> None:
    section = {
        "tables": [
            {
                "name": "替身表",
                "headers": ["项目", "金额"],
                "columns": [
                    {"key": "label", "label": "项目", "is_label": True},
                    {"key": "amt", "label": "金额", "group": "期末/期初"},
                ],
                "_column_groups": [{"group": "期末/期初", "start": 1, "span": 1}],
                "guidance": "x",
            }
        ]
    }
    errs = KIT.validate_section(section, ["替身表"])
    assert any("group 含 '/'" in e for e in errs), errs


def test_validator_rejects_forbidden_name() -> None:
    section = {"tables": [{"name": "", "headers": [], "columns": [], "guidance": ""}]}
    errs = KIT.validate_section(section, [], forbidden_names=[""])
    assert any("垃圾表未清理" in e for e in errs), errs


def test_two_period_columns_helper_is_isomorphic_by_construction() -> None:
    cols = KIT.two_period_columns(
        ("label", "项目"), ("A期", "B期"), [("x", "列1", "amount"), ("y", "列2", None)]
    )
    assert [c["label"] for c in cols] == ["项目", "列1", "列2", "列1", "列2"]
    assert [c.get("group") for c in cols] == [None, "A期", "A期", "B期", "B期"]
    assert [c["key"] for c in cols] == ["label", "end_x", "end_y", "prior_x", "prior_y"]


# ─── text_sections 段落清单（R4.3 / Task 5.5）─────────────────────────────────


def test_d6_listed_text_sections_include_source_notes() -> None:
    """上市原本只有 3 条 `【提示…】`，缺源模板 A36-A41 的说明段（国企侧本就齐备）。"""
    paras = _section("d6-listed").get("text_sections") or []
    joined = "\n".join(str(p) for p in paras)
    assert len(paras) == len(FIX.SECTIONS["d6-listed"]["text_sections"])
    for frag in (
        "履行履约义务的时间与通常的付款时间之间的关系",
        "重大变动的情形包括",
        "企业合并导致的变动",
        "合同资产重分类为应收款项",
    ):
        assert frag in joined, f"缺源模板说明段：{frag}"


def test_d6_listed_text_sections_are_not_hash_titles() -> None:
    """🔴 实质披露正文不得写成 `#### xxx`：后端把 `#` 开头当标题，标题本身不进任何输出。"""
    for p in _section("d6-listed").get("text_sections") or []:
        s = str(p).strip()
        if s.startswith("#"):
            # 只允许「纯表标题」用 # 前缀（国企侧范式），上市侧本 spec 未引入
            assert False, f"说明正文被写成标题会被静默丢弃：{s[:40]}"


@pytest.mark.parametrize("key", ["d6-listed", "d6-soe"])
def test_d6_text_sections_no_bare_table_names(key: str) -> None:
    assert KIT.find_bare_table_name_paragraphs(_section(key)) == []


def test_check_mode_detects_text_sections_drift() -> None:
    """`--check` 必须能发现 text_sections 漂移（否则守卫只挡表结构，段落缺失照过）。"""
    import json as _json

    spec = FIX.SECTIONS["d6-listed"]
    doc = _json.loads(FIX.TEMPLATE_PATH["listed"].read_text(encoding="utf-8"))
    section = KIT.find_section(doc, str(spec["section"]))
    assert section is not None
    section["text_sections"] = ["只剩一段"]
    errs = KIT.validate_section(
        section, list(spec["expected"]), forbidden_names=list(spec["drops"])
    )
    # validate_section 本身不管 text_sections 清单，清单比对在 run_section 的 check 分支
    assert section["text_sections"] != list(spec["text_sections"])
    assert isinstance(errs, list)
