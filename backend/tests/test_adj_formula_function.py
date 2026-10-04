"""ADJ() 公式函数的 L1 内核守卫。

spec: tb-adjustment-column-formula-closure Phase 1（tasks 1.1~1.5）

覆盖：
- 1.1 `FormulaContext.adj_data` 字段存在且与既有 5 个数据源字段同构
- 1.2 `_handle_adj` 归一复用 `normalize_adj_type`，归一失败报错而非静默 0
- 1.3 注册进 `_REGISTRY`（名称/arity/category）
- 1.4 **P6**：handler 纯同步（非 coroutine + 源码无 await + 不碰 DB 会话）
- 1.5 `validate_formula` 白名单自动生效 + 双向变异

判据设计：`ADJ('x','aje_net')` 在空 `adj_data` 上返 0 是**诚实的 0**（该科目确无
调整），与「第二参写错」必须区分 —— 后者走 `FormulaColumnError`。这是 Phase 0
B7 教训的直接应用：静默 0 会让配置错看起来像数据缺失。
"""
from __future__ import annotations

import ast
import inspect
import re
from dataclasses import fields as dc_fields
from decimal import Decimal

import pytest

from app.services.formula_engine import (
    _REGISTRY,
    FormulaContext,
    _handle_adj,
    execute,
    validate_formula,
)

# ─── fixture ────────────────────────────────────────────────────────────────

#: 与 `adj_net_batch` 返回值逐键同构（含 dr/cr，证明 handler 只取 net）
_ADJ_ROW = {
    "aje_net": Decimal("10000"),
    "aje_dr": Decimal("10000"),
    "aje_cr": Decimal("0"),
    "rje_net": Decimal("-2500"),
    "rje_dr": Decimal("0"),
    "rje_cr": Decimal("2500"),
}


@pytest.fixture()
def ctx() -> FormulaContext:
    return FormulaContext(
        tb_data={"6001": {"期末余额": Decimal("1000"), "AJE调整": Decimal("99")}},
        adj_data={"6001": dict(_ADJ_ROW)},
    )


# ─── 1.1 字段 ───────────────────────────────────────────────────────────────

def test_adj_data_field_exists_and_defaults_empty():
    """`adj_data` 必须是 default_factory=dict —— 缺省即空，既有调用方零回归。"""
    names = {f.name for f in dc_fields(FormulaContext)}
    assert "adj_data" in names, "FormulaContext 缺 adj_data 字段（Task 1.1）"
    assert FormulaContext().adj_data == {}, "adj_data 缺省必须是空 dict"


def test_adj_data_is_same_shape_as_other_sources():
    """与既有 5 个「code → {key: Decimal}」数据源字段同构（需求 3.1）。"""
    ctx_ = FormulaContext()
    two_level = ["tb_data", "prior_tb_data", "note_data", "wp_data", "aux_data", "adj_data"]
    for name in two_level:
        assert isinstance(getattr(ctx_, name), dict), f"{name} 应为 dict"


# ─── 1.3 注册 ───────────────────────────────────────────────────────────────

def test_adj_registered_in_registry():
    assert "ADJ" in _REGISTRY.known_function_names(), "ADJ 未注册进 _REGISTRY（Task 1.3）"


def test_adj_registry_metadata():
    meta = [m for m in _REGISTRY.list_all() if m.get("name") == "ADJ"]
    assert len(meta) == 1, f"ADJ 元数据应恰 1 条，实得 {len(meta)}"
    assert meta[0]["arity"] == 2, "ADJ 是双参函数"
    assert meta[0]["category"] == "取数", "ADJ 属取数类（与 TB/SUM_TB/AUX 同组）"


# ─── 1.2 归一 + 求值 ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw_type,expected",
    [
        ("aje_net", Decimal("10000")),
        ("aje", Decimal("10000")),
        ("AJE", Decimal("10000")),
        ("审计调整", Decimal("10000")),
        ("rje_net", Decimal("-2500")),
        ("rje", Decimal("-2500")),
        ("RJE", Decimal("-2500")),
        ("重分类", Decimal("-2500")),
    ],
)
def test_adj_accepts_all_normalize_variants(ctx, raw_type, expected):
    """第二参必须接受 `normalize_adj_type` 的全部既有写法（Task 1.2 复用要求）。"""
    r = execute(f"ADJ('6001','{raw_type}')", ctx)
    assert r.errors == [], f"{raw_type} 不应报错：{r.errors}"
    assert r.value == expected


def test_adj_variants_cover_the_whole_normalize_table():
    """🔴 变异防护：归一表若新增写法，本文件的参数化必须同步扩。

    直接对着单一真源 `VALID_ADJ_TYPE_LITERALS` 断言，而不是手抄一份清单 ——
    手抄的清单会在真源扩充时静默漏测。
    """
    from app.services.adjustment_amount_source import VALID_ADJ_TYPE_LITERALS

    covered = {"aje_net", "aje", "AJE", "审计调整", "rje_net", "rje", "RJE", "重分类"}
    # 归一是 lower() 后查表，故用小写比对
    assert {c.lower() for c in covered} >= set(VALID_ADJ_TYPE_LITERALS), (
        f"归一表新增了写法但本测试未覆盖："
        f"{set(VALID_ADJ_TYPE_LITERALS) - {c.lower() for c in covered}}"
    )


def test_adj_missing_account_returns_honest_zero(ctx):
    """科目不在 adj_data → 0 且**无 error**（诚实的 0：该科目确无调整）。"""
    r = execute("ADJ('9999','aje_net')", ctx)
    assert r.errors == []
    assert r.value == Decimal("0")


def test_adj_empty_context_returns_zero_without_error():
    """空 adj_data 不报错 —— 既有调用方（不填 adj_data）零回归。"""
    r = execute("ADJ('6001','aje_net')", FormulaContext())
    assert r.errors == []
    assert r.value == Decimal("0")


@pytest.mark.parametrize("bad_type", ["aje_dr", "aje_cr", "rje_dr", "xxx", ""])
def test_adj_bad_type_reports_error_not_silent_zero(ctx, bad_type):
    """🔴 第二参写错必须报错。

    静默返 0 会让「配置错」看起来像「该科目无调整」—— 那是 Phase 0 B7 缺陷的
    同一形态（已注册但无数据 vs 根本没这个键）。

    `aje_dr`/`aje_cr` 刻意落在这里：ADR-ADJ-005 的原始借贷是**展示口径**，
    参与算式会对贷方正常类方向反掉（Phase 0 修掉的 B4）。
    """
    r = execute(f"ADJ('6001','{bad_type}')", ctx)
    assert r.errors, f"ADJ 第二参 {bad_type!r} 应报错，实得静默值 {r.value}"
    assert "ADJ('6001'" in r.errors[0], f"错误信息应含出错的调用形态：{r.errors}"


def test_adj_only_exposes_net_never_raw_dr_cr(ctx):
    """ADJ 取的是 net，不是 dr 或 cr —— fixture 里三者刻意不同值。"""
    r = execute("ADJ('6001','aje_net')", ctx)
    assert r.value == _ADJ_ROW["aje_net"]
    # rje 的 net 为负而 cr 为正，若实现误取 cr 会得 +2500
    r2 = execute("ADJ('6001','rje_net')", ctx)
    assert r2.value == Decimal("-2500"), "rje 必须取归一净额（负数），不得取 cr 原始值"


def test_adj_participates_in_arithmetic(ctx):
    r = execute(
        "TB('6001','期末余额') + ADJ('6001','aje_net') + ADJ('6001','rje_net')", ctx
    )
    assert r.errors == []
    assert r.value == Decimal("8500"), "1000 + 10000 + (-2500)"


def test_adj_realtime_differs_from_tb_persisted_snapshot(ctx):
    """需求 3.3 的观测基础：ADJ（实时）与 TB(code,'AJE调整')（快照）是两个口径。

    fixture 刻意让两者不等（10000 vs 99）。这不是 bug —— 不等即说明持久化列
    过期，正是 Task 1.11 要暴露的信号。本测试钉住「两者确实走不同数据源」，
    防止后续有人"顺手"把 ADJ 改成读 tb_data 而让差异永远观测不到。
    """
    assert execute("ADJ('6001','aje_net')", ctx).value == Decimal("10000")
    assert execute("TB('6001','AJE调整')", ctx).value == Decimal("99")


# ─── 1.4 P6：L1 纯同步 ──────────────────────────────────────────────────────

def test_p6_handler_is_not_coroutine():
    assert not inspect.iscoroutinefunction(_handle_adj), (
        "L1 handler 必须纯同步 —— async handler 会让 execute() 返回 coroutine"
    )


def test_p6_handler_source_has_no_await():
    """源码级断言无 await（AST 口径，不靠字符串匹配避免注释误报）。"""
    tree = ast.parse(inspect.getsource(_handle_adj).lstrip())
    awaits = [n for n in ast.walk(tree) if isinstance(n, ast.Await)]
    assert awaits == [], f"_handle_adj 含 {len(awaits)} 处 await"


def test_p6_handler_does_not_touch_db_session():
    """不碰 DB 会话。

    判据是「无 DB 会话调用」而非「无 import 语句」—— handler 内 lazy import
    `normalize_adj_type`（纯同步函数）是 Task 1.2 明确要求的复用，不是耦合。
    故按**调用形态**判：不得出现 db/session 的执行调用或查询构造。
    """
    src = inspect.getsource(_handle_adj)
    banned = [
        r"\bdb\.execute\b",
        r"\bsession\.execute\b",
        r"\bawait\b",
        r"\bsa\.select\b",
        r"\bAsyncSession\b",
        r"\badj_net_batch\b",  # 取数是 L2 的事，L1 只消费 ctx
        r"\badj_net\b(?!_)",
    ]
    hits = [p for p in banned if re.search(p, src)]
    assert hits == [], f"_handle_adj 出现 DB/取数耦合形态：{hits}"


def test_p6_handler_reads_only_from_ctx():
    """正面判据：handler 的数据来源只能是 ctx.adj_data。"""
    src = inspect.getsource(_handle_adj)
    assert "ctx.adj_data" in src, "handler 必须从 ctx.adj_data 取数"


# ─── 1.5 白名单自动生效 + 双向变异 ──────────────────────────────────────────

def test_validate_formula_accepts_adj():
    """`validate_formula` 的已知函数集派生于 `_REGISTRY` ⇒ 注册后自动放行。"""
    assert validate_formula("ADJ('6001','aje_net')") == []


def test_validate_formula_accepts_adj_in_composite_expression():
    assert validate_formula(
        "TB('6001','期末余额') + ADJ('6001','aje_net') - ADJ('6001','rje_net')"
    ) == []


def test_validate_formula_still_rejects_unknown_function():
    """🔴 反向变异：白名单不是全放行。"""
    errs = validate_formula("NOSUCHFUNC('6001')")
    assert errs, "未注册函数必须被拒"
    assert any("NOSUCHFUNC" in e for e in errs), errs


def test_adj_not_classified_as_blocked():
    """`execute` 的 `_is_blocked_formula` 不得拦下 ADJ。"""
    r = execute("ADJ('6001','aje_net')", FormulaContext(adj_data={"6001": dict(_ADJ_ROW)}))
    assert not r.blocked, f"ADJ 被误判 BLOCKED：{r.errors}"
    assert r.value == Decimal("10000")


# ─── 1.6 P9：豁免已删且不复活 ───────────────────────────────────────────────

#: 被删豁免常量的名字。拆写拼接，避免本模块自身成为扫描命中。
_EXEMPT_NAME = "_KNOWN_ADJ" + "_EXEMPT"


def _symbol_references(path, name: str) -> list[int]:
    """返回 `name` 作为**真实符号**（赋值目标/读取/属性/import）出现的行号。

    🔴 判据是 AST 符号引用，**不是**文本匹配。理由（铁律㉒的直接应用）：
    docstring 与注释里写出历史常量名是**有价值的记录**（说明为什么删掉它），
    文本口径会把这种记录判成"缺陷复活"，即假阳。首版就是这么写的，
    立刻被自己的 docstring 打红。
    """
    import ast as _ast

    try:
        tree = _ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    lines: list[int] = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Name) and node.id == name:
            lines.append(node.lineno)
        elif isinstance(node, _ast.Attribute) and node.attr == name:
            lines.append(node.lineno)
        elif isinstance(node, (_ast.Import, _ast.ImportFrom)):
            if any(a.name == name or a.asname == name for a in node.names):
                lines.append(node.lineno)
    return sorted(lines)


def test_p9_exemption_constant_is_gone():
    """`_KNOWN_ADJ_EXEMPT` 的**符号引用**数必须为 0（P9）。

    spec: tb-adjustment-column-formula-closure 需求 2.5

    该常量曾把「校验引擎不认 ADJ()」固化成预期行为（断言两条预设**必须**失败）。
    其注释自称「两套并存的既有平台缺口」⇒ 留着即假绿：测试全绿会让人以为
    ADJ() 可用，而实际上它在校验层被拒。本测试防它以任何形式复活。
    """
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    me = Path(__file__).resolve()

    hits: list[str] = []
    for py in backend.rglob("*.py"):
        if py.resolve() == me:
            continue
        for lineno in _symbol_references(py, _EXEMPT_NAME):
            hits.append(f"{py.relative_to(backend)}:{lineno}")

    assert hits == [], f"豁免常量以符号形式复活：{hits}"


def test_p9_scanner_catches_real_reference(tmp_path):
    """🔴 双向变异：扫描器必须能抓到真实引用，否则上一条是空转。

    正面样本（应命中）：赋值 + 读取 + import
    负面样本（不得命中）：docstring / 注释里的同名文本
    """
    positive = tmp_path / "pos.py"
    positive.write_text(
        f'{_EXEMPT_NAME} = {{"AJE调整"}}\n'
        f'def f():\n    return {_EXEMPT_NAME}\n',
        encoding="utf-8",
    )
    assert _symbol_references(positive, _EXEMPT_NAME), "扫描器漏掉真实符号引用（空转）"

    negative = tmp_path / "neg.py"
    negative.write_text(
        f'"""历史说明：原 {_EXEMPT_NAME} = {{"AJE调整","RJE调整"}} 已删。"""\n'
        f'# 也不要命中注释里的 {_EXEMPT_NAME}\n'
        f'X = 1\n',
        encoding="utf-8",
    )
    assert _symbol_references(negative, _EXEMPT_NAME) == [], (
        "扫描器把 docstring/注释里的历史记录判成引用（假阳）"
    )


def test_p9_all_platform_adj_presets_validate():
    """🔴 全平台 ADJ() 预设必须全部通过校验 —— 这是注册的真实收益面。

    豁免的注释只提到「K1-1 早已用 ADJ()」，实测**远不止 K1**：
    现算 78 个底稿（D1~N5 + F5）共 160 条预设用 ADJ()，注册前**全部**校验失败。

    断言用「零失败 + 规模下界」两条：
    - 零失败：任何一条不通过即打红
    - 规模下界写成 `>= 100`（**非**等值）—— 预设库会随底稿扩充增长，
      写死 160 会让新增底稿把本测试打红；但下界足够大到能发现"预设被整批删空"。
    """
    from app.services.formula_engine import validate_formula as _vf
    from app.services.formula_management.preset_library import convert_prefill_presets

    adj_entries = [e for e in convert_prefill_presets() if "ADJ(" in e.expression]
    assert len(adj_entries) >= 100, (
        f"全平台 ADJ() 预设现算 {len(adj_entries)} 条，低于下界 100 —— "
        f"预设库可能被整批删空，先查 preset_library 再改本断言"
    )
    failing = {
        f"[{e.page_key}] {e.target_cell}": _vf(e.expression)
        for e in adj_entries
        if _vf(e.expression)
    }
    assert failing == {}, f"ADJ() 预设校验失败 {len(failing)} 条：{failing}"


# ─── 1.7 grammar pattern 与消费方契约 ───────────────────────────────────────

def test_adj_pattern_exists_and_parses():
    """`ADJ_PATTERN` 在 grammar 单一真源里（Task 1.7）。"""
    from app.services.formula_grammar import ADJ_PATTERN

    m = ADJ_PATTERN.search("ADJ('6001','aje_net')")
    assert m is not None
    assert m.group(1) == "6001"
    assert m.group(2) == "aje_net"


def test_adj_pattern_in_token_patterns():
    from app.services.formula_grammar import ADJ_PATTERN, TOKEN_PATTERNS

    assert ("ADJ", ADJ_PATTERN) in TOKEN_PATTERNS


def test_token_patterns_index_contract():
    """🔴 `TOKEN_PATTERNS` 的硬编码下标契约。

    `formula_engine.get_formula_account_codes` 写的是
    `_TOKEN_PATTERNS[1][1]`（SUM_TB）与 `_TOKEN_PATTERNS[2][1]`（TB）。
    新 token 若插在前部会让它静默取到错误 pattern —— 科目码提取错会连带
    调整额汇总错（`get_formula_account_codes` 正是 `summary_with_adjustments`
    用来决定"这一行涉及哪些科目"的函数）。

    本测试钉住下标，迫使后来者把新 token 追加到末尾。
    """
    from app.services.formula_grammar import (
        SUM_TB_PATTERN,
        TB_PATTERN,
        TOKEN_PATTERNS,
    )

    assert TOKEN_PATTERNS[1] == ("SUM_TB", SUM_TB_PATTERN), (
        "下标 1 必须是 SUM_TB —— get_formula_account_codes 按此下标取 pattern"
    )
    assert TOKEN_PATTERNS[2] == ("TB", TB_PATTERN), (
        "下标 2 必须是 TB —— get_formula_account_codes 按此下标取 pattern"
    )


def test_every_token_pattern_has_regex_branch():
    """🔴 `TOKEN_PATTERNS` 的每个 token 在 `_execute_regex` 里都要有分支。

    该函数 `val` 初值为 `Decimal("0")`、循环末尾无条件替换 ⇒ 缺分支 = 静默置 0。
    这是「AST 路径对、降级路径错」的隐蔽形态。按源码文本判分支存在性。
    """
    from app.services.formula_engine import _execute_regex
    from app.services.formula_grammar import TOKEN_PATTERNS

    src = inspect.getsource(_execute_regex)
    missing = [
        name for name, _ in TOKEN_PATTERNS
        if f'"{name}"' not in src and f"'{name}'" not in src
    ]
    assert missing == [], f"_execute_regex 缺这些 token 的分支（会被静默置 0）：{missing}"


def test_regex_path_and_ast_path_agree_on_adj(ctx):
    """降级路径与 AST 路径对 ADJ 必须同值（Task 1.7 的实质判据）。"""
    from app.services.formula_engine import _execute_regex

    for expr, expected in [
        ("ADJ('6001','aje_net')", Decimal("10000")),
        ("ADJ('6001','rje_net')", Decimal("-2500")),
        ("ADJ('9999','aje_net')", Decimal("0")),
    ]:
        ast_val = execute(expr, ctx).value
        regex_val = _execute_regex(expr, ctx).value
        assert ast_val == regex_val == expected, (
            f"{expr}: AST={ast_val} regex={regex_val} 期望={expected}"
        )


def test_regex_path_reports_error_on_bad_adj_type(ctx):
    """降级路径对第二参写错也必须记 error（与 AST 路径同口径）。"""
    from app.services.formula_engine import _execute_regex

    r = _execute_regex("ADJ('6001','aje_dr')", ctx)
    assert r.errors, "降级路径静默吞掉了第二参错误"


def test_adj_not_in_report_engine_zero_substitution_list():
    """🔴 反向断言：ADJ **不得**被加进 report_engine 的「一律置 0」列表。

    spec tasks 1.7 的显式警告。`report_engine.evaluate_formula` 对
    PREV/NOTE/WP/AUX 做 `expression.replace(match.group(0), "0", 1)` ——
    那是报表域的有意行为（这些数据源在报表路径上不可用）。
    ADJ 走 `ctx.adj_data`（由 L2 经 `adj_net_batch` 填充），
    若被加进置 0 列表则报表域调整额恒 0，且**不报错**、无 trace 线索。
    """
    from app.services import report_engine as _re_mod

    src = inspect.getsource(_re_mod.evaluate_formula)
    # 定位置 0 的那段：形如 `for pattern in [_NOTE_PATTERN, _WP_PATTERN, _AUX_PATTERN]:`
    zero_block = re.search(r"for pattern in \[([^\]]+)\]", src)
    assert zero_block, "未找到 report_engine 的置 0 pattern 列表（结构变了，需复核本守卫）"
    listed = zero_block.group(1)
    assert "_ADJ_PATTERN" not in listed and "ADJ_PATTERN" not in listed, (
        f"ADJ 被加进了 report_engine 的置 0 列表 ⇒ 报表域调整额会恒 0：{listed}"
    )
    # 同时确认 PREV 的单独置 0 循环里也没混入 ADJ
    assert "_ADJ_PATTERN.finditer" not in src or "adj_data" in src, (
        "ADJ 在 report_engine 里被 finditer 置 0 而未走 adj_data"
    )


def test_adj_ref_produces_no_uri():
    """ADJ 不产生地址 URI —— 这是它不进宽松表的理由，也是安全网。

    `address_registry.validate_formula_refs` 遍历全部宽松 pattern，
    对每个命中调 `formula_ref_to_uri`，`if uri and uri not in uri_set` 则报
    「悬空引用」。即使将来 ADJ 被加进宽松表，只要这里返 `None` 就不会误报。
    两条守卫（本条 + `test_adj_deliberately_absent_from_relaxed_patterns`）
    构成双保险：任一被破坏都会打红。
    """
    from app.services.address_registry import formula_ref_to_uri

    assert formula_ref_to_uri("ADJ('6001','aje_net')") is None, (
        "ADJ 现在会产生 URI —— 须同步把 ADJ 科目码注册进 tb 地址域，"
        "否则 validate_formula_refs 会对每条 ADJ 公式报悬空引用"
    )


def test_adj_deliberately_absent_from_relaxed_patterns():
    """🔴 ADJ **不得**进 `RELAXED_FORMULA_PATTERNS`（实测后撤回的决定）。

    该表不只是「宽松正则」，它同时是 **ACNR 地址域函数集**：
    `address_registry.formula_ref_to_uri` 遍历它做公式↔URI 互转，
    `acnr/formula_validation._NON_WP_FUNCS` 由它派生。

    ADJ 没有 ACNR URI 等价（调整额是按 `(科目, 调整类型)` 聚合的实时汇总，
    不是可寻址坐标）⇒ 加进去只会让它白跑两条 ACNR 消费路径。

    我在 Task 1.7 首版按「保持风格一致」把它加进去了，随后实测发现
    `normalize_ref` 的状态判定链路上它没有地址语义，据实证撤回。
    """
    from app.services.formula_grammar import RELAXED_FORMULA_PATTERNS

    assert "ADJ" not in RELAXED_FORMULA_PATTERNS, (
        "ADJ 被加进宽松表 —— 若确要加，必须同时给 address_registry.formula_ref_to_uri "
        "加 ADJ 分支并把科目码注册进地址域，否则 validate_formula_refs 会误报悬空引用"
    )


def test_fallback_known_funcs_matches_registry():
    """🔴 `_FALLBACK_KNOWN_FUNCS` 是 `_REGISTRY` 的手抄副本，必须同步。

    不同步的后果只在 `formula_engine` import 失败的 fail-open 路径上显现：
    新注册函数被判 `unmapped_function` → pending，而正常路径判 migrated
    ⇒ 同一条公式两种迁移状态，且只在降级时错（最难发现的形态）。

    自定义函数（`category="自定义"`，运行时 `register`）不在手抄清单里是正常的，
    故只断言**内置函数**全覆盖。
    """
    from app.services.formula_engine import _REGISTRY
    from app.services.formula_management.preset_acnr_migration import (
        _FALLBACK_KNOWN_FUNCS,
    )

    builtin = {
        m["name"].upper()
        for m in _REGISTRY.list_all()
        if m.get("category") != "自定义"
    }
    missing = builtin - set(_FALLBACK_KNOWN_FUNCS)
    assert missing == set(), (
        f"这些内置函数已注册但未同步进 _FALLBACK_KNOWN_FUNCS：{sorted(missing)} —— "
        f"fail-open 路径会把它们判成 pending"
    )


def test_adj_is_not_in_pending_allowlist():
    """ADJ 已注册 ⇒ 不得留在「无 ACNR 等价、待迁移」白名单里。

    留着会让 `test_p22_pending_allowlist_functions_are_pending` 与实际状态矛盾
    （`normalize_ref` 按 `_known_acnr_funcs()` = `_REGISTRY` 判，已返 migrated）。
    """
    from app.services.formula_management.preset_acnr_migration import (
        PENDING_FUNCTION_ALLOWLIST,
    )

    assert "ADJ" not in PENDING_FUNCTION_ALLOWLIST


def test_adj_normalizes_to_migrated():
    """`normalize_ref("=ADJ(...)")` 判 migrated（与注册状态一致）。"""
    from app.services.formula_management.preset_acnr_migration import (
        STATUS_MIGRATED,
        normalize_ref,
    )

    assert normalize_ref("=ADJ('1121','aje_net')").status == STATUS_MIGRATED
    assert normalize_ref("=ADJ('1121','rje_net')").status == STATUS_MIGRATED


def test_aux_pattern_unchanged_by_adj_addition():
    """🔴 回归钉子：加 ADJ 时我手误把 AUX_PATTERN 从三参改成两参，已修回。

    AUX 是**三参**且第二参允许空串（`[^']*?`）—— 真库存在 `AUX('1122','','期末')`
    这类维度为空的写法。写成 `[^']+` 会让它整条匹配不上而静默按 0 处理。
    """
    from app.services.formula_grammar import AUX_PATTERN

    m = AUX_PATTERN.search("AUX('1122','客户A','期末余额')")
    assert m is not None and len(m.groups()) == 3, "AUX 必须是三参"
    assert AUX_PATTERN.search("AUX('1122','','期末余额')") is not None, (
        "AUX 第二参必须允许空串（[^']*? 而非 [^']+）"
    )


# ─── 1.9 from_simple_map 只增不改 ───────────────────────────────────────────

_SIMPLE_TB = {"1122": Decimal("500"), "6001": Decimal("1000")}
_SIMPLE_ADJ = {
    "1122": {"aje_net": Decimal("77"), "rje_net": Decimal("-11")},
    "6001": {"aje_net": Decimal("300"), "rje_net": Decimal("0")},
    # 刻意含一个 tb_map 里没有的科目，验证不会无中生有
    "9999": {"aje_net": Decimal("999"), "rje_net": Decimal("999")},
}


def test_from_simple_map_default_produces_exactly_three_keys():
    """🔴 需求 3.4：不传 `adj_map` 时，内层键集必须**恰好**是既有 3 键。

    多一个键都不行 —— 既有调用方（10 个测试文件 + `execute_formula`）
    的行为必须逐字不变。
    """
    ctx = FormulaContext.from_simple_map(dict(_SIMPLE_TB))
    for code in _SIMPLE_TB:
        assert set(ctx.tb_data[code]) == {"期末余额", "审定数", "未审数"}, (
            f"{code} 的键集变了：{set(ctx.tb_data[code])}"
        )
    assert ctx.adj_data == {}, "不传 adj_map 时 adj_data 必须为空"


def test_from_simple_map_default_values_unchanged():
    """既有 3 键的**值**语义不变：三者一律等于 tb_map 的原值。"""
    ctx = FormulaContext.from_simple_map(dict(_SIMPLE_TB))
    for code, val in _SIMPLE_TB.items():
        assert ctx.tb_data[code]["期末余额"] == val
        assert ctx.tb_data[code]["审定数"] == val
        assert ctx.tb_data[code]["未审数"] == val


def test_from_simple_map_with_adj_map_adds_two_keys():
    """传 `adj_map` 时补两键，且既有 3 键的值仍不变。"""
    ctx = FormulaContext.from_simple_map(dict(_SIMPLE_TB), adj_map=_SIMPLE_ADJ)

    assert set(ctx.tb_data["1122"]) == {
        "期末余额", "审定数", "未审数", "AJE调整", "RJE调整",
    }
    # 既有 3 键值不变（只增不改的"不改"部分）
    assert ctx.tb_data["1122"]["期末余额"] == Decimal("500")
    # 新增两键取归一净额
    assert ctx.tb_data["1122"]["AJE调整"] == Decimal("77")
    assert ctx.tb_data["1122"]["RJE调整"] == Decimal("-11")


def test_from_simple_map_does_not_invent_accounts():
    """🔴 `adj_map` 里有而 `tb_map` 里没有的科目不得进 `tb_data`。

    本方法的 `tb_data` 分母由 `tb_map` 决定。凭 `adj_map` 无中生有会让
    `SUM_TB('1100~1199','期末余额')` 之类的区间求和多出本不存在的科目 ——
    而那些科目没有 `期末余额` 键，会落进「已注册但无数据」态（B7 同形）。
    """
    ctx = FormulaContext.from_simple_map(dict(_SIMPLE_TB), adj_map=_SIMPLE_ADJ)
    assert "9999" not in ctx.tb_data, "adj_map 独有的科目被塞进了 tb_data"
    # 但 adj_data 保留完整（它是另一个分母，ADJ() 按科目直查不做区间求和）
    assert "9999" in ctx.adj_data


def test_from_simple_map_adj_map_serves_both_paths():
    """一个 `adj_map` 同时让 `TB(...,'AJE调整')` 与 `ADJ(...,'aje_net')` 可解析。"""
    ctx = FormulaContext.from_simple_map(dict(_SIMPLE_TB), adj_map=_SIMPLE_ADJ)

    r_tb = execute("TB('1122','AJE调整')", ctx)
    assert r_tb.errors == [] and r_tb.value == Decimal("77")

    r_adj = execute("ADJ('1122','aje_net')", ctx)
    assert r_adj.errors == [] and r_adj.value == Decimal("77")

    # 🔴 本路径下两者相等是**因为同源**（都来自 adj_map），
    # 与 L2 真实路径的"快照 vs 实时"差异不矛盾：那里 tb_data 的 AJE调整
    # 来自 trial_balance 持久化列，adj_data 来自 adj_net_batch。
    assert r_tb.value == r_adj.value


def test_from_simple_map_adj_data_is_not_aliased():
    """`adj_data` 应是 `adj_map` 的副本，调用方后续改动不得影响已建 ctx。"""
    src = {"1122": {"aje_net": Decimal("1")}}
    ctx = FormulaContext.from_simple_map({"1122": Decimal("10")}, adj_map=src)
    src["8888"] = {"aje_net": Decimal("999")}
    assert "8888" not in ctx.adj_data, "adj_data 与入参共享引用（应 dict() 拷贝）"


def test_from_simple_map_signature_is_backward_compatible():
    """`adj_map` 必须是**最后**一个参数且有默认值（既有位置调用零回归）。

    既有调用形态含 `from_simple_map(tb, row_cache, prior_map)` 的**位置**传参
    （如 `test_formula_engine_baseline._build_fe_ctx`），插在中间会静默错位。
    """
    sig = inspect.signature(FormulaContext.from_simple_map)
    params = list(sig.parameters)
    assert params == ["tb_map", "row_cache", "prior_map", "adj_map"], (
        f"参数顺序变了：{params} —— 既有位置传参会错位"
    )
    assert sig.parameters["adj_map"].default is None


# ─── 1.12 文档与实现一致 ───────────────────────────────────────────────────


def test_caliber_matrix_has_fourth_row():
    """口径矩阵必须含第 4 行（试算平衡表调整列）—— Phase 0 收敛的那一处。"""
    from app.services import adjustment_amount_source as mod

    doc = mod.__doc__ or ""
    assert "试算平衡表调整列" in doc, "口径矩阵缺第 4 行（试算平衡表调整列）"
    # 该行的两个过滤必须写明
    idx = doc.index("试算平衡表调整列")
    row = doc[idx : idx + 120]
    assert "approved" in row and "workpaper" in row, (
        f"第 4 行未写明两个过滤：{row}"
    )


def test_doc_explains_snapshot_vs_realtime_semantics():
    """🔴 文档必须说明 `TB(...,'AJE调整')` 与 `ADJ(...,'aje_net')` 的语义差异。

    两者读的是不同东西（持久化快照 vs 实时汇总），混用会让人以为
    "两个写法等价、随便用哪个"。Task 1.12 要求写清。
    """
    from app.services import adjustment_amount_source as mod

    doc = mod.__doc__ or ""
    assert "TB(code,'AJE调整')" in doc, "文档未提 TB 写法"
    assert "ADJ(code,'aje_net')" in doc, "文档未提 ADJ 写法"
    assert "持久化快照" in doc and "实时汇总" in doc, "未说明两者语义"
    assert "recalc_adjustments" in doc, "未说明快照的产生方（谁落列）"


def test_doc_points_to_the_observability_signal():
    """文档必须指向那个报告差异的检查项（否则读者不知道去哪看）。"""
    from app.services import adjustment_amount_source as mod

    doc = mod.__doc__ or ""
    assert "_check_adjustment_snapshot_vs_realtime" in doc or (
        "check_full_chain" in doc
    ), "文档未指向可观测信号的实现位置"
    assert "不自动重算" in doc or "也不自动重算" in doc, (
        "文档未明示不承诺自动 recalc（需求 3.3）"
    )


def test_doc_explains_why_adj_has_no_dr_cr():
    """文档必须解释 ADJ 只给净额的原因（否则会被当成疏漏"补上"）。"""
    from app.services import adjustment_amount_source as mod

    doc = mod.__doc__ or ""
    assert "aje_dr" in doc, "文档未提 dr/cr 的处置"
    assert "B4" in doc, "未关联 Phase 0 的 B4 缺陷（方向反掉）"


def test_documented_signal_method_actually_exists():
    """🔴 文档提到的检查方法必须真实存在（防文档写了实现没做）。"""
    from app.services.consistency_check_service import ConsistencyCheckService

    assert hasattr(
        ConsistencyCheckService, "_check_adjustment_snapshot_vs_realtime"
    ), "文档声称的检查方法不存在"


def test_documented_adj_dr_behaviour_matches_implementation():
    """🔴 文档说 `ADJ(code,'aje_dr')` 会报错 —— 实证它真的报错。

    文档与实现的一致性必须**可执行地**验证，不能只靠人读。
    """
    ctx_ = FormulaContext(adj_data={"6001": dict(_ADJ_ROW)})
    r = execute("ADJ('6001','aje_dr')", ctx_)
    assert r.errors, "文档声称 aje_dr 会报错，实际静默返值 —— 文档或实现有一方过期"
