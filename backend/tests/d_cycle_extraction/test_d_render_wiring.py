"""D 循环 render 接线守卫 —— Property 1 / 2 / 6 / 8 / 11。

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 1.1, 1.2, 1.3, 1.8

不连库（源码级 + `inspect.signature` 实证），可进 CI。

**为什么要源码级守卫**：平台已多次出现「共享件写好了却零消费方 = 死代码」
（`d_cycle_specs` 本身就是一例）以及「按错误签名调用被 `except Exception` 吞成
WARNING → 取数恒空且无报错线索」（N2/N5 实证）。这两类都不会被功能测试抓到。
"""
from __future__ import annotations

import importlib
import inspect
import re

import pytest

# 走 `d_account_resolver` 的循环（D1 走自己的薄壳、D4 走 D4AccountScope）
_RESOLVER_CYCLES = {
    "D2": "app.routers.wp_render_strategies._d2_accounts_receivable",
    "D3": "app.routers.wp_render_strategies._d3_prepaid_accounts",
    "D5": "app.routers.wp_render_strategies._d5_receivables_financing",
    "D6": "app.routers.wp_render_strategies._d6_contract_assets",
    "D7": "app.routers.wp_render_strategies._d7_contract_liabilities",
}
_ALL_CYCLES = dict(
    _RESOLVER_CYCLES,
    D1="app.routers.wp_render_strategies._d1_notes_receivable",
    D4="app.routers.wp_render_strategies._d4_operating_revenue",
)

#: 改造前各循环的硬编码前缀（必须清零）。
#: D3 的 `2205%` 是**有意保留**的 D3↔D7 交叉核对，不在此表。
_LEGACY_HARDCODED = {
    "D2": ("LIKE '1122%'", "LIKE '1231-02%'", '"hardcoded"'),
    "D5": ("LIKE '1124%'",),
    "D6": ("LIKE '1141%'",),
    "D7": ("LIKE '2205%'",),
}


def _code(mod_path: str) -> str:
    """模块源码（去整行注释，避免注释里的反例被数成真实调用）。"""
    src = inspect.getsource(importlib.import_module(mod_path))
    return "\n".join(l for l in src.split("\n") if not l.strip().startswith("#"))


# ───────────────── Property 1：解析结果被真实消费而非仅被赋值 ─────────────────


@pytest.mark.parametrize("wp,mod_path", sorted(_RESOLVER_CYCLES.items()))
def test_property1_解析结果被真实消费(wp, mod_path):
    """判据必须**变量名无关** —— 先抓赋值目标，再数该变量被读次数。

    平台已实证：按固定变量名（如 `accounts.`）grep 会假阴性 —— G6/G7 的子策略
    赋值给 `result`，曾被误判成死代码。
    """
    code = _code(mod_path)
    m = re.search(r"(\w+)\s*=\s*await\s+resolve_d_cycle_account_codes", code)
    assert m, "%s 未调用 resolve_d_cycle_account_codes" % wp
    var = m.group(1)
    reads = len(re.findall(r"\b%s\s*[.\[]" % re.escape(var), code))
    passes = len(re.findall(r"[(,]\s*%s\s*[,)]" % re.escape(var), code))
    none_checks = len(re.findall(r"%s\s+is\s+not\s+None" % re.escape(var), code))
    assert reads + passes >= 1, (
        "%s 的解析结果 `%s` 被赋值但从不消费（死代码）；reads=%d passes=%d checks=%d"
        % (wp, var, reads, passes, none_checks)
    )


def test_property1_d1_走自己的薄壳(wp=None):
    """D1 是零回归红线：必须继续用 `resolve_d1_account_codes`，且不得误接 D2~D7 的解析器。"""
    code = _code(_ALL_CYCLES["D1"])
    assert "resolve_d1_account_codes" in code
    assert "resolve_d_cycle_account_codes" not in code, (
        "D1 误接了 D2~D7 的解析器 —— 它有自己的 D1AccountCodes 与守卫，属零回归红线"
    )


# ───────────────── Property 2：render 内不残留硬编码科目码 ─────────────────


@pytest.mark.parametrize("wp,patterns", sorted(_LEGACY_HARDCODED.items()))
def test_property2_硬编码前缀已清零(wp, patterns):
    code = _code(_ALL_CYCLES[wp])
    left = [p for p in patterns if p in code]
    assert not left, "%s 仍残留硬编码：%s" % (wp, left)


def test_property2_d3_保留有意的交叉核对():
    """🔴 反向锁死：D3 的 `2205%` 是**有意的** D3↔D7 交叉核对，不得当硬编码清掉。

    它注入的是**合同负债**审定数（落 `responses_snapshot['D3-d7-tb-audited-amount']`），
    供 D3 披露表做 CAS14 预收拆分口径核对。误删会让该核对静默失效。
    """
    code = _code(_ALL_CYCLES["D3"])
    assert "LIKE '2205%'" in code, "D3↔D7 交叉核对被误删"
    assert "D3-d7-tb-audited-amount" in code, "D3↔D7 交叉核对的锚点被误删"


# ───────────────── Property 6：共享件按实证签名调用 ─────────────────


def test_property6_select_leaves_不得被_await():
    """`select_leaves` 是**同步纯函数** —— `await` 它会 TypeError 并被 fail-open 吞掉。

    平台实证：G6 的 `_fetch_tb_data` 曾整段静默失效正是因为 `await select_leaves(...)`。
    """
    from app.services.four_table import leaf_aggregation

    assert not inspect.iscoroutinefunction(leaf_aggregation.select_leaves)
    for wp, mod_path in _ALL_CYCLES.items():
        code = _code(mod_path)
        assert "await select_leaves" not in code, "%s 对同步函数用了 await" % wp
    for mod_name in (
        "app.services.d_cycle_extraction.d_tb_fetch",
        "app.services.d_cycle_extraction.d_account_resolver",
    ):
        assert "await select_leaves" not in _code(mod_name), mod_name


def test_property6_get_active_filter_四参且async():
    """`get_active_filter` 全签名 4 参且 async —— 单参调用会被 except 吞成空结果。"""
    from app.services.dataset_query import get_active_filter

    assert inspect.iscoroutinefunction(get_active_filter)
    params = list(inspect.signature(get_active_filter).parameters)
    assert params[:4] == ["db", "table", "project_id", "year"], params


def test_property6_编排件用共享取数入口():
    """编排件必须复用共享件，不得自造 tb_balance / trial_balance 查询。"""
    code = _code("app.services.d_cycle_extraction.d_tb_fetch")
    for fn in (
        "fetch_tb_subtree",
        "fetch_trial_balance_rows",
        "fetch_trial_balance_amounts",
        "resolve_leaf_totals",
        "build_parent_check",
    ):
        assert fn in code, "编排件未使用共享件 %s" % fn
    # 不得自己写 SQL
    assert "sa.select" not in code, "编排件自造了 ORM 查询（应走 tb_query 共享件）"
    assert "sa.text" not in code, "编排件自造了裸 SQL（应走 tb_query 共享件）"


def test_property6_resolve_leaf_totals_前不得筛叶子():
    """🔴 `resolve_leaf_totals` 需要**父行**做符号约定判定 —— 预先筛叶子会让它失效。

    判据是**调用形态** `select_leaves(` 而非字符串出现 —— `_code()` 只剥整行注释，
    docstring 里以反引号提及该函数名是合法的（本守卫首版即因此假红）。
    """
    code = _code("app.services.d_cycle_extraction.d_tb_fetch")
    calls = re.findall(r"\bselect_leaves\s*\(", code)
    assert not calls, (
        "编排件调用了 select_leaves(%d 处) —— resolve_leaf_totals 前筛掉父行会让"
        "「取与父额勾稽成立的符号约定」永久失效" % len(calls)
    )
    # 反向自检：该文件确实提到过这个函数名（否则本断言等于扫了个空文件）
    assert "select_leaves" in code, "锚点丢失 —— 本守卫可能在扫错文件"


# ───────────────── Property 8 / 11：槽间不互相污染 ─────────────────


def test_property11_原值与备抵槽键不同():
    from app.services.d_cycle_extraction.d_tb_fetch import (
        SLOT_GROSS,
        SLOT_KEYS,
        SLOT_PROVISION,
    )

    assert SLOT_GROSS != SLOT_PROVISION
    assert set(SLOT_KEYS) == {SLOT_GROSS, SLOT_PROVISION}


def test_property8_d1_d2_备抵科目声明不同():
    """D1 与 D2 的备抵兜底码与主体关键词都必须不同（否则两循环会取同一份坏账）。"""
    from app.services.d_cycle_extraction.d1_account_resolver import (
        D1_FALLBACK_PROVISION,
    )
    from app.services.d_cycle_extraction.d_account_resolver import (
        D2_SPEC,
        D_SUBJECT_KEYWORDS,
    )

    assert D1_FALLBACK_PROVISION not in D2_SPEC.fallback_provision
    assert D2_SPEC.fallback_provision == ("1231-02",)
    assert D1_FALLBACK_PROVISION == "1231-01"
    assert D_SUBJECT_KEYWORDS["D2"] == ("应收账款",)


# ───────────────── 四态与溯源键：全部循环都下发 ─────────────────


#: `parent_check` 的合法**写入**形态（下发到载荷才算下发）。
#
# 🔴 断言必须按写入形态、不能用裸子串 `"parent_check" in code`（2026-08-05 变异检验
# 抓出）：`from ... import build_d_parent_check` 这个 **import 名本身含该子串** →
# 删掉真正的下发行后守卫**仍然绿**。与 memory 已记的「标签存在性断言必须带边界，
# `toContain('<Foo')` 会被 `<FooREMOVED` 骗过」同族。
_PARENT_CHECK_WRITE_RE = re.compile(
    r'(?:html_data|project_context)\s*\[\s*[\'"]parent_check[\'"]\s*\]\s*='
)


@pytest.mark.parametrize("wp,mod_path", sorted(_ALL_CYCLES.items()))
def test_每个循环都下发_parent_check(wp, mod_path):
    """三口径自检是本 spec 对全部 7 个循环的统一要求（暴露 trial_balance 父子双算）。

    **Validates: Requirements 1.6**
    """
    code = _code(mod_path)
    assert _PARENT_CHECK_WRITE_RE.search(code), (
        "%s 未把 parent_check **写入载荷**（只 import 不下发 = 死代码）" % wp
    )


def test_parent_check_写入形态断言的反向自检():
    """🔴 证明本文件的判据确实比裸子串强 —— 否则「删掉下发行」这个最核心的变异会静默逃逸。"""
    # 只有 import、没有写入 → 裸子串判据会误判为通过，写入形态判据必须判否
    only_import = "from app.services.d_cycle_extraction.d_tb_fetch import build_d_parent_check\n"
    assert "parent_check" in only_import, "裸子串判据在此样本上为真（正是它的缺陷）"
    assert not _PARENT_CHECK_WRITE_RE.search(only_import), (
        "写入形态判据必须能区分「import 了」与「下发了」"
    )
    # 两种真实写入形态都要认
    for sample in (
        'html_data["parent_check"] = _d1_tb.parent_check',
        "project_context['parent_check'] = await build_parent_check_for_specs(",
    ):
        assert _PARENT_CHECK_WRITE_RE.search(sample), "合法写入形态被漏判: %s" % sample


@pytest.mark.parametrize("wp,mod_path", sorted(_ALL_CYCLES.items()))
def test_每个循环都下发_tb_source_codes(wp, mod_path):
    assert "tb_source_codes" in _code(mod_path), "%s 未下发 tb_source_codes" % wp


def test_四态标识齐备():
    """`SlotAmounts.state` 必须覆盖四态且两两互斥（Property 10 的结构前提）。"""
    from app.services.d_cycle_extraction.d_tb_fetch import SlotAmounts

    assert SlotAmounts(key="g", found=False).state == "no_account"
    assert SlotAmounts(key="g", found=True, query_codes=("1231-05",),
                       tb_rows_count=0, prefix_mismatch=True).state == "prefix_mismatch"
    assert SlotAmounts(key="g", found=True, query_codes=("1141",),
                       tb_rows_count=0).state == "no_data"
    assert SlotAmounts(key="g", found=True, query_codes=("1122",),
                       tb_rows_count=3, closing=0.0).state == "ok"
    states = {
        SlotAmounts(key="g", found=False).state,
        SlotAmounts(key="g", found=True, query_codes=("x",), tb_rows_count=0,
                    prefix_mismatch=True).state,
        SlotAmounts(key="g", found=True, query_codes=("x",), tb_rows_count=0).state,
        SlotAmounts(key="g", found=True, query_codes=("x",), tb_rows_count=1).state,
    }
    assert len(states) == 4, "四态出现重叠：%s" % states
