"""附注模板存货章节结构契约（对齐源模版两级表头）。

- 上市版 §五、9 存货（`基础数据/附注模版/上市报表附注.md`）
- 国企版 §八、10 存货（`基础数据/附注模版/国企报表附注.md`）
- 列数口径交叉印证：`note_check_preset_formulas.json` F9-1~F9-13a

卡点目的：`scripts/fix/rebuild_note_from_md.py` 从 md 重建模板时会把两级表头压扁
（第二行表头降级成 `row_type: header_label` 数据行），本文件在 CI 阶段拦住这种回退，
提示重跑 `backend/scripts/fix/fix_note_inventory_structure.py`。

Validates: Requirements 4.1~4.10；Property 6 / 7 / 8

spec: .kiro/specs/f2-inventory-disclosure-template-alignment/
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
LISTED_PATH = _BACKEND / "data" / "note_template_listed.json"
SOE_PATH = _BACKEND / "data" / "note_template_soe.json"
LISTED_SECTION = "五、9"
SOE_SECTION = "八、10"
ALIGNED_BY = "f2-inventory-disclosure-template-alignment"
_FIX_HINT = "请重跑 python backend/scripts/fix/fix_note_inventory_structure.py"

_IMP = "跌价准备/合同履约成本减值准备"
PORTFOLIO_HEADERS = ["组合", "金额", "比例(%)", "金额", "计提标准", "比例(%)", "账面价值"]
PORTFOLIO_GROUPS = [
    {"group": "账面余额", "start": 1, "span": 2},
    {"group": "存货跌价准备", "start": 3, "span": 3},
]
PORTFOLIO_TABLES = [
    "按组合计提存货跌价准备",
    "按组合计提存货跌价准备（续）",
    "按库龄组合计提存货跌价准备",
    "按库龄组合计提存货跌价准备（续）",
]


def _load_section(path: Path, section_number: str) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    sec = next(
        (s for s in doc.get("sections") or [] if str(s.get("section_number")) == section_number),
        None,
    )
    assert sec is not None, f"{path.name} 缺少 {section_number} 章节"
    return sec


@pytest.fixture(scope="module")
def listed() -> dict[str, Any]:
    return _load_section(LISTED_PATH, LISTED_SECTION)


@pytest.fixture(scope="module")
def soe() -> dict[str, Any]:
    return _load_section(SOE_PATH, SOE_SECTION)


def _by_name(section: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(t.get("name")): t for t in section.get("tables") or []}


def _get(section: dict[str, Any], name: str) -> dict[str, Any]:
    tbl = _by_name(section).get(name)
    assert tbl is not None, f"缺表「{name}」；{_FIX_HINT}"
    return tbl


# ─────────────── R4.1 / R4.4：存货分类 7 列两级表头 ───────────────

def test_listed_classification_is_seven_columns(listed: dict[str, Any]) -> None:
    # R19：标签列头取源 xlsx A8「存货种类」（第一轮误写为「项目」）
    tbl = _get(listed, "存货分类")
    assert tbl["headers"] == ["存货种类", "账面余额", _IMP, "账面价值", "账面余额", _IMP, "账面价值"]
    assert tbl["_column_groups"] == [
        {"group": "期末余额", "start": 1, "span": 3},
        {"group": "上年年末余额", "start": 4, "span": 3},
    ]


def test_soe_classification_is_seven_columns(soe: dict[str, Any]) -> None:
    """国企用「期末数 / 期初数」（上市为「期末余额 / 上年年末余额」）。"""
    tbl = _get(soe, "存货分类")
    assert tbl["headers"] == ["项目", "账面余额", _IMP, "账面价值", "账面余额", _IMP, "账面价值"]
    assert tbl["_column_groups"] == [
        {"group": "期末数", "start": 1, "span": 3},
        {"group": "期初数", "start": 4, "span": 3},
    ]


# ─────────────── R4.2 / R4.5：跌价准备变动表 ───────────────

def test_listed_movement_merges_reversal_and_writeoff(listed: dict[str, Any]) -> None:
    """上市本期减少为「转回或转销」单列 → 7 列。"""
    tbl = _get(listed, "存货跌价准备及合同履约成本减值准备")
    assert tbl["headers"] == [
        "存货种类", "期初余额", "计提", "其他", "转回或转销", "其他", "期末余额",
    ]
    assert tbl["_column_groups"] == [
        {"group": "本期增加", "start": 2, "span": 2},
        {"group": "本期减少", "start": 4, "span": 2},
    ]


def test_soe_movement_splits_reversal_and_writeoff(soe: dict[str, Any]) -> None:
    """国企本期减少拆「转回 / 转销 / 其他」→ 8 列。"""
    tbl = _get(soe, "存货跌价准备及合同履约成本减值准备")
    assert tbl["headers"] == [
        "存货种类", "期初数", "计提", "其他", "转回", "转销", "其他", "期末数",
    ]
    assert tbl["_column_groups"] == [
        {"group": "本期增加", "start": 2, "span": 2},
        {"group": "本期减少", "start": 4, "span": 3},
    ]


# ─────────────── R4.3：按组合计提 4 张表各 7 列 ───────────────

@pytest.mark.parametrize("name", PORTFOLIO_TABLES)
def test_listed_portfolio_tables_are_seven_columns(listed: dict[str, Any], name: str) -> None:
    tbl = _get(listed, name)
    assert tbl["headers"] == PORTFOLIO_HEADERS, f"{name} 表头未对齐；{_FIX_HINT}"
    assert tbl["_column_groups"] == PORTFOLIO_GROUPS


# ─────────────── R4.8：表名可区分且与同步子表键一致 ───────────────

def test_listed_table_names_are_unique(listed: dict[str, Any]) -> None:
    names = [str(t.get("name")) for t in listed.get("tables") or []]
    assert len(names) == len(set(names)), f"表名重复：{names}；{_FIX_HINT}"


def test_listed_has_no_bare_continuation_table_name(listed: dict[str, Any]) -> None:
    """裸「续：」会被前端 currentNoteTables 误判为续表并列合并到上一张表。"""
    names = [str(t.get("name")) for t in listed.get("tables") or []]
    assert "续：" not in names, f"仍存在裸「续：」表名；{_FIX_HINT}"


def test_listed_portfolio_continuation_name_matches_sync_key(listed: dict[str, Any]) -> None:
    """与 f2DisclosureSyncPayload 的子表键一致，底稿同步才能落到同一张表。"""
    assert "按组合计提存货跌价准备（续）" in _by_name(listed)


def test_soe_table_names_are_unique(soe: dict[str, Any]) -> None:
    names = [str(t.get("name")) for t in soe.get("tables") or []]
    assert len(names) == len(set(names)), f"表名重复：{names}"


# ─────────────── R4.6：无 header_label 残留 ───────────────

@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_no_header_label_rows_remain(request: pytest.FixtureRequest, fixture_name: str) -> None:
    section = request.getfixturevalue(fixture_name)
    offenders = [
        f"{t.get('name')}[{i}]"
        for t in section.get("tables") or []
        for i, r in enumerate(t.get("rows") or [])
        if str(r.get("row_type", "")) == "header_label"
    ]
    assert not offenders, f"仍有 header_label 行：{offenders}；{_FIX_HINT}"


# ─────────────── Property 6：列宽自洽 ───────────────

@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_values_length_matches_headers(request: pytest.FixtureRequest, fixture_name: str) -> None:
    section = request.getfixturevalue(fixture_name)
    for tbl in section.get("tables") or []:
        n_val = max(len(tbl.get("headers") or []) - 1, 0)
        for i, row in enumerate(tbl.get("rows") or []):
            vals = row.get("values")
            if isinstance(vals, list):
                assert len(vals) == n_val, (
                    f"{tbl.get('name')} 第 {i} 行 values={len(vals)} ≠ headers-1={n_val}"
                )


@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_columns_length_matches_headers(request: pytest.FixtureRequest, fixture_name: str) -> None:
    section = request.getfixturevalue(fixture_name)
    for tbl in section.get("tables") or []:
        cols = tbl.get("columns")
        if not cols:
            continue
        assert len(cols) == len(tbl.get("headers") or []), (
            f"{tbl.get('name')} columns={len(cols)} ≠ headers={len(tbl.get('headers') or [])}"
        )


# ─────────────── Property 7：_column_groups 区间合法 ───────────────

@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_column_groups_ranges_are_valid(request: pytest.FixtureRequest, fixture_name: str) -> None:
    section = request.getfixturevalue(fixture_name)
    for tbl in section.get("tables") or []:
        groups = tbl.get("_column_groups")
        if not groups:
            continue
        headers = tbl.get("headers") or []
        occupied: set[int] = set()
        for g in groups:
            start, span = int(g["start"]), int(g["span"])
            assert start >= 1, f"{tbl.get('name')} 分组 {g['group']} start={start} 覆盖了标签列"
            assert start + span <= len(headers), (
                f"{tbl.get('name')} 分组 {g['group']} 越界：{start}+{span} > {len(headers)}"
            )
            rng = set(range(start, start + span))
            assert not (rng & occupied), f"{tbl.get('name')} 分组 {g['group']} 区间重叠"
            occupied |= rng


# ─────────────── R4.9：国企 text_sections 补齐 ───────────────

def test_soe_text_sections_contain_data_resource_notes(soe: dict[str, Any]) -> None:
    texts = soe.get("text_sections") or []
    joined = "\n".join(str(t) for t in texts)
    assert "《企业数据资源相关会计处理暂行规定》" in joined
    assert "评估结论成立的假设前提和限制条件" in joined
    assert "可索引至相关内容" in joined


def test_soe_text_sections_have_no_duplicates(soe: dict[str, Any]) -> None:
    """幂等保证：重复执行修订脚本不得重复追加文本段。"""
    texts = [str(t) for t in soe.get("text_sections") or []]
    dupes = [t for t in set(texts) if texts.count(t) > 1]
    assert not dupes, f"text_sections 重复：{[d[:40] for d in dupes]}"


# ─────────────── R4.10 / Property 8：对齐标记 ───────────────

@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_section_carries_alignment_stamp(
    request: pytest.FixtureRequest, fixture_name: str,
) -> None:
    section = request.getfixturevalue(fixture_name)
    assert section.get("_aligned_by") == ALIGNED_BY, _FIX_HINT
    assert section.get("_aligned_at")


# ─────────────── R18：seed 行集以源 xlsx 为准 ───────────────
#
# 第一轮的「行不动原则」（以 `基础数据/附注模版/*.md` 为裁决者、不引入「委托加工物资」
# 「发出商品」）已推翻：该目录在本仓库不存在无法核对，而运行时权威模板
# `backend/wp_templates/F/F2-1至F2-14 …xlsx` 的披露 sheet 明确含这两行
# （上市 r12/r14、国企 r12/r16），底稿常量也与之一致。

# Sprint 8：补「开发成本」「开发产品」（源 xlsx r20 注要求房企增加这两个种类；
# 原 9 类的取数键并集漏掉 1408/1409/1412，房企与商业零售企业的审定数无落点）
_LISTED_CATEGORY_LABELS = [
    "原材料", "在产品", "开发成本", "委托加工物资", "库存商品", "开发产品",
    "发出商品", "周转材料", "合同履约成本", "消耗性生物资产", "数据资源",
]

_SOE_CATEGORY_LABELS = [
    "原材料",
    "自制半成品及在产品",
    "其中：开发成本",
    "委托加工物资",
    "库存商品（产成品）",
    "其中：开发产品",
    "周转材料（包装物、低值易耗品等）",
    "发出商品",
    "消耗性生物资产",
    "合同履约成本",
    "数据资源",
    "其他",
    "其中：尚未开发的土地储备（由房地产开发企业填列）",
]


@pytest.mark.parametrize(
    "table_name",
    [
        "存货分类",
        "存货跌价准备及合同履约成本减值准备",
        "存货跌价准备及合同履约成本减值准备（续）",
    ],
)
def test_listed_rows_follow_source_xlsx(listed: dict[str, Any], table_name: str) -> None:
    """上市三表 seed 行 = 源 xlsx 的 9 个分类行 + 合计，且顺序一致。"""
    labels = [str(r.get("label")) for r in _get(listed, table_name).get("rows") or []]
    assert labels == _LISTED_CATEGORY_LABELS + ["合计"], _FIX_HINT


@pytest.mark.parametrize(
    "table_name",
    ["存货分类", "存货跌价准备及合同履约成本减值准备"],
)
def test_soe_rows_follow_source_xlsx(soe: dict[str, Any], table_name: str) -> None:
    """国企两表 seed 行 = 源 xlsx 的 13 行 + 合计（含 3 个「其中」子集行）。"""
    rows = _get(soe, table_name).get("rows") or []
    labels = [str(r.get("label")) for r in rows]
    assert labels == _SOE_CATEGORY_LABELS + ["合计"], _FIX_HINT
    assert sum(1 for x in labels if x.startswith("其中：")) == 3
    # 「其中：」行带 is_detail 标记，供渲染缩进与合计防双计
    for row in rows:
        if str(row.get("label", "")).startswith("其中："):
            assert row.get("is_detail") is True


def test_seed_rows_match_workpaper_push_labels(
    listed: dict[str, Any], soe: dict[str, Any],
) -> None:
    """seed 骨架行标签必须与底稿常量逐字一致，否则「未同步」与「已同步」行集异构。"""
    ts_dir = (
        Path(__file__).resolve().parents[3]
        / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"
    )
    listed_src = (ts_dir / "useF2DisclosureListed.ts").read_text(encoding="utf-8")
    soe_src = (ts_dir / "useF2DisclosureSoe.ts").read_text(encoding="utf-8")

    for label in _LISTED_CATEGORY_LABELS:
        assert f"label: '{label}'" in listed_src, f"底稿上市常量缺「{label}」"
    for label in _SOE_CATEGORY_LABELS:
        assert f"label: '{label}'" in soe_src, f"底稿国企常量缺「{label}」"


# ─────────────── R4：数据资源表三段式（F9-7~F9-13a）───────────────

@pytest.mark.parametrize(
    "fixture_name,imp_section_label",
    [("listed", "二、存货跌价准备"), ("soe", "二、跌价准备")],
)
def test_data_resource_table_three_segments(
    request: pytest.FixtureRequest, fixture_name: str, imp_section_label: str,
) -> None:
    section = request.getfixturevalue(fixture_name)
    tbl = _get(section, "确认为存货的数据资源")
    assert tbl["headers"] == [
        "项目", "外购的数据资源存货", "自行加工的数据资源存货",
        "其他方式取得的数据资源存货", "合计",
    ]
    labels = [str(r.get("label")) for r in tbl.get("rows") or []]
    assert labels[0] == "一、账面原值"
    assert imp_section_label in labels
    assert "三、账面价值" in labels


# ═══════════════════════════════════════════════════════════════════
# Sprint 7：seed 路径守卫
#
# 上一轮只给「同步载荷」（f2DisclosureSyncPayload.buildF2*Columns）加了 flat，
# 模板 JSON 的 columns 没加 → **seed 路径**（新建项目 / 重新生成附注）仍会回退
# `_infer_groups_from_headers` 前缀推断，实测凭空造出：
#   开发产品 → {本期,span2} + {期末,span2}
#   周转房   → {本期,span2}
#   开发成本 → {预计,span2}（把「预计竣工时间」与「预计总投资」凑成一组）
# 故守卫必须直接跑 `_extract_column_groups(模板 columns)`，只测同步载荷会漏。
# ═══════════════════════════════════════════════════════════════════

_INFERENCE_RISK_HINT = (
    "该表 `_extract_column_groups` 返回 None → 渲染时回退前缀推断，"
    "会凭空造出父表头。请在 columns 的标签列标 `flat: True`（单级表头）"
    "或给数据列标 `group`（多级表头）。修复：python backend/scripts/fix/"
    "fix_note_inventory_structure.py"
)


@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_seed_path_never_falls_back_to_prefix_inference(
    request: pytest.FixtureRequest, fixture_name: str,
) -> None:
    """每张表都必须在 flat / group 之间明确表态，禁止落入前缀推断。"""
    from app.services.note_sub_table_projector import _extract_column_groups

    section = request.getfixturevalue(fixture_name)
    offenders: list[str] = []
    for tbl in section.get("tables") or []:
        cols = tbl.get("columns")
        if not cols:
            offenders.append(f"{tbl.get('name')}（无 columns）")
            continue
        if _extract_column_groups(cols) is None:
            offenders.append(str(tbl.get("name")))
    assert not offenders, f"以下表会落入前缀推断：{offenders}。{_INFERENCE_RISK_HINT}"


@pytest.mark.parametrize(
    "fixture_name,table_name",
    [
        ("listed", "开发成本"),
        ("listed", "开发产品"),
        ("listed", "周转房"),
        ("listed", "确认为存货的数据资源"),
        ("listed", "存货跌价准备及合同履约成本减值准备（续）"),
        ("soe", "确认为存货的数据资源"),
    ],
)
def test_single_level_tables_declare_flat(
    request: pytest.FixtureRequest, fixture_name: str, table_name: str,
) -> None:
    """源模版为单行表头的表必须显式 flat（返回 [] 而非 None）。"""
    from app.services.note_sub_table_projector import _extract_column_groups

    tbl = _get(request.getfixturevalue(fixture_name), table_name)
    cols = tbl.get("columns") or []
    assert any(c.get("flat") for c in cols), f"{table_name} 未标 flat；{_INFERENCE_RISK_HINT}"
    assert _extract_column_groups(cols) == [], f"{table_name} 应为显式单级（[]）"


@pytest.mark.parametrize(
    "fixture_name,table_name,forbidden",
    [
        ("listed", "开发产品", ["本期", "期末"]),
        ("listed", "周转房", ["本期"]),
        ("listed", "开发成本", ["预计"]),
    ],
)
def test_no_phantom_parent_headers_from_inference(
    request: pytest.FixtureRequest, fixture_name: str, table_name: str, forbidden: list[str],
) -> None:
    """反例守卫：这些父表头是前缀推断的产物，源模版里不存在，不得出现。"""
    from app.services.note_sub_table_projector import _extract_column_groups

    tbl = _get(request.getfixturevalue(fixture_name), table_name)
    groups = _extract_column_groups(tbl.get("columns")) or []
    got = {g.get("group") for g in groups if isinstance(g, dict)}
    assert not (got & set(forbidden)), (
        f"{table_name} 出现凭空父表头 {got & set(forbidden)}（源模版为单行表头）"
    )


def test_flat_and_group_are_mutually_exclusive() -> None:
    """同一张表不得同时声明 flat 与 group（语义冲突：单级 vs 多级）。"""
    import json as _json
    from pathlib import Path

    for path, want in (
        ("note_template_listed.json", "五、9"),
        ("note_template_soe.json", "八、10"),
    ):
        doc = _json.loads(
            (Path(__file__).resolve().parents[2] / "data" / path).read_text(encoding="utf-8")
        )
        sec = next(s for s in doc["sections"] if str(s.get("section_number") or "") == want)
        for tbl in sec.get("tables") or []:
            cols = tbl.get("columns") or []
            has_flat = any(c.get("flat") for c in cols if isinstance(c, dict))
            has_group = any(c.get("group") for c in cols if isinstance(c, dict))
            assert not (has_flat and has_group), (
                f"{path} / {tbl.get('name')} 同时声明 flat 与 group"
            )


# ═══════════════════════════════════════════════════════════════════
# Sprint 7：guidance（附注 TAB 编制提示）
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_every_table_has_guidance(request: pytest.FixtureRequest, fixture_name: str) -> None:
    """每张表都要有 TAB 编制提示（K1 已启用的平台范式，存货此前全缺）。"""
    section = request.getfixturevalue(fixture_name)
    missing = [
        str(t.get("name"))
        for t in section.get("tables") or []
        if not str(t.get("guidance") or "").strip()
    ]
    assert not missing, f"缺 guidance：{missing}；{_FIX_HINT}"


@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_guidance_is_substantive(request: pytest.FixtureRequest, fixture_name: str) -> None:
    """提示需有实质内容（过短等于没写，会诱导编制者忽略口径）。"""
    section = request.getfixturevalue(fixture_name)
    too_short = [
        (str(t.get("name")), len(str(t.get("guidance"))))
        for t in section.get("tables") or []
        if len(str(t.get("guidance") or "").strip()) < 30
    ]
    assert not too_short, f"guidance 过短：{too_short}"


def test_portfolio_guidance_states_mutual_exclusion(listed: dict[str, Any]) -> None:
    """(3) 的两组表在附注模版里是「或」的关系（二选一），提示必须说明。

    源：`基础数据/附注模版/上市报表附注.md` 行 2500「续：」/ 2511「或：」——
    第一组按品类组合、第二组按库龄组合（行标签为「1年以内」「1至2年」）。
    底稿侧目前只有按品类组合的录入区块，库龄组合两张表暂无数据来源。
    """
    for name in ("按组合计提存货跌价准备", "按组合计提存货跌价准备（续）"):
        g = str(_get(listed, name).get("guidance") or "")
        assert "或" in g and "二选一" in g, f"{name} 未说明与库龄组合的互斥关系"
    for name in ("按库龄组合计提存货跌价准备", "按库龄组合计提存货跌价准备（续）"):
        g = str(_get(listed, name).get("guidance") or "")
        assert "库龄" in g, f"{name} 提示未点明库龄口径"
        assert "二选一" in g, f"{name} 未说明与按组合计提的互斥关系"


def test_guidance_cites_authoritative_sources(listed: dict[str, Any]) -> None:
    """禁止自造披露要求：提示须可溯源到 15 号文 / 源模版 / 监管文件 / 勾稽口径。"""
    markers = ("15 号文", "15号文", "源模版", "暂行规定", "监管报告", "通知", "勾稽")
    for tbl in listed.get("tables") or []:
        g = str(tbl.get("guidance") or "")
        assert any(m in g for m in markers), (
            f"{tbl.get('name')} 的 guidance 无权威来源标注：{g[:60]}"
        )


# ═══════════════════════════════════════════════════════════════════
# Sprint 7：headers 纯文本 + 与 columns[].label 一致
#
# 附注模版 md 的表格里用 `<br/>` 做表头内换行（「预计总<br/>投资」、
# 「本期转回或转销<br/>存货跌价准备…」），但源 xlsx（D67 / B35 / C35）是纯文本。
# 前端 `el-table-column :label` 与 Word 导出都不解析 HTML → 留着会显示字面量。
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_headers_are_plain_text(request: pytest.FixtureRequest, fixture_name: str) -> None:
    """headers 不得含 HTML 标记（`el-table-column :label` 是纯文本渲染）。"""
    section = request.getfixturevalue(fixture_name)
    offenders: list[str] = []
    for tbl in section.get("tables") or []:
        for h in tbl.get("headers") or []:
            if "<" in str(h) and ">" in str(h):
                offenders.append(f"{tbl.get('name')} → {h!r}")
    assert not offenders, f"headers 含 HTML 标记：{offenders}；{_FIX_HINT}"


@pytest.mark.parametrize(
    "table_name,header_index,expected",
    [
        ("开发成本", 3, "预计总投资"),
        ("存货跌价准备及合同履约成本减值准备（续）", 2,
         "本期转回或转销存货跌价准备/合同履约成本减值准备的原因"),
    ],
)
def test_specific_br_headers_normalized(
    listed: dict[str, Any], table_name: str, header_index: int, expected: str,
) -> None:
    """定点回归：这两处曾带 `<br/>`。"""
    headers = _get(listed, table_name).get("headers") or []
    assert headers[header_index] == expected


@pytest.mark.parametrize("fixture_name", ["listed", "soe"])
def test_headers_match_column_labels(
    request: pytest.FixtureRequest, fixture_name: str,
) -> None:
    """headers 与 columns[].label 逐位一致，避免表头与列定义两套说法。"""
    section = request.getfixturevalue(fixture_name)
    mismatches: list[str] = []
    for tbl in section.get("tables") or []:
        headers = tbl.get("headers") or []
        cols = tbl.get("columns") or []
        if len(cols) != len(headers):
            continue
        for k, (h, c) in enumerate(zip(headers, cols)):
            if isinstance(c, dict) and str(c.get("label") or "") != str(h):
                mismatches.append(f"{tbl.get('name')}[{k}] {h!r} ≠ {c.get('label')!r}")
    assert not mismatches, f"表头与列定义不一致：{mismatches}"
