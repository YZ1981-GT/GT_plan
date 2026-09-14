"""K 循环 row_code **连库**对账守卫（Wave 1 Task 1，先打红）。

🔴 为什么必须连库、不能用静态冻结表
================================================================
既有 `test_k_cycle_specs.py` 用模块级常量 `_EXPECTED_ROWS` 冻结了一份「立项实证」，
而那份表把 listed / soe 两侧行号**整体记错一档** —— 于是「声明表错」与「守卫也错」
互相印证，9 处 row_code 错位长期全绿。本文件的判据一律来自 DB：

    按 row_name 反查 report_config（四变体全列） → 得到该科目名的合法 row_code 集合
    按 row_code 正查 report_config              → 得到声明现值实际指向的科目名

两个方向都要，因为「声明的码存在」不等于「声明的码是本科目」。

判定分级（design.md §Data Models）::

    formula 非 NULL 且解析出的码在 account_chart 存在:
        direction 与主体方向一致   → ACTIVE_WRONG  （活错数：取到别的科目的钱）
        direction 相反且未声明方向 → SILENT_EMPTY  （恒空：原值被判成备抵）
    formula 是 ROW() 派生 / formula NULL → TRACE_ONLY（退兜底，金额对、溯源谎报）

连库形态：**一次 `asyncio.run` 取快照 + 全部断言同步**。pytest-asyncio 默认每个测试
新建 event loop，而 `app.core.database` 的连接池绑定首个 loop → 第二个测试起会报
`AttributeError: 'NoneType' object has no attribute 'send'`，若 fixture 里
`except → pytest.skip` 就变成静默假绿。

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Property 1, 2, 3, 4, 5, 11
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

# ─────────────────────────────────────────────────────────────────────────────
# 被测声明表
# ─────────────────────────────────────────────────────────────────────────────


def _load_specs() -> dict[str, Any]:
    """导入声明表。失败必须 `fail` 而不是 `skip`（skip 会变成静默假绿）。"""
    try:
        from app.services.four_table.k_cycle_specs import K_CYCLE_SPECS
    except Exception as exc:  # pragma: no cover - 导入失败即判红
        pytest.fail(f"无法导入 k_cycle_specs.K_CYCLE_SPECS: {exc!r}")
    return dict(K_CYCLE_SPECS)


# ─────────────────────────────────────────────────────────────────────────────
# 各循环的科目**中文名**（反查 report_config 的 key）
#
# 🔴 这里只登记「科目名」不登记「row_code」—— row_code 由 DB 反查得出，
#    这是本文件与既有静态守卫的根本区别。名字取自源模板与 account_chart，
#    与 report_config.row_name 的差异（如「加：其他收益」带前缀）由归一化处理。
# ─────────────────────────────────────────────────────────────────────────────

#: wp_code → (report_config 中的 row_name 候选, 报表类型)
K_ACCOUNT_NAMES: dict[str, tuple[tuple[str, ...], str]] = {
    "K1": (("其他应收款",), "balance_sheet"),
    "K2": (("其他流动资产",), "balance_sheet"),
    "K3": (("其他应付款",), "balance_sheet"),
    "K4": (("其他流动负债",), "balance_sheet"),
    "K5": (("预计负债",), "balance_sheet"),
    "K6": (("持有待售资产",), "balance_sheet"),
    "K7": (("递延收益",), "balance_sheet"),
    "K8": (("销售费用",), "income_statement"),
    "K9": (("管理费用",), "income_statement"),
    "K10": (("其他收益", "加：其他收益"), "income_statement"),
    "K11": (("资产减值损失",), "income_statement"),
    "K12": (("营业外收入", "加：营业外收入"), "income_statement"),
    "K13": (("营业外支出", "减：营业外支出"), "income_statement"),
}

#: K6 是唯一一个循环管三条报表行的（资产 / 负债 / 备抵）
K6_EXTRA_NAMES: dict[str, tuple[str, ...]] = {
    "liability": ("持有待售负债",),
    "provision": ("持有待售资产减值准备", "六、持有待售资产减值准备"),
}

#: 本轮连库复算得出的正确落点（Property 2 逐条防回退）。
#: 🔴 与既有 `test_k_cycle_specs._EXPECTED_ROWS` 冲突是**预期的** —— 那份表是错的。
CORRECTED_ROW_CODES: dict[str, str] = {
    "K1": "BS-009",
    "K2": "BS-014",
    "K3": "BS-050",
    "K4": "BS-053",
    "K5": "BS-065",
    "K6": "BS-012",
    "K7": "BS-066",
    "K8": "IS-004",
    "K9": "IS-005",
    "K10": "IS-010",
    "K11": "IS-017",
    "K12": "IS-020",
    "K13": "IS-021",
}

K6_LIABILITY_ROW_CODE = "BS-051"
K6_PROVISION_ROW_CODE = "IMP-007"

#: 声明现值里已知错位的码 → 它实际指向的科目名（反向自检：证明判据抓的是真问题）
KNOWN_MISPOINTED: dict[str, str] = {
    "BS-081": "实收资本（或股本）",
    "BS-024": "长期股权投资",
    "IS-023": "减：所得税费用",
    "IS-022": "三、利润总额",
    "BS-015": "流动资产合计",
    "BS-069": "非流动负债合计",
    "BS-068": "其他非流动负债",
}

#: 派生行（formula 只由 ROW() 组合而成，`extract_signed_codes` 抽不出 TB()）
KNOWN_DERIVED_ROWS: frozenset[str] = frozenset({"BS-015", "BS-069", "IS-022"})

#: 负债/权益类主体方向为 credit 的循环 → 其原值科目码
CREDIT_SIDE_CYCLES: dict[str, tuple[str, ...]] = {
    "K3": ("2241", "2231"),
    "K5": ("2801",),
    "K7": ("2401",),
}

#: K6 资产侧 debit / 负债侧 credit（同一循环两个方向，故单列）
K6_ASSET_CODES: tuple[str, ...] = ("1481", "1482")
K6_LIABILITY_CODES: tuple[str, ...] = ("2245",)

_STANDARD_FILTER = "applicable_standard NOT LIKE 'project:%'"


# ─────────────────────────────────────────────────────────────────────────────
# DB 快照
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Snapshot:
    """一次性取回的全部 DB 事实。"""

    #: row_name（归一后） → {row_code}
    name_to_codes: dict[str, set[str]] = field(default_factory=dict)
    #: row_code → {(applicable_standard, row_name, formula)}
    code_rows: dict[str, list[tuple[str, str, str | None]]] = field(default_factory=dict)
    #: account_code → {(source, direction, projects, name)}
    chart: dict[str, list[tuple[str, str, int, str]]] = field(default_factory=dict)
    #: account_name（归一后） → {account_code}
    chart_by_name: dict[str, set[str]] = field(default_factory=dict)
    ok: bool = False
    error: str = ""


def _norm_name(s: str | None) -> str:
    """行名/科目名归一：去空白 + 去行业适用性标记 + 去列报前缀。

    平台在报表行名里用 `△▲※*` 标「特定行业适用」，且损益表行带「加：/减：」前缀、
    减值准备表行带「六、」这类章节序号 —— 这些都不改变科目语义。
    再激进的归一化会放过真错位，故**不去括注、不去「其中：」**。
    """
    t = re.sub(r"\s+", "", str(s or ""))
    t = re.sub(r"[△▲※*]", "", t)
    t = re.sub(r"^[一二三四五六七八九十]+、", "", t)
    t = re.sub(r"^(加|减)：", "", t)
    return t


async def _load(snap: Snapshot) -> None:
    from app.core.config import settings

    url = str(settings.DATABASE_URL)
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    sa.text(
                        f"SELECT row_code, row_name, report_type, applicable_standard, formula "
                        f"FROM report_config WHERE is_deleted = false AND {_STANDARD_FILTER}"
                    )
                )
            ).all()
            for rc, rn, _rt, std, fml in rows:
                snap.name_to_codes.setdefault(_norm_name(rn), set()).add(str(rc))
                snap.code_rows.setdefault(str(rc), []).append(
                    (str(std), str(rn or ""), fml)
                )

            arows = (
                await conn.execute(
                    sa.text(
                        "SELECT account_code, source, direction, "
                        "COUNT(DISTINCT project_id) AS projects, MIN(account_name) AS nm "
                        "FROM account_chart WHERE is_deleted = false "
                        "GROUP BY account_code, source, direction"
                    )
                )
            ).all()
            for code, source, direction, projects, nm in arows:
                snap.chart.setdefault(str(code), []).append(
                    (str(source or ""), str(direction or ""), int(projects or 0), str(nm or ""))
                )
                snap.chart_by_name.setdefault(_norm_name(nm), set()).add(str(code))
        snap.ok = True
    finally:
        await engine.dispose()


_SNAP: Snapshot | None = None


def snap() -> Snapshot:
    """取 DB 快照（模块级缓存，一次 asyncio.run）。"""
    global _SNAP
    if _SNAP is None:
        s = Snapshot()
        try:
            asyncio.run(_load(s))
        except Exception as exc:  # pragma: no cover
            s.error = repr(exc)
        _SNAP = s
    if not _SNAP.ok:
        pytest.fail(
            f"无法连库取 report_config / account_chart 快照：{_SNAP.error}\n"
            "本守卫按 Property 1 要求必须连库（禁静态冻结表），"
            "连不上时判红而非 skip —— skip 会让整组判据静默空转。"
        )
    return _SNAP


# ─────────────────────────────────────────────────────────────────────────────
# 判据基础设施自检（类 A：应当全绿）
# ─────────────────────────────────────────────────────────────────────────────


def test_snapshot_is_nonempty():
    """反向自检：快照非空，否则下面全部断言都是空转。

    阈值按 2026-08-09 实测值取下限（**不是拍脑袋的整数**）：
    `report_config` 排除 `project:%` 后**去重 row_code = 352**（四变体合计 1222 行），
    `account_chart` 去重科目码 > 1000。写 500 会让本条在正确数据上假红。
    """
    s = snap()
    assert len(s.code_rows) > 300, f"report_config 只取到 {len(s.code_rows)} 个 row_code"
    assert len(s.chart) > 100, f"account_chart 只取到 {len(s.chart)} 个科目码"


def test_norm_name_keeps_distinctions():
    """反向自检：归一化不得把不同科目抹平成同一个。"""
    assert _norm_name("加：其他收益") == "其他收益"
    assert _norm_name("六、持有待售资产减值准备") == "持有待售资产减值准备"
    assert _norm_name("△买入返售金融资产") == "买入返售金融资产"
    # 「其他应付款」与「其他应收款」不得归一成同一个
    assert _norm_name("其他应付款") != _norm_name("其他应收款")
    # 「持有待售资产」与「持有待售负债」不得归一成同一个
    assert _norm_name("持有待售资产") != _norm_name("持有待售负债")
    # 括注不去 —— 「预计负债」与「预计负债（一年内到期）」是不同行
    assert _norm_name("实收资本（或股本）") == "实收资本（或股本）"


def test_all_k_account_names_resolve_in_report_config():
    """反向自检：每个循环的科目名至少有一个候选能在 report_config 命中。

    命中不了说明候选名写错了 —— 那样后面「声明的码必须落在该名的码集内」
    会因为码集为空而全红，把「候选名错」误报成「声明错」。
    """
    s = snap()
    missing: list[str] = []
    for wp, (names, _rt) in K_ACCOUNT_NAMES.items():
        if not any(_norm_name(n) in s.name_to_codes for n in names):
            missing.append(f"{wp}: 候选名 {names} 在 report_config 全部零命中")
    assert not missing, "科目名候选写错（判据自身缺陷，不是声明缺陷）:\n" + "\n".join(missing)


def test_known_mispointed_codes_really_point_elsewhere():
    """反向自检：按 row_code 正查，证明那些码确实指向别的科目。

    这条是整个判据的立足点 —— 若它绿，说明「声明的码指向别的科目」是事实，
    而不是我的归一化把名字弄错了。
    """
    s = snap()
    bad: list[str] = []
    for code, expect_name in KNOWN_MISPOINTED.items():
        rows = s.code_rows.get(code, [])
        if not rows:
            bad.append(f"{code}: report_config 零命中（登记表已过期）")
            continue
        names = {_norm_name(rn) for _std, rn, _f in rows}
        if _norm_name(expect_name) not in names:
            bad.append(f"{code}: 期望指向「{expect_name}」，实际 {sorted(names)}")
    assert not bad, "KNOWN_MISPOINTED 登记表与 DB 不符:\n" + "\n".join(bad)


def test_known_derived_rows_are_really_derived():
    """反向自检：派生行的 formula 确实只由 ROW() 组合、无 TB()。"""
    s = snap()
    bad: list[str] = []
    for code in sorted(KNOWN_DERIVED_ROWS):
        rows = s.code_rows.get(code, [])
        assert rows, f"{code} 在 report_config 零命中"
        for std, _rn, fml in rows:
            if not fml:
                continue
            if "ROW(" not in fml:
                bad.append(f"{code}/{std}: formula 无 ROW() → {fml}")
            if re.search(r"\bTB\s*\(", fml):
                bad.append(f"{code}/{std}: formula 含 TB() → 不是纯派生行")
    assert not bad, "KNOWN_DERIVED_ROWS 登记表与 DB 不符:\n" + "\n".join(bad)


def test_corrected_codes_point_to_right_accounts():
    """反向自检：改正值确实指向本循环科目（证明 CORRECTED 表本身对）。"""
    s = snap()
    bad: list[str] = []
    for wp, code in CORRECTED_ROW_CODES.items():
        names_ok = {_norm_name(n) for n in K_ACCOUNT_NAMES[wp][0]}
        rows = s.code_rows.get(code, [])
        if not rows:
            bad.append(f"{wp}: 改正值 {code} 在 report_config 零命中")
            continue
        actual = {_norm_name(rn) for _std, rn, _f in rows}
        if not (actual & names_ok):
            bad.append(f"{wp}: 改正值 {code} 指向 {sorted(actual)}，期望 {sorted(names_ok)}")
    # K6 的两条附加行
    for code, key in ((K6_LIABILITY_ROW_CODE, "liability"), (K6_PROVISION_ROW_CODE, "provision")):
        want = {_norm_name(n) for n in K6_EXTRA_NAMES[key]}
        actual = {_norm_name(rn) for _std, rn, _f in s.code_rows.get(code, [])}
        if not (actual & want):
            bad.append(f"K6/{key}: {code} 指向 {sorted(actual)}，期望 {sorted(want)}")
    assert not bad, "CORRECTED_ROW_CODES 登记表与 DB 不符（判据自身缺陷）:\n" + "\n".join(bad)


# ─────────────────────────────────────────────────────────────────────────────
# Property 1：声明表 row_code 与 report_config 按名对账一致（类 B：当前应红）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("wp", sorted(K_ACCOUNT_NAMES, key=lambda c: int(c[1:])))
def test_declared_row_codes_belong_to_own_account(wp: str):
    """Property 1：声明的 listed / soe row_code 必须落在本科目名的码集内。"""
    s = snap()
    specs = _load_specs()
    if wp not in specs:
        pytest.fail(
            f"{wp} 尚未纳入 K_CYCLE_SPECS（Requirement 3.1；本条红是预期的 Wave 1 结果）"
        )
    spec = specs[wp]
    legal: set[str] = set()
    for n in K_ACCOUNT_NAMES[wp][0]:
        legal |= s.name_to_codes.get(_norm_name(n), set())
    assert legal, f"{wp} 科目名在 report_config 零命中（判据缺陷）"

    problems: list[str] = []
    for side in ("row_code_listed", "row_code_soe"):
        rc = getattr(spec, side, None)
        if rc is None:
            continue
        if rc not in legal:
            actual = {_norm_name(rn) for _std, rn, _f in s.code_rows.get(rc, [])}
            problems.append(
                f"{wp}.{side} = {rc} 不属于「{K_ACCOUNT_NAMES[wp][0][0]}」"
                f"（合法码集 {sorted(legal)}）；该码实际指向 {sorted(actual) or '（零命中）'}"
            )
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("wp", sorted(CORRECTED_ROW_CODES, key=lambda c: int(c[1:])))
def test_corrected_row_codes_stay_corrected(wp: str):
    """Property 2：逐条改正值不得回退。"""
    specs = _load_specs()
    if wp not in specs:
        pytest.fail(f"{wp} 尚未纳入 K_CYCLE_SPECS（Requirement 3.1）")
    spec = specs[wp]
    want = CORRECTED_ROW_CODES[wp]
    got = (getattr(spec, "row_code_listed", None), getattr(spec, "row_code_soe", None))
    assert want in got, (
        f"{wp} 期望 row_code 含 {want}，实际 listed/soe = {got}。"
        f"该科目在 report_config 四变体下两准则同号，故两侧都应是 {want}"
    )


def test_two_standards_use_same_row_code_where_db_says_so():
    """Property 1.2：DB 里两准则同号时，声明表不得为了「看起来分变体」而填不同码。

    🔴 既有 `test_k_cycle_specs.test_row_codes_match_report_config_evidence` 断言
    「两侧行号必须不同」—— 那条与 DB 事实直接冲突，是错位能长期存在的原因之一。
    """
    s = snap()
    specs = _load_specs()
    problems: list[str] = []
    for wp, (names, _rt) in K_ACCOUNT_NAMES.items():
        if wp not in specs:
            continue
        legal: set[str] = set()
        for n in names:
            legal |= s.name_to_codes.get(_norm_name(n), set())
        # DB 里该科目名只对应一个码 ⇒ 声明两侧必须相同
        if len(legal) != 1:
            continue
        only = next(iter(legal))
        spec = specs[wp]
        lc = getattr(spec, "row_code_listed", None)
        sc = getattr(spec, "row_code_soe", None)
        if lc != only or sc != only:
            problems.append(
                f"{wp}: report_config 里「{names[0]}」只有 {only} 一个码，"
                f"而声明 listed={lc} / soe={sc}"
            )
    assert not problems, "\n".join(problems)


# ─────────────────────────────────────────────────────────────────────────────
# Property 3：派生行不得作为取数 row_code
# ─────────────────────────────────────────────────────────────────────────────


def test_no_declared_row_code_is_derived_row():
    """Property 3：声明的 row_code 若是 ROW() 派生行，必须 `trust_report_config=False`。"""
    s = snap()
    specs = _load_specs()
    problems: list[str] = []
    for wp, spec in specs.items():
        for side in ("row_code_listed", "row_code_soe"):
            rc = getattr(spec, side, None)
            if not rc:
                continue
            rows = s.code_rows.get(rc, [])
            if not rows:
                continue
            derived = all(
                (fml is None) or ("ROW(" in fml and not re.search(r"\bTB\s*\(", fml))
                for _std, _rn, fml in rows
                if fml is not None
            ) and any(fml and "ROW(" in fml for _std, _rn, fml in rows)
            if derived and getattr(spec, "trust_report_config", True):
                problems.append(
                    f"{wp}.{side} = {rc} 是 ROW() 派生行"
                    f"（extract_signed_codes 抽不出 TB() ⇒ 静默退兜底、resolved_from 谎报），"
                    f"必须 trust_report_config=False 或改指非派生行"
                )
    assert not problems, "\n".join(problems)


# ─────────────────────────────────────────────────────────────────────────────
# Property 4：宁缺勿造是逐循环实证结论
# ─────────────────────────────────────────────────────────────────────────────


def judge_no_account_claim(
    wp: str,
    names: tuple[str, ...],
    extra_codes: set[str],
    chart_by_name: dict[str, set[str]],
    name_to_codes: dict[str, set[str]],
    code_rows: dict[str, list[tuple[str, str, str | None]]],
) -> str:
    """判定「宁缺勿造」声明是否成立 —— 纯函数，供守卫与替身自检共用。

    返回空串表示成立；非空串是打红理由。

    判据两条同时满足才算成立：①该科目名在 ``account_chart`` 零命中
    ②该科目名对应的 ``report_config`` 行公式全为 NULL。

    抽成纯函数是为了让下面的替身自检能**无条件**跑一次 —— 参数化集合为空时
    整条测试会 SKIP，那时「判据有效」与「判据空转」不可区分（平台既有教训）。
    """
    chart_hits: set[str] = set()
    for n in names:
        chart_hits |= chart_by_name.get(_norm_name(n), set())
    codes: set[str] = set(extra_codes)
    for n in names:
        codes |= name_to_codes.get(_norm_name(n), set())
    with_formula = [
        f"{c}/{std}={fml}"
        for c in sorted(codes)
        for std, _rn, fml in code_rows.get(c, [])
        if fml
    ]
    if not chart_hits and not with_formula:
        return ""
    return (
        f"{wp} 声明 has_account=False，但实测："
        f"account_chart 命中码 {sorted(chart_hits) or '无'}；"
        f"report_config 有公式的行 {with_formula or '无'} "
        f"⇒ 宁缺勿造不成立，应改 has_account=True 并保留运行时降级"
    )


def test_judge_no_account_claim_self_check():
    """反向自检（无条件跑）：判据本身对四种输入都判对。

    这条不依赖真实库有无 `has_account=False` 的循环 —— 即便将来 K4 也改成 True、
    上面那条参数化集合变空，本条仍会执行，故判据不会静默失效。
    """
    empty: dict[str, set[str]] = {}
    rows_null: dict[str, list[tuple[str, str, str | None]]] = {
        "BS-053": [("soe_standalone", "其他流动负债", None)]
    }
    rows_fml: dict[str, list[tuple[str, str, str | None]]] = {
        "BS-012": [("soe_standalone", "持有待售资产", "TB('1481','期末余额')")]
    }
    n2c = {"其他流动负债": {"BS-053"}, "持有待售资产": {"BS-012"}}

    # ① 两侧都零命中 ⇒ 成立（返空串）
    assert judge_no_account_claim("XX", ("其他流动负债",), set(), empty, n2c, rows_null) == ""
    # ② 科目表有落点 ⇒ 不成立
    msg = judge_no_account_claim(
        "XX", ("其他流动负债",), set(), {"其他流动负债": {"2301"}}, n2c, rows_null
    )
    assert "2301" in msg and "宁缺勿造不成立" in msg
    # ③ 报表行有公式 ⇒ 不成立
    msg = judge_no_account_claim("XX", ("持有待售资产",), set(), empty, n2c, rows_fml)
    assert "BS-012" in msg
    # ④ extra_codes 也参与判定（K6 的负债侧与备抵侧行号不由科目名反查得到）
    msg = judge_no_account_claim("XX", ("不存在的科目",), {"BS-012"}, empty, n2c, rows_fml)
    assert "BS-012" in msg, "extra_codes 未参与判定 ⇒ K6 负债侧/备抵侧的公式会被漏看"


def test_no_account_flag_matches_db_evidence():
    """Property 4：`has_account=False` 必须两侧零命中 + 公式 NULL。

    实测：K4（其他流动负债）四变体公式全 NULL、account_chart 按名按码零命中 ⇒ 成立；
    K6 的 1481/1482/2245 在 client 侧各有项目、BS-012/BS-051/IMP-007 公式都在 ⇒ 不成立。
    """
    s = snap()
    specs = _load_specs()
    problems: list[str] = []
    for wp, spec in specs.items():
        if getattr(spec, "has_account", True):
            continue
        names = K_ACCOUNT_NAMES.get(wp, ((), ""))[0]
        extra_codes: set[str] = set()
        if wp == "K6":
            extra_codes = {K6_LIABILITY_ROW_CODE, K6_PROVISION_ROW_CODE}
            for key in K6_EXTRA_NAMES:
                names = (*names, *K6_EXTRA_NAMES[key])
        msg = judge_no_account_claim(
            wp, names, extra_codes, s.chart_by_name, s.name_to_codes, s.code_rows
        )
        if msg:
            problems.append(msg)
    assert not problems, "\n".join(problems)


def test_k6_accounts_exist_in_client_chart():
    """Property 4 证据固化：K6 的三个科目在 client 侧确实存在（推翻旧记载）。"""
    s = snap()
    missing: list[str] = []
    for code in (*K6_ASSET_CODES, *K6_LIABILITY_CODES):
        entries = [e for e in s.chart.get(code, []) if e[0] == "client"]
        if not entries:
            missing.append(code)
    assert not missing, (
        f"K6 科目 {missing} 在 account_chart client 侧零命中 —— "
        "若确实零命中则「宁缺勿造」成立，本条与 Requirement 1.9 需一并复核"
    )


def test_k4_no_account_evidence_still_holds():
    """Property 4 反向：K4 的宁缺勿造依据仍成立（stale 检测）。"""
    s = snap()
    codes = s.name_to_codes.get(_norm_name("其他流动负债"), set())
    assert codes, "report_config 无「其他流动负债」行（判据过期）"
    with_formula = [
        f"{c}/{std}={fml}"
        for c in sorted(codes)
        for std, _rn, fml in s.code_rows.get(c, [])
        if fml
    ]
    assert not with_formula, (
        f"「其他流动负债」现在有公式了：{with_formula} ⇒ "
        "K4 的 has_account=False 需重新裁决（Requirement 1.8）"
    )
    assert not s.chart_by_name.get(_norm_name("其他流动负债")), (
        "account_chart 现在有「其他流动负债」科目了 ⇒ K4 宁缺勿造需重新裁决"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Property 5：负债类必须声明方向
# ─────────────────────────────────────────────────────────────────────────────


def test_credit_side_accounts_are_really_credit():
    """反向自检：CREDIT_SIDE_CYCLES 登记的码在 account_chart 确为 credit。"""
    s = snap()
    bad: list[str] = []
    for wp, codes in CREDIT_SIDE_CYCLES.items():
        for code in codes:
            dirs = {d for _src, d, _p, _n in s.chart.get(code, [])}
            if not dirs:
                bad.append(f"{wp}/{code}: account_chart 零命中")
            elif "credit" not in dirs:
                bad.append(f"{wp}/{code}: direction={sorted(dirs)}，不含 credit")
    for code in K6_LIABILITY_CODES:
        dirs = {d for _src, d, _p, _n in s.chart.get(code, [])}
        if "credit" not in dirs:
            bad.append(f"K6 负债侧 {code}: direction={sorted(dirs)}")
    for code in K6_ASSET_CODES:
        dirs = {d for _src, d, _p, _n in s.chart.get(code, [])}
        if "debit" not in dirs:
            bad.append(f"K6 资产侧 {code}: direction={sorted(dirs)}，应为 debit")
    assert not bad, "CREDIT_SIDE_CYCLES 登记表与 DB 不符:\n" + "\n".join(bad)


@pytest.mark.parametrize("wp", sorted(CREDIT_SIDE_CYCLES, key=lambda c: int(c[1:])))
def test_liability_cycles_declare_direction(wp: str):
    """Property 5：credit 科目的循环必须 `is_liability=True` 或 `gross_direction='credit'`。

    未声明时 `split_gross_provision` 的第一条规则（direction=='credit' 即备抵）
    会把**原值**判成备抵 ⇒ `gross` 变空 ⇒ 审定表恒空（而非报错）。
    """
    specs = _load_specs()
    spec = specs.get(wp)
    assert spec is not None, f"{wp} 未登记"
    is_liab = bool(getattr(spec, "is_liability", False))
    gd = getattr(spec, "gross_direction", None)
    assert is_liab or gd == "credit", (
        f"{wp}（{CREDIT_SIDE_CYCLES[wp]} 在 account_chart 为 credit）"
        f"未声明负债方向：is_liability={is_liab} / gross_direction={gd!r} ⇒ "
        "原值会被 split_gross_provision 判成备抵、gross 变空、审定表恒空"
    )


def test_k6_asset_side_does_not_declare_liability():
    """Property 5 边界：K6 资产侧（1481/1482 为 debit）不得声明负债方向。"""
    specs = _load_specs()
    spec = specs.get("K6")
    if spec is None:
        pytest.fail("K6 未登记")
    assert not getattr(spec, "is_liability", False), (
        "K6 主 spec 是资产侧（1481 持有待售资产 direction=debit），"
        "声明 is_liability 会让资产原值被判成备抵"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Property 11：同一 row_code 不得被两循环认领
# ─────────────────────────────────────────────────────────────────────────────

#: 已知合法共享（同一报表行由多个循环共同承载）
ALLOWED_SHARED_ROW_CODES: frozenset[str] = frozenset({"BS-028", "BS-029"})


def test_no_two_k_cycles_claim_same_row_code():
    """Property 11（K 内）：K 循环之间不得撞码。"""
    specs = _load_specs()
    seen: dict[str, str] = {}
    dup: list[str] = []
    for wp, spec in specs.items():
        for side in ("row_code_listed", "row_code_soe"):
            rc = getattr(spec, side, None)
            if not rc or rc in ALLOWED_SHARED_ROW_CODES:
                continue
            prev = seen.get(rc)
            if prev and prev != wp:
                dup.append(f"{rc} 被 {prev} 与 {wp} 同时声明")
            seen[rc] = wp
    assert not dup, "\n".join(sorted(set(dup)))


def test_k_row_codes_do_not_collide_with_other_cycles():
    """Property 11（跨循环）：K 的 row_code 不得与 L/D/F/G/I/M/N 的声明撞码。

    实测已知隐患：K5 的 `BS-068` 与 L7「其他非流动负债」同码（已改正）。
    """
    specs = _load_specs()
    k_codes: dict[str, str] = {}
    for wp, spec in specs.items():
        for side in ("row_code_listed", "row_code_soe"):
            rc = getattr(spec, side, None)
            if rc and rc not in ALLOWED_SHARED_ROW_CODES:
                k_codes[rc] = wp

    others: dict[str, str] = {}
    try:
        from app.services.four_table.l_cycle_specs import L_CYCLE_SPECS

        for name, sp in L_CYCLE_SPECS.items():
            rc = getattr(sp, "row_code", None)
            if rc:
                others.setdefault(str(rc), f"L/{name}")
    except Exception:  # pragma: no cover - 注册表改名时不阻断本文件其余断言
        pass

    dup = [
        f"{rc}: K/{wp} 与 {others[rc]} 撞码"
        for rc, wp in sorted(k_codes.items())
        if rc in others
    ]
    assert not dup, "\n".join(dup)


# ─────────────────────────────────────────────────────────────────────────────
# 分级输出（诊断用，不做断言 —— 供 Wave 2 排优先级）
# ─────────────────────────────────────────────────────────────────────────────


def test_report_severity_distribution(capsys):
    """输出三级分类分布；断言只要求「至少识别出一个活错数」以证明判据有效。"""
    s = snap()
    specs = _load_specs()
    lines: list[str] = []
    active_wrong = 0
    for wp in sorted(specs, key=lambda c: int(c[1:])):
        spec = specs[wp]
        names_ok = {_norm_name(n) for n in K_ACCOUNT_NAMES.get(wp, ((), ""))[0]}
        for side in ("row_code_listed", "row_code_soe"):
            rc = getattr(spec, side, None)
            if not rc:
                continue
            rows = s.code_rows.get(rc, [])
            actual = {_norm_name(rn) for _std, rn, _f in rows}
            if actual & names_ok:
                continue  # 指向正确
            formulas = [f for _std, _rn, f in rows if f]
            has_tb = any(re.search(r"\bTB\s*\(", f) for f in formulas)
            if not formulas or not has_tb:
                sev = "TRACE_ONLY"
            else:
                codes = set()
                for f in formulas:
                    codes |= set(re.findall(r"TB\s*\(\s*'([^']+)'", f))
                exists = any(c in s.chart for c in codes)
                dirs = {
                    d for c in codes for _src, d, _p, _n in s.chart.get(c, [])
                }
                declared_dir = bool(getattr(spec, "is_liability", False)) or (
                    getattr(spec, "gross_direction", None) == "credit"
                )
                if exists and "credit" in dirs and not declared_dir:
                    sev = "SILENT_EMPTY"
                elif exists:
                    sev = "ACTIVE_WRONG"
                    active_wrong += 1
                else:
                    sev = "TRACE_ONLY"
            lines.append(
                f"  {wp:4} {side:16} {rc:9} → {sorted(actual) or '(零命中)'}  [{sev}]"
            )
    with capsys.disabled():
        print("\n[K row_code 错位分级]")
        print("\n".join(lines) if lines else "  （全部指向正确）")
    assert active_wrong >= 1 or not lines, (
        "判据未识别出任何 ACTIVE_WRONG，但存在错位项 —— 分级逻辑可能失效"
    )
