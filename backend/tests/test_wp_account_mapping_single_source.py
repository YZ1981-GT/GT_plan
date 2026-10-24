r"""底稿科目映射表 ``wp_account_mapping.json`` 与四表口径单一来源一致。

推送取数早已改走单一来源（``four_table/*_cycle_specs``、``j_cycle_account_scope``、``k_cycle_specs``，均已真库对账），
这张表错了不会在推送里暴露，只会让其余读取方静默取错（全链路生成底稿、调整到达通知、一致性检查、质控、报表过期标记、
地址库、行名对齐、附注模板绑定生成）。本守卫把它钉在单一来源上；期望值来自单一来源 / 平台标准科目表 / 真库，不从映射表本身派生。

判据：
1. 码形态 ``^\d{4}(-\d{2})?$``；
2. 码存在：平台标准科目表 ∪ 单一来源声明 ∪ 双族码 ∪ 登记的偏差码；连库时真库 ``account_chart`` 至少一个项目有该码；
3. 有单一来源声明的族：映射码 ⊆ 声明 ∪ 双族码，超出的逐码登记原因（``KNOWN_DEVIATIONS``，只许减少，失效即红）；
   声明为空（宁缺勿造）⇒ 映射为空；声明的原值码必须出现在映射里；
4. 没有单一来源声明却列了科目的只许是函证族（X0），其码 ⊆ 同循环各族的声明，跨循环的逐码登记；
5. 条目名里出现的平台标准科目名（一级科目），其码必须在条目码里（例外逐条登记）；
6. 修正脚本登记的各批修正全部生效（改回旧值或改成链外的值都打红）。

spec: .kiro/specs/formula-fetch-followup-defect-closure/ R1.6
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

from app.services.four_table.declared_codes import declared_codes, declared_gross_codes
from app.services.four_table.dual_family_codes import ALL_DUAL_FAMILY_CODES

_BACKEND = Path(__file__).resolve().parents[1]
_MAPPING_PATH = _BACKEND / "data" / "wp_account_mapping.json"
_STD_CHART_PATH = _BACKEND / "data" / "standard_account_chart.json"
_FIX_SCRIPT = _BACKEND / "scripts" / "fix" / "fix_wp_account_mapping_wrong_codes.py"

_CODE_RE = re.compile(r"^\d{4}(-\d{2})?$")
_FAMILY_RE = re.compile(r"^([A-Z]\d+)")
_CONFIRMATION_RE = re.compile(r"^[A-Z]0$")

#: 存货族（区间口径 BS-010 = SUM_TB('1401~1499')，按名归类见 `f2_extraction.category_rules`）：两套标准科目表变体里都是存货的码
_F2_RANGE = (
    "1402", "1403", "1404", "1405", "1406", "1407", "1408", "1409", "1411",
    "1416", "1421", "1431", "1441", "1451", "1452", "1461", "1471", "1472",
)

#: 映射码超出单一来源声明、但有理由的（族 → 码 → 原因）。只许减少；登记了却不再出现即打红。
KNOWN_DEVIATIONS: dict[str, dict[str, str]] = {
    "D4": {"6051": "营业收入 = 主营业务收入 + 其他业务收入；单一来源 D4 只给主科目兜底码 6001（报表按名取数）"},
    "F5": {"6402": "营业成本 = 主营业务成本 + 其他业务成本；单一来源 F5 只给主科目兜底码 6401"},
    "I6": {"1704": "I6-3「研发费用资本化 / 费用化分类」同时看开发支出"},
    "F2": {code: "存货按区间取数、按名归类，单一来源只给首码兜底 1401" for code in _F2_RANGE},
}

#: 函证族跨循环的科目（族 → 码 → (声明该码的族, 原因)）
CONFIRMATION_CROSS_CYCLE: dict[str, dict[str, tuple[str, str]]] = {
    "E0": {
        "2001": ("L1", "银行询证函同时函证借款（E0-4 借款发函记录表）"),
        "2501": ("L3", "银行询证函同时函证借款（E0-4 借款发函记录表）"),
        "2201": ("F3", "银行询证函同时函证承兑汇票（E0-5 应付银行承兑汇票发函记录表）"),
    },
}

#: 条目名与科目名规则的例外：按循环（整循环）或按条目
NAME_RULE_EXEMPT_CYCLES: dict[str, str] = {
    "M": "平台标准科目表（standard_account_chart.json）把权益类编在 3xxx，客户科目表与 2006 国标在 4xxx；"
         "M 循环以 M_CYCLE_SPECS（已真库对账）为准",
}
NAME_RULE_EXEMPT_ENTRIES: dict[str, str] = {
    "L8-5": "汇兑损益是财务费用的明细项（平台标准科目表 6201 汇兑损益是金融企业科目）",
    "I2-4": "开发支出转入无形资产：本表取的是开发支出 1704",
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


_MAPPINGS: list[dict] = _load(_MAPPING_PATH)["mappings"]
_STD_ACCOUNTS: list[dict] = _load(_STD_CHART_PATH)["accounts"]
_STD_CODES = {str(a["code"]) for a in _STD_ACCOUNTS}


def _families(mappings: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for e in mappings:
        m = _FAMILY_RE.match(str(e.get("wp_code") or ""))
        if m:
            out[m.group(1)].append(e)
    return dict(out)


def _family_codes(entries: list[dict]) -> set[str]:
    return {c for e in entries for c in (e.get("account_codes") or [])}


def _all_codes(mappings: list[dict]) -> set[str]:
    return {c for e in mappings for c in (e.get("account_codes") or [])}


def family_violations(mappings: list[dict]) -> list[str]:
    """判据 3 / 4：族级映射码对单一来源。返回违规描述（空 = 通过）。"""
    out: list[str] = []
    fams = _families(mappings)
    cycle_declared: dict[str, set[str]] = defaultdict(set)
    for fam in fams:
        cycle_declared[fam[0]] |= set(declared_codes(fam) or ())
    for fam, entries in sorted(fams.items()):
        codes = _family_codes(entries)
        declared = declared_codes(fam)
        if declared is None:
            if not codes:
                continue
            if not _CONFIRMATION_RE.match(fam):
                out.append(f"{fam}: 列了科目 {sorted(codes)} 但单一来源没有声明 —— 先在 four_table 规格里声明")
                continue
            cross = CONFIRMATION_CROSS_CYCLE.get(fam, {})
            for code in sorted(codes - cycle_declared[fam[0]] - set(ALL_DUAL_FAMILY_CODES) - set(cross)):
                out.append(f"{fam}: 函证码 {code} 不属于 {fam[0]} 循环任何一族的声明")
            continue
        if not declared:
            if codes:
                out.append(f"{fam}: 单一来源声明为空（没有标准科目），映射却列了 {sorted(codes)}")
            continue
        allowed = set(declared) | set(ALL_DUAL_FAMILY_CODES) | set(KNOWN_DEVIATIONS.get(fam, {}))
        for code in sorted(codes - allowed):
            out.append(f"{fam}: 映射码 {code} 不在单一来源声明 {list(declared)} 里")
        for code in declared_gross_codes(fam) or ():
            if code not in codes:
                out.append(f"{fam}: 单一来源的原值码 {code} 没进映射")
    return out


def _chart_name_index() -> list[tuple[str, set[str]]]:
    """平台标准科目表一级科目（4 位码）名 → 码，按名长降序（长名先匹配，免得「其他综合收益」被拆）。"""
    idx: dict[str, set[str]] = defaultdict(set)
    for a in _STD_ACCOUNTS:
        code = str(a["code"])
        if re.fullmatch(r"\d{4}", code):
            idx[a["name"]].add(code)
    return sorted(idx.items(), key=lambda kv: len(kv[0]), reverse=True)


def name_code_hits(entry: dict, index: list[tuple[str, set[str]]]) -> tuple[list[str], set[str]]:
    text = f'{entry.get("account_name") or ""}|{entry.get("wp_name") or ""}'
    names: list[str] = []
    codes: set[str] = set()
    for name, name_codes in index:
        if name in text:
            names.append(name)
            codes |= name_codes
            text = text.replace(name, "#" * len(name))
    return names, codes


def name_code_violations(mappings: list[dict], *, with_exemptions: bool = True) -> list[str]:
    """判据 5：条目名里出现的科目名，其码必须在条目码里。"""
    index = _chart_name_index()
    out: list[str] = []
    for e in mappings:
        codes = set(e.get("account_codes") or [])
        if not codes:
            continue
        wp = str(e.get("wp_code") or "")
        if with_exemptions and (wp in NAME_RULE_EXEMPT_ENTRIES or wp[:1] in NAME_RULE_EXEMPT_CYCLES):
            continue
        names, name_codes = name_code_hits(e, index)
        if names and not (name_codes & codes):
            out.append(f"{wp}「{e.get('wp_name')}」名含 {names}（{sorted(name_codes)}），条目码却是 {sorted(codes)}")
    return out


# ─── 1 / 2 码形态与存在 ───────────────────────────────────────────────


def test_code_shape():
    bad = sorted(c for c in _all_codes(_MAPPINGS) if not _CODE_RE.match(c))
    assert bad == []


def test_codes_exist_statically():
    known = set(_STD_CODES) | set(ALL_DUAL_FAMILY_CODES)
    for fam in _families(_MAPPINGS):
        known |= set(declared_codes(fam) or ())
        known |= set(KNOWN_DEVIATIONS.get(fam, {}))
    assert sorted(_all_codes(_MAPPINGS) - known) == []


def _pg_codes(codes: list[str]) -> set[str] | None:
    try:
        import psycopg2
    except ImportError:
        return None
    try:
        conn = psycopg2.connect(dbname="audit_platform", user="postgres", password="postgres",
                                host="localhost", port=5432, connect_timeout=3)
    except Exception:  # noqa: BLE001 — 没有库就跳过
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT account_code FROM account_chart WHERE is_deleted = false AND account_code = ANY(%s)",
                (codes,),
            )
            return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


def test_codes_exist_in_real_account_chart():
    codes = sorted(_all_codes(_MAPPINGS))
    found = _pg_codes(codes)
    if found is None:
        pytest.skip("本地 PostgreSQL 不可用")
    assert [c for c in codes if c not in found] == []


# ─── 3 / 4 族级对单一来源 ─────────────────────────────────────────────


def test_mapping_follows_single_source():
    assert family_violations(_MAPPINGS) == []


def test_known_deviations_are_live():
    fams = _families(_MAPPINGS)
    stale = []
    for fam, codes in KNOWN_DEVIATIONS.items():
        declared = set(declared_codes(fam) or ())
        present = _family_codes(fams.get(fam, []))
        stale += [f"{fam} {c}" for c in codes if c not in present or c in declared]
    assert stale == [], "登记项已失效（映射里不再有，或单一来源已声明）：删掉这些条目"


def test_confirmation_cross_cycle_codes_are_live_and_declared_by_named_family():
    fams = _families(_MAPPINGS)
    problems = []
    for fam, codes in CONFIRMATION_CROSS_CYCLE.items():
        present = _family_codes(fams.get(fam, []))
        for code, (owner, _why) in codes.items():
            if code not in present:
                problems.append(f"{fam} {code} 已不在映射里")
            if code not in (declared_codes(owner) or ()):
                problems.append(f"{fam} {code} 登记的归属族 {owner} 并未声明该码")
    assert problems == []


@pytest.mark.parametrize("fam", ["D5", "I5", "K4", "L7", "M8"])
def test_no_standard_account_means_empty_mapping(fam):
    assert declared_codes(fam) == ()
    assert _family_codes(_families(_MAPPINGS)[fam]) == set()


# ─── 5 条目名对科目名 ─────────────────────────────────────────────────


def test_entry_names_match_codes():
    assert name_code_violations(_MAPPINGS) == []


def test_name_rule_exemptions_are_live():
    raw = name_code_violations(_MAPPINGS, with_exemptions=False)
    stale = [wp for wp in NAME_RULE_EXEMPT_ENTRIES if not any(v.startswith(f"{wp}「") for v in raw)]
    stale += [cyc for cyc in NAME_RULE_EXEMPT_CYCLES if not any(v.startswith(cyc) for v in raw)]
    assert stale == [], "例外已不再需要：删掉这些登记"


# ─── 6 修正脚本 ───────────────────────────────────────────────────────


def _fix_module():
    spec = importlib.util.spec_from_file_location("_fix_wp_account_mapping_wrong_codes", _FIX_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_all_registered_fixes_are_applied():
    mod = _fix_module()
    todo, done, bad = mod.plan(_load(_MAPPING_PATH))
    assert (todo, bad) == ([], [])
    assert done


def test_fix_chain_reports_reverted_and_foreign_values():
    mod = _fix_module()
    doc = _load(_MAPPING_PATH)
    by_wp = {e["wp_code"]: e for e in doc["mappings"]}
    by_wp["F2-55"]["account_codes"] = ["1411", "1412"]  # 第二批之前的原值：链上 ⇒ 待改
    by_wp["G8"]["account_codes"] = ["9999"]  # 链外的值 ⇒ 拒绝覆盖
    todo, _done, bad = mod.plan(doc)
    assert any(t.startswith("F2-55.account_codes") and "'1472'" in t for t in todo)
    assert any(b.startswith("G8.account_codes") for b in bad)


def test_fix_chain_rejects_unlinked_batches(monkeypatch):
    mod = _fix_module()
    monkeypatch.setattr(mod, "FIXES", [("X1", "account_codes", ["1"], ["2"], "a"), ("X1", "account_codes", ["3"], ["4"], "b")])
    with pytest.raises(ValueError, match="修正链断开"):
        mod._chains()


# ─── 派生物 ───────────────────────────────────────────────────────────


def _gen_module():
    path = _BACKEND / "scripts" / "gen" / "gen_account_to_wp_ts.py"
    spec = importlib.util.spec_from_file_location("_gen_account_to_wp_ts", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_frontend_account_to_wp_table_is_generated_from_mapping():
    """前端挂凭推荐表 = 生成器按当前映射表的输出（手改或映射表改了没重生成都打红）。"""
    mod = _gen_module()
    on_disk = mod.OUTPUT_PATH.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert on_disk == mod.render(_MAPPINGS), "运行 python backend/scripts/gen/gen_account_to_wp_ts.py --write"


def test_frontend_account_to_wp_table_rows():
    """生成规则：D~N 主条目（非函证、有科目）一码一行 —— 字面量抽样，不从生成器派生。"""
    rows = re.findall(r"\{ prefix: '([^']+)', wpCode: '([^']+)'", _gen_module().render(_MAPPINGS))
    assert ("1506", "G6") in rows and ("1507", "G8") in rows and ("1901", "K2") in rows
    assert ("2705", "J2") in rows and ("4201", "M3") in rows and ("4401", "M10") in rows
    assert {("1641", "H8"), ("1651", "H8"), ("2601", "H9"), ("2651", "H9")} <= set(rows)
    forbidden = {("1503", "G6"), ("1701", "K2"), ("1901", "H8"), ("2611", "J2"), ("1124", "D5"), ("2261", "K4"),
                 ("4103", "M5"), ("1606B", "H6")}
    assert forbidden.isdisjoint(rows)
    assert not [wp for _code, wp in rows if wp.endswith("0") and len(wp) == 2], "函证底稿不进挂凭推荐"
    assert {wp for _c, wp in rows}.isdisjoint({"D5", "I5", "K4", "L7", "M8", "J3"}), "没有标准科目的底稿不列"


# ─── 自检：判据对植入的错码打红（证明上面不是恒绿） ─────────────────────


def _planted(changes: dict[str, list[str]]) -> list[dict]:
    """改一份副本：键是底稿编码；以 ``*`` 结尾表示整族（如 ``J2*``）。"""
    mappings = copy.deepcopy(_MAPPINGS)
    for e in mappings:
        wp = e["wp_code"]
        m = _FAMILY_RE.match(wp)
        for key, codes in changes.items():
            if wp == key or (key.endswith("*") and m and m.group(1) == key[:-1]):
                e["account_codes"] = codes
    return mappings


@pytest.mark.parametrize(
    ("changes", "expect"),
    [
        ({"G8": ["1503"]}, "G8: 映射码 1503"),  # 旧准则可供出售金融资产
        ({"K2-1": ["1701"]}, "K2: 映射码 1701"),  # 无形资产
        ({"M5": ["4103"]}, "M5: 映射码 4103"),  # 本年利润
        ({"D5": ["1124"]}, "D5: 单一来源声明为空"),
        ({"J2*": []}, "J2: 单一来源的原值码 2705 没进映射"),
        ({"E0-4": ["1122"]}, "E0: 函证码 1122"),
        ({"A1": ["1001"]}, "A1: 列了科目"),
    ],
)
def test_family_rule_catches_planted_codes(changes, expect):
    found = family_violations(_planted(changes))
    assert any(v.startswith(expect) for v in found), found


@pytest.mark.parametrize(
    ("changes", "expect"),
    [
        ({"F2-6": ["1403"]}, "F2-6「库存商品明细」"),
        ({"F2-4": ["1401"]}, "F2-4「原材料明细」"),
        ({"E0-5": ["1002"]}, "E0-5「应付银行承兑汇票发函记录表」"),
        ({"H1-3": ["1603"]}, "H1-3「固定资产折旧测算」"),
    ],
)
def test_name_rule_catches_planted_codes(changes, expect):
    found = name_code_violations(_planted(changes))
    assert any(v.startswith(expect) for v in found), found
