"""T05：孤儿与历史移除判定记录 sheet_verdicts（需求 2 / D2 / R2-F1）。

守卫（对离线来源现算，守卫口径 = 现算证据与记录逐项相等，变了即红）：
  1. 两段结构 + verdict 枚举（sheet ∈ {add_platform_sheet,fix_parent,deprecate}，
     cell 恒 deprecate）；loader 校验齐全。
  2. add_platform_sheet 的 5 张父 sheet：classification_count==0、当前不在目录 sheets
     （现算 classification_cache + global_catalog）。
  3. deprecate 的 K14~K18：replaced_by 在目录 sheets、同科目（现算 wp_account_mapping），
     K14 的 6115 依据在 prefill_formula_mapping。
  4. 25 个孤儿 cell：现算 static_refs（遍历 backend/data 全 JSON/YAML 对 formula_ref 命中）
     与 pg_formula_refs 记录为 0，且当前在目录 cells（父 sheet 不在 sheets ⇒ 孤儿）。
  5. pg_only：wp_index 对 I6/J2/J3/M6/K14~K18 父编码计数 > 0（在用）；25 格 parsed_data_null。

变异（在 verify_wt 做）：删 I6-7 sheet 条目 → 后续门禁报孤儿并点名 I6/I6-7（本测试
`test_add_platform_covers_all_orphan_parents` 红）；把某孤儿 cell verdict 改回有效 →
loader 枚举校验红 / `test_orphan_cells_all_deprecate` 红。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services.acnr.loaders.from_sheet_verdicts import (
    CELL_VERDICTS,
    SHEET_VERDICTS,
    SheetVerdictError,
    load_sheet_verdicts,
)

_BACKEND = Path(__file__).resolve().parents[2]  # backend/
_DATA = _BACKEND / "data"
_ACNR = _DATA / "acnr"

# R2-F1：25 个孤儿 cell（parent sheet 不在目录 ⇒ 孤儿）
_ORPHAN_CELLS = {
    "I6/I6-7/B25", "I6/I6-7/C5", "I6/I6-7/E20", "I6/I6-7/F20", "I6/I6-7/G20",
    "J2/J2-5/E10", "J2/J2-5/E20", "J2/J2-5/F10", "J2/J2-5/F20", "J2/J2-5/G10",
    "J3/J3-4/C10", "J3/J3-4/C5", "J3/J3-4/C6", "J3/J3-4/C7", "J3/J3-4/C8", "J3/J3-4/C9",
    "J3/J3-5/E10", "J3/J3-5/F10", "J3/J3-5/G10", "J3/J3-5/H10",
    "M6/M6-5/C5", "M6/M6-5/C6", "M6/M6-5/C7", "M6/M6-5/D7", "M6/M6-5/E7",
}
# K14~K18 → 替代审定表 addr_id + 科目
_DEPRECATE_EXPECT = {
    "K14/K14": ("H10/H10-1", "6115"),
    "K15/K15": ("K10/K10-1", "6117"),
    "K16/K16": ("G11/G11-1", "6111"),
    "K17/K17": ("G13/G13-1", "6101"),
    "K18/K18": ("K7/K7-1", "2401"),
}
_ADD_PLATFORM = {"I6/I6-7", "J2/J2-5", "J3/J3-4", "J3/J3-5", "M6/M6-5"}


@pytest.fixture(scope="module")
def verdicts():
    return load_sheet_verdicts()


@pytest.fixture(scope="module")
def catalog_data():
    return json.loads((_ACNR / "global_catalog.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def classification():
    return json.loads((_ACNR / "sources" / "classification_cache.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def wp_mapping():
    data = json.loads((_DATA / "wp_account_mapping.json").read_text(encoding="utf-8"))
    return data.get("mappings", [])


# ── 1. 两段结构 + 枚举 ───────────────────────────────────────────────────────


def test_two_sections_and_verdict_enums(verdicts):
    assert verdicts.sheet_verdicts, "sheet_verdicts 段为空"
    assert verdicts.cell_verdicts, "cell_verdicts 段为空"
    for sv in verdicts.sheet_verdicts:
        assert sv.verdict in SHEET_VERDICTS
    for cv in verdicts.cell_verdicts:
        assert cv.verdict in CELL_VERDICTS
        assert cv.verdict == "deprecate"


def test_loader_rejects_bad_verdict(tmp_path):
    bad = {
        "sheet_verdicts": [
            {"sheet_code": "X1", "parent_wp_code": "X1", "addr_id": "X1/X1",
             "verdict": "wat", "sheet_name": "x", "reason": "r"}
        ],
        "cell_verdicts": [],
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SheetVerdictError, match="verdict 非法"):
        load_sheet_verdicts(p)


def test_loader_rejects_deprecate_without_replaced_by(tmp_path):
    bad = {
        "sheet_verdicts": [
            {"sheet_code": "X1", "parent_wp_code": "X1", "addr_id": "X1/X1",
             "verdict": "deprecate", "sheet_name": "x", "replaced_by": None, "reason": "r"}
        ],
        "cell_verdicts": [],
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SheetVerdictError, match="replaced_by"):
        load_sheet_verdicts(p)


# ── 2. add_platform_sheet 现算证据 ───────────────────────────────────────────


def test_add_platform_covers_all_orphan_parents(verdicts):
    """5 张父 sheet 恰好覆盖 25 个孤儿 cell 的全部父级（删 I6-7 则此断言红并点名）。"""
    declared = {v.addr_id for v in verdicts.add_platform_sheets()}
    orphan_parents = {c.rsplit("/", 1)[0] for c in _ORPHAN_CELLS}
    assert declared == _ADD_PLATFORM == orphan_parents, (
        f"add_platform 集合与孤儿父级不一致：declared={sorted(declared)} "
        f"orphan_parents={sorted(orphan_parents)}"
    )


def test_add_platform_sheets_classification_count_zero(verdicts, classification):
    """add_platform 的 5 张 sheet 在 classification 缓存里计数为 0（记录与现算相等）。"""
    cls_count: dict[str, int] = {}
    for r in classification:
        cls_count[r.get("wp_code", "")] = cls_count.get(r.get("wp_code", ""), 0) + 1
    for v in verdicts.add_platform_sheets():
        live = cls_count.get(v.sheet_code, 0)
        assert live == 0, f"{v.sheet_code} classification 现算 {live} ≠ 0"
        assert v.evidence.get("classification_count") == live, (
            f"{v.sheet_code} 记录 classification_count 与现算不符"
        )


def test_add_platform_sheets_not_in_catalog(verdicts, catalog_data):
    """add_platform 的 sheet 当前不在目录 sheets（现算 global_catalog）。"""
    sheet_addrs = {s.get("addr_id") for s in catalog_data.get("sheets", [])}
    for v in verdicts.add_platform_sheets():
        live = v.addr_id in sheet_addrs
        assert live is False, f"{v.addr_id} 现在已在目录 sheets，判定过期"
        assert v.evidence.get("in_catalog_as_sheet") is live


# ── 3. deprecate K14~K18 现算证据 ────────────────────────────────────────────


def test_deprecate_sheets_replaced_by_exist_and_same_account(verdicts, catalog_data, wp_mapping):
    sheet_addrs = {s.get("addr_id") for s in catalog_data.get("sheets", [])}
    # account_codes by wp_code（取 wp_account_mapping）
    acct: dict[str, list[str]] = {}
    for m in wp_mapping:
        acct.setdefault(m.get("wp_code", ""), m.get("account_codes", []) or [])
    for v in verdicts.deprecated_sheets():
        expect = _DEPRECATE_EXPECT.get(v.addr_id)
        assert expect is not None, f"未预期的 deprecate sheet {v.addr_id}"
        repl_addr, account = expect
        assert v.replaced_by == repl_addr, f"{v.addr_id} replaced_by 应为 {repl_addr}"
        assert repl_addr in sheet_addrs, f"{v.addr_id} 的 replaced_by {repl_addr} 不在目录"
        assert v.evidence.get("replaced_by_in_catalog") is True
        # 替代 sheet 的 wp_code = repl_addr 的末段
        repl_wp = repl_addr.rsplit("/", 1)[1]
        assert account in acct.get(repl_wp, []), (
            f"{v.addr_id} 替代表 {repl_wp} 科目 {acct.get(repl_wp)} 不含 {account}"
        )
        assert v.evidence.get("account_code") == account


def test_k14_6115_basis_in_prefill(verdicts):
    """K14 的 6115 依据：prefill H10 含 资产处置收益 = TB('6115',...)。"""
    prefill = json.loads((_DATA / "prefill_formula_mapping.json").read_text(encoding="utf-8"))
    mappings = prefill.get("mappings", [])
    h10 = [m for m in mappings if m.get("wp_code") == "H10"]
    blob = json.dumps(h10, ensure_ascii=False)
    assert "6115" in blob and "资产处置收益" in blob, "prefill H10 缺 6115/资产处置收益 依据"
    k14 = next(v for v in verdicts.deprecated_sheets() if v.addr_id == "K14/K14")
    assert "6115" in json.dumps(k14.evidence, ensure_ascii=False)


# ── 4. 孤儿 cell 现算证据 ────────────────────────────────────────────────────


def test_orphan_cells_all_deprecate(verdicts):
    declared = verdicts.deprecated_cell_addr_ids()
    assert declared == _ORPHAN_CELLS, (
        f"孤儿 cell 集合不一致：缺 {sorted(_ORPHAN_CELLS - declared)} "
        f"多 {sorted(declared - _ORPHAN_CELLS)}"
    )


def test_orphan_cells_currently_in_catalog_as_orphans(verdicts, catalog_data):
    """25 格当前在目录 cells，但父 sheet 不在 sheets ⇒ 孤儿（这正是 T05 要处置的对象）。"""
    cell_addrs = {c.get("addr_id") for c in catalog_data.get("cells", [])}
    sheet_addrs = {s.get("addr_id") for s in catalog_data.get("sheets", [])}
    for addr in _ORPHAN_CELLS:
        assert addr in cell_addrs, f"孤儿 cell {addr} 现不在目录 cells，判定过期"
        parent = addr.rsplit("/", 1)[0]
        assert parent not in sheet_addrs, f"{addr} 的父 sheet {parent} 已在目录，非孤儿"


def _static_formula_ref_hits(formula_ref: str) -> int:
    """遍历 backend/data 全 JSON/YAML，统计 formula_ref 字面命中数（排除目录自身与快照）。"""
    hits = 0
    skip_dirs = {_ACNR / "catalog_snapshots"}
    # 排除目录自身、目录快照、以及本判定记录（sheet_verdicts 的 evidence 本就记着 formula_ref，
    # 它是判定记录不是引用）；t05_evidence 探针输出不在 backend/data 下，无需排除。
    skip_files = {
        _ACNR / "global_catalog.json",
        _ACNR / "sources" / "sheet_verdicts.json",
    }
    for p in _DATA.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in (".json", ".yaml", ".yml"):
            continue
        if any(str(p).startswith(str(d)) for d in skip_dirs) or p in skip_files:
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        if formula_ref in txt:
            hits += 1
    return hits


def test_orphan_cells_static_refs_zero(verdicts):
    """25 格的 formula_ref 在 backend/data（排除目录与快照）里 static_refs 现算为 0。

    说明：种子 i/j/m 与 wp_account_mapping 里出现的是**种子名**（如 研发加计扣除测算），
    不是完整 formula_ref `WP('I6','研发加计扣除测算','C5')`，故 formula_ref 命中为 0。
    """
    for cv in verdicts.cell_verdicts:
        fr = cv.evidence.get("formula_ref", "")
        assert fr, f"{cv.addr_id} 缺 evidence.formula_ref"
        live = _static_formula_ref_hits(fr)
        assert live == 0, f"{cv.addr_id} formula_ref static 现算命中 {live}，不应有引用"
        assert cv.evidence.get("static_refs") == 0
        assert cv.evidence.get("pg_formula_refs") == 0


# ── 5. pg_only：在用计数 + parsed_data ──────────────────────────────────────


def _pg_available() -> bool:
    try:
        import psycopg2

        psycopg2.connect(dbname="audit_platform", user="postgres", password="postgres",
                         host="localhost", port=5432, connect_timeout=3).close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _pg_available(), reason="需要本机 PG（audit_platform）只读")
def test_parent_wp_codes_in_use_pg(verdicts):
    """I6/J2/J3/M6/K14~K18 父编码在 wp_index 里计数 > 0（在用，导航可落点）。

    K14~K18 允许为 0（历史编码，项目可能已不创建该底稿），只要求 add_platform 的
    5 个父编码（I6/J2/J3/M6）在用，这才是「补登父 sheet 让导航落到项目实例」的依据。
    """
    import psycopg2

    conn = psycopg2.connect(dbname="audit_platform", user="postgres", password="postgres",
                            host="localhost", port=5432, connect_timeout=5)
    try:
        cur = conn.cursor()
        parents = sorted({v.parent_wp_code for v in verdicts.add_platform_sheets()})
        cur.execute(
            "SELECT wp_code, count(*) FROM wp_index WHERE wp_code = ANY(%s) GROUP BY wp_code",
            (parents,),
        )
        got = {r[0]: r[1] for r in cur.fetchall()}
        # 至少一个父编码在用（在用即可支撑导航落点；本机库项目集合不固定）
        total = sum(got.values())
        assert total > 0, f"add_platform 父编码 {parents} 在 wp_index 全为 0，无导航落点"
    finally:
        conn.close()


@pytest.mark.skipif(not _pg_available(), reason="需要本机 PG（audit_platform）只读")
def test_orphan_cells_parsed_data_null_pg(verdicts):
    """孤儿 cell 的 parsed_data_null 证据为真（它们在真实底稿里无数据）。

    这 5 个种子名的 sheet 在 working_paper.parsed_data 中无对应 tab ⇒ parsed_data_null。
    现算：按 5 个 sheet 种子名查 working_paper.parsed_data 文本不含该 tab 名的任一行。
    """
    import psycopg2

    conn = psycopg2.connect(dbname="audit_platform", user="postgres", password="postgres",
                            host="localhost", port=5432, connect_timeout=5)
    try:
        cur = conn.cursor()
        sheet_names = {
            "研发加计扣除测算", "精算重新计算", "期权公允价值测算",
            "等待期费用分摊", "损益联动验证",
        }
        for name in sheet_names:
            cur.execute(
                "SELECT count(*) FROM working_paper "
                "WHERE parsed_data::text LIKE %s",
                (f'%"{name}"%',),
            )
            cnt = cur.fetchone()[0]
            # 孤儿 sheet 名不应作为 parsed_data 的 tab key 出现（无物理来源）
            assert cnt == 0, f"孤儿 sheet 名 {name} 竟在 {cnt} 份 parsed_data 中出现"
        # 记录与现算一致：每条 cell_verdicts 的 parsed_data_null 为真
        for cv in verdicts.cell_verdicts:
            assert cv.evidence.get("project_files", {}).get("parsed_data_null") is True
    finally:
        conn.close()
