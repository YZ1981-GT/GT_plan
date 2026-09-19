"""E1 账户级取数的**连库**判据守卫（Wave 1，先打红）。

spec: .kiro/specs/e-cycle-extraction-formula-and-disclosure-completion/
      Requirements 1.1, 1.5, 10.1, 10.2 / Property 1, 2

**为什么必须连库**

账户级明细在 `tb_aux_balance` 的 `aux_type='银行账户'` 维度，而它有两个只有真实库
才能暴露的坑：

1. **非 active dataset 有完全重复行** —— 同一 `aux_dimensions_raw` 两行、
   `closing_balance` 完全相同（一行有 `raw_extra` 一行无）⇒ 裸 `is_deleted == False`
   求和必翻倍。替身测试造不出这种「两个 dataset 各一份」的形态。
2. **active dataset 内同账号可有多行** —— 实测 `a7fc75e5` 的账号
   `1207014210004455` 有 +25,954,468.80 与 −25,874,468.80 两笔（`rows=39` 而
   `names=38`）⇒ 不按账号 GROUP BY 会多出一行。

**两类断言（红必须落在「功能未实现」而不是「守卫写坏了」）**

- **类 A（独立 SQL 口径）**：数据存在性 / 基线计数 / 裸查对照 / 与 `tb_balance`
  叶子勾稽。全部用**本文件自己的 SQL** 算，不碰被测实现 ⇒ 现在就应该绿，
  这证明判据基础设施本身有效（不是空转）。
- **类 B（被测实现）**：`e1_bank_accounts` 的解析 / 聚合 / 归属 / 勾稽产出必须与
  类 A 的 SQL 口径一致 ⇒ Wave 2 Task 4 落地前必红。

🔴 **连库范式**（memory 铁律）：一次 `asyncio.run` 取全部快照 + 全部断言同步。
pytest-asyncio 默认每个测试新建 loop，而 `app.core.database` 的共享池绑定**首个**
loop ⇒ 第二个 async 测试起报 `Event loop is closed`；且用 `create_async_engine`
开**专用 NullPool 引擎**并在同一 loop 内 `dispose()`，全程不碰共享池（防双向污染）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from functools import lru_cache
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.audit_platform_models import TbAuxBalance, TbBalance
from app.services.dataset_query import get_active_filter
from app.services.four_table import (
    aggregate_leaves,
    fetch_tb_subtree,
    resolve_semantic_accounts,
    select_leaves,
)
from app.services.four_table.e_cycle_specs import E1_MONETARY_FUND_SPEC

#: 账户级明细所在的辅助维度（`aux_type`）
AUX_TYPE_BANK_ACCOUNT = "银行账户"

#: 金额比对容差（分以下视为相等）
TOLERANCE = 0.005

#: 冻结实证基线：`project_id 前 8 位 → 科目 1002 的 distinct aux_name 数`。
#:
#: 🔴 数值全部来自 2026-08-08 对真实库的**实测复算**（不是按预期写的）：
#: 口径 = active dataset + `aux_type='银行账户'` + `account_code LIKE '1002%'`
#: 的 `count(DISTINCT aux_name)`。用 `aux_name` 而非解析出的账号作口径，
#: 是为了让基线**不依赖被测解析器**（否则解析器一改基线就跟着漂）。
#:
#: 只许因**数据变更**而变 —— 若某项目计数变了，请重新实测并在此留证，
#: 不要为了让测试变绿而改数字。
#: 🔴 键必须是 **`短码:年度`** 复合键，不能只用短码 —— 同一 `project_id` 可有多个
#: 审计年度且账户数不同（实测 `2aa00f57` 2024=23 / 2025=17）。按短码建索引时两行
#: 会**互相覆盖**，基线就会比到错的那个年度（首轮实测即把 17 比到了 2024 的 23 上，
#: 报出「基线不符」的假警报）。
ACCOUNT_COUNT_BASELINE: dict[str, int] = {
    "52c04ed1:2025": 21,  # 重庆医药集团医疗器械有限公司
    "b39809ed:2025": 6,   # 重庆医药集团和平物流有限公司
    "4f6dbc36:2025": 2,   # 重庆医药集团四川物流有限公司
    "c8621493:2025": 1,   # 重庆医药集团宜宾医药有限公司新健康大药房临港店
    "f064f5e4:2024": 23,  # 重庆和平药房连锁有限责任公司
    "2aa00f57:2024": 23,  # 重庆和平药房连锁有限责任公司（同项目另一年度）
    "2aa00f57:2025": 17,  # 重庆和平药房连锁有限责任公司
    "0ec33ac9:2025": 22,  # 重药控股安徽有限公司
    "12c15a96:2025": 22,  # 实测补录（首轮基线漏了该项目）
    "a7fc75e5:2025": 38,  # 陕西华氏医药有限公司
}


# ─────────────────────────── 快照数据结构 ────────────────────────────────


@dataclass
class SlotFacts:
    """一个语义槽的科目前缀与 `tb_balance` 叶子合计。"""

    key: str
    found: bool
    codes: tuple[str, ...]
    leaf_opening: float
    leaf_closing: float


@dataclass
class AuxAccountFacts:
    """一条按账号聚合后的账户级事实（口径全部来自本文件的 SQL）。"""

    account_code: str
    aux_name: str
    dims_raw: str
    currency: str
    opening: float
    closing: float
    row_count: int


@dataclass
class ProjectFacts:
    project_id: str
    short_id: str
    client_name: str
    year: int
    slots: dict[str, SlotFacts] = field(default_factory=dict)
    #: `aux_type='银行账户'` 的账户级明细（active dataset，按 `(科目, aux_name)` 聚合）
    aux_accounts: list[AuxAccountFacts] = field(default_factory=list)
    #: 每个科目的 active 合计（独立 SQL 口径）
    aux_active_by_code: dict[str, float] = field(default_factory=dict)
    #: 每个科目的**裸查**合计（`is_deleted == False`，用于反向自检「必翻倍」）
    aux_naive_by_code: dict[str, float] = field(default_factory=dict)
    #: 科目 1002 的 `count(DISTINCT aux_name)`（对基线）
    name_count_1002: int = 0
    #: aux 侧出现的非记账本位币（供 AC 1.9 的提示信号断言）
    foreign_currencies: tuple[str, ...] = ()


@dataclass
class Snapshot:
    projects: list[ProjectFacts] = field(default_factory=list)
    load_error: str = ""


# ─────────────────────────── 快照加载（一次 asyncio.run）──────────────────


def _num(v: object) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


async def _collect(db, proj) -> ProjectFacts:
    year = int(proj.audit_year)
    pf = ProjectFacts(
        project_id=str(proj.id),
        short_id=str(proj.id)[:8],
        client_name=proj.client_name or "",
        year=year,
    )

    # ── 语义槽 + tb_balance 叶子合计（既有共享件，Task 4 之前就存在）──────
    ctx = SimpleNamespace(db=db, project_id=proj.id, year=year)
    accounts = await resolve_semantic_accounts(ctx, E1_MONETARY_FUND_SPEC)
    prefixes: list[str] = []
    for slot in (accounts.slots or {}).values():
        prefixes.extend(slot.codes or [])
    prefixes = [p for p in dict.fromkeys(prefixes) if p]

    subtree = await fetch_tb_subtree(db, proj.id, year, prefixes) if prefixes else []
    leaves = select_leaves(subtree)
    for key, slot in (accounts.slots or {}).items():
        codes = tuple(slot.codes or [])
        agg = aggregate_leaves(leaves, list(codes)) if codes else {"opening": 0.0, "closing": 0.0}
        pf.slots[key] = SlotFacts(
            key=key,
            found=bool(slot.found),
            codes=codes,
            leaf_opening=_num(agg.get("opening")),
            leaf_closing=_num(agg.get("closing")),
        )

    if not prefixes:
        return pf

    like_clause = sa.or_(*[TbAuxBalance.account_code.like(f"{p}%") for p in prefixes])

    # ── aux 侧：active dataset，按 (科目, aux_name) 聚合（独立 SQL 口径）──
    active_filter = await get_active_filter(db, TbAuxBalance.__table__, proj.id, year)
    rows = (
        await db.execute(
            sa.select(
                TbAuxBalance.account_code.label("code"),
                TbAuxBalance.aux_name.label("nm"),
                sa.func.max(sa.func.coalesce(TbAuxBalance.aux_dimensions_raw, "")).label("dims"),
                sa.func.max(sa.func.coalesce(TbAuxBalance.currency_code, "")).label("cur"),
                sa.func.count().label("n"),
                sa.func.sum(sa.func.coalesce(TbAuxBalance.opening_balance, 0)).label("os"),
                sa.func.sum(sa.func.coalesce(TbAuxBalance.closing_balance, 0)).label("cs"),
            )
            .where(
                sa.and_(
                    active_filter,
                    TbAuxBalance.aux_type == AUX_TYPE_BANK_ACCOUNT,
                    like_clause,
                )
            )
            .group_by(TbAuxBalance.account_code, TbAuxBalance.aux_name)
            .order_by(TbAuxBalance.account_code, TbAuxBalance.aux_name)
        )
    ).fetchall()
    for r in rows:
        pf.aux_accounts.append(
            AuxAccountFacts(
                account_code=(r.code or "").strip(),
                aux_name=(r.nm or "").strip(),
                dims_raw=(r.dims or "").strip(),
                currency=(r.cur or "").strip(),
                opening=_num(r.os),
                closing=_num(r.cs),
                row_count=int(r.n or 0),
            )
        )
    for a in pf.aux_accounts:
        pf.aux_active_by_code[a.account_code] = (
            pf.aux_active_by_code.get(a.account_code, 0.0) + a.closing
        )
    pf.name_count_1002 = len(
        {a.aux_name for a in pf.aux_accounts if a.account_code.startswith("1002")}
    )
    pf.foreign_currencies = tuple(
        sorted(
            {
                a.currency.upper()
                for a in pf.aux_accounts
                if a.currency and a.currency.upper() not in ("CNY", "RMB")
            }
        )
    )

    # ── aux 侧：裸查（无 dataset 过滤）—— 反向自检「必翻倍」的对照口径 ─────
    naive = (
        await db.execute(
            sa.select(
                TbAuxBalance.account_code.label("code"),
                sa.func.sum(sa.func.coalesce(TbAuxBalance.closing_balance, 0)).label("cs"),
            )
            .where(
                sa.and_(
                    TbAuxBalance.project_id == proj.id,
                    TbAuxBalance.year == year,
                    TbAuxBalance.is_deleted == sa.false(),
                    TbAuxBalance.aux_type == AUX_TYPE_BANK_ACCOUNT,
                    like_clause,
                )
            )
            .group_by(TbAuxBalance.account_code)
        )
    ).fetchall()
    for r in naive:
        pf.aux_naive_by_code[(r.code or "").strip()] = _num(r.cs)

    return pf


async def _load_async() -> Snapshot:
    snap = Snapshot()
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {},
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            projs = (
                await db.execute(
                    sa.text(
                        "SELECT id, client_name, audit_year FROM projects "
                        "WHERE is_deleted = false AND audit_year IS NOT NULL "
                        "ORDER BY client_name, audit_year"
                    )
                )
            ).fetchall()
            for p in projs:
                snap.projects.append(await _collect(db, p))
    finally:
        await engine.dispose()
    return snap


@lru_cache(maxsize=1)
def _snapshot() -> Snapshot:
    """加载一次真实库快照。失败时把原因带进 Snapshot 供测试如实报告。"""
    try:
        return asyncio.run(_load_async())
    except Exception as e:  # noqa: BLE001 — 连不上库时如实报告而不是静默 skip
        return Snapshot(load_error=f"{type(e).__name__}: {e}")


def _require_db() -> Snapshot:
    snap = _snapshot()
    if snap.load_error:
        pytest.skip(f"真实库不可用，本连库守卫无法验证：{snap.load_error}")
    if not snap.projects:
        pytest.skip("真实库无在册项目（is_deleted=false 且 audit_year 非空），无法验证")
    return snap


def _with_accounts(snap: Snapshot) -> list[ProjectFacts]:
    return [p for p in snap.projects if p.aux_accounts]


# ═══════════════════ 类 A：独立 SQL 口径（应当已绿）════════════════════════


class TestAuxDataSourceAvailable:
    """账户级数据源本身可用 —— 这组绿了才说明后面的判据不是空转。"""

    def test_at_least_one_project_has_bank_accounts(self):
        snap = _require_db()
        withacc = _with_accounts(snap)
        detail = " / ".join(
            f"{p.short_id}:{len(p.aux_accounts)}" for p in snap.projects
        )
        assert withacc, (
            "全部项目都取不到 aux_type='银行账户' 的账户级明细。"
            f"逐项目账户数：{detail}。"
            "若确认当前库无该维度数据，请先导入含银行账户辅助维度的序时账/余额表。"
        )

    def test_account_count_matches_baseline(self):
        """科目 1002 的 distinct aux_name 数必须与冻结基线相符。

        🔴 索引键是 **`短码:年度`** —— 只用短码会让同一项目的多个年度互相覆盖
        （见 `ACCOUNT_COUNT_BASELINE` 的注释：实测 `2aa00f57` 2024=23 / 2025=17）。
        """
        snap = _require_db()
        by_key = {f"{p.short_id}:{p.year}": p for p in snap.projects}
        # 反向自检：复合键不得因覆盖而丢项目
        assert len(by_key) == len(snap.projects), (
            f"复合键发生覆盖（{len(by_key)} != {len(snap.projects)}）—— "
            "同一项目同一年度出现多行？"
        )
        mismatch: list[str] = []
        checked = 0
        for key, expect in ACCOUNT_COUNT_BASELINE.items():
            pf = by_key.get(key)
            if pf is None:
                continue
            checked += 1
            if pf.name_count_1002 != expect:
                mismatch.append(
                    f"{key}({pf.client_name}) 实测 {pf.name_count_1002} != 基线 {expect}"
                )
        assert checked > 0, (
            "基线里的项目在当前库中一个都不存在，基线已完全过期。"
            f"当前库项目：{sorted(by_key)}"
        )
        assert not mismatch, (
            "科目 1002 的账户数与冻结基线不符：" + "；".join(mismatch) + "。"
            "若确因数据重导而变化，请重新实测并更新 ACCOUNT_COUNT_BASELINE 并在注释里留证；"
            "不要为了让测试变绿而改数字。"
        )

    def test_aux_active_sum_ties_to_tb_balance_leaves(self):
        """核心勾稽：aux 账户级合计 == tb_balance 叶子合计（逐科目）。

        这是 Property 1 的独立 SQL 口径 —— 不碰被测实现，故它是「数据源可用」
        的证据而不是「实现正确」的证据。
        """
        snap = _require_db()
        withacc = _with_accounts(snap)
        if not withacc:
            pytest.skip("无项目含账户级明细（已由上一条测试报告）")
        bad: list[str] = []
        for pf in withacc:
            # 逐科目：aux 合计 vs 该科目在 tb_balance 的叶子合计
            for code, aux_sum in sorted(pf.aux_active_by_code.items()):
                leaf_rows = [
                    s for s in pf.slots.values() if code in s.codes
                ]
                if not leaf_rows:
                    # 该 aux 科目未被任何槽声明 —— 属 unassigned，不在本条判据内
                    continue
                # 槽的叶子合计是「该槽全部科目」的和，故只在槽恰好只声明该一个码时可直比
                slot = leaf_rows[0]
                if len(slot.codes) != 1:
                    continue
                if abs(aux_sum - slot.leaf_closing) > TOLERANCE:
                    bad.append(
                        f"{pf.short_id}/{code} aux={aux_sum:.2f} vs 叶子={slot.leaf_closing:.2f} "
                        f"diff={aux_sum - slot.leaf_closing:.2f}"
                    )
        assert not bad, (
            "aux 账户级合计与 tb_balance 叶子合计不符（两者应逐分相等）：" + "；".join(bad)
        )

    def test_aux_dimensions_raw_carries_both_bank_and_account(self):
        """`aux_dimensions_raw` 一行即含「金融机构」与「银行账户」两个维度。

        这是「不需要跨 aux_type 配对」这一设计前提的实证；若某天导出格式变了，
        这条会打红并提示解析器要走降级路径。
        """
        snap = _require_db()
        withacc = _with_accounts(snap)
        if not withacc:
            pytest.skip("无项目含账户级明细")
        with_dims = [a for p in withacc for a in p.aux_accounts if a.dims_raw]
        assert with_dims, (
            "全部账户行的 aux_dimensions_raw 都为空 —— 解析器只能走 level 3 降级"
            "（账号取 aux_name、银行名留空）。这不是缺陷但要确认前端提示到位。"
        )
        both = [a for a in with_dims if "银行账户" in a.dims_raw and "金融机构" in a.dims_raw]
        assert both, (
            "没有任何账户行的 aux_dimensions_raw 同时含「金融机构」与「银行账户」；"
            f"样本：{[a.dims_raw[:80] for a in with_dims[:3]]}"
        )


class TestNaiveQueryDoublesReverseSelfCheck:
    """反向自检：去掉 dataset 过滤必然翻倍 —— 证明 get_active_filter 是必要的。"""

    def test_naive_query_differs_from_active(self):
        snap = _require_db()
        withacc = _with_accounts(snap)
        if not withacc:
            pytest.skip("无项目含账户级明细")
        differing: list[str] = []
        for pf in withacc:
            for code, active_sum in sorted(pf.aux_active_by_code.items()):
                naive_sum = pf.aux_naive_by_code.get(code)
                if naive_sum is None:
                    continue
                if abs(naive_sum - active_sum) > TOLERANCE:
                    differing.append(
                        f"{pf.short_id}/{code} active={active_sum:.2f} naive={naive_sum:.2f}"
                    )
        if not differing:
            pytest.skip(
                "反向自检暂不可验证：当前库每个项目的该维度只有一个 dataset，"
                "裸查与 active 查结果相同。一旦出现多 dataset 项目本条即生效。"
                "⚠️ 这不等于可以省掉 get_active_filter —— 实测曾出现完全重复行。"
            )
        assert differing, "unreachable"  # 上面已处理

    def test_active_sum_is_the_one_tying_to_tb_balance(self):
        """在裸查与 active 不同的项目上，**只有 active 口径**与 tb_balance 勾稽。"""
        snap = _require_db()
        withacc = _with_accounts(snap)
        if not withacc:
            pytest.skip("无项目含账户级明细")
        proofs: list[str] = []
        for pf in withacc:
            for code, active_sum in sorted(pf.aux_active_by_code.items()):
                naive_sum = pf.aux_naive_by_code.get(code)
                if naive_sum is None or abs(naive_sum - active_sum) <= TOLERANCE:
                    continue
                slot = next((s for s in pf.slots.values() if s.codes == (code,)), None)
                if slot is None:
                    continue
                assert abs(active_sum - slot.leaf_closing) <= TOLERANCE, (
                    f"{pf.short_id}/{code}: active 口径也与 tb_balance 不符 "
                    f"(active={active_sum:.2f} 叶子={slot.leaf_closing:.2f})"
                )
                assert abs(naive_sum - slot.leaf_closing) > TOLERANCE, (
                    f"{pf.short_id}/{code}: 裸查口径竟然也与 tb_balance 相符 "
                    f"(naive={naive_sum:.2f} 叶子={slot.leaf_closing:.2f})，"
                    "反向自检失去意义，请核对该项目的 dataset 状态"
                )
                proofs.append(f"{pf.short_id}/{code}")
        if not proofs:
            pytest.skip("当前库无「裸查与 active 不同」的项目，本条无从取证")


class TestSameAccountMultipleRows:
    """active dataset 内同账号多行必须被聚合（Property 2 的数据前提）。"""

    def test_multi_row_accounts_are_aggregated_by_name(self):
        snap = _require_db()
        withacc = _with_accounts(snap)
        if not withacc:
            pytest.skip("无项目含账户级明细")
        multi = [
            (p.short_id, a) for p in withacc for a in p.aux_accounts if a.row_count > 1
        ]
        if not multi:
            pytest.skip(
                "当前库无「同账号多行」样本，Property 2 的数据前提暂不可验证。"
                "⚠️ 实测曾出现（a7fc75e5 的 1207014210004455 有两笔 ±25,954,468.80），"
                "故聚合逻辑仍不可省。"
            )
        # 有样本时断言：聚合后每个 (科目, 账号) 只出现一次
        for short, a in multi:
            same = [
                x
                for p in withacc
                if p.short_id == short
                for x in p.aux_accounts
                if x.account_code == a.account_code and x.aux_name == a.aux_name
            ]
            assert len(same) == 1, (
                f"{short}/{a.account_code}/{a.aux_name} 聚合后仍有 {len(same)} 行，"
                "说明 GROUP BY 口径不对"
            )


# ═══════════════════ 类 B：被测实现（Task 4 落地前必红）══════════════════


def _import_impl():
    """import 被测模块；未实现时 fail（**不是 skip**）。

    🔴 用 `pytest.fail` 而不是模块顶层 import：顶层 import 失败会让整个文件
    collection error、零断言执行 ⇒ 无法区分「功能未实现」与「守卫写坏了」。
    """
    try:
        from app.services.four_table import e1_bank_accounts as impl  # noqa: PLC0415
    except ImportError as e:
        pytest.fail(
            "app.services.four_table.e1_bank_accounts 尚未实现（Wave 2 Task 4）。"
            f"import 失败：{e}。本条红是**预期**的 Wave 1 打红结果。"
        )
    return impl


class TestImplementationMatchesSqlBaseline:
    """被测实现的产出必须与类 A 的独立 SQL 口径一致。"""

    def test_module_exposes_required_api(self):
        impl = _import_impl()
        missing = [
            name
            for name in (
                "parse_aux_dimensions",
                "fetch_e1_bank_accounts",
                "assign_accounts_to_slots",
                "check_accounts_vs_leaves",
                "build_e1_account_prefill",
            )
            if not hasattr(impl, name)
        ]
        assert not missing, f"e1_bank_accounts 缺少必需 API：{missing}"

    def test_parse_handles_real_dims_raw(self):
        """用真实库里的 `aux_dimensions_raw` 跑解析器，账号必须与 aux_name 相符。"""
        impl = _import_impl()
        snap = _require_db()
        withacc = _with_accounts(snap)
        if not withacc:
            pytest.skip("无项目含账户级明细")
        bad: list[str] = []
        for pf in withacc:
            for a in pf.aux_accounts:
                got = impl.parse_aux_dimensions(a.dims_raw or None, a.aux_name)
                if a.dims_raw and "银行账户" in a.dims_raw:
                    if got.account_no != a.aux_name:
                        bad.append(
                            f"{pf.short_id}/{a.account_code}: 解析出账号 {got.account_no!r} "
                            f"与 aux_name {a.aux_name!r} 不符（dims={a.dims_raw[:70]!r}）"
                        )
                    if not got.bank_name:
                        bad.append(
                            f"{pf.short_id}/{a.account_code}: dims 含金融机构但银行名为空"
                            f"（dims={a.dims_raw[:70]!r}）"
                            if "金融机构" in a.dims_raw
                            else ""
                        )
        bad = [b for b in bad if b]
        assert not bad, "解析器与真实 aux_dimensions_raw 不符：" + "；".join(bad[:8])

    def test_fetch_result_ties_to_sql_baseline(self):
        """`fetch_e1_bank_accounts` 的合计必须等于类 A 的 active SQL 合计。"""
        impl = _import_impl()
        snap = _require_db()
        withacc = _with_accounts(snap)
        if not withacc:
            pytest.skip("无项目含账户级明细")
        # 被测实现是 async，这里在**同一次** asyncio.run 里跑完全部项目
        async def _run() -> dict[str, dict[str, float]]:
            url = settings.DATABASE_URL
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            engine = create_async_engine(
                url,
                poolclass=NullPool,
                connect_args={"ssl": False}
                if getattr(settings, "DB_DISABLE_SSL", False)
                else {},
            )
            Session = async_sessionmaker(engine, expire_on_commit=False)
            out: dict[str, dict[str, float]] = {}
            try:
                async with Session() as db:
                    for pf in withacc:
                        prefixes = sorted(
                            {c for s in pf.slots.values() for c in s.codes}
                        )
                        rows = await impl.fetch_e1_bank_accounts(
                            db, pf.project_id, pf.year, account_prefixes=prefixes
                        )
                        agg: dict[str, float] = {}
                        for r in rows:
                            agg[r.account_code] = agg.get(r.account_code, 0.0) + float(
                                r.closing
                            )
                        out[pf.short_id] = agg
            finally:
                await engine.dispose()
            return out

        got = asyncio.run(_run())
        bad: list[str] = []
        for pf in withacc:
            impl_agg = got.get(pf.short_id, {})
            for code, sql_sum in sorted(pf.aux_active_by_code.items()):
                impl_sum = impl_agg.get(code, 0.0)
                if abs(impl_sum - sql_sum) > TOLERANCE:
                    bad.append(
                        f"{pf.short_id}/{code} 实现={impl_sum:.2f} vs 独立SQL={sql_sum:.2f}"
                    )
        assert not bad, (
            "fetch_e1_bank_accounts 与独立 SQL 口径不符：" + "；".join(bad[:8])
        )
