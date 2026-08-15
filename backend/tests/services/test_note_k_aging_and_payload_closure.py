"""K 循环账龄枚举与载荷元数据收口（Requirement 10.x / 12.x / Task 19）。

判据真源：
- 账龄字面 → 前端 `composables/disclosureAgingLabels.ts`（平台唯一真源）
- 章节号 / owner → `backend/data/note_workpaper_sync_registry.json`
- 表名 → `note_template_{listed,soe}.json` 的 `tables[].name`

**逐条实测后对 tasks.md 的两处更正**（写在对应用例的 docstring 里）：
1. 「K1/K3 账龄行集都由 `disclosureAgingLabels` 驱动」—— K3 **没有账龄枚举表**。
   它两版的「账龄超过1年的重要其他应付款」是**逐项列示表**（行 = 债权单位，
   表内既无账龄行也无账龄列），正是 AC 10.5 要求保持独立的那张。故 10.1 只落在 K1。
2. 「账龄作列的表共 4 处」—— 实测 **5 处**（K1 listed 3 张 + soe 2 张）。

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 10.1~10.6, 12.1~12.4, 12.6~12.8
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_DATA = _ROOT / "backend/data"
_FE = _ROOT / "audit-platform/frontend/src/components/workpaper/composables"
_AGING_TS = _FE / "disclosureAgingLabels.ts"


@pytest.fixture(scope="module")
def templates() -> dict[str, dict]:
    return {
        v: json.loads((_DATA / f"note_template_{v}.json").read_text(encoding="utf-8"))
        for v in ("listed", "soe")
    }


@pytest.fixture(scope="module")
def k_sections() -> dict[str, dict[str, str]]:
    doc = json.loads((_DATA / "note_workpaper_sync_registry.json").read_text(encoding="utf-8"))
    return {
        str(e["wp_code"]).upper(): {
            "listed": str(e.get("listed") or ""),
            "soe": str(e.get("soe") or ""),
        }
        for e in doc.get("entries") or []
        if str(e.get("wp_code") or "").upper().startswith("K")
    }


def _section(templates: dict, variant: str, number: str) -> dict | None:
    for sec in templates[variant].get("sections") or []:
        if isinstance(sec, dict) and str(sec.get("section_number") or "").strip() == number:
            return sec
    return None


def _tables(templates: dict, variant: str, number: str) -> list[dict]:
    sec = _section(templates, variant, number)
    return [t for t in ((sec or {}).get("tables") or []) if isinstance(t, dict)]


def _fe(name: str) -> str:
    path = _FE / name
    assert path.exists(), f"前端文件缺失：{name}"
    return path.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 10.1 / 10.2：账龄字面单一真源
# ─────────────────────────────────────────────────────────────────────────────


def test_aging_single_source_exists_and_declares_soe_first_bucket() -> None:
    """账龄真源模块存在，且 soe 首档字面就在里面（10.2）。"""
    src = _fe("disclosureAgingLabels.ts")
    assert "export const DISCLOSURE_AGING_WITHIN1_SOE" in src
    m = re.search(r"DISCLOSURE_AGING_WITHIN1_SOE\s*=\s*'([^']+)'", src)
    assert m, "取不到 soe 首档字面（真源写法变了？）"
    assert m.group(1) == "1年以内（含1年）", f"soe 首档字面变了：{m.group(1)!r}"


def test_k1_aging_rows_are_driven_by_single_source() -> None:
    """10.1：K1 的账龄行集必须来自共享真源，不得自己写一份枚举。

    K3 不在此列 —— 它没有账龄枚举表（见模块 docstring 的更正 1）。
    """
    src = _fe("k1DisclosureModel.ts")
    assert "from './disclosureAgingLabels'" in src, (
        "K1 未接账龄共享真源 ⇒ 两版首档字面会分叉（listed `1年以内` / soe `1年以内（含1年）`）"
    )
    assert "buildDisclosureAgingLabelMap" in src


def test_soe_aging_table_uses_soe_first_bucket(templates, k_sections) -> None:
    """10.2 落地面：soe 账龄表首行字面 == `DISCLOSURE_AGING_WITHIN1_SOE`。"""
    m = re.search(
        r"DISCLOSURE_AGING_WITHIN1_SOE\s*=\s*'([^']+)'", _fe("disclosureAgingLabels.ts")
    )
    assert m
    want = m.group(1)
    checked = 0
    for t in _tables(templates, "soe", k_sections["K1"]["soe"]):
        rows = [str(r.get("label") or "") for r in (t.get("rows") or []) if isinstance(r, dict)]
        if not rows or not any("1年以内" in x for x in rows):
            continue
        checked += 1
        assert rows[0] == want, (
            f"soe 账龄表 {t.get('name')!r} 首行 {rows[0]!r} != 真源 {want!r}"
        )
    assert checked >= 2, f"只核到 {checked} 张 soe 账龄表，判据源可疑"


def test_listed_first_bucket_differs_from_soe(templates, k_sections) -> None:
    """反向自检：listed 首档**不带**「（含1年）」—— 两版确实不同，禁统一。"""
    rows_by_table = {
        str(t.get("name")): [
            str(r.get("label") or "") for r in (t.get("rows") or []) if isinstance(r, dict)
        ]
        for t in _tables(templates, "listed", k_sections["K1"]["listed"])
    }
    aging = {n: r for n, r in rows_by_table.items() if r and any("1年以内" in x for x in r)}
    assert aging, "listed 侧找不到账龄表，判据源可疑"
    for name, rows in aging.items():
        assert rows[0] == "1年以内", f"listed 账龄表 {name!r} 首行变成 {rows[0]!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 10.3 / 10.4 / 10.5：账龄作列、月度细分行、K3 独立表
# ─────────────────────────────────────────────────────────────────────────────

#: 账龄作**列维度**的表（10.3）—— 实测 **5 处**（AC 原写 4 处）。
#:
#: 这些表的账龄是「某笔款项的账龄」属性列，不是枚举行；改成行会把逐项列示表
#: 拆成账龄分档表，语义完全变掉。
AGING_AS_COLUMN_TABLES: tuple[tuple[str, str], ...] = (
    ("listed", "重要的账龄超过1年的应收股利"),
    ("listed", "按欠款方归集的其他应收款期末余额前五名单位情况"),
    ("listed", "应收政府补助情况"),
    ("soe", "按欠款方归集的期末余额前五名的其他应收款项"),
    ("soe", "涉及政府补助的应收款项"),
)


def test_aging_stays_as_column_where_registered(templates, k_sections) -> None:
    """10.3：登记的 5 张表必须**仍有账龄列**（不得改成账龄行）。"""
    missing: list[str] = []
    for variant, table_name in AGING_AS_COLUMN_TABLES:
        tbl = next(
            (
                t
                for t in _tables(templates, variant, k_sections["K1"][variant])
                if str(t.get("name") or "") == table_name
            ),
            None,
        )
        if tbl is None:
            missing.append(f"{variant}/{table_name}: 表不见了")
            continue
        labels = [str(c.get("label") or "") for c in (tbl.get("columns") or [])]
        if not any("账龄" in x for x in labels):
            missing.append(f"{variant}/{table_name}: 列头里没有账龄 → 被改成行了？{labels}")
        rows = [str(r.get("label") or "") for r in (tbl.get("rows") or []) if isinstance(r, dict)]
        if any(re.fullmatch(r"\d年以[内上].*|\d至\d年", x) for x in rows):
            missing.append(f"{variant}/{table_name}: 行里出现账龄分档 {rows}")
    assert not missing, f"10.3 违规：{missing}"


def test_aging_as_column_registry_is_complete(templates, k_sections) -> None:
    """反向自检：模板里凡有账龄列的 K 表都必须在登记表里（防漏登）。"""
    found: list[tuple[str, str]] = []
    for wp, nums in sorted(k_sections.items()):
        for variant in ("listed", "soe"):
            if not nums[variant]:
                continue
            for t in _tables(templates, variant, nums[variant]):
                labels = [str(c.get("label") or "") for c in (t.get("columns") or [])]
                if any("账龄" in x for x in labels):
                    found.append((variant, str(t.get("name") or "")))
    assert sorted(found) == sorted(AGING_AS_COLUMN_TABLES), (
        f"账龄作列的表集合变了\n实测={sorted(found)}\n登记={sorted(AGING_AS_COLUMN_TABLES)}"
    )


def test_listed_monthly_subdivision_rows_kept(templates, k_sections) -> None:
    """10.4：K1 listed 的月度细分行是源模板事实，必须保留。"""
    tbl = next(
        (
            t
            for t in _tables(templates, "listed", k_sections["K1"]["listed"])
            if str(t.get("name") or "") == "按账龄披露"
        ),
        None,
    )
    assert tbl is not None, "K1 listed 找不到「按账龄披露」表"
    rows = [str(r.get("label") or "") for r in (tbl.get("rows") or []) if isinstance(r, dict)]
    for want in ("其中：0-X个月", "X-Y个月", "1年以内小计："):
        assert want in rows, f"月度细分行 {want!r} 被删了：{rows}"


def test_k3_over_one_year_stays_standalone_without_aging(templates, k_sections) -> None:
    """10.5：K3 两版「账龄超过1年」是**独立表**，且表内既无账龄行也无账龄列。"""
    expected = {
        "listed": "其中，账龄超过1年的重要其他应付款",
        "soe": "账龄超过1年的重要其他应付款项",
    }
    for variant, name in expected.items():
        tbl = next(
            (
                t
                for t in _tables(templates, variant, k_sections["K3"][variant])
                if str(t.get("name") or "") == name
            ),
            None,
        )
        assert tbl is not None, f"K3 {variant} 缺独立表 {name!r}"
        labels = [str(c.get("label") or "") for c in (tbl.get("columns") or [])]
        assert not any("账龄" in x for x in labels), f"{name}: 混进了账龄列 {labels}"
        rows = [str(r.get("label") or "") for r in (tbl.get("rows") or []) if isinstance(r, dict)]
        assert not any("年以" in x or "至" in x for x in rows), f"{name}: 混进了账龄行 {rows}"


# ─────────────────────────────────────────────────────────────────────────────
# 10.6：无账龄循环反向锁死
# ─────────────────────────────────────────────────────────────────────────────

#: 无账龄维度的 11 个循环（Requirement 10.6）
NO_AGING_CYCLES: tuple[str, ...] = (
    "K2", "K4", "K5", "K6", "K7", "K8", "K9", "K10", "K11", "K12", "K13",
)


def test_no_aging_cycles_have_no_aging_enum(templates, k_sections) -> None:
    """10.6：这 11 个循环不得引入账龄枚举（行或列）。"""
    offenders: list[str] = []
    scanned = 0
    for wp in NO_AGING_CYCLES:
        for variant in ("listed", "soe"):
            num = k_sections[wp][variant]
            if not num:
                continue
            for t in _tables(templates, variant, num):
                scanned += 1
                labels = [str(c.get("label") or "") for c in (t.get("columns") or [])]
                rows = [
                    str(r.get("label") or "")
                    for r in (t.get("rows") or [])
                    if isinstance(r, dict)
                ]
                for text in labels + rows:
                    if re.fullmatch(r"\d年以[内上].*|\d至\d年|.*账龄.*", text):
                        offenders.append(f"{wp}/{variant}/{t.get('name')}: {text!r}")
    # 🔴 扫描面非空自检：扫到 0 张表时上面的循环恒绿（判据空转）
    assert scanned >= 20, f"只扫到 {scanned} 张表，11 个循环的章节定位可疑"
    assert not offenders, f"10.6 违规（无账龄循环出现账龄枚举）：{offenders}"


def test_aging_cycles_really_have_aging(templates, k_sections) -> None:
    """反向自检：K1 **确实**有账龄枚举 —— 否则上一条的「零命中」不可解读。"""
    rows_all: list[str] = []
    for variant in ("listed", "soe"):
        for t in _tables(templates, variant, k_sections["K1"][variant]):
            rows_all += [
                str(r.get("label") or "")
                for r in (t.get("rows") or [])
                if isinstance(r, dict)
            ]
    assert any("1至2年" in x for x in rows_all), "K1 也没有账龄行 ⇒ 判据/章节定位错了"


# ─────────────────────────────────────────────────────────────────────────────
# 12.1~12.4 / 12.6~12.8：子表名与载荷元数据
# ─────────────────────────────────────────────────────────────────────────────

_HEADER_WORDS = ("项目", "本期发生额", "上期发生额", "期末余额", "期初余额")
_ENGLISH_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _subtable_values(wp: str) -> dict[str, list[str]]:
    """取该循环全部 `*SUBTABLE*` 常量的字符串值（按常量名分组）。"""
    src = _fe(f"{wp.lower()}NoteSectionMap.ts")
    out: dict[str, list[str]] = {}
    for m in re.finditer(rf"export\s+const\s+({wp}[A-Z0-9_]*SUBTABLE[A-Z0-9_]*)\s*(?::[^=]+)?=\s*", src):
        j, depth = m.end(), 0
        while j < len(src):
            if src[j] in "{[":
                depth += 1
            elif src[j] in "}]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = src[m.end(): j + 1]
        vals = [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", body) if (a or b)]
        # 🔴 值可能是**引用**而不是字面量（K7 的两个变体常量都写成
        #    `deferredIncome: K7_SUBTABLE.deferredIncome`）。只抓字面量会把它们读成
        #    空数组，从而把「已填好」误判成「12.3 违规」—— 解析器缺陷冒充产品缺陷。
        for ref in re.findall(rf"{wp}_[A-Z0-9_]*SUBTABLE[A-Z0-9_]*\.(\w+)", body):
            base = out.get(f"{wp}_SUBTABLE") or []
            key_vals = re.search(
                rf"export\s+const\s+{wp}_SUBTABLE\s*(?::[^=]+)?=\s*\{{(.*?)\n\}}",
                src,
                re.S,
            )
            if key_vals:
                m2 = re.search(rf"\b{ref}\s*:\s*'([^']*)'", key_vals.group(1))
                if m2:
                    vals.append(m2.group(1))
                    continue
            vals += base
        out[m.group(1)] = vals
    return out


def test_subtable_values_match_template_names(templates, k_sections) -> None:
    """12.1：`*SUBTABLE*` 的每个值都要逐字命中模板 `tables[].name`。"""
    bad: list[str] = []
    total = 0
    for wp in sorted(k_sections, key=lambda x: (len(x), x)):
        names = {
            str(t.get("name") or "")
            for variant in ("listed", "soe")
            if k_sections[wp][variant]
            for t in _tables(templates, variant, k_sections[wp][variant])
        }
        for const, vals in _subtable_values(wp).items():
            for v in vals:
                total += 1
                if v not in names:
                    bad.append(f"{wp}.{const}: {v!r} 不在模板表名里")
    assert total >= 25, f"只解析到 {total} 个子表名值，解析器可疑"
    assert not bad, f"12.1 违规（子表名与模板脱钩 ⇒ 推送落不到表）：{bad}"


def test_subtable_values_are_not_headers_or_english_keys(k_sections) -> None:
    """12.2：子表名常量不得混入表头文字或英文列 key。"""
    bad: list[str] = []
    for wp in sorted(k_sections, key=lambda x: (len(x), x)):
        for const, vals in _subtable_values(wp).items():
            for v in vals:
                if v in _HEADER_WORDS or _ENGLISH_KEY_RE.fullmatch(v):
                    bad.append(f"{wp}.{const}: {v!r}")
    assert not bad, f"12.2 违规（表头文字/英文 key 混进子表名）：{bad}"


def test_k7_subtable_constants_are_not_empty() -> None:
    """12.3：K7 两个子表名常量不得为空。"""
    vals = _subtable_values("K7")
    for const in ("K7_LISTED_SUBTABLE", "K7_SOE_SUBTABLE"):
        assert const in vals, f"K7 缺常量 {const}"
        assert vals[const], f"{const} 为空 ⇒ 推送找不到表"


#: 12.4：K1 是唯一没有 `build*Columns` / `buildK1SyncPayload` 的循环 —— **登记**。
K1_PAYLOAD_PATH_REGISTERED = (
    "K1 的披露推送不走 `build*Columns` + `build*SyncPayload` 那套（K2~K13 的范式），"
    "而是 `k1DisclosureModel.ts` 建模 + `k1DisclosureSyncPayload.ts` 组装 —— "
    "K1 有 21/19 张表、含三阶段快照与账龄矩阵，单函数装不下。"
    "登记为**已知分叉**并由本用例钉死其现有路径存在；改成统一范式属独立重构。"
)


def test_k1_payload_path_is_registered_and_exists() -> None:
    """12.4：K1 的推送路径按 AC 允许的第二条路（登记 + 守卫）收口。"""
    assert len(K1_PAYLOAD_PATH_REGISTERED) >= 60, "登记理由过短"
    for name in ("k1DisclosureModel.ts", "k1DisclosureSyncPayload.ts"):
        assert (_FE / name).exists(), f"K1 登记的推送路径文件缺失：{name}"
    src = _fe("k1DisclosureSyncPayload.ts")
    assert re.search(r"export\s+(?:function|const)\s+\w*[Pp]ayload", src), (
        "k1DisclosureSyncPayload.ts 没有导出载荷构造函数 ⇒ 登记的路径是空的"
    )


def test_conditional_table_cycles_declare_removed_table_keys(templates, k_sections) -> None:
    """12.6：**有多张表**的循环必须带 `_removed_table_keys`（条件表关闭时清孤儿）。

    判据由数据驱动而非白名单：只有一张表的循环没有条件表，也就没有孤儿可清
    （实测 K5 / K10 两版各 1 张表 ⇒ 不强制）。
    """
    bad: list[str] = []
    checked = 0
    for wp in sorted(k_sections, key=lambda x: (len(x), x)):
        max_tables = max(
            (
                len(_tables(templates, variant, k_sections[wp][variant]))
                for variant in ("listed", "soe")
                if k_sections[wp][variant]
            ),
            default=0,
        )
        if max_tables <= 1:
            continue
        checked += 1
        src = _fe(f"{wp.lower()}NoteSectionMap.ts")
        if "removedTableKeys" not in src and "_removed_table_keys" not in src:
            bad.append(f"{wp}（{max_tables} 张表）")
    # 实测多表循环 6 个：K1(21/19) K2(3/1) K3(7/6) K4(3/1) K6(5/4) K7(1/2)；
    # 其余 7 个（K5/K8~K13）两版各 1 张表
    assert checked == 6, f"多表循环数变成 {checked}（实测基线 6），请核实后更新"
    assert not bad, f"12.6 违规（多表循环缺孤儿清理声明）：{bad}"


# ─────────────────────────────────────────────────────────────────────────────
# 12.5：列 key 风格（Task 20 —— 同循环内一致 + 跨循环分叉登记）
# ─────────────────────────────────────────────────────────────────────────────

#: 🔴 跨循环列 key 风格分叉的**裁决登记**（Requirement 12.5 / Task 20）。
#:
#: 实测：K1 的 151 个数据列 key 全是**中文字面量**（`期末余额` / `逾期时间（月）`…），
#: K2~K13 的 145 个全是 **snake_case**（`end_amount` / `current_amount`…）。
#: 同一循环内**没有**混用（13/13 各只有一种风格），分叉只发生在 K1 与其余之间。
#:
#: **裁决 = 保持分叉，不统一。** 理由（缺一条这条登记就不成立）：
#: 列 key 是 `disclosure_notes.table_data.sub_table_data[表名][行].{key}` 的
#: **数据键**，也是 `_cell_meta` / `_cell_modes` 的索引键。改 key 等于让所有已录入
#: 的单元格值与元数据**对不上号** —— 表现不是报错而是**数据凭空消失**（渲染器按新 key
#: 取值取到 undefined，旧值仍在库里但再也读不出来）。K1 是 21/19 张表、体量最大的
#: 循环，改它的收益（风格整齐）远小于风险（丢已录入数据）。
#:
#: 若将来真要统一，前置条件是**先写数据迁移脚本**（逐 note 逐表逐行改键 + 同步
#: `_cell_meta`/`_cell_modes` 的索引）并配 round-trip 验证，属独立 spec。
COLUMN_KEY_STYLE_DIVERGENCE = {
    "cjk_cycles": ("K1",),
    "snake_cycles": ("K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9", "K10", "K11", "K12", "K13"),
    "verdict": "保持分叉，不统一",
    "reason": (
        "列 key 是 sub_table_data 的数据键与 _cell_meta/_cell_modes 的索引键，"
        "改 key 会让已录入数据与元数据对不上号 —— **改 key 会丢已录入数据**，"
        "且表现是数据凭空消失而不是报错。统一须先有数据迁移脚本，属独立 spec。"
    ),
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _key_styles(templates: dict, k_sections: dict, wp: str) -> dict[str, int]:
    stat = {"cjk": 0, "snake": 0, "other": 0}
    for variant in ("listed", "soe"):
        num = k_sections[wp][variant]
        if not num:
            continue
        for t in _tables(templates, variant, num):
            for c in t.get("columns") or []:
                key = str(c.get("key") or "")
                if not key or key == "label":
                    continue  # 标签列由 12.8 单独管
                if _CJK_RE.search(key):
                    stat["cjk"] += 1
                elif _SNAKE_RE.fullmatch(key):
                    stat["snake"] += 1
                else:
                    stat["other"] += 1
    return stat


def test_key_style_is_consistent_within_each_cycle(templates, k_sections) -> None:
    """12.5 前半：同一循环内列 key 风格必须一致（混用无从维护）。"""
    mixed: list[str] = []
    total = 0
    for wp in sorted(k_sections, key=lambda x: (len(x), x)):
        stat = _key_styles(templates, k_sections, wp)
        total += sum(stat.values())
        styles = [n for n, v in stat.items() if v]
        if len(styles) > 1:
            mixed.append(f"{wp}: {stat}")
    assert total >= 250, f"只统计到 {total} 个数据列 key，判据源可疑"
    assert not mixed, f"12.5 违规（同循环内列 key 风格混用）：{mixed}"


def test_cross_cycle_divergence_matches_registry(templates, k_sections) -> None:
    """12.5 后半：跨循环分叉必须与登记一致（谁中文、谁 snake 都不许悄悄变）。

    这条同时是「统一化改动」的闸门：真要统一必须先改这份登记，
    而登记里写着「改 key 会丢已录入数据」+ 前置条件。
    """
    actual_cjk: list[str] = []
    actual_snake: list[str] = []
    for wp in sorted(k_sections, key=lambda x: (len(x), x)):
        stat = _key_styles(templates, k_sections, wp)
        if stat["cjk"]:
            actual_cjk.append(wp)
        elif stat["snake"]:
            actual_snake.append(wp)
    assert tuple(actual_cjk) == COLUMN_KEY_STYLE_DIVERGENCE["cjk_cycles"], (
        f"中文 key 的循环集合变了：实测 {actual_cjk}，"
        f"登记 {list(COLUMN_KEY_STYLE_DIVERGENCE['cjk_cycles'])}"
    )
    assert tuple(actual_snake) == COLUMN_KEY_STYLE_DIVERGENCE["snake_cycles"], (
        f"snake_case 的循环集合变了：实测 {actual_snake}，"
        f"登记 {list(COLUMN_KEY_STYLE_DIVERGENCE['snake_cycles'])}"
    )


def test_divergence_reason_states_data_loss_risk() -> None:
    """登记理由必须写明「改 key 会丢已录入数据」—— 这是裁决成立的唯一依据。"""
    reason = COLUMN_KEY_STYLE_DIVERGENCE["reason"]
    assert "改 key 会丢已录入数据" in reason, f"登记理由没写数据丢失风险：{reason!r}"
    assert len(reason) >= 60, "登记理由过短，读者看不出为什么不统一"


#: 12.8 的**唯一例外**：标签列 key 不是 `label`，但**已有落库数据**在用它。
#:
#: 形态：``{(wp, variant, table): (key, 落库行数, 理由)}``
#:
#: 🔴 判据是**连库实查**而不是「觉得风险大」：本轮改 12.8 的三处违规时逐个查了
#: `disclosure_notes.table_data`（只读）——
#:   * K4 两张表的 `bond_name`：落库 **0 行** ⇒ 改名零风险，**已改成 `label`**
#:   * K7 的 `grant_item`：落库 **2 行** ⇒ 改名会让那 2 个附注的该列数据读不出来
#:     （渲染器按新 key 取值取到 undefined，旧值仍在库里但再也读不出来），故登记不改
#:
#: 解除条件：写数据迁移脚本（逐 note 逐表逐行改键 + 同步 `_cell_meta`/`_cell_modes`
#: 索引）并配 round-trip 验证 —— 与 `COLUMN_KEY_STYLE_DIVERGENCE` 同一前置条件。
LABEL_KEY_EXEMPTIONS: dict[tuple[str, str, str], tuple[str, int, str]] = {
    ("K7", "soe", "其中：递延收益-政府补助情况"): (
        "grant_item",
        2,
        "落库 2 行在用该键；改名会让这 2 个附注的该列数据读不出来（不报错、直接空）",
    ),
}


def test_label_column_key_is_label(templates, k_sections) -> None:
    """12.8：标签列 key 一律 `label`（平台惯例），例外须连库举证后登记。"""
    bad: list[str] = []
    checked = 0
    for wp in sorted(k_sections, key=lambda x: (len(x), x)):
        for variant in ("listed", "soe"):
            num = k_sections[wp][variant]
            if not num:
                continue
            for t in _tables(templates, variant, num):
                name = str(t.get("name") or "")
                for c in t.get("columns") or []:
                    if not c.get("is_label"):
                        continue
                    checked += 1
                    key = str(c.get("key") or "")
                    if key == "label":
                        continue
                    exempt = LABEL_KEY_EXEMPTIONS.get((wp, variant, name))
                    if exempt and exempt[0] == key:
                        continue
                    bad.append(f"{wp}/{variant}/{name}: key={key!r}")
    assert checked >= 50, f"只核到 {checked} 个标签列，判据源可疑"
    assert not bad, f"12.8 违规（标签列 key 不是 `label` 且未登记）：{bad[:8]}"


def test_label_key_exemptions_are_still_needed(templates, k_sections) -> None:
    """反向自检：登记的例外必须**仍然存在**且理由写明落库行数。

    哪天那张表的 key 被改成 `label`（或表没了），本条打红提醒把登记移出 ——
    登记不许长期失效地挂着。
    """
    for (wp, variant, name), (key, rows, why) in LABEL_KEY_EXEMPTIONS.items():
        tbl = next(
            (
                t
                for t in _tables(templates, variant, k_sections[wp][variant])
                if str(t.get("name") or "") == name
            ),
            None,
        )
        assert tbl is not None, f"登记的例外表已不存在：{wp}/{variant}/{name}"
        keys = [str(c.get("key") or "") for c in (tbl.get("columns") or []) if c.get("is_label")]
        assert key in keys, (
            f"{wp}/{variant}/{name} 的标签列 key 已不是 {key!r}（现为 {keys}）"
            " —— 请把本条从 LABEL_KEY_EXEMPTIONS 移出"
        )
        assert rows > 0, "例外的成立前提是「有落库数据」，行数必须 > 0"
        assert "落库" in why and len(why) >= 25, f"例外理由未写落库举证：{why!r}"


def test_single_table_cycles_really_have_one_table(templates, k_sections) -> None:
    """反向自检：被上一条豁免的循环确实只有一张表。"""
    for wp in ("K5", "K10"):
        for variant in ("listed", "soe"):
            num = k_sections[wp][variant]
            if not num:
                continue
            n = len(_tables(templates, variant, num))
            assert n == 1, f"{wp}/{variant} 有 {n} 张表，不该被 12.6 豁免"
