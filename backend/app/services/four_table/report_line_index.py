"""跨循环「底稿编号 → 报表行编码」索引 —— **零新增映射知识**。

Feature: procedure-trim-report-line-account-resolution — Task 4
Requirements: 1.1, 1.2, 1.3, 1.4, 1.7
守卫: ``backend/tests/procedure_trim/test_report_line_index.py``

## 它解决什么

程序裁剪的重要性判据需要知道「这条程序对应的科目余额是多少」。改造前的定位方式是
**科目名单向子串匹配**（拿程序名去 ``trial_balance.account_name`` 里找包含关系），
在真实数据上大面积失效 —— 因为**程序按报表项目组织，而试算表存的是明细科目名**，
两者是层级关系不是命名关系。实证：E 循环 5 条程序名一律「货币资金 …」，而该项目
试算表里没有「货币资金」这一行，只有明细「银行存款」与「其他货币资金」。

本模块补上第一段映射：``wp_code`` → 报表行编码。后两段（报表行 → 公式 → 金额）
分别由 ``report_config`` 数据与 ``report_engine.ReportFormulaParser`` 承担。

## 🔴 本模块**不含任何报表行编码字面量**

11 个循环的报表行声明早已存在于 ``four_table/*_cycle_specs.py``。本模块若再抄一份，
就成了平台反复治的双真源：某循环改了报表行号，索引不跟随，而**两侧各自的单测都全绿**
（各用自己的常量构造样本）。故本模块的实现形态是**取值 dispatch**，每个分支只做
「从既有声明取值」不做判断，并配一条交叉锁死守卫逐个比对两侧。

判据落在守卫 ``test_index_module_has_zero_row_code_literals``：剥注释后的代码里
零 ``BS-\\d+`` / ``IS-\\d+`` / ``IMP-\\d+`` 命中。故所有面向用户的原因文案一律用
**格式化占位符**拼接，不得写死任何行号示例。

## 准则维度：一律复用既有选择件

三个循环的报表行按适用准则不同，各自的选择逻辑早已实现，本模块只调用不重写：

===== ===================================================== ==========
循环   委托对象                                              准则维度
===== ===================================================== ==========
D      ``d_cycle_specs.D_CYCLE_SPECS[code].row_code``        无
E      ``e_cycle_specs.E1_REPORT_ROW_CODE``                  无（四准则一致，已实证）
F      ``f_cycle_specs.F_CYCLE_SPECS[code].row_code``        无
G      ``g_cycle_specs.G_CYCLE_SPECS[code].row_code``        无
H      ``h_cycle_specs.H_CYCLE_SPECS[code].row_code``        无
I      ``i_cycle_accounts.resolve_row_code(code, stds)``     **有**
J      ``j_cycle_account_scope.pick_spec(table, stds)``      **有**
K      ``k_cycle_specs.get_k_cycle_spec(code).spec_for()``   **有**
L      ``l_cycle_specs.L_CYCLE_SPECS[code].row_code``        无
M      ``m_cycle_specs.M_CYCLE_SPECS[code].row_code``        无
N      ``n_cycle_specs.N_CYCLE_SPECS[code].row_code``        无
===== ===================================================== ==========

H 循环走 ``h_cycle_specs.H_CYCLE_SPECS`` 而不是逐个 import 十个
``h{n}_account_scope.H{n}_ACCOUNT_SPEC``：前者是后者的汇总注册表
（``H_CYCLE_SPECS["H1"] is H1_ACCOUNT_SPEC``），同一真源、少十行重复。

## 三态：``resolved`` / ``no_report_line`` / ``non_balance_driven``

「不适用」与「无落点」**必须可区分**：

- ``non_balance_driven``（A / B / C / S 循环）= **设计如此**。报表与调整、计划、
  控制测试、专项事项类程序与单一科目余额没有对应关系，压根不该看金额。
- ``no_report_line`` = **待补的映射或有意的空**。三种成因各自写进 ``reason``：
  ① 该循环的注册表里没有这个码 ② 声明存在但 ``row_code`` 为空（实证 G2 / G3 / H5 /
  L2 / L6 —— 这些科目在资产负债表上确实无独立行，是有意为之而非漏填）
  ③ 循环字母不在平台已登记的范围内。

两态混同会让调用方无法判断「该不该去补映射」。

## wp_code 归一

真实库 ``procedure_instances.wp_code`` 有 **332 个 distinct 取值、其中 19 个区间型**
（``D2-1至D2-4`` / ``E1-14至E1-15`` / ``F2-1至F2-14`` …），**0 个**不以「字母段 +
数字段」开头。归一规则 = 取首个「字母段 + 数字段」，与前端 ``subjectPrefixOf`` 的
``/^([A-Z]+\\d+)/`` 同语义；两侧语言不同无法共享实现，由交叉锁死守卫兜住
（前端守卫现场从本文件抽正则字面量比对）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import (
    d_cycle_specs,
    e_cycle_specs,
    f_cycle_specs,
    g_cycle_specs,
    h_cycle_specs,
    i_cycle_accounts,
    j_cycle_account_scope,
    k_cycle_specs,
    l_cycle_specs,
    m_cycle_specs,
    n_cycle_specs,
)

# ─────────────────────────────────────────────────────────────────────────────
# 状态取值域
# ─────────────────────────────────────────────────────────────────────────────
#: 解析成功 —— 该底稿有报表行落点且取到了编码
REF_RESOLVED = "resolved"
#: 无报表行落点 —— 未登记 / 声明为空 / 未知循环（成因写进 ``reason``）
REF_NO_REPORT_LINE = "no_report_line"
#: 不适用 —— 该循环不按科目余额驱动裁剪（不是失败）
REF_NON_BALANCE_DRIVEN = "non_balance_driven"

#: 不按科目余额驱动的循环（与前端 ``procedureTrimDecision.BALANCE_DRIVEN_CYCLES``
#: 的补集一致：那边由完整性清单派生出 D~N 十一个循环，A / B / C / S 刻意不登记）。
#: 守卫钉死本集合恰为这四个字母。
NON_BALANCE_DRIVEN_CYCLES: frozenset[str] = frozenset({"A", "B", "C", "S"})

#: 底稿编号归一正则 —— 与前端 ``subjectPrefixOf`` 同语义（交叉锁死守卫现场抽取）
_WP_CODE_PREFIX_RE = re.compile(r"^([A-Z]+\d+)")


@dataclass(frozen=True)
class ReportLineRef:
    """一条底稿的报表行落点。

    :param wp_code: 归一后的底稿主码（``D2-1至D2-4`` → ``D2``）
    :param row_code: 报表行编码；空串 = 未解析出（``status`` 非 ``resolved``）
    :param status: 三态之一（:data:`REF_RESOLVED` / :data:`REF_NO_REPORT_LINE` /
        :data:`REF_NON_BALANCE_DRIVEN`）
    :param source_symbol: 取值出处（形如 ``d_cycle_specs.D_CYCLE_SPECS['D2'].row_code``）
        —— 既是溯源也是守卫交叉锁死的锚
    :param reason: 未解析时的中文原因（``resolved`` 态为空串）
    """

    wp_code: str
    row_code: str = ""
    status: str = REF_NO_REPORT_LINE
    source_symbol: str = ""
    reason: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# dispatch 表 —— 每个条目只声明「去哪取」，不声明取到什么
# ─────────────────────────────────────────────────────────────────────────────
#: 无准则维度的循环：``(循环字母, 模块名, 注册表属性名, 注册表对象)``
_SIMPLE_REGISTRIES: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    ("D", "d_cycle_specs", "D_CYCLE_SPECS", d_cycle_specs.D_CYCLE_SPECS),
    ("F", "f_cycle_specs", "F_CYCLE_SPECS", f_cycle_specs.F_CYCLE_SPECS),
    ("G", "g_cycle_specs", "G_CYCLE_SPECS", g_cycle_specs.G_CYCLE_SPECS),
    ("H", "h_cycle_specs", "H_CYCLE_SPECS", h_cycle_specs.H_CYCLE_SPECS),
    ("L", "l_cycle_specs", "L_CYCLE_SPECS", l_cycle_specs.L_CYCLE_SPECS),
    ("M", "m_cycle_specs", "M_CYCLE_SPECS", m_cycle_specs.M_CYCLE_SPECS),
    ("N", "n_cycle_specs", "N_CYCLE_SPECS", n_cycle_specs.N_CYCLE_SPECS),
)

#: E 循环：模块级常量（不是注册表）。取值一律 ``getattr``，不写字面量。
_E_CONSTANTS: tuple[tuple[str, str], ...] = (
    ("E1", "E1_REPORT_ROW_CODE"),
)

#: J 循环：每个底稿一张「实体类型 → spec」表，准则选择委托 ``pick_spec``
_J_SPEC_TABLES: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("J1", "J1_SPEC_BY_ENTITY", j_cycle_account_scope.J1_SPEC_BY_ENTITY),
    ("J2", "J2_SPEC_BY_ENTITY", j_cycle_account_scope.J2_SPEC_BY_ENTITY),
)


def normalize_wp_code(raw: Any) -> str:
    """归一到底稿主码：取首个「字母段 + 数字段」。

    ``D2-1至D2-4`` → ``D2``；``  m1-2  `` → ``M1``；``H10-3`` → ``H10``；
    无法归一（空 / 纯中文 / 不以字母开头）→ ``""``。

    与前端 ``subjectPrefixOf`` 的 ``/^([A-Z]+\\d+)/`` 同语义。
    """
    m = _WP_CODE_PREFIX_RE.match(str(raw or "").strip().upper())
    return m.group(1) if m else ""


def _row_code_of(spec: Any) -> str:
    """从声明对象取 ``row_code``，``None`` 与缺失一律归一为空串。

    🔴 声明里的 ``None`` 是**有意的空**（该科目在报表上无独立行），不是缺陷 ——
    实证 G2 / G3 / H5 / L2 / L6 五个。归一为空串后由调用方按 ``no_report_line`` 处理。
    """
    return str(getattr(spec, "row_code", None) or "").strip()


def _ref(
    wp_code: str, row_code: str, source_symbol: str, empty_reason: str
) -> ReportLineRef:
    """按 ``row_code`` 是否取到组装 ``resolved`` 或 ``no_report_line``。"""
    if row_code:
        return ReportLineRef(
            wp_code=wp_code,
            row_code=row_code,
            status=REF_RESOLVED,
            source_symbol=source_symbol,
        )
    return ReportLineRef(
        wp_code=wp_code,
        status=REF_NO_REPORT_LINE,
        source_symbol=source_symbol,
        reason=empty_reason,
    )


def _resolve_registry(
    code: str, letter: str, module: str, registry_name: str, registry: dict[str, Any]
) -> ReportLineRef | None:
    """无准则维度的注册表分支；该码未登记返 ``None`` 交由调用方统一处理。"""
    spec = registry.get(code)
    if spec is None:
        return None
    symbol = f"{module}.{registry_name}[{code!r}].row_code"
    return _ref(
        code,
        _row_code_of(spec),
        symbol,
        f"{letter} 循环底稿 {code} 已登记但未声明报表行落点"
        f"（该科目在报表上无独立行，取值出处 {symbol}）",
    )


def _resolve_e(code: str) -> ReportLineRef | None:
    for wp, attr in _E_CONSTANTS:
        if wp != code:
            continue
        symbol = f"e_cycle_specs.{attr}"
        return _ref(
            code,
            str(getattr(e_cycle_specs, attr, "") or "").strip(),
            symbol,
            f"E 循环底稿 {code} 的报表行常量 {symbol} 为空",
        )
    return None


def _resolve_i(code: str, standards: list[str]) -> ReportLineRef | None:
    if code not in i_cycle_accounts.I_CYCLE_ROW_CODES:
        return None
    symbol = f"i_cycle_accounts.resolve_row_code({code!r}, standards)"
    return _ref(
        code,
        str(i_cycle_accounts.resolve_row_code(code, standards) or "").strip(),
        symbol,
        f"I 循环底稿 {code} 在本项目准则下无报表行落点（取值出处 {symbol}）",
    )


def _resolve_j(code: str, standards: list[str]) -> ReportLineRef | None:
    for wp, table_name, table in _J_SPEC_TABLES:
        if wp != code:
            continue
        symbol = f"j_cycle_account_scope.pick_spec({table_name}, standards).row_code"
        return _ref(
            code,
            _row_code_of(j_cycle_account_scope.pick_spec(table, standards)),
            symbol,
            f"J 循环底稿 {code} 在本项目准则下无报表行落点（取值出处 {symbol}）",
        )
    return None


def _resolve_k(code: str, standards: list[str]) -> ReportLineRef | None:
    spec = k_cycle_specs.get_k_cycle_spec(code)
    if spec is None:
        return None
    symbol = f"k_cycle_specs.get_k_cycle_spec({code!r}).spec_for(standards).row_code"
    return _ref(
        code,
        _row_code_of(spec.spec_for(standards)),
        symbol,
        f"K 循环底稿 {code} 在本项目准则下无报表行落点（取值出处 {symbol}）",
    )


def resolve_report_line_ref(
    wp_code: Any, applicable_standards: Any = None
) -> ReportLineRef:
    """按底稿编号取报表行落点（纯函数，无 IO，恒返 :class:`ReportLineRef`）。

    :param wp_code: 底稿编号，可为区间型（``D2-1至D2-4``）或带后缀（``H10-3``）
    :param applicable_standards: 项目适用准则列表（形如 ``["soe_standalone", "soe",
        "standalone"]``）。仅 I / J / K 三循环用到；``None`` 时各既有件按自身默认处理。
    :return: 三态之一，恒非 ``None``，**不抛异常**

    未登记与不适用严格区分 —— 见模块 docstring「三态」一节。
    """
    code = normalize_wp_code(wp_code)
    standards = [str(s) for s in (applicable_standards or []) if str(s or "").strip()]

    if not code:
        return ReportLineRef(
            wp_code="",
            status=REF_NO_REPORT_LINE,
            reason=f"底稿编号 {str(wp_code or '')!r} 无法归一到「字母段 + 数字段」形态",
        )

    letter = code[0]
    if letter in NON_BALANCE_DRIVEN_CYCLES:
        return ReportLineRef(
            wp_code=code,
            status=REF_NON_BALANCE_DRIVEN,
            reason=(
                f"{letter} 循环不按科目余额驱动裁剪，报表行与科目金额判据对其不适用"
            ),
        )

    for cyc, module, registry_name, registry in _SIMPLE_REGISTRIES:
        if letter != cyc:
            continue
        ref = _resolve_registry(code, cyc, module, registry_name, registry)
        if ref is not None:
            return ref
        return _unregistered(code, cyc, f"{module}.{registry_name}")

    if letter == "E":
        ref = _resolve_e(code)
        if ref is not None:
            return ref
        return _unregistered(code, "E", "e_cycle_specs")

    if letter == "I":
        ref = _resolve_i(code, standards)
        if ref is not None:
            return ref
        return _unregistered(code, "I", "i_cycle_accounts.I_CYCLE_ROW_CODES")

    if letter == "J":
        ref = _resolve_j(code, standards)
        if ref is not None:
            return ref
        return _unregistered(code, "J", "j_cycle_account_scope")

    if letter == "K":
        ref = _resolve_k(code, standards)
        if ref is not None:
            return ref
        return _unregistered(code, "K", "k_cycle_specs.K_CYCLE_SPECS")

    return ReportLineRef(
        wp_code=code,
        status=REF_NO_REPORT_LINE,
        reason=(
            f"循环字母 {letter} 不在平台已登记范围内"
            f"（科目余额驱动 = D~N，不适用 = {'/'.join(sorted(NON_BALANCE_DRIVEN_CYCLES))}）"
        ),
    )


def _unregistered(code: str, letter: str, registry_label: str) -> ReportLineRef:
    """该循环存在但这个码未登记 —— 与「声明为空」的原因文案有意不同。"""
    return ReportLineRef(
        wp_code=code,
        status=REF_NO_REPORT_LINE,
        reason=f"{letter} 循环的声明表 {registry_label} 里没有底稿 {code}",
    )


def indexed_wp_codes() -> list[str]:
    """索引覆盖的全部底稿编号（升序去重）。

    取值一律来自既有声明表的**键**，故与 per-cycle 声明的覆盖面**恒等** ——
    守卫按集合相等断言（多了 = 索引自造了映射知识；少了 = 某循环漏接）。
    """
    codes: set[str] = set()
    for _cyc, _module, _name, registry in _SIMPLE_REGISTRIES:
        codes.update(str(k).strip().upper() for k in registry)
    codes.update(wp for wp, _attr in _E_CONSTANTS)
    codes.update(str(k).strip().upper() for k in i_cycle_accounts.I_CYCLE_ROW_CODES)
    codes.update(wp for wp, _name, _table in _J_SPEC_TABLES)
    codes.update(str(k).strip().upper() for k in k_cycle_specs.K_CYCLE_SPECS)
    return sorted(codes)


__all__ = [
    "NON_BALANCE_DRIVEN_CYCLES",
    "REF_NON_BALANCE_DRIVEN",
    "REF_NO_REPORT_LINE",
    "REF_RESOLVED",
    "ReportLineRef",
    "indexed_wp_codes",
    "normalize_wp_code",
    "resolve_report_line_ref",
]
