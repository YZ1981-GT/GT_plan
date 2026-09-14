"""报表行 → 科目金额解析守卫（四态 / 不兜 0 / 复用报表引擎）。

Feature: procedure-trim-report-line-account-resolution — Task 2（Wave 1 打红）
Requirements: 4.1, 4.2, 4.3, 7.1（Task 6 追加 1.5 / 2.2 / 2.3 / 2.4）
Validates: Property 6（复用报表引擎、不按槽拆）, Property 9（``ROW()`` 拒解析）,
           Property 11（准则未设置即不可解析）, Property 12（四态可区分且非 resolved 恒无金额）,
           Property 13（异常记 ERROR 且不阻断）

═══ 断言分两类 ═══

- **类 A = 独立口径判据**：``ReportFormulaParser`` 的方法签名（读源码 + inspect，不实例化）、
  真实库 ``report_config`` 的公式事实、真实库项目准则分布、
  ``derive_applicable_standards`` 永不为空的反向自检、零 0 冒充判据的反向自检。
  **现在就应全绿**。
- **类 B = 被测实现**：``trim_report_line_amounts`` 的存在与行为。
  **Task 5 之前应全红**。

🔴 禁在模块顶层 import 生产模块（顶层失败 = collection error = 零断言执行）。

═══ 真实库实证（2026-08-15，只读）═══

- ``BS-002``（货币资金）四个准则变体的 formula **逐字相同** ⇒ E 循环基准可跨变体复用::

      TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')

- ``BS-006``（应收账款）四变体**不全相同** ⇒ 准则维度真实存在::

      listed_consolidated  TB('1122','期末余额')
      listed_standalone    TB('1122','期末余额') - TB('1231','期末余额')
      soe_consolidated     TB('1122','期末余额')
      soe_standalone       TB('1122','期末余额') - TB('1231-02','期末余额')

- ``BS-069``（非流动负债合计）公式**全是 ``ROW()`` 引用** ⇒ Property 9 的真实样本
  （J1 在 soe 准则下声明的就是这个号）。
- ``projects`` 实测 **8 个已设准则（全部 soe_standalone）+ 24 个 NULL**
  ⇒ ``standard_unset`` 是真实库主流状态，不是边缘态；``listed_*`` 与
  ``soe_consolidated`` 在库中**无项目** ⇒ Task 14 对它们输出 ``UNVERIFIABLE``。
- 🔴 **``derive_applicable_standards`` 永不为空** —— 无法推断时补
  ``DEFAULT_STANDARD = {entity_type: soe, scope: standalone}``。故 R3.3 的
  「准则未设置」**不能**靠它判（会把 24 个未填准则的项目静默算成国企个别报表），
  必须直读 ``projects.applicable_standard_v2`` 判空。下方有一条类 A 判据钉死这一点。
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import io
import re
import tokenize
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
_AMOUNTS_PATH = _BACKEND / "app" / "services" / "trim_report_line_amounts.py"
_ENGINE_PATH = _BACKEND / "app" / "services" / "report_engine.py"

_NOT_IMPLEMENTED = "尚未实现（Task 5）。本条红是预期的 Wave 1 打红结果"

#: 四个准则变体（`report_config.applicable_standard` 的取值域）
_STANDARDS = (
    "listed_consolidated",
    "listed_standalone",
    "soe_consolidated",
    "soe_standalone",
)


# ═══════════════════════════════════════════════════════════════════════════
# 剥注释 helper + 反向自检
# ═══════════════════════════════════════════════════════════════════════════
def _strip_py_comments(src: str) -> str:
    """只剥 ``#`` 注释，保留普通字符串字面量。"""
    spans: list[tuple[int, int]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                spans.append((tok.start[0], tok.start[1]))
    except tokenize.TokenError:  # pragma: no cover
        return src
    lines = src.splitlines()
    for row, col in spans:
        if 1 <= row <= len(lines):
            lines[row - 1] = lines[row - 1][:col]
    return "\n".join(lines)


def _code_only(src: str) -> str:
    """剥 ``#`` 注释与全部 docstring，保留普通字符串字面量。

    本文件的判据大量形如「代码里**不得**出现 X」（不得引用 slot、不得自己求和、
    异常不得降级为 WARNING）。被测模块的 docstring 会**有意**写这些反例作为设计留痕
    ⇒ 不剥 docstring 会把说明文字数成真实使用，判据在正确实现上打红。
    """
    no_comment = _strip_py_comments(src)
    try:
        tree = ast.parse(no_comment)
    except SyntaxError:  # pragma: no cover
        return no_comment
    lines = no_comment.splitlines()
    blank: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", None) or []
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                blank.add(ln)
    return "\n".join("" if (i + 1) in blank else ln for i, ln in enumerate(lines))


def test_code_only_self_check_both_directions():
    """🔴 剥注释 helper 双向自检。"""
    sample = '''
"""docstring 提到 SemanticAccountSpec 与 WARNING 作为反例留痕。"""
LOG_TEMPLATE = "取数失败 wp=%s"


def f():
    """函数 docstring 也提到 slot 拆分。"""
    return LOG_TEMPLATE
'''
    code = _code_only(sample)
    assert "SemanticAccountSpec" not in code, "docstring 未剥 —— 反例说明会被数成真实引用"
    assert "slot 拆分" not in code, "函数 docstring 未剥"
    assert "取数失败 wp=%s" in code, "普通字符串字面量被误剥 —— 日志模板判据会全部失效"


# ═══════════════════════════════════════════════════════════════════════════
# 零 0 冒充判据 + 反向自检（本 spec 最关键的一条不变式）
# ═══════════════════════════════════════════════════════════════════════════
def _find_zero_masquerade(items, resolved_status: str) -> list[str]:
    """找出「状态非 resolved 却带了金额」的项；返回违规描述（空 = 合规）。

    🔴 判据必须查 ``is not None`` 而**不是** falsy —— ``0.0`` 是 falsy，
    用 ``if amt:`` 会把「编造 0」当合规放过。编造 0 的后果：该程序被误判成
    「低于任何阈值」而产生裁剪建议，而正确结论是「该维度对它不可用」。
    """
    bad: list[str] = []
    for key, it in (items or {}).items():
        status = getattr(it, "status", None)
        if status == resolved_status:
            continue
        if not hasattr(it, "amount"):
            bad.append(f"{key}: 缺 amount 字段（应为 None 而非缺键）")
            continue
        amount = getattr(it, "amount")
        if amount is not None:
            bad.append(f"{key}: status={status!r} 却带 amount={amount!r}（应为 None）")
    return bad


def test_zero_masquerade_detector_catches_zero_not_just_truthy():
    """🔴 反向自检：``amount = 0.0`` 且状态非 resolved 必须被抓到。

    若本条打红（检测器放过了 0.0），说明它查的是 falsy 而不是 ``None``
    ⇒ 「不兜 0」这条判据是空转，被测实现编造 0 也会全绿。
    """
    fake = {
        "E1": SimpleNamespace(status="no_report_line", amount=0.0),
        "D2": SimpleNamespace(status="resolved", amount=0.0),  # resolved 下 0 合法
    }
    bad = _find_zero_masquerade(fake, "resolved")
    assert len(bad) == 1, f"检测器应恰抓到 1 项（E1），实得 {bad}"
    assert "E1" in bad[0], f"抓错了项：{bad}"
    assert "0.0" in bad[0], "违规描述未带实际值 —— 排查时看不出是编造 0 还是别的数"


def test_zero_masquerade_detector_catches_missing_key():
    """🔴 反向自检：缺 ``amount`` 字段也算违规（R4.2 要求「或 amount 为 null」）。"""
    fake = {"L2": SimpleNamespace(status="no_report_line")}
    bad = _find_zero_masquerade(fake, "resolved")
    assert bad and "缺 amount" in bad[0], f"缺键未被抓到：{bad}"


def test_zero_masquerade_detector_passes_compliant_sample():
    """🔴 反向自检（正向）：合规样本不得误报。"""
    fake = {
        "L2": SimpleNamespace(status="no_report_line", amount=None),
        "E1": SimpleNamespace(status="resolved", amount=8607977.04),
    }
    assert _find_zero_masquerade(fake, "resolved") == []


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-1：报表取数引擎的接口事实（读源码 + inspect，不实例化）
# ═══════════════════════════════════════════════════════════════════════════
def test_report_formula_parser_exposes_required_methods():
    """类 A（R2.1）：``ReportFormulaParser`` 的三个方法存在且签名可用。

    金额解析必须复用它 —— 自己聚合科目会引入第二个金额口径，
    审计师会在报表页看到一个数、在裁剪建议里看到另一个数，且无从判断该信哪个。
    """
    try:
        from app.services.report_engine import ReportFormulaParser
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import ReportFormulaParser: {e!r}")

    init_params = list(inspect.signature(ReportFormulaParser.__init__).parameters)
    assert init_params[:4] == ["self", "db", "project_id", "year"], (
        f"构造签名已变更：{init_params} —— 金额解析的实例化方式须同步"
    )

    for name, expected_params in (
        ("execute", ["self", "formula", "row_cache"]),
        ("extract_account_codes", ["self", "formula"]),
        ("extract_row_refs", ["self", "formula"]),
    ):
        method = getattr(ReportFormulaParser, name, None)
        assert method is not None, f"ReportFormulaParser 无 {name} 方法"
        params = list(inspect.signature(method).parameters)
        assert params == expected_params, f"{name} 签名已变更：{params}"

    assert inspect.iscoroutinefunction(ReportFormulaParser.execute), (
        "execute 不再是 async —— 金额解析的调用方式须同步"
    )


def test_report_engine_does_prefix_aggregation():
    """类 A（R2.2）：报表引擎的 ``TB()`` 走前缀聚合（``LIKE 'code%'``）。

    这是「不必自己实现前缀聚合」的依据 —— 若上游改成精确码匹配，
    本 spec 的 R2.2 就落空了，必须在此打红提醒。
    """
    code = _code_only(_ENGINE_PATH.read_text(encoding="utf-8"))
    assert "_get_tb_rows_prefix" in code, "报表引擎无 _get_tb_rows_prefix —— 前缀聚合口径已变"
    assert 'like(f"{account_code}%")' in code, (
        "前缀聚合的 LIKE 表达式已变更 —— R2.2 的依据须复核"
    )


def test_derive_applicable_standards_never_returns_empty():
    """🔴 类 A（R3.3 的关键设计约束）：``derive_applicable_standards`` 永不为空。

    它在无法推断时补 ``DEFAULT_STANDARD``（soe / standalone）⇒ **不能**用它判
    「项目未设置准则」。真实库有 24 个 ``applicable_standard_v2 IS NULL`` 的项目，
    用它判会把这些项目静默算成国企个别报表并给出金额 —— 那正是 R3.3 禁止的
    「默认取某一个变体」。

    故金额解析必须**直读** ``projects.applicable_standard_v2`` 判空。
    本条打红（该函数变成可返回空）时，R3.3 的实现可以简化，须同步复核。
    """
    try:
        from app.services.standard_unification_service import (
            DEFAULT_STANDARD,
            derive_applicable_standards,
        )
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import derive_applicable_standards: {e!r}")

    for empty_input in (None, {}, {"entity_type": None}, {"bogus": "x"}):
        got = derive_applicable_standards(empty_input)
        assert got, f"入参 {empty_input!r} 竟返回空 —— 请复核 R3.3 的实现路径"
        assert got[0] == f"{DEFAULT_STANDARD['entity_type']}_{DEFAULT_STANDARD['scope']}", (
            f"入参 {empty_input!r} 的兜底首值为 {got[0]!r}，与 DEFAULT_STANDARD 不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 类 A-2：连库事实（现在应绿）
# ═══════════════════════════════════════════════════════════════════════════
_LIVE_FORMULA_SQL = """
SELECT row_code, applicable_standard, row_name, formula
FROM report_config
WHERE row_code = ANY(:codes) AND is_deleted = false
"""

_LIVE_PROJECT_SQL = """
SELECT id::text AS pid, name, audit_year, applicable_standard_v2,
       template_type, report_scope,
       (SELECT count(*) FROM procedure_instances pi WHERE pi.project_id = p.id) AS pi_n,
       (SELECT count(*) FROM trial_balance tb
          WHERE tb.project_id = p.id AND tb.is_deleted = false)                 AS tb_n
FROM projects p
WHERE is_deleted = false
  AND EXISTS (SELECT 1 FROM procedure_instances pi WHERE pi.project_id = p.id)
ORDER BY pi_n DESC
"""


def _live_snapshot():
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                formulas = [
                    dict(r._mapping)
                    for r in (
                        await conn.execute(
                            sa.text(_LIVE_FORMULA_SQL),
                            {"codes": ["BS-002", "BS-006", "BS-069", "IS-001"]},
                        )
                    ).all()
                ]
                projects = [
                    dict(r._mapping)
                    for r in (await conn.execute(sa.text(_LIVE_PROJECT_SQL))).all()
                ]
            return {"formulas": formulas, "projects": projects}
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"真实库不可达（本组为连库判据）: {e!r}")


@pytest.fixture(scope="module")
def live():
    return _live_snapshot()


def _formula_map(live) -> dict[tuple[str, str], str | None]:
    return {(r["row_code"], r["applicable_standard"]): r["formula"] for r in live["formulas"]}


def test_live_bs002_formula_identical_across_standards(live):
    """类 A：``BS-002`` 四变体公式逐字相同（E 循环基准，本 spec 的立项现场）。"""
    fm = _formula_map(live)
    got = {std: fm.get(("BS-002", std)) for std in _STANDARDS}
    missing = [s for s, f in got.items() if not f]
    assert not missing, f"BS-002 在以下变体无公式：{missing}"
    assert len(set(got.values())) == 1, (
        f"BS-002 四变体公式不再逐字相同 —— E 循环基准须按变体分别验：{got}"
    )
    only = next(iter(set(got.values())))
    for code in ("1001", "1002", "1012"):
        assert code in only, f"BS-002 公式不再引用 {code} —— 实测基准金额须重算：{only}"


def test_live_bs006_formula_differs_by_standard(live):
    """类 A（R3.4 / Property 10）：``BS-006`` 四变体公式**不全相同**。

    这是「准则维度真实存在」的证据。若哪天四变体被统一，
    Property 10 就失去真实样本，须改用别的行或构造样本并在此登记。
    """
    fm = _formula_map(live)
    got = {std: fm.get(("BS-006", std)) for std in _STANDARDS}
    missing = [s for s, f in got.items() if not f]
    assert not missing, f"BS-006 在以下变体无公式：{missing}"
    assert len(set(got.values())) > 1, (
        f"BS-006 四变体公式已被统一 —— 准则维度失去真实样本：{got}"
    )
    # 减项公式的真实样本（Property 8 的算术复核对象，Task 6 用）
    minus_variants = [s for s, f in got.items() if "-" in str(f).replace("BS-", "")]
    assert minus_variants, f"BS-006 已无含减项的变体 —— Property 8 失去真实样本：{got}"


def test_live_bs069_formula_is_row_reference_only(live):
    """类 A（Property 9）：``BS-069`` 公式全是 ``ROW()`` 引用（J1 soe 侧的落点）。

    这是「``ROW()`` 一律拒解析」在真实库里的样本 —— 不是构造出来的边缘态。
    """
    fm = _formula_map(live)
    formula = fm.get(("BS-069", "soe_standalone"))
    if not formula:
        pytest.skip("BS-069 在 soe_standalone 无公式")
    assert "ROW(" in formula, f"BS-069 已不含 ROW() 引用 —— Property 9 失去真实样本：{formula}"
    assert "TB(" not in formula, (
        f"BS-069 现在混有 TB() —— 拒解析判据须改为「含 ROW() 即拒」而非「全 ROW()」：{formula}"
    )


def test_live_is001_uses_sum_tb_range(live):
    """类 A（R2.3）：``IS-001`` 用 ``SUM_TB`` 区间语义（Task 6 的算术复核对象）。"""
    fm = _formula_map(live)
    formula = fm.get(("IS-001", "soe_standalone"))
    assert formula, "IS-001 在 soe_standalone 无公式"
    assert "SUM_TB(" in formula, f"IS-001 已不用 SUM_TB —— R2.3 失去真实样本：{formula}"
    assert "~" in formula, f"IS-001 的 SUM_TB 无区间分隔符：{formula}"


def test_live_project_standard_states_both_exist(live):
    """类 A（R3.3 / Property 11）：真实库同时存在「已设准则」与「未设准则」的项目。

    两态都有真实样本，故 ``standard_unset`` 与 ``resolved`` 都能用生产数据验证。
    """
    projects = live["projects"]
    assert projects, "无任何带程序实例的项目 —— 无法做行为验收"
    with_std = [p for p in projects if isinstance(p["applicable_standard_v2"], dict) and p["applicable_standard_v2"]]
    without_std = [p for p in projects if not (isinstance(p["applicable_standard_v2"], dict) and p["applicable_standard_v2"])]
    assert with_std, "无任何已设准则的项目 —— resolved 态无法用真实数据验证"
    assert without_std, (
        "无任何未设准则的项目 —— standard_unset 态无法用真实数据验证，须构造样本"
    )


def test_live_available_standard_variants_are_reported_honestly(live):
    """类 A（R7.3）：如实记录真实库覆盖到的准则变体，未覆盖者留待 UNVERIFIABLE。

    实测只有 ``soe_standalone``；``listed_*`` 与 ``soe_consolidated`` 在库中无项目。
    本条**不打红**未覆盖变体（那是真实状态不是缺陷），只保证「至少有一个变体可验」
    并把实际覆盖面固化成可读事实，供 Task 14 决定哪些输出 UNVERIFIABLE。
    """
    covered = set()
    for p in live["projects"]:
        std = p["applicable_standard_v2"]
        if isinstance(std, dict) and std.get("entity_type") and std.get("scope"):
            covered.add(f"{std['entity_type']}_{std['scope']}")
    assert covered, "真实库无任何可用准则变体 —— 全部验收都将是 UNVERIFIABLE"
    assert covered <= set(_STANDARDS) | {"private_standalone", "private_consolidated"}, (
        f"出现 report_config 取值域外的准则组合：{sorted(covered - set(_STANDARDS))} ⇒ "
        "该组合在 report_config 无对应行，金额恒 formula_unavailable，须在实现里显式处理"
    )


def test_live_two_standard_field_groups_can_diverge(live):
    """🔴 类 A：平台有**两组**准则字段，且真实库里已经分叉。

    - ``projects.applicable_standard_v2``（结构化，权威真源）
    - ``projects.template_type`` + ``report_scope``（旧字段，**报表页实际用的就是这组**，
      见 ``report_config_service.resolve_applicable_standard``）

    实测 32 个项目：24 个两组都未设 · 7 个一致 · **1 个分叉**
    （``v2=soe_standalone`` 而 ``template_type=listed``，且它是程序实例最多的项目）。

    分叉意味着报表页按上市准则出数、平台其他模块按国企 ⇒ 同一底稿的 ``BS-006`` 公式
    不同（``TB('1122')-TB('1231')`` vs ``TB('1122')-TB('1231-02')``）⇒ 金额不同。

    本条**不打红分叉本身**（那是既有数据缺陷，本 spec 范围外，已登记为独立议题），
    只固化「分叉真实存在」这个事实 —— 否则后来者会把「分叉项目返 standard_unset」
    当成实现 bug 去"修好"，从而让裁剪判据用一个说不清的准则去自动裁审计程序。
    """
    groups = {"both_unset": [], "consistent": [], "diverged": []}
    for p in live["projects"]:
        v2, legacy = _v2_combo(p), _legacy_combo(p)
        if not v2 and not legacy:
            groups["both_unset"].append(p["pid"])
        elif v2 and legacy and v2 != legacy:
            groups["diverged"].append(f"{p['pid']} v2={v2} legacy={legacy}")
        elif v2 and legacy:
            groups["consistent"].append(p["pid"])
    assert groups["consistent"], (
        "无任何「两组准则字段一致」的项目 —— resolved 态无法用真实数据验证。"
        f"分布：consistent=0 diverged={len(groups['diverged'])} "
        f"both_unset={len(groups['both_unset'])}"
    )
    # 分叉存在时输出到断言消息里留档（不打红）
    if groups["diverged"]:
        assert len(groups["diverged"]) < len(live["projects"]), (
            f"全部项目都分叉，无可验收样本：{groups['diverged']}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 类 B：被测实现（Task 5 之前应全红）
# ═══════════════════════════════════════════════════════════════════════════
def _amounts_mod():
    try:
        from app.services import trim_report_line_amounts as mod
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import app.services.trim_report_line_amounts —— {_NOT_IMPLEMENTED}: {e!r}")
    return mod


def test_amounts_module_exports_contract():
    """类 B（R4.1）：模块导出约定接口与四个状态常量。"""
    mod = _amounts_mod()
    for name in (
        "ReportLineAmount",
        "resolve_trim_report_line_amounts",
        "AMOUNT_RESOLVED",
        "AMOUNT_NO_REPORT_LINE",
        "AMOUNT_FORMULA_UNAVAILABLE",
        "AMOUNT_STANDARD_UNSET",
    ):
        assert hasattr(mod, name), f"未导出 {name} —— {_NOT_IMPLEMENTED}"


def test_amounts_status_domain_is_exactly_four():
    """类 B（R4.1 / Property 12）：状态取值域恰为四个且值互不相同。"""
    mod = _amounts_mod()
    values = [
        mod.AMOUNT_RESOLVED,
        mod.AMOUNT_NO_REPORT_LINE,
        mod.AMOUNT_FORMULA_UNAVAILABLE,
        mod.AMOUNT_STANDARD_UNSET,
    ]
    assert len(set(values)) == 4, f"四个状态常量有重复值：{values}"
    assert all(isinstance(v, str) and v.strip() for v in values), f"状态常量非空字符串：{values}"


def test_amounts_dataclass_defaults_never_fabricate_zero():
    """类 B（R4.2 / Property 12）：``ReportLineAmount`` 的 ``amount`` 默认为 ``None``。

    默认 ``0.0`` 会让每一个未显式赋值的分支静默产出 0 —— 这是本平台已实证的
    「编造 0 让程序被误判成低于任何阈值」的入口。
    """
    mod = _amounts_mod()
    inst = mod.ReportLineAmount(wp_code="D2", status=mod.AMOUNT_NO_REPORT_LINE)
    assert inst.amount is None, f"amount 默认值为 {inst.amount!r}，必须是 None"
    for field in ("row_code", "row_name", "standard_codes", "reason", "source_symbol"):
        assert hasattr(inst, field), f"ReportLineAmount 缺字段 {field}（R6.1 溯源需要）"


def test_amounts_each_status_has_distinct_chinese_reason():
    """类 B（R4.3 / Property 12）：每态有独立且互不相同的中文 reason 模板。

    四态共用一句「取数失败」会让审计师看到的原因与实际成因不符 ——
    「本项目没填准则」与「这个报表行没配公式」是两件完全不同的事，
    前者审计师能自己解决，后者要找平台维护者。
    """
    mod = _amounts_mod()
    getter = getattr(mod, "reason_for_status", None)
    assert callable(getter), (
        f"未导出 reason_for_status(status, **ctx) —— 无法验证每态文案独立（{_NOT_IMPLEMENTED}）"
    )
    texts = {}
    for status in (
        mod.AMOUNT_NO_REPORT_LINE,
        mod.AMOUNT_FORMULA_UNAVAILABLE,
        mod.AMOUNT_STANDARD_UNSET,
    ):
        text = str(getter(status) or "")
        assert text.strip(), f"{status} 的 reason 为空"
        assert re.search(r"[\u4e00-\u9fff]", text), f"{status} 的 reason 非中文：{text!r}"
        texts[status] = text
    assert len(set(texts.values())) == 3, f"三态 reason 文案有重复：{texts}"


def test_amounts_module_reuses_report_formula_parser():
    """类 B（R2.1 / Property 6）：复用报表引擎，不含第二份公式求值或科目求和。"""
    assert _AMOUNTS_PATH.exists(), f"模块不存在：{_AMOUNTS_PATH} —— {_NOT_IMPLEMENTED}"
    code = _code_only(_AMOUNTS_PATH.read_text(encoding="utf-8"))
    assert "ReportFormulaParser" in code, "未使用 ReportFormulaParser —— 会引入第二个金额口径"
    for banned, why in (
        ("safe_eval_expr", "自己求值公式"),
        ("evaluate_formula", "绕过 parser.execute 直接调内核"),
        ("_TB_PATTERN", "自己解析 TB() 语法"),
        ("TrialBalance", "自己查 trial_balance 聚合金额"),
    ):
        assert banned not in code, f"代码引用了 {banned}（{why}）—— 必须全权委托 parser"


def test_amounts_module_does_not_split_by_semantic_slot():
    """类 B（R2.5 / Property 6）：不按 ``SemanticAccountSpec`` 的槽拆分后再合计。

    实证多槽规格下报表公式兜底会把整行金额分配给某个槽，E1 曾因此把
    ``1002``/``1012`` 算两遍（8,935,072.24 vs 真值 4,467,536.12，虚增一倍）。
    """
    code = _code_only(_AMOUNTS_PATH.read_text(encoding="utf-8"))
    for banned in ("SemanticAccountSpec", "SemanticAccountSlot", "resolve_semantic_accounts"):
        assert banned not in code, f"代码引用了 {banned} —— 按槽拆分会重复计算整行金额"
    assert ".slots" not in code, "代码访问了 .slots —— 按槽拆分会重复计算整行金额"


def test_amounts_module_rejects_row_reference_formulas():
    """类 B（R2.6 / Property 9）：含 ``ROW()`` 的公式判为不可解析，不伪造 row_cache。"""
    code = _code_only(_AMOUNTS_PATH.read_text(encoding="utf-8"))
    assert "extract_row_refs" in code, (
        "未调用 extract_row_refs —— 无法识别 ROW() 依赖，会把部分结果当完整金额"
    )
    assert "AMOUNT_FORMULA_UNAVAILABLE" in code, "未使用 formula_unavailable 状态"


def test_amounts_module_logs_error_not_warning_on_failure():
    """类 B（R4.4 / Property 13）：求值异常记 **ERROR** 级，不是 WARNING。

    本平台已多次出现 ``except Exception`` 把「函数名/列名拼错、传错客户端形态」
    吞成 WARNING 甚至静默 ⇒ 表现为「本项目无此数据」，而 Volar / vitest /
    get_diagnostics / HEAD-swap 四层全绿。ERROR 级留下可检索的错误痕迹是
    唯一能在事后发现接线错误的手段。
    """
    code = _code_only(_AMOUNTS_PATH.read_text(encoding="utf-8"))
    assert "logger.error" in code, "无 logger.error —— 求值异常会静默，接线错误无从发现"
    tree = ast.parse(code)
    # 每个 except 块里必须有 logger.error（不允许只有 warning/debug 或纯 pass）
    weak: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        body_src = "\n".join(
            ast.unparse(stmt) for stmt in node.body  # type: ignore[arg-type]
        )
        if "logger.error" not in body_src:
            weak.append(node.lineno)
    assert not weak, (
        f"以下 except 块未记 ERROR（行 {weak}）—— 异常会被降级掩盖成「本项目无此数据」"
    )


def test_amounts_module_queries_report_config_in_batch():
    """类 B（性能与一致性）：``report_config`` 一次批量查回，不在循环里逐个发查询。

    逐 wp_code 发查询在 331 条程序实例的项目上是 331 次往返；
    更重要的是「同一批 wp_code 用同一份配置快照」是金额可比的前提。
    """
    code = _code_only(_AMOUNTS_PATH.read_text(encoding="utf-8"))
    tree = ast.parse(code)
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Await):
                continue
            src = ast.unparse(inner)
            if "db.execute" in src or "conn.execute" in src:
                offenders.append(getattr(inner, "lineno", -1))
    assert not offenders, (
        f"以下行在循环体内发 DB 查询（行 {offenders}）—— report_config 须一次批量查回"
    )


def test_amounts_module_builds_one_parser_per_project():
    """类 B：``ReportFormulaParser`` 每项目只建一个实例（复用其内部两级缓存）。

    它的 ``_tb_cache`` / ``_tb_prefix_cache`` 是实例级 —— 每个 wp_code 各建一个
    实例会让缓存全部失效，等于把批量退化成 N 次全表扫。
    """
    code = _code_only(_AMOUNTS_PATH.read_text(encoding="utf-8"))
    tree = ast.parse(code)
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "ReportFormulaParser"
            ):
                offenders.append(getattr(inner, "lineno", -1))
    assert not offenders, (
        f"以下行在循环体内实例化 ReportFormulaParser（行 {offenders}）—— 缓存会全部失效"
    )


def test_amounts_module_reads_project_standard_field_directly():
    """类 B（R3.3 / Property 11）：直读 ``applicable_standard_v2`` 判「准则未设置」。

    🔴 不能用 ``derive_applicable_standards`` 判空（它永不为空，见上方类 A 判据）——
    那会把 24 个未填准则的项目静默算成国企个别报表并给出金额。
    """
    code = _code_only(_AMOUNTS_PATH.read_text(encoding="utf-8"))
    assert "applicable_standard_v2" in code, (
        "未直读 applicable_standard_v2 —— 无法区分「未设准则」与「默认国企」"
    )
    assert "AMOUNT_STANDARD_UNSET" in code, "未使用 standard_unset 状态"


def test_amounts_resolve_signature():
    """类 B：``resolve_trim_report_line_amounts`` 签名与 async 形态。"""
    mod = _amounts_mod()
    fn = mod.resolve_trim_report_line_amounts
    assert inspect.iscoroutinefunction(fn), "resolve_trim_report_line_amounts 必须是 async"
    params = list(inspect.signature(fn).parameters)
    assert params[:4] == ["db", "project_id", "year", "wp_codes"], (
        f"签名与 design 约定不符：{params}"
    )


# ── 类 B：行为判据（连库真跑）──────────────────────────────────────────────
def _run_resolve(pid: str, year: int, wp_codes: list[str]):
    """在专用 NullPool engine + 单一 loop 内真跑一次金额解析。"""
    mod = _amounts_mod()
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with AsyncSession(engine) as session:
                return await mod.resolve_trim_report_line_amounts(
                    session, pid, year, wp_codes
                )
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _v2_combo(p) -> str:
    """项目的结构化准则组合（``applicable_standard_v2``）；未设置返空串。"""
    std = p["applicable_standard_v2"]
    if not isinstance(std, dict):
        return ""
    e = str(std.get("entity_type") or "").strip().lower()
    s = str(std.get("scope") or "").strip().lower()
    return f"{e}_{s}" if e and s else ""


def _legacy_combo(p) -> str:
    """项目的旧字段准则组合（``template_type`` + ``report_scope``）；未设置返空串。

    🔴 **报表页实际用的是这一组**（``report_config_service.resolve_applicable_standard``）。
    """
    e = str(p.get("template_type") or "").strip().lower()
    s = str(p.get("report_scope") or "").strip().lower()
    return f"{e}_{s}" if e and s else ""


def _pick_project(live, *, with_standard: bool):
    """选一个项目：``with_standard`` 指「结构化准则是否已设置」。"""
    for p in live["projects"]:
        has = bool(_v2_combo(p))
        if has is with_standard and (p["tb_n"] > 0 or not with_standard):
            return p
    return None


def _pick_consistent_project(live, *, entity: str = ""):
    """选一个**两组准则字段一致**且有试算表数据的项目。

    🔴 不能只按「结构化准则已设置」选 —— 真实库实测有 1 个项目两组分叉
    （``v2=soe_standalone`` 而 ``template_type=listed``，且它是程序实例最多的那个）。
    分叉项目按设计返 ``standard_unset``（宁缺勿造），故 ``resolved`` 态的验收
    必须避开它，否则会把正确行为当成缺陷（本文件初版实测踩到）。
    """
    for p in live["projects"]:
        v2 = _v2_combo(p)
        if not v2 or v2 != _legacy_combo(p) or p["tb_n"] <= 0:
            continue
        if entity and not v2.startswith(entity):
            continue
        return p
    return None


def test_amounts_behavior_never_fabricates_zero(live):
    """类 B（R4.2 / Property 12）：真跑一次，非 resolved 态一律无金额。"""
    proj = _pick_consistent_project(live) or _pick_project(live, with_standard=True)
    if proj is None:
        pytest.skip("无已设准则且有试算表数据的项目")
    mod = _amounts_mod()
    # 混入必然不可解析的码（L2 声明 row_code=None、D99 未登记、A1 非余额驱动）
    result = _run_resolve(
        proj["pid"], int(proj["audit_year"] or 0), ["E1", "D2", "L2", "D99", "A1"]
    )
    bad = _find_zero_masquerade(result, mod.AMOUNT_RESOLVED)
    assert not bad, f"出现「状态非 resolved 却带金额」：{bad}"


def test_amounts_behavior_status_within_domain(live):
    """类 B（R4.1）：真跑结果的状态全在四态取值域内。"""
    proj = _pick_consistent_project(live) or _pick_project(live, with_standard=True)
    if proj is None:
        pytest.skip("无已设准则且有试算表数据的项目")
    mod = _amounts_mod()
    domain = {
        mod.AMOUNT_RESOLVED,
        mod.AMOUNT_NO_REPORT_LINE,
        mod.AMOUNT_FORMULA_UNAVAILABLE,
        mod.AMOUNT_STANDARD_UNSET,
    }
    result = _run_resolve(
        proj["pid"], int(proj["audit_year"] or 0), ["E1", "D2", "L2", "D99", "A1"]
    )
    seen = {getattr(v, "status", None) for v in result.values()}
    assert seen <= domain, f"出现取值域外状态：{sorted(seen - domain)}"


def test_amounts_behavior_standard_unset_project(live):
    """类 B（R3.3 / Property 11）：未设准则的项目全部返 ``standard_unset``。"""
    proj = _pick_project(live, with_standard=False)
    if proj is None:
        pytest.skip("无未设准则的项目")
    mod = _amounts_mod()
    result = _run_resolve(proj["pid"], int(proj["audit_year"] or 2025), ["E1", "D2"])
    assert result, "未设准则的项目返回空 dict —— 应返四态而非空"
    for key, item in result.items():
        assert item.status == mod.AMOUNT_STANDARD_UNSET, (
            f"{key} 在未设准则项目上的状态是 {item.status!r}，应为 standard_unset"
        )
        assert item.amount is None, f"{key} 竟带金额 {item.amount!r}"
        assert str(item.reason or "").strip(), f"{key} 的 reason 为空"


def test_amounts_behavior_diverged_standard_project(live):
    """类 B（R3.3 / Property 11）：两组准则字段分叉的项目返 ``standard_unset``。

    🔴 为什么分叉时宁缺勿造：报表页必须出一张报表所以它按旧字段兜底，而裁剪判据是
    **自动裁掉审计程序**的依据 —— 用一个说不清的准则算出的金额去裁程序，风险远高于
    报表上显示一个可能不准的数。且 ``reason`` 必须写明是「两处声明不一致」而不是
    笼统的「未设置」，否则审计师会去填一个已经填过的字段。
    """
    diverged = None
    for p in live["projects"]:
        v2, legacy = _v2_combo(p), _legacy_combo(p)
        if v2 and legacy and v2 != legacy:
            diverged = p
            break
    if diverged is None:
        pytest.skip("真实库已无两组准则字段分叉的项目（数据已被修正）")
    mod = _amounts_mod()
    result = _run_resolve(diverged["pid"], int(diverged["audit_year"] or 2025), ["E1", "D2"])
    assert result, "分叉项目返回空 dict —— 应返四态而非空"
    for key, item in result.items():
        assert item.status == mod.AMOUNT_STANDARD_UNSET, (
            f"{key} 在准则分叉项目上的状态是 {item.status!r}，应为 standard_unset"
        )
        assert item.amount is None, f"{key} 竟带金额 {item.amount!r}"
        assert "不一致" in str(item.reason), (
            f"{key} 的 reason 未说明是「两处声明不一致」，审计师会误以为没填过：{item.reason!r}"
        )


def test_amounts_behavior_e1_resolves_on_live_project(live):
    """类 B（R2.1 / R7.4 的后端侧）：E1 在真实 soe 项目上解析成功且溯源齐备。

    E 循环是本 spec 的立项缺陷现场 —— 改造前它的 ``accountAmount`` 恒 ``null``。
    """
    proj = _pick_consistent_project(live)
    if proj is None:
        pytest.skip("无「两组准则字段一致 + 有试算表数据」的项目")
    mod = _amounts_mod()
    result = _run_resolve(proj["pid"], int(proj["audit_year"] or 0), ["E1"])
    item = result.get("E1")
    assert item is not None, "E1 未出现在结果里"
    assert item.status == mod.AMOUNT_RESOLVED, (
        f"E1 状态为 {item.status!r}（reason={item.reason!r}）—— 立项缺陷未被修复"
    )
    assert isinstance(item.amount, float), f"E1 金额类型为 {type(item.amount)}"
    assert item.row_code, "E1 缺 row_code（R6.1 溯源）"
    assert item.row_name, "E1 缺 row_name（R6.1 溯源）"
    assert item.formula, "E1 缺 formula 原文（R6.1 溯源）"
    assert item.standard_codes, "E1 缺 standard_codes（R6.1 溯源）"
    assert item.applicable_standard, "E1 缺 applicable_standard"


def test_amounts_behavior_row_reference_is_unavailable(live):
    """类 B（R2.6 / Property 9）：落在全 ``ROW()`` 公式行的底稿返不可解析。

    真实样本 = J1 在 soe 准则下声明 ``BS-069``（非流动负债合计，公式全 ``ROW()``）。
    """
    proj = _pick_consistent_project(live, entity="soe")
    if proj is None:
        pytest.skip("无「国企准则 + 两组一致 + 有试算表数据」的项目（BS-069 样本不可达）")
    mod = _amounts_mod()
    item = _run_resolve(proj["pid"], int(proj["audit_year"] or 0), ["J1"]).get("J1")
    assert item is not None, "J1 未出现在结果里"
    if item.row_code != "BS-069":
        pytest.skip(f"J1 在 soe 下已不指向 BS-069（实得 {item.row_code}）")
    assert item.status == mod.AMOUNT_FORMULA_UNAVAILABLE, (
        f"J1 落在全 ROW() 公式行却返 {item.status!r} —— 部分结果被当完整金额"
    )
    assert item.amount is None, f"J1 竟带金额 {item.amount!r}"
    assert str(item.reason or "").strip(), "J1 的 reason 为空 —— 审计师看不出为何算不出"


def test_amounts_behavior_one_failure_does_not_block_others(live):
    """类 B（R4.5 / Property 13）：单个 wp_code 不可解析不影响其余。"""
    proj = _pick_consistent_project(live)
    if proj is None:
        pytest.skip("无「两组准则字段一致 + 有试算表数据」的项目")
    mod = _amounts_mod()
    result = _run_resolve(
        proj["pid"], int(proj["audit_year"] or 0), ["D99", "E1", "A1", "L2"]
    )
    assert set(result) >= {"D99", "E1", "A1", "L2"}, (
        f"部分 wp_code 从结果里消失（实得 {sorted(result)}）—— 单个失败阻断了整批"
    )
    assert result["E1"].status == mod.AMOUNT_RESOLVED, (
        f"混入不可解析码后 E1 也失败了：{result['E1'].status!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Task 6：连库独立算术复核（前缀聚合 / 区间语义 / 公式符号）
#
# Requirements: 1.5, 2.2, 2.3, 2.4
# Validates: Property 4（索引 row_code 在真实库存在）,
#            Property 7（前缀聚合与区间语义）, Property 8（公式符号运算）,
#            Property 13（异常记 ERROR 且不阻断，行为级）
#
# 🔴 判据形态 = 「真跑被测路径 + 独立 SQL 复算 + 两侧比对」。
#    不能只断言「函数返回了一个数」—— 那对「前缀没聚合」「减项被当加项」全都恒绿。
#    独立 SQL 只负责算期望值，被测值一律来自 ReportFormulaParser 真跑。
#
# ═══ 真实样本（2026-08-15 实测，项目 2aa00f57 和平药房 / soe_standalone / 两组一致）═══
#
#   1122      应收账款             151,273,548.62   （无 1122-* 子科目）
#   1231      坏账准备               1,718,193.78   ← 父行存的就是子科目合计
#   1231-01   坏账准备-应收票据              0.00
#   1231-02   坏账准备-应收账款        406,014.85
#   1231-03   坏账准备-其他应收款    1,312,178.93
#   1231-04/05                            0.00
#   1002      银行存款                 327,095.20
#   1012      其他货币资金           8,280,881.84
#   6001      营业收入           1,044,179,479.82
#
# ⚠️ **``1231`` 父行 = 子科目合计**（406,014.85 + 1,312,178.93 = 1,718,193.78）⇒
#    ``TB('1231')`` 的前缀聚合会把父与子**都算进去**（结果 3,436,387.56 而非
#    1,718,193.78）。这是 ``report_engine._get_tb_rows_prefix`` 的既有口径，**报表页
#    也是这么算的**，R2.2 明确要求沿用 —— 本 spec 不改它，只如实记录：所以裁剪建议的
#    金额与报表上那个数一致（这正是复用取数引擎的目的），而不是与"应该是多少"一致。
#    ``BS-006`` 在国企个别准则下用的是精确子科目 ``TB('1231-02')``，不受双算影响。
# ═══════════════════════════════════════════════════════════════════════════
_ARITH_SQL = """
SELECT
  (SELECT coalesce(sum(audited_amount), 0) FROM trial_balance
     WHERE project_id = :pid AND year = :yr AND is_deleted = false
       AND standard_account_code LIKE '1231%')                       AS prefix_1231,
  (SELECT coalesce(sum(audited_amount), 0) FROM trial_balance
     WHERE project_id = :pid AND year = :yr AND is_deleted = false
       AND standard_account_code = '1231')                           AS exact_1231,
  (SELECT coalesce(sum(audited_amount), 0) FROM trial_balance
     WHERE project_id = :pid AND year = :yr AND is_deleted = false
       AND standard_account_code LIKE '1231-%')                      AS children_1231,
  (SELECT coalesce(sum(audited_amount), 0) FROM trial_balance
     WHERE project_id = :pid AND year = :yr AND is_deleted = false
       AND standard_account_code LIKE '1122%')                       AS prefix_1122,
  (SELECT coalesce(sum(audited_amount), 0) FROM trial_balance
     WHERE project_id = :pid AND year = :yr AND is_deleted = false
       AND standard_account_code LIKE '1231-02%')                    AS prefix_1231_02,
  (SELECT coalesce(sum(coalesce(audited_amount, 0) - coalesce(opening_balance, 0)), 0)
     FROM trial_balance
     WHERE project_id = :pid AND year = :yr AND is_deleted = false
       AND standard_account_code BETWEEN '6001' AND '6099')          AS period_6001_6099,
  (SELECT count(*) FROM trial_balance
     WHERE project_id = :pid AND year = :yr AND is_deleted = false
       AND standard_account_code LIKE '1231-%'
       AND coalesce(audited_amount, 0) <> 0)                         AS nonzero_children_1231,
  (SELECT count(*) FROM trial_balance
     WHERE project_id = :pid AND year = :yr AND is_deleted = false
       AND standard_account_code BETWEEN '6001' AND '6099')          AS n_rows_6001_6099
"""


def _run_arith(pid: str, year: int, formulas: dict[str, str]):
    """一次 loop 内：取独立 SQL 期望值 + 用真实 ``ReportFormulaParser`` 求值各公式。

    🔴 专用 ``NullPool`` engine + 同 loop ``dispose()``：连接池绑定首个事件循环，
    借共享池会双向污染（第二个测试起报 ``Event loop is closed``）。
    """
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
        from app.services.report_engine import ReportFormulaParser
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with AsyncSession(engine) as session:
                expected = dict(
                    (
                        await session.execute(
                            sa.text(_ARITH_SQL), {"pid": pid, "yr": year}
                        )
                    ).one()._mapping
                )
                parser = ReportFormulaParser(session, pid, year)
                got: dict[str, Any] = {}
                for key, formula in formulas.items():
                    got[key] = await parser.execute(formula, {})
                return expected, got
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"真实库不可达（本组为连库判据）: {e!r}")


@pytest.fixture(scope="module")
def arith(live):
    """选「两组准则一致 + 有非零多级子科目」的项目跑算术复核。"""
    proj = None
    for p in live["projects"]:
        v2 = _v2_combo(p)
        if v2 and v2 == _legacy_combo(p) and p["tb_n"] > 0:
            proj = p
            break
    if proj is None:
        pytest.skip("无「两组准则一致 + 有试算表数据」的项目")
    pid = proj["pid"]
    year = int(proj["audit_year"] or 0)
    expected, got = _run_arith(pid, year, {
        "prefix_1231": "TB('1231','期末余额')",
        "exact_1231_02": "TB('1231-02','期末余额')",
        "prefix_1122": "TB('1122','期末余额')",
        "bs006_soe_standalone": "TB('1122','期末余额') - TB('1231-02','期末余额')",
        "bs002": (
            "TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')"
        ),
        "sum_tb_range": "SUM_TB('6001~6099','本期发生额')",
        "bogus_code": "TB('9999999','期末余额')",
    })
    return {"pid": pid, "year": year, "expected": expected, "got": got, "proj": proj}


def test_live_arith_fixture_really_ran_the_parser(arith):
    """🔴 反向自检：parser 真的跑了并读到了数据（不是恒返 0 的空转）。

    若被测路径其实什么都没查（连错库 / 项目 id 类型不对 / 年度不匹配），
    下面所有比对都会是「0 == 0」恒绿。本条先确认至少一个公式取到非零值。
    """
    got = arith["got"]
    nonzero = {k: v for k, v in got.items() if float(v) != 0.0}
    assert nonzero, (
        f"全部公式都求出 0 —— parser 未读到数据，后续比对全是 0==0 空转。"
        f"项目 {arith['pid']} year={arith['year']}"
    )
    assert float(got["bogus_code"]) == 0.0, (
        f"不存在的科目码竟求出 {got['bogus_code']} —— 取数范围不受科目码约束"
    )


def test_live_prefix_aggregation_includes_children(arith):
    """R2.2 / Property 7：``TB('1231')`` 含该码全部子科目（与独立 SQL 前缀聚合相等）。"""
    exp, got = arith["expected"], arith["got"]
    if int(exp["nonzero_children_1231"]) == 0:
        pytest.skip(f"项目 {arith['pid']} 的 1231 子科目全为 0，前缀聚合无区分度")

    assert float(got["prefix_1231"]) == pytest.approx(float(exp["prefix_1231"]), abs=0.01), (
        f"TB('1231') 求得 {got['prefix_1231']}，独立 SQL 前缀聚合 {exp['prefix_1231']}"
    )
    # 🔴 区分度：前缀聚合结果必须 ≠ 只取精确码，否则「含子科目」这条判据是空转
    assert float(got["prefix_1231"]) != pytest.approx(float(exp["exact_1231"]), abs=0.01), (
        f"TB('1231') 的结果与只取精确码相同（{exp['exact_1231']}）—— "
        "前缀聚合未生效，或本项目子科目恰好全为 0（那样本条无判据价值）"
    )
    # 父 + 子 = 前缀聚合（如实记录：父行是汇总行时会双算，这是报表引擎既有口径）
    assert float(exp["prefix_1231"]) == pytest.approx(
        float(exp["exact_1231"]) + float(exp["children_1231"]), abs=0.01
    ), "独立 SQL 三个口径不自洽 —— 复核查询本身有误"


def test_live_signed_formula_is_not_absolute_sum(arith):
    """R2.4 / Property 8：含减项的公式按符号运算，**不等于**各项绝对值之和。

    真实样本 = ``BS-006`` 在国企个别准则下的 ``TB('1122') - TB('1231-02')``。
    「把各项相加」是最常见的实现错误，且在减项为 0 的项目上与正确实现无法区分 ——
    故本条要求减项非零，否则 skip 并说明。
    """
    exp, got = arith["expected"], arith["got"]
    gross = float(exp["prefix_1122"])
    provision = float(exp["prefix_1231_02"])
    if provision == 0.0:
        pytest.skip(f"项目 {arith['pid']} 的 1231-02 为 0，符号判据无区分度")

    signed = gross - provision
    absolute = gross + provision
    assert float(got["bs006_soe_standalone"]) == pytest.approx(signed, abs=0.01), (
        f"含减项公式求得 {got['bs006_soe_standalone']}，按符号加权应为 {signed}"
    )
    assert float(got["bs006_soe_standalone"]) != pytest.approx(absolute, abs=0.01), (
        f"含减项公式的结果等于各项绝对值之和（{absolute}）—— 减项被当成了加项"
    )


def test_live_sum_tb_range_covers_interval(arith):
    """R2.3 / Property 7：``SUM_TB('6001~6099')`` 覆盖区间内全部科目。

    ``本期发生额`` 在报表引擎里是 ``audited_amount - opening_balance``
    （``_COLUMN_MAP`` 把它映射到 ``_period_amount`` 特殊分支），独立 SQL 用同一算式。
    """
    exp, got = arith["expected"], arith["got"]
    if int(exp["n_rows_6001_6099"]) == 0:
        pytest.skip(f"项目 {arith['pid']} 在 6001~6099 区间无科目行")
    assert float(got["sum_tb_range"]) == pytest.approx(
        float(exp["period_6001_6099"]), abs=0.01
    ), (
        f"SUM_TB('6001~6099','本期发生额') 求得 {got['sum_tb_range']}，"
        f"独立 SQL 区间聚合 {exp['period_6001_6099']}"
    )
    assert float(got["sum_tb_range"]) != 0.0, (
        "区间聚合结果为 0 —— 本项目收入类科目全为 0，本条无判据价值"
    )


def test_live_bs002_matches_independent_sum(arith):
    """R7.4 的后端侧：``BS-002`` 货币资金金额 = ``1001 + 1002 + 1012`` 独立聚合。

    这是 Task 16 浏览器实测的期望值来源 —— 界面上显示的数必须等于此处算出的数。
    """
    got = arith["got"]
    pid, year = arith["pid"], arith["year"]
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                return float(
                    (
                        await conn.execute(
                            sa.text(
                                "SELECT coalesce(sum(audited_amount), 0) FROM trial_balance "
                                "WHERE project_id = :pid AND year = :yr AND is_deleted = false "
                                "AND (standard_account_code LIKE '1001%' "
                                "  OR standard_account_code LIKE '1002%' "
                                "  OR standard_account_code LIKE '1012%')"
                            ),
                            {"pid": pid, "yr": year},
                        )
                    ).scalar_one()
                )
        finally:
            await engine.dispose()

    try:
        expected = asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"真实库不可达: {e!r}")

    assert float(got["bs002"]) == pytest.approx(expected, abs=0.01), (
        f"BS-002 公式求得 {got['bs002']}，独立聚合 1001/1002/1012 得 {expected}"
    )


def test_live_indexed_row_codes_have_config_for_project_standard(arith):
    """R1.5 / Property 4：索引覆盖的底稿在本项目准则下要么有配置、要么原因明确。

    判据落在**金额模块的真实输出**上（不是只查 ``report_config`` 有没有行）：
    对索引全部 wp_code 跑一遍，凡 ``formula_unavailable`` 的必须带非空 ``reason``，
    且 ``resolved`` 的必须四项溯源齐备。这样「索引给了一个查不到配置的号」会以
    可读原因暴露，而不是静默变成 0。
    """
    try:
        from app.services.four_table.report_line_index import indexed_wp_codes
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"无法 import report_line_index: {e!r}")

    mod = _amounts_mod()
    codes = indexed_wp_codes()
    assert codes, "索引覆盖面为空"
    result = _run_resolve(arith["pid"], arith["year"], codes)
    assert set(result) == set(codes), (
        f"结果键与入参不一一对应：缺 {sorted(set(codes) - set(result))}、"
        f"多 {sorted(set(result) - set(codes))}"
    )

    bad: list[str] = []
    resolved = 0
    for code, item in sorted(result.items()):
        if item.status == mod.AMOUNT_RESOLVED:
            resolved += 1
            for field_name in ("row_code", "row_name", "formula"):
                if not str(getattr(item, field_name) or "").strip():
                    bad.append(f"{code}: resolved 但缺 {field_name}")
            if not item.standard_codes:
                bad.append(f"{code}: resolved 但 standard_codes 为空")
            if item.amount is None:
                bad.append(f"{code}: resolved 但 amount 为 None")
        else:
            if item.amount is not None:
                bad.append(f"{code}: {item.status} 却带 amount={item.amount!r}")
            if not str(item.reason or "").strip():
                bad.append(f"{code}: {item.status} 但 reason 为空")
    assert not bad, f"索引全量跑出以下问题：{bad[:15]}"
    assert resolved > 0, (
        f"索引 {len(codes)} 个底稿在项目 {arith['pid']} 上零解析成功 —— "
        "报表行取数整体空转"
    )


def test_live_evaluation_failure_logs_error_and_isolates(arith, caplog, monkeypatch):
    """Property 13（行为级）：求值抛异常时记 **ERROR** 且不阻断其余 wp_code。

    🔴 这条比源码级 AST 断言强：AST 只能证明「写了 logger.error」，
    证明不了「异常真的会走到那一行」。此处用 monkeypatch 让 parser 对特定公式抛错，
    真跑一遍看日志级别与其余项是否存活。
    """
    import logging as _logging

    mod = _amounts_mod()
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings
        from app.services.report_engine import ReportFormulaParser
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"连库依赖不可用: {e!r}")

    original = ReportFormulaParser.execute
    boom_marker = "1012"  # BS-002 的公式含它 ⇒ E1 会炸

    async def _boom(self, formula, row_cache):  # noqa: ANN001
        if boom_marker in str(formula or ""):
            raise RuntimeError("注入的求值故障（判据用）")
        return await original(self, formula, row_cache)

    monkeypatch.setattr(ReportFormulaParser, "execute", _boom)

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with AsyncSession(engine) as session:
                return await mod.resolve_trim_report_line_amounts(
                    session, arith["pid"], arith["year"], ["E1", "D2"]
                )
        finally:
            await engine.dispose()

    with caplog.at_level(_logging.DEBUG, logger="app.services.trim_report_line_amounts"):
        try:
            result = asyncio.run(_run())
        except Exception as e:  # noqa: BLE001
            pytest.fail(f"求值异常未被吸收，整批抛出：{e!r}")

    e1 = result.get("E1")
    assert e1 is not None, "E1 从结果里消失了 —— 单个失败阻断了整批"
    assert e1.status == mod.AMOUNT_FORMULA_UNAVAILABLE, (
        f"求值失败后 E1 状态为 {e1.status!r}，应为 formula_unavailable"
    )
    assert e1.amount is None, f"求值失败却给了金额 {e1.amount!r} —— 编造了数值"

    records = [r for r in caplog.records if r.name == "app.services.trim_report_line_amounts"]
    assert records, "求值失败未产生任何日志 —— 接线错误会静默"
    errors = [r for r in records if r.levelno >= _logging.ERROR]
    assert errors, (
        "求值失败只记了 WARNING/DEBUG 级 —— 本平台已多次出现 except 把接线错误"
        f"吞成「本项目无此数据」。实际级别：{sorted({r.levelname for r in records})}"
    )
    joined = " ".join(r.getMessage() for r in errors)
    for token in ("E1", "BS-002"):
        assert token in joined, f"ERROR 日志未含 {token} —— 排查时定位不到是哪个底稿/报表行"

    # 其余 wp_code 不受影响（D2 的公式不含注入标记）
    d2 = result.get("D2")
    assert d2 is not None, "D2 从结果里消失了"
    assert d2.status in {
        mod.AMOUNT_RESOLVED, mod.AMOUNT_FORMULA_UNAVAILABLE, mod.AMOUNT_NO_REPORT_LINE,
    }, f"D2 状态异常：{d2.status!r}"
