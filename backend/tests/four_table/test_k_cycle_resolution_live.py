"""Task 5 / Property 10~12：K 循环科目定位的**连库真跑**守卫。

与本目录另两个 K 守卫的分工（三者判据不同，不是双真源）：

- :mod:`test_k_cycle_specs`：**不连库**，只校验声明表结构自洽（字段齐备 / 分流 / 留痕）。
- :mod:`test_k_cycle_row_code_evidence`：连库查 ``report_config`` / ``account_chart``
  的**静态事实**，断言声明的 row_code 落在该科目名的码集内。
- 本文件：连库**真实调用** :func:`resolve_report_line_accounts`，断言
  「解析结果」而非「声明值」—— 即声明方向后 `resolved_from` 是否真的转为
  ``report_config``、`extra_standard_codes` 是否真的单列不并入 gross。

🔴 为什么必须真跑而不是源码断言（memory §踩坑铁律，本平台踩过多次）：

    「源码守卫 + 替身单测 + fail-open」这三层组合本身就是缺陷模式 ——
    `_resolve_provision` 那类逻辑写错列名时，源码守卫（查有没有出现某标识符）
    与纯函数替身（不连真实 DB）**都会通过**，只有真实执行会暴露。

连库形态：**一次 `asyncio.run` 取快照 + 全部断言同步**。pytest-asyncio 默认每个
测试新建 event loop，而共享连接池绑定首个 loop → 第二个测试起报
``AttributeError: 'NoneType' object has no attribute 'send'``；若 fixture 里
`except → pytest.skip` 就变成静默假绿。本文件用**一次性 NullPool 引擎**并在同一
loop 内 dispose，完全不碰 `app.core.database` 的共享池。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.services.four_table.k_cycle_specs import (
    K_CYCLE_SPECS,
    liability_spec_for,
)
from app.services.four_table.report_line_accounts import (
    ReportLineAccounts,
    resolve_report_line_accounts,
)

# ─────────────────────────────────────────────────────────────────────────────
# 期望（Property 10~12）
# ─────────────────────────────────────────────────────────────────────────────

#: Requirement 2.5：有公式的负债类循环，声明方向后 `resolved_from` 必须转为
#: `report_config`（改正前这三个都是 `fallback` —— 原值被 split_gross_provision
#: 按 `direction=='credit'` 整体误判成备抵，gross 变空 → 谎报兜底）。
LIABILITY_MUST_RESOLVE: dict[str, tuple[str, str]] = {
    # wp_code: (期望 row_code, 期望解析出的原值标准码)
    "K3": ("BS-050", "2241"),
    "K5": ("BS-065", "2801"),
    "K7": ("BS-066", "2401"),
}

#: K3 的 `2231 应付利息`（财会[2018]15 号并入其他应付款列报）必须落在 `extra`
#: **单列**、不并入 gross —— 并入会让 K3 审定表把应付利息混进其他应付款余额。
K3_EXTRA_CODE = "2231"

#: 资产类循环（无方向声明）解析后的期望，作为「方向声明不影响资产类」的对照。
ASSET_MUST_RESOLVE: dict[str, tuple[str, str]] = {
    "K1": ("BS-009", "1221"),
    "K6": ("BS-012", "1481"),
}

#: K6 备抵独立报表行（`IMP-007 六、持有待售资产减值准备 = TB('1482','期末余额')`）。
K6_PROVISION_ROW = "IMP-007"
K6_PROVISION_CODE = "1482"

#: K6 负债侧（持有待售负债自成一行，不在 BS-012 公式里）。
K6_LIABILITY_ROW = "BS-051"
K6_LIABILITY_CODE = "2245"

#: `report_config` 公式为 NULL 的循环 → 必然退兜底，`resolved_from='fallback'`
#: 是**正确行为**不是缺陷（Requirement 1.11：溯源如实反映，不许伪装成 report_config）。
NULL_FORMULA_EXPECT_FALLBACK: dict[str, str] = {
    "K2": "BS-014",  # 四变体公式全 NULL，兜底 1901
    "K4": "BS-053",  # 四变体公式全 NULL；K4 无兜底码故 gross 为空
}


# ─────────────────────────────────────────────────────────────────────────────
# DB 快照：对每个在册项目 × 每个目标循环真跑一次 resolver
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProjectRef:
    pid: str
    name: str
    year: int
    entity: str
    scope: str

    @property
    def standards(self) -> list[str]:
        """与 `standard_unification_service.derive_applicable_standards` 同口径。

        组合值在前、维度值兜底；stage 不入列表。
        """
        return [f"{self.entity}_{self.scope}", self.entity, self.scope]


@dataclass
class Snapshot:
    projects: list[ProjectRef] = field(default_factory=list)
    #: (pid, wp_code) → 解析结果；`wp_code` 用 `K6#liability` 表示负债侧
    results: dict[tuple[str, str], ReportLineAccounts] = field(default_factory=dict)
    #: (pid, wp_code) → 真跑时抛出的异常（必须为空 —— fail-open 会把接线错误
    #: 伪装成「本项目无此科目」，故这里显式收集并断言无异常）
    errors: dict[tuple[str, str], str] = field(default_factory=dict)
    ok: bool = False
    error: str = ""


_TARGETS: tuple[str, ...] = tuple(
    dict.fromkeys(
        [
            *LIABILITY_MUST_RESOLVE,
            *ASSET_MUST_RESOLVE,
            *NULL_FORMULA_EXPECT_FALLBACK,
        ]
    )
)

#: 负债侧独立解析的伪 wp_code（`results` 的键）
K6_LIABILITY_KEY = "K6#liability"


async def _load(snap: Snapshot) -> None:
    from app.core.config import settings
    from sqlalchemy.ext.asyncio import async_sessionmaker

    url = str(settings.DATABASE_URL)
    engine = create_async_engine(url, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            rows = (
                await db.execute(
                    sa.text(
                        """
                        SELECT id::text, name, audit_year,
                               COALESCE(applicable_standard_v2->>'entity_type','soe') AS ent,
                               COALESCE(report_scope,'standalone') AS scope
                        FROM projects
                        WHERE is_deleted = false AND audit_year IS NOT NULL
                        ORDER BY name
                        """
                    )
                )
            ).all()
            for pid, name, year, ent, scope in rows:
                snap.projects.append(
                    ProjectRef(
                        pid=str(pid),
                        name=str(name or ""),
                        year=int(year),
                        entity=str(ent or "soe").lower(),
                        scope=str(scope or "standalone").lower(),
                    )
                )

            for proj in snap.projects:
                ctx = SimpleNamespace(db=db, project_id=proj.pid, year=proj.year)
                for wp in _TARGETS:
                    spec = K_CYCLE_SPECS.get(wp)
                    if spec is None:
                        continue
                    try:
                        res = await resolve_report_line_accounts(
                            ctx, spec.spec_for(proj.standards)
                        )
                    except Exception as exc:  # noqa: BLE001
                        snap.errors[(proj.pid, wp)] = f"{type(exc).__name__}: {exc}"
                        continue
                    snap.results[(proj.pid, wp)] = res

                lspec = liability_spec_for(proj.standards)
                if lspec is not None:
                    try:
                        res = await resolve_report_line_accounts(ctx, lspec)
                    except Exception as exc:  # noqa: BLE001
                        snap.errors[(proj.pid, K6_LIABILITY_KEY)] = (
                            f"{type(exc).__name__}: {exc}"
                        )
                    else:
                        snap.results[(proj.pid, K6_LIABILITY_KEY)] = res
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
            f"无法连库真跑 resolve_report_line_accounts：{_SNAP.error}\n"
            "本守卫按 Requirement 2.5 必须真跑（源码断言 + 替身单测查不出接线错误），"
            "连不上时判红而非 skip —— skip 会让整组判据静默空转。"
        )
    return _SNAP


# ─────────────────────────────────────────────────────────────────────────────
# 类 A：判据基础设施自检（应当全绿；红了说明守卫本身在空转）
# ─────────────────────────────────────────────────────────────────────────────


def test_snapshot_has_projects_and_results():
    """反向自检：真跑面非空，否则下面全部断言都是空转。"""
    s = snap()
    assert s.projects, "在册项目为 0 —— 本守卫无从真跑，判据空转"
    assert len(s.projects) >= 5, (
        f"在册项目仅 {len(s.projects)} 个（实测应 ≥5）；数量骤降说明取数条件写错，"
        "而非项目真的被删"
    )
    assert s.results, "resolver 一次都没成功跑过 —— 判据空转"
    expected_pairs = len(s.projects) * (len(_TARGETS) + 1)
    assert len(s.results) + len(s.errors) == expected_pairs, (
        f"真跑组合数 {len(s.results) + len(s.errors)} != 期望 {expected_pairs}"
        f"（{len(s.projects)} 项目 × {len(_TARGETS)} 循环 + 负债侧）"
    )


def test_resolver_never_raises():
    """真跑不得抛异常。

    🔴 这条是「fail-open 把接线错误伪装成本项目无此科目」的唯一防线 ——
    生产路径里 render 的 `except Exception` 会把 `TypeError`（签名不匹配）、
    `UndefinedColumnError`（列名写错）吞成 WARNING，表现为取数恒空。
    """
    s = snap()
    assert not s.errors, (
        "resolve_report_line_accounts 真跑抛异常（生产路径会被 fail-open 吞成"
        "「本项目无此科目」）：\n"
        + "\n".join(f"  {pid[:8]}/{wp}: {msg}" for (pid, wp), msg in s.errors.items())
    )


def test_target_cycles_are_all_declared():
    """本守卫覆盖的循环必须都在声明表里（防 spec 改名后守卫静默少测）。"""
    missing = [wp for wp in _TARGETS if wp not in K_CYCLE_SPECS]
    assert not missing, f"守卫期望表引用了声明表里不存在的循环: {missing}"


def test_liability_spec_for_returns_k6_liability_row():
    """`liability_spec_for` 必须产出 K6 负债侧规格（否则负债侧断言全空转）。"""
    spec = liability_spec_for(["soe_standalone", "soe", "standalone"])
    assert spec is not None, "liability_spec_for 返回 None —— 负债侧判据空转"
    assert spec.row_code == K6_LIABILITY_ROW
    assert spec.is_liability is True, (
        "K6 负债侧必须声明 is_liability —— 否则 2245（credit）会被判成备抵、gross 变空"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 类 B：被测实现（Property 10~12）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("wp_code", sorted(LIABILITY_MUST_RESOLVE))
def test_liability_cycles_resolve_from_report_config(wp_code: str):
    """Requirement 2.5：声明方向后负债类循环必须真正走报表公式解析。

    改正前这三个都是 `resolved_from='fallback'` —— 金额碰巧对（兜底码正确），
    但溯源面板谎称「兜底科目」，且客户用非标准码时兜底前缀不中即静默取空。
    """
    s = snap()
    want_row, want_code = LIABILITY_MUST_RESOLVE[wp_code]
    problems: list[str] = []
    for proj in s.projects:
        res = s.results.get((proj.pid, wp_code))
        if res is None:
            continue
        if res.row_code != want_row:
            problems.append(
                f"{proj.name}: row_code={res.row_code} 期望 {want_row}"
            )
        if res.resolved_from != "report_config":
            problems.append(
                f"{proj.name}: resolved_from={res.resolved_from!r} 期望 'report_config'"
                f"（formula={res.formula!r}）—— 负债类未声明方向时原值会被误判成备抵"
            )
        if want_code not in res.gross_standard:
            problems.append(
                f"{proj.name}: gross_standard={res.gross_standard} 未含 {want_code}"
            )
    assert not problems, f"[{wp_code}] " + "\n".join(problems)


def test_k3_extra_code_is_listed_separately():
    """Requirement 2.5 后半：K3 的 `2231` 单列不并入 gross。

    `BS-050 = TB('2241') + TB('2231')` —— 两个码都在公式里，但 K3 的科目余额
    口径是「其他应付款」本身（2241），应付利息（2231）由 K3 披露表单独列示。
    并入 gross 会让审定表未审数把应付利息混进来（数字错，不是取不到）。
    """
    s = snap()
    problems: list[str] = []
    for proj in s.projects:
        res = s.results.get((proj.pid, "K3"))
        if res is None:
            continue
        if K3_EXTRA_CODE in res.gross_standard:
            problems.append(
                f"{proj.name}: {K3_EXTRA_CODE} 混进 gross_standard={res.gross_standard}"
                " —— 应付利息会被算进其他应付款余额"
            )
        if K3_EXTRA_CODE not in (res.extra or {}):
            problems.append(
                f"{proj.name}: extra={res.extra} 未含 {K3_EXTRA_CODE}"
                " —— extra_standard_codes 未生效，披露表拿不到应付利息"
            )
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("wp_code", sorted(ASSET_MUST_RESOLVE))
def test_asset_cycles_still_resolve_from_report_config(wp_code: str):
    """对照组：资产类循环（无方向声明）解析不受方向字段引入影响。

    这条是 additive 零回归的活证据 —— `is_liability` / `gross_direction`
    默认值必须让资产类逐字等价。
    """
    s = snap()
    want_row, want_code = ASSET_MUST_RESOLVE[wp_code]
    problems: list[str] = []
    for proj in s.projects:
        res = s.results.get((proj.pid, wp_code))
        if res is None:
            continue
        if res.row_code != want_row:
            problems.append(f"{proj.name}: row_code={res.row_code} 期望 {want_row}")
        if res.resolved_from != "report_config":
            problems.append(
                f"{proj.name}: resolved_from={res.resolved_from!r} 期望 'report_config'"
            )
        if want_code not in res.gross_standard:
            problems.append(
                f"{proj.name}: gross_standard={res.gross_standard} 未含 {want_code}"
            )
    assert not problems, f"[{wp_code}] " + "\n".join(problems)


def test_k6_provision_comes_from_independent_report_row():
    """K6 备抵必须由独立报表行 `IMP-007` 解析，而非写死字面量兜底。

    ⚠️ 判据**不能**用 `provision_resolved_from == 'report_config'` ——
    平台既有保守口径：`provision_exact` 为 False（反解退化为宽前缀）时会把
    `provision_resolved_from` 降级为 `fallback`（保 D1 零回归）。
    `provision_row_code` 与 `provision_formula` 非空才是「独立报表行生效」的证据。
    """
    s = snap()
    problems: list[str] = []
    for proj in s.projects:
        res = s.results.get((proj.pid, "K6"))
        if res is None:
            continue
        if res.provision_row_code != K6_PROVISION_ROW:
            problems.append(
                f"{proj.name}: provision_row_code={res.provision_row_code!r} "
                f"期望 {K6_PROVISION_ROW!r} —— 备抵未走独立报表行"
            )
        if not res.provision_formula:
            problems.append(
                f"{proj.name}: provision_formula 为空 —— IMP-007 公式未被解析"
            )
        if K6_PROVISION_CODE not in res.provision_standard:
            problems.append(
                f"{proj.name}: provision_standard={res.provision_standard} "
                f"未含 {K6_PROVISION_CODE}"
            )
        if K6_PROVISION_CODE in res.gross_standard:
            problems.append(
                f"{proj.name}: 备抵码 {K6_PROVISION_CODE} 混进 gross_standard"
                f"={res.gross_standard} —— 原值会被备抵抵减两次"
            )
    assert not problems, "\n".join(problems)


def test_k6_liability_side_resolves_independently():
    """K6 负债侧（持有待售负债）自成报表行，必须独立解析且方向正确。"""
    s = snap()
    problems: list[str] = []
    for proj in s.projects:
        res = s.results.get((proj.pid, K6_LIABILITY_KEY))
        if res is None:
            problems.append(f"{proj.name}: 负债侧未产出解析结果")
            continue
        if res.row_code != K6_LIABILITY_ROW:
            problems.append(
                f"{proj.name}: 负债侧 row_code={res.row_code} 期望 {K6_LIABILITY_ROW}"
            )
        if res.resolved_from != "report_config":
            problems.append(
                f"{proj.name}: 负债侧 resolved_from={res.resolved_from!r} "
                "期望 'report_config'"
            )
        if K6_LIABILITY_CODE not in res.gross_standard:
            problems.append(
                f"{proj.name}: 负债侧 gross_standard={res.gross_standard} "
                f"未含 {K6_LIABILITY_CODE}（credit 科目未声明方向时会被判成备抵）"
            )
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("wp_code", sorted(NULL_FORMULA_EXPECT_FALLBACK))
def test_null_formula_cycles_honestly_report_fallback(wp_code: str):
    """Requirement 1.11：公式为 NULL 的循环必须如实报 `fallback`。

    🔴 这是**正向**断言不是缺陷登记 —— `BS-014`/`BS-053` 四变体公式全 NULL，
    退兜底是正确行为；要禁的是「伪装成 report_config」（那会让溯源面板谎称
    「报表规则映射」而实际用的是兜底码）。
    """
    s = snap()
    want_row = NULL_FORMULA_EXPECT_FALLBACK[wp_code]
    problems: list[str] = []
    for proj in s.projects:
        res = s.results.get((proj.pid, wp_code))
        if res is None:
            continue
        if res.row_code != want_row:
            problems.append(f"{proj.name}: row_code={res.row_code} 期望 {want_row}")
        if res.resolved_from != "fallback":
            problems.append(
                f"{proj.name}: resolved_from={res.resolved_from!r} 期望 'fallback'"
                f"（{want_row} 四变体公式均为 NULL，formula={res.formula!r}）"
            )
        if res.formula is not None:
            problems.append(
                f"{proj.name}: formula={res.formula!r} 应为 None —— "
                f"{want_row} 在 report_config 里公式为 NULL"
            )
    assert not problems, f"[{wp_code}] " + "\n".join(problems)


def test_k4_has_no_fallback_code_by_design():
    """K4 无兜底码是**有意为之**（宁缺勿造），gross 为空须可诊断。

    `BS-053 其他流动负债` 四变体公式全 NULL，而「其他流动负债」这个科目名在
    `account_chart` 两侧都零命中（`2301` 全库不存在）⇒ 给兜底码只会取到别的
    科目。故 gross 为空是正确的；关键是**不许伪装成 report_config**。
    """
    s = snap()
    spec = K_CYCLE_SPECS["K4"]
    rspec = spec.spec_for(["soe_standalone", "soe", "standalone"])
    assert rspec.fallback_gross == (), (
        f"K4 不应有兜底码（宁缺勿造），实际 {rspec.fallback_gross}"
    )
    for proj in s.projects:
        res = s.results.get((proj.pid, "K4"))
        if res is None:
            continue
        assert res.gross_standard == [], (
            f"{proj.name}: K4 gross_standard={res.gross_standard} 应为空 —— "
            "有值说明有人补了兜底码，须先确认该码真是「其他流动负债」"
        )


def test_no_cross_cycle_code_collision_in_resolution():
    """解析结果层面的跨循环撞码检查（比声明层更强）。

    声明层撞码由 `test_k_cycle_specs` 查 row_code；本条查**解析出的科目码** ——
    两个循环解析到同一科目意味着该科目余额被算两次（K3 与 K4 曾因 `BS-053`
    撞码，K6 与 G7 曾因 `1511` 撞码）。
    """
    s = snap()
    problems: list[str] = []
    for proj in s.projects:
        owner: dict[str, list[str]] = {}
        for wp in (*_TARGETS, K6_LIABILITY_KEY):
            res = s.results.get((proj.pid, wp))
            if res is None:
                continue
            for code in res.gross_standard:
                owner.setdefault(code, []).append(wp)
        for code, wps in owner.items():
            if len(wps) > 1:
                problems.append(f"{proj.name}: 科目 {code} 被 {wps} 同时认领")
    assert not problems, (
        "解析结果出现跨循环撞码（该科目余额会被算两次）：\n" + "\n".join(problems)
    )
