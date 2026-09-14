"""``report_config`` 科目码一致性守卫（连库）.

spec: `report-config-account-code-integrity`（Task 2）。

这张表此前**零一致性校验**：`row_name` 与 formula 引用科目的实际名从不比对，
错码可以静默存在数年（2026-08-03 全表对账查出 13 行，此前两次手工修复只覆盖 5 行
且其中一次前提错误 —— V136 的 WHERE 从不命中）。

🔴 **本文件必须先在修正前的现状下打红 13 行**，那是它有效的唯一证明。
先改数据再写守卫无法区分「守卫有效」与「守卫空转」——
`test_semantic_resolver_coverage.py` 第一版成为假绿源正是这个机理。

五组断言：
  - ``TestNoMismatchedCodes``        行名 ↔ 科目名（经别名归一）必须对应
  - ``TestZeroHitCodesWhitelisted``  零命中码必须在白名单且 reason 非空
  - ``TestDerivedRowsHaveNoAccount`` 派生行 formula 必须为 NULL
  - ``TestNoCrossRowDoubleClaim``    同一码不得被同表两行认领为主科目
  - ``TestReverseSelfcheck``         注入已知错码必红 / 清空别名必红 / 合并 source 必红
"""
from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from dataclasses import dataclass

import pytest
import sqlalchemy as sa

from app.services.four_table.report_config_account_names import (  # noqa: E402
    ADJUDICATED_2026_08_05,
    CODE_CORRECTIONS,
    DETAIL_ROW_PREFIXES,
    DERIVED_ROWS_WITHOUT_ACCOUNT,
    DUAL_SYSTEM_CODES,
    KNOWN_CORRECT_EQUITY_ROWS,
    PENDING_ADJUDICATION,
    ROW_NAME_ACCOUNT_ALIASES,
    SUSPECTED_NEW_ISSUES,
    ZERO_HIT_WHITELIST,
    alias_group,
    extract_tb_codes,
    extract_tb_refs,
    head_code,
    is_detail_row,
    is_name_comparable,
    names_match,
    normalize_name,
)

# 本仓库 `backend/pytest.ini` 设 `asyncio_mode = auto` → async 测试无需显式标记；
# 显式加 `pytestmark = pytest.mark.asyncio` 会让同类里的同步测试全部报
# PytestWarning（"marked with asyncio but is not an async function"）。


# ─── 数据模型 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Ref:
    """`report_config` 里的一条 TB 引用。"""

    row_code: str
    row_name: str
    applicable_standard: str
    code: str  # 原样码（可能带 - / . / ~）
    head: str  # 查 account_chart 用的主段
    column: str  # 取数列（期末余额 / 期初余额 / 本期发生额…）；跨行双算判定必需
    name_comparable: bool  # 该行是否适用严格行名↔科目名对账

    @property
    def table(self) -> str:
        """所属报表（`BS` / `IS` / `EQ` / `IMP` / `CFSS`）。"""
        return self.row_code.split("-", 1)[0]


# ─── 加载 ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Snapshot:
    """一次性取回的对账快照（避免多次进出事件循环）。"""

    refs: list[Ref]
    chart: dict[tuple[str, str], set[str]]
    name_index: dict[tuple[str, str], set[str]]
    rows: list[dict]


def _resolve_db_url() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("DB_URL") or ""
    if url:
        return url
    try:
        from app.core.config import settings  # noqa: PLC0415

        return getattr(settings, "DATABASE_URL", "") or ""
    except Exception:  # noqa: BLE001
        return ""


async def _load_all() -> Snapshot:
    """🔴 全部查询合并在**同一个** async 函数里跑完。

    连接池绑定首个事件循环 → 多次 `asyncio.run` / 每测试一个 loop 都会让
    第二次拿到已关闭的 transport（memory 铁律，本文件实测踩中过一次）。
    """
    from app.core.database import async_session  # noqa: PLC0415

    async with async_session() as db:
        rows = (
            await db.execute(
                sa.text(
                    "SELECT row_code, row_name, applicable_standard, formula "
                    "FROM report_config "
                    "WHERE is_deleted = false "
                    "  AND applicable_standard NOT LIKE 'project:%' "
                    "ORDER BY row_code, applicable_standard"
                )
            )
        ).mappings().all()
        rows = [dict(r) for r in rows]

        refs: list[Ref] = []
        for r in rows:
            pairs = extract_tb_refs(r["formula"])
            comparable = is_name_comparable(r["row_code"], [c for c, _ in pairs])
            for code, column in pairs:
                refs.append(
                    Ref(
                        row_code=r["row_code"],
                        row_name=r["row_name"] or "",
                        applicable_standard=r["applicable_standard"],
                        code=code,
                        head=head_code(code),
                        column=column,
                        name_comparable=comparable,
                    )
                )

        chart_rows = (
            await db.execute(
                sa.text(
                    "SELECT account_code, source, account_name "
                    "FROM account_chart "
                    "WHERE account_code IS NOT NULL AND account_name IS NOT NULL "
                    "GROUP BY account_code, source, account_name"
                )
            )
        ).mappings().all()

    chart: dict[tuple[str, str], set[str]] = defaultdict(set)
    name_index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in chart_rows:
        code = str(r["account_code"]).strip()
        source = str(r["source"]).strip()
        name = str(r["account_name"]).strip()
        chart[(code, source)].add(name)
        name_index[(normalize_name(name), source)].add(code)

    return Snapshot(refs=refs, chart=dict(chart), name_index=dict(name_index), rows=rows)


@pytest.fixture(scope="module")
def snap() -> Snapshot:
    """连库快照；无 DB 时 skip **并打印原因**（静默 skip 是假绿源，Property 12）。"""
    if not _resolve_db_url():
        pytest.skip(
            "report_config 一致性守卫需要真实 DB —— 未取到 DATABASE_URL/DB_URL，"
            "也未能从 app.core.config.settings 读到。CI 上本 job 必须挂在有 DB 的 job。"
        )
    try:
        return asyncio.run(_load_all())
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"DB 取数失败（{type(exc).__name__}: {exc}）—— 守卫需要真实 report_config × account_chart"
        )


# ─── 判定核心（纯函数，供正向断言与反向自检共用） ────────────────────────────


def classify_ref(
    ref: Ref,
    chart: dict[tuple[str, str], set[str]],
    name_index: dict[tuple[str, str], set[str]],
    *,
    aliases_enabled: bool = True,
    merge_sources: bool = False,
) -> tuple[str, str]:
    """返回 ``(verdict, detail)``。

    verdict ∈ {``ok``, ``mismatch``, ``zero_hit_wrong_code``, ``zero_hit_business_fact``}

    - ``ok``                      行名与该码的某个科目名一致（分 source 任一命中即可）
    - ``mismatch``                该码存在但名字对不上，且该行名挂在别的码上 → 错码
    - ``zero_hit_wrong_code``     该码全库零命中，但该行名在库中有归属 → 错码
    - ``zero_hit_business_fact``  该码零命中且该行名亦零命中 → 业务事实（需白名单）
    """
    sources = ("client", "standard")

    detail = is_detail_row(ref.row_name)

    def _match(row_name: str, account_name: str) -> bool:
        if aliases_enabled:
            return names_match(row_name, account_name, detail_row=detail)
        # 反向自检：关掉别名后只做归一后精确相等
        return normalize_name(row_name) == normalize_name(account_name)

    if merge_sources:
        pools = {"__merged__": set().union(*(chart.get((ref.head, s), set()) for s in sources))}
    else:
        pools = {s: chart.get((ref.head, s), set()) for s in sources}

    code_exists = any(pools.values())

    # 方向①：码 → 名
    if code_exists:
        for src, names in pools.items():
            for account_name in names:
                if _match(ref.row_name, account_name):
                    return "ok", f"{ref.head}@{src} = {account_name}"

    # 方向②：名 → 码（该行名在库里挂在哪些码上）
    owning_codes: set[str] = set()
    for group_name in alias_group(ref.row_name) if aliases_enabled else {normalize_name(ref.row_name)}:
        for src in sources:
            owning_codes |= name_index.get((group_name, src), set())
    owning_codes.discard(ref.head)

    if not code_exists:
        if owning_codes:
            return (
                "zero_hit_wrong_code",
                f"{ref.head} 全库零命中，而「{ref.row_name}」实际挂在 {sorted(owning_codes)}",
            )
        return (
            "zero_hit_business_fact",
            f"{ref.head} 与「{ref.row_name}」在全库均零命中",
        )

    actual = sorted({n for names in pools.values() for n in names})
    if owning_codes:
        return (
            "mismatch",
            f"{ref.head} 实际是 {actual}，而「{ref.row_name}」实际挂在 {sorted(owning_codes)}",
        )
    # 码存在但名字对不上，且该行名在库中无归属 → 仍视为不一致（fail closed），
    # 但 detail 里说明「该名无归属」以便人工分档
    return (
        "mismatch",
        f"{ref.head} 实际是 {actual}，而「{ref.row_name}」在库中无归属（须人工分档）",
    )


# ─── 反向自检：模块常量层（不连库，先跑） ────────────────────────────────────


class TestModuleConstantsSanity:
    """常量表自身的自洽性（不连库，任何环境都跑）。"""

    def test_whitelist_reasons_non_empty(self) -> None:
        """Property 9：白名单 reason 必填。"""
        assert ZERO_HIT_WHITELIST, "反向自检：白名单不应为空"
        for row_code, reason in ZERO_HIT_WHITELIST.items():
            assert reason and reason.strip(), f"{row_code} 的白名单 reason 为空 = 未登记"
            assert len(reason.strip()) >= 15, f"{row_code} 的 reason 过短，须写明实证"

    def test_derived_rows_reasons_non_empty(self) -> None:
        assert DERIVED_ROWS_WITHOUT_ACCOUNT
        for row_code, reason in DERIVED_ROWS_WITHOUT_ACCOUNT.items():
            assert reason and reason.strip(), f"{row_code} 的派生行判定依据为空"
            assert len(reason.strip()) >= 15, f"{row_code} 的依据过短"

    def test_corrections_and_derived_are_disjoint(self) -> None:
        """改码与置 NULL 是互斥处置，同一行不能两边都在。"""
        overlap = set(CODE_CORRECTIONS) & set(DERIVED_ROWS_WITHOUT_ACCOUNT)
        assert not overlap, f"同一行既改码又置 NULL：{sorted(overlap)}"

    def test_pending_adjudication_excluded_from_corrections(self) -> None:
        """BS-014 待裁决，不得混进 V138 的修正清单。"""
        for row_code in PENDING_ADJUDICATION:
            assert row_code not in CODE_CORRECTIONS
            assert row_code not in DERIVED_ROWS_WITHOUT_ACCOUNT

    def test_normalize_name_strips_known_noise(self) -> None:
        assert normalize_name("△分出再保险合同负债") == "分出再保险合同负债"
        assert normalize_name("减：库存股") == "库存股"
        assert normalize_name("（五）专项储备") == "专项储备"
        assert normalize_name("七、债权投资减值准备") == "债权投资减值准备"
        assert normalize_name("十六、商誉减值准备") == "商誉减值准备"
        assert normalize_name("实收资本（或股本）") == "实收资本"
        assert normalize_name('存货的减少（增加以"－"号填列）') == "存货的减少"
        assert normalize_name("其中：应收股利") == "应收股利"
        assert normalize_name("  资本 公积　") == "资本公积"
        assert normalize_name(None) == ""
        assert normalize_name("") == ""

    def test_normalize_name_does_not_over_strip(self) -> None:
        """不得把正常行名剥空或剥掉实义部分。"""
        # 「一年内到期的非流动资产」以「一」开头但不是序号（后面不是「、」）
        assert normalize_name("一年内到期的非流动资产") == "一年内到期的非流动资产"
        assert normalize_name("其他权益工具") == "其他权益工具"

    def test_alias_group_is_symmetric(self) -> None:
        for left, right in ROW_NAME_ACCOUNT_ALIASES:
            assert normalize_name(right) in alias_group(left), f"{left} → {right} 别名不生效"
            assert normalize_name(left) in alias_group(right), f"{right} → {left} 别名不对称"

    def test_names_match_uses_aliases(self) -> None:
        assert names_match("未分配利润", "利润分配")
        assert names_match("减：库存股", "库存股")
        assert not names_match("其他权益工具", "其他综合收益")
        assert not names_match("专项储备", "本年利润")

    def test_extract_tb_codes_handles_both_spacings(self) -> None:
        """实证：BS-* 无空格、EQ/IMP/CFSS 逗号后有空格。"""
        assert extract_tb_codes("TB('4003','期末余额')") == ["4003"]
        assert extract_tb_codes("TB('1502', '期末余额')") == ["1502"]
        assert extract_tb_codes(
            "TB('4201', '期末余额') - TB('4201', '期初余额')"
        ) == ["4201", "4201"], "重复必须保留（EQ-015 两处都要修）"
        # 🔴 平台函数名是 `SUM_TB`（全表实证），不是 `TB_SUM`
        assert extract_tb_codes("SUM_TB('1401~1499','期末余额')") == ["1401~1499"]
        assert extract_tb_codes("TB_SUM('1401~1499','期末余额')") == [], (
            "`TB_SUM` 不是平台函数名，不应被抽到（防把不存在的形态写进判据）"
        )
        assert extract_tb_codes(None) == []
        assert extract_tb_codes("ROW('IS-019')+ROW('IS-020')") == []

    def test_head_code(self) -> None:
        assert head_code("1231-03") == "1231"
        assert head_code("1231.03") == "1231"
        assert head_code("1401~1499") == "1401"
        assert head_code("4003") == "4003"


# ─── 正向断言（连库） ────────────────────────────────────────────────────────


class TestRefExtraction:
    """抽取本身不能空转（抽到 0 条比不一致更危险）。"""

    def test_refs_non_empty(self, snap: Snapshot) -> None:
        refs = snap.refs
        assert len(refs) >= 100, (
            f"只抽到 {len(refs)} 条 TB 引用，正则可能失效 —— "
            "2026-08-03 基线是 132 条引用 / 102 个报表行"
        )

    def test_chart_non_empty_and_split_by_source(self, snap: Snapshot) -> None:
        chart = snap.chart
        assert chart, "account_chart 为空"
        sources = {src for (_code, src) in chart}
        assert {"client", "standard"} <= sources, f"应同时有 client/standard，实为 {sources}"


class TestNoMismatchedCodes:
    """行名 ↔ 科目名（经别名归一 + 分 source）必须对应。"""

    def test_no_mismatched_codes(self, snap: Snapshot) -> None:
        refs = snap.refs
        chart = snap.chart
        name_index = snap.name_index

        bad: list[str] = []
        for ref in refs:
            if ref.row_code in ZERO_HIT_WHITELIST:
                continue
            if ref.row_code in PENDING_ADJUDICATION:
                continue  # 待用户裁决，另行处置
            if ref.row_code in SUSPECTED_NEW_ISSUES:
                continue  # 本轮新查出，未经裁决不并入本断言
            if not ref.name_comparable:
                # 流量表（变动额语义）与多码合成行不做名称比对 —— 见
                # report_config_account_names.is_name_comparable 的三条判据。
                # 它们仍受「码必须存在」（下面的零命中断言）与派生行断言约束。
                continue
            verdict, detail = classify_ref(ref, chart, name_index)
            if verdict in ("mismatch", "zero_hit_wrong_code"):
                bad.append(
                    f"{ref.row_code}[{ref.applicable_standard}] "
                    f"「{ref.row_name}」= TB('{ref.code}') → {verdict}: {detail}"
                )

        assert not bad, "report_config 存在错码：\n" + "\n".join(sorted(set(bad)))


class TestZeroHitCodesWhitelisted:
    """零命中码必须在白名单，且白名单不得掩盖真错码。"""

    def test_zero_hit_refs_are_whitelisted(self, snap: Snapshot) -> None:
        refs = snap.refs
        chart = snap.chart
        name_index = snap.name_index

        unregistered: list[str] = []
        for ref in refs:
            if ref.row_code in PENDING_ADJUDICATION:
                continue
            verdict, detail = classify_ref(ref, chart, name_index)
            if verdict == "zero_hit_business_fact" and ref.row_code not in ZERO_HIT_WHITELIST:
                unregistered.append(f"{ref.row_code} TB('{ref.code}') — {detail}")

        assert not unregistered, (
            "零命中码未登记白名单（须逐条写明实证）：\n" + "\n".join(sorted(set(unregistered)))
        )

    def test_whitelisted_names_still_absent(self, snap: Snapshot) -> None:
        """Property 6 后半：白名单条目的科目名一旦在库中出现 → 打红迫使复核。"""
        refs = snap.refs
        chart = snap.chart
        name_index = snap.name_index

        resurrected: list[str] = []
        for ref in refs:
            if ref.row_code not in ZERO_HIT_WHITELIST:
                continue
            verdict, detail = classify_ref(ref, chart, name_index)
            if verdict != "zero_hit_business_fact":
                resurrected.append(f"{ref.row_code}: {verdict} — {detail}")

        assert not resurrected, (
            "白名单条目的前提已变（码或名在库中出现了），须复核是否其实是错码：\n"
            + "\n".join(sorted(set(resurrected)))
        )


class TestDerivedRowsHaveNoAccount:
    """派生行必须 formula IS NULL（Property 5）。"""

    def test_derived_rows_formula_is_null(self, snap: Snapshot) -> None:
        rows = [
            r
            for r in snap.rows
            if r["row_code"] in DERIVED_ROWS_WITHOUT_ACCOUNT and r["formula"] is not None
        ]

        bad = [
            f"{r['row_code']}[{r['applicable_standard']}]「{r['row_name']}」= {r['formula']}"
            f"  ← {DERIVED_ROWS_WITHOUT_ACCOUNT[r['row_code']]}"
            for r in rows
        ]
        assert not bad, "派生行仍挂着科目码（应置 NULL 让调用方走兜底）：\n" + "\n".join(bad)


class TestNoCrossRowDoubleClaim:
    """同一码不得被同一张报表内两个不同 row_code 认领（Property 10）。"""

    def test_no_double_claim_within_same_table(self, snap: Snapshot) -> None:
        refs = snap.refs

        claims: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        for ref in refs:
            if ref.row_code in PENDING_ADJUDICATION:
                continue
            if ref.row_code in SUSPECTED_NEW_ISSUES:
                continue
            if ref.row_name.startswith(DETAIL_ROW_PREFIXES):
                continue  # 「其中：」是上一行的明细展开，不是并列认领
            # 🔴 按**完整码 + 取数列**判，不能按 head：
            #   · BS-005/006/009 各引 1231-01 / 1231 / 1231-03 → 不同备抵明细，非双算
            #   · IMP-001/IMP-002 引 1231 / 1231.02 → 父行与明细行，非双算
            #   · CFSS-026/027 引同码但列为 期末余额 / 期初余额 → 同科目两时点，非双算
            claims[(ref.table, ref.code, ref.column)].add(ref.row_code)

        # 备抵可与原值行重合 → IMP 表与 BS 表之间不算双算（table 已区分）；
        # 同表内多行认领同码才是双算。
        conflicts = {
            key: sorted(rows) for key, rows in claims.items() if len(rows) > 1
        }
        # CAS 有意聚合的例外：BS-050 其他应付款 = 2231 + 2241（应付利息/应付股利并入）
        # —— 这是「一行引多码」不是「多行引一码」，不会出现在这里。
        assert not conflicts, (
            "同一报表内多个行认领同一科目码 = 跨行双算：\n"
            + "\n".join(
                f"  {table}/{code}[{column or '默认列'}]: {rows}"
                for (table, code, column), rows in sorted(conflicts.items())
            )
        )


class TestKnownCorrectRowsStayCorrect:
    """Property 2：已实证正确的权益段行不得被波及。"""

    def test_known_correct_equity_rows(self, snap: Snapshot) -> None:
        rows = [r for r in snap.rows if r["row_code"] in KNOWN_CORRECT_EQUITY_ROWS]
        assert rows, "反向自检：应能读到 BS-081/083/087/088"

        for r in rows:
            expected = KNOWN_CORRECT_EQUITY_ROWS[r["row_code"]]
            codes = extract_tb_codes(r["formula"])
            assert codes == [expected], (
                f"{r['row_code']}[{r['applicable_standard']}] 的码应恒为 {expected}，实为 {codes}"
            )


# ─── 反向自检（连库，证明判据不空转） ────────────────────────────────────────


class TestReverseSelfcheck:
    """每条都必须红，否则说明对应判据是空转的（Property 8）。"""

    def test_injected_wrong_code_is_flagged(self, snap: Snapshot) -> None:
        """注入 `BS-090 少数股东权益 = TB('4201')` 必判红。"""
        chart = snap.chart
        name_index = snap.name_index
        injected = Ref(
            row_code="BS-090",
            row_name="少数股东权益",
            applicable_standard="soe_consolidated",
            code="4201",
            head="4201",
            column="期末余额",
            name_comparable=True,
        )
        verdict, detail = classify_ref(injected, chart, name_index)
        assert verdict != "ok", (
            "注入的已知错码被判通过 = 不一致检测空转（4201 实为库存股）"
        )
        assert "库存股" in detail

    def test_aliases_actually_do_work(self, snap: Snapshot) -> None:
        """清空别名后 `BS-088 未分配利润 = TB('4104')` 必由绿转红。"""
        chart = snap.chart
        name_index = snap.name_index
        ref = Ref(
            row_code="BS-088",
            row_name="未分配利润",
            applicable_standard="soe_standalone",
            code="4104",
            head="4104",
            column="期末余额",
            name_comparable=True,
        )
        with_alias, _ = classify_ref(ref, chart, name_index, aliases_enabled=True)
        without_alias, _ = classify_ref(ref, chart, name_index, aliases_enabled=False)
        assert with_alias == "ok", "BS-088 在别名开启时应通过（科目名是「利润分配」）"
        assert without_alias != "ok", "关掉别名后仍通过 = 别名表没在起作用"

    def test_source_split_actually_matters(self, snap: Snapshot) -> None:
        """Property 7：`4101` 在 standard 侧同时有制造费用与盈余公积。

        分域判定下 `BS-087 盈余公积 = 4101` 通过；此处直接实证「同码双名」
        确实存在，证明若把「一码多名」当缺陷判红就会误杀。
        """
        chart = snap.chart
        std_names = chart.get(("4101", "standard"), set())
        client_names = chart.get(("4101", "client"), set())
        assert len(std_names) >= 2, (
            f"反向自检：standard 侧 4101 应有两套体系的两个名，实为 {std_names}"
        )
        assert "盈余公积" in std_names or "盈余公积" in client_names
        assert "制造费用" in std_names, "旧制体系的 4101 制造费用 应仍在库中"
        assert "4101" in DUAL_SYSTEM_CODES

        name_index = snap.name_index
        ref = Ref("BS-087", "盈余公积", "soe_standalone", "4101", "4101", "期末余额", True)
        verdict, _ = classify_ref(ref, chart, name_index)
        assert verdict == "ok", "BS-087 应通过（client 8 项目 = 盈余公积）"

    def test_derived_row_refilled_is_flagged(self, snap: Snapshot) -> None:
        """把派生行填回一个码必红（此处用纯判定，不写库）。"""
        chart = snap.chart
        name_index = snap.name_index
        ref = Ref(
            "BS-013", "一年内到期的非流动资产", "soe_standalone", "1503", "1503", "期末余额", True
        )
        verdict, detail = classify_ref(ref, chart, name_index)
        assert verdict != "ok", "1503 实为可供出售金融资产，填回必须被判红"
        assert "可供出售金融资产" in detail

class TestSumTbIsExtracted:
    """`SUM_TB` 必须被抽到（否则区间口径行会被误判成单码行）。"""

    def test_sum_tb_form_is_matched(self) -> None:
        """🔴 函数名是 `SUM_TB` 不是 `TB_SUM` —— 全表实证只有 TB / SUM_TB / ROW。"""
        assert extract_tb_codes("SUM_TB('1401~1499','期末余额')") == ["1401~1499"]
        assert extract_tb_codes(
            "SUM_TB('1401~1499','期末余额') - TB('1416','期末余额')"
        ) == ["1401~1499", "1416"]

    def test_interval_row_is_not_name_comparable(self) -> None:
        """`BS-010 存货` 是「区间 + 减备抵」两码行 → 不做严格名称比对。

        反向自检：漏抽 SUM_TB 会让它变成单码行，于是拿「存货」比对
        备抵科目「存货跌价准备」而误报（本守卫第一版实测踩中）。
        """
        codes = extract_tb_codes("SUM_TB('1401~1499','期末余额') - TB('1416','期末余额')")
        assert len(codes) == 2
        assert not is_name_comparable("BS-010", codes)
        # 只抽到 1416 时（漏抽 SUM_TB 的形态）会被判为可比对 → 证明该断言有效
        assert is_name_comparable("BS-010", ["1416"])

    def test_all_formula_functions_are_known(self, snap: Snapshot) -> None:
        """全表 formula 只允许 TB / SUM_TB / ROW —— 出现新函数名说明抽取需扩展。"""
        import re as _re

        seen: set[str] = set()
        for r in snap.rows:
            if r["formula"]:
                seen |= set(_re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", r["formula"]))
        assert seen, "反向自检：应能抽到函数名"
        unknown = seen - {"TB", "SUM_TB", "ROW"}
        assert not unknown, (
            f"report_config 出现未知公式函数 {sorted(unknown)} —— "
            "TB_REF_RE 需相应扩展，否则这些行的引用会被静默漏抽"
        )


class TestCodeCorrectionsApplied:
    """`CODE_CORRECTIONS` 每行必须已用正确码（修正前必红，修正后转绿）。

    🔴 这组断言覆盖 `EQ-015`（权益变动表）与其他非余额类报表的改码行 ——
    它们不适用行名 ↔ 科目名比对（`EQ-015 （五）专项储备` 是**变动额**），
    但「码写错了」这件事仍必须被抓住。
    """

    def test_corrections_use_right_code(self, snap: Snapshot) -> None:
        by_row: dict[str, list[dict]] = defaultdict(list)
        for r in snap.rows:
            if r["row_code"] in CODE_CORRECTIONS and r["formula"]:
                by_row[r["row_code"]].append(r)

        assert by_row, "反向自检：应能读到待修正行"

        bad: list[str] = []
        for row_code, (wrong, right, evidence) in CODE_CORRECTIONS.items():
            for r in by_row.get(row_code, []):
                codes = extract_tb_codes(r["formula"])
                if wrong in codes:
                    bad.append(
                        f"{row_code}[{r['applicable_standard']}]「{r['row_name']}」"
                        f"仍在用错码 {wrong}（应为 {right}）—— {evidence}"
                    )
                elif right not in codes:
                    bad.append(
                        f"{row_code}[{r['applicable_standard']}]「{r['row_name']}」"
                        f"既无错码 {wrong} 也无正确码 {right}，实为 {codes} —— 须人工复核"
                    )

        assert not bad, "改码清单未落地：\n" + "\n".join(bad)

    def test_new_code_exists_in_chart(self, snap: Snapshot) -> None:
        """Property 4：每个新码必须在库中确实存在，且至少一个 source 下叫得上名。"""
        missing: list[str] = []
        for row_code, (_wrong, right, evidence) in CODE_CORRECTIONS.items():
            names = snap.chart.get((right, "client"), set()) | snap.chart.get(
                (right, "standard"), set()
            )
            if not names:
                missing.append(f"{row_code}: 新码 {right} 在全库 account_chart 零命中 —— {evidence}")
        assert not missing, "改码目标不存在于科目表：\n" + "\n".join(missing)


class TestSuspectedNewIssuesReported:
    """本轮新查出、未经裁决的疑似问题必须有登记且理由充分（不静默放过）。"""

    def test_suspected_entries_have_evidence(self) -> None:
        for row_code, reason in SUSPECTED_NEW_ISSUES.items():
            assert reason and len(reason.strip()) >= 30, f"{row_code} 的疑似问题说明过短"
            assert "2026-" in reason, f"{row_code} 未写发现日期"

    def test_suspected_not_silently_in_whitelist(self) -> None:
        """疑似错码不得同时挂在零命中白名单里（那会让它被当业务事实放过）。"""
        overlap = set(SUSPECTED_NEW_ISSUES) & set(ZERO_HIT_WHITELIST)
        assert not overlap, (
            f"{sorted(overlap)} 既登记为疑似错码又在零命中白名单 —— 判据自相矛盾"
        )


class TestAdjudicationLanded:
    """已裁决条目必须**真的落地**且**从待办登记表里移除**（Task 10 交叉锁死）。

    🔴 为什么需要这一组：`ADJUDICATED_2026_08_05` 的 docstring 声称
    「守卫断言每条都必须已落地到 CODE_CORRECTIONS 或 DERIVED_ROWS_WITHOUT_ACCOUNT 之一，
    且不得再挂在 SUSPECTED_NEW_ISSUES / PENDING_ADJUDICATION 里」——
    但 2026-08-05 实测该断言**并不存在**（本文件当时压根没 import 这个常量）。
    「声称有守卫但没写」与「注释结论错、取值恰好对」同族：下个会话会照注释信任它。

    两个方向都要锁：
      · 裁决了但没落地 → 数据仍是错码 / 仍挂着旧公式，而登记表看起来已收口；
      · 落地了但登记表没清 → `SUSPECTED_NEW_ISSUES` / `PENDING_ADJUDICATION` 变成
        **陈旧断言**（守卫的跳过集里还留着已修好的行 ⇒ 那两行永久豁免正向断言 = 假绿）。
    """

    def test_registry_not_empty(self) -> None:
        """哨兵：登记表空 = 本组全部断言空转（假绿）。"""
        assert ADJUDICATED_2026_08_05, (
            "ADJUDICATED_2026_08_05 为空 —— 本组断言会全部空转。"
            "若确已无裁决记录需保留，应连同本测试类一起删除而不是留空表"
        )

    def test_each_adjudication_landed_in_exactly_one_enforcing_set(self) -> None:
        """每条裁决必须落到「改码」或「置 NULL」**其中之一**（互斥且必居其一）。

        这两个集合各自都有 DB 级强制断言（`TestCodeCorrectionsApplied` /
        `TestDerivedRowsHaveNoAccount`）⇒ 落进任一集合即等于被真实数据盯住；
        两边都不在 = 裁决只写在注释里，没有任何断言保证它已落地。
        """
        bad: list[str] = []
        for row_code in ADJUDICATED_2026_08_05:
            in_corr = row_code in CODE_CORRECTIONS
            in_null = row_code in DERIVED_ROWS_WITHOUT_ACCOUNT
            if in_corr and in_null:
                bad.append(f"{row_code}: 同时登记为改码与置 NULL —— 处置自相矛盾")
            elif not in_corr and not in_null:
                bad.append(
                    f"{row_code}: 已裁决但未落地 —— 既不在 CODE_CORRECTIONS 也不在 "
                    "DERIVED_ROWS_WITHOUT_ACCOUNT ⇒ 无任何 DB 级断言保证它已生效"
                )
        assert not bad, "裁决未落地：\n" + "\n".join(bad)

    def test_adjudicated_rows_removed_from_pending_registries(self) -> None:
        """🔴 已裁决的行必须从「待办」登记表移除，否则守卫的跳过集会永久豁免它们。

        `TestNoMismatchedCodes` / `TestNoCrossRowDoubleClaim` 都把
        `SUSPECTED_NEW_ISSUES` 与 `PENDING_ADJUDICATION` 当跳过集 ——
        修好后不清，那两行就再也不会被正向断言检查（陈旧断言 = 假绿）。
        """
        stale_suspected = set(ADJUDICATED_2026_08_05) & set(SUSPECTED_NEW_ISSUES)
        stale_pending = set(ADJUDICATED_2026_08_05) & set(PENDING_ADJUDICATION)
        assert not stale_suspected, (
            f"{sorted(stale_suspected)} 已裁决落地却仍挂在 SUSPECTED_NEW_ISSUES —— "
            "守卫会继续跳过它们的名称/双算断言"
        )
        assert not stale_pending, (
            f"{sorted(stale_pending)} 已裁决落地却仍挂在 PENDING_ADJUDICATION —— "
            "同上，且 test_pending_adjudication_excluded_from_corrections 会与落地结果冲突"
        )

    def test_adjudicated_rows_not_in_zero_hit_whitelist(self) -> None:
        """裁决为「错码」或「置 NULL」的行不得同时享受零命中白名单豁免。

        `BS-066` 就是这么被漏过的：立项时只查了码（`2811` 零命中）没查名
        （「递延收益」实挂 `2401`）→ 误列白名单当业务事实。
        """
        overlap = set(ADJUDICATED_2026_08_05) & set(ZERO_HIT_WHITELIST)
        assert not overlap, (
            f"{sorted(overlap)} 既已裁决为需修正又在零命中白名单 —— 判据自相矛盾"
        )

    def test_adjudication_reasons_carry_evidence(self) -> None:
        """裁决理由必须写明实证与日期（同 SUSPECTED_NEW_ISSUES 的纪律）。"""
        for row_code, reason in ADJUDICATED_2026_08_05.items():
            assert reason and len(reason.strip()) >= 30, f"{row_code} 的裁决说明过短"
            assert "2026-" in reason or "V144" in reason, (
                f"{row_code} 未写裁决日期或落地迁移号"
            )

