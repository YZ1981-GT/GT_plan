"""凭证身份单一来源守卫（spec voucher-identity-writeback-and-audit-phase 任务 5，需求 2.7）

凭证号不唯一（同号别日、同日同号别凭证字都是不同凭证；一套账还可能有两个主体），抽样、穿透、
登记相关后端模块不得只按凭证号定位凭证。纯 AST 判定（注释与 docstring 不进 AST，写在说明里的
反例不会误报）：

- IN：``*.voucher_no.in_ / notin_ / not_in(...)`` —— 按号批量取 / 排除，改用 ``voucher_keys_in`` /
  ``voucher_keys_not_in``；
- GROUP：``group_by(...)`` 含 ``voucher_no`` 列却不含主体 / 日期 / 凭证字 —— 改用 ``voucher_key_sql``；
- DISTINCT：``distinct(*.voucher_no)`` —— 按号计数凭证；
- EQ：``*.voucher_no == x`` 所在函数既没有走 ``single_voucher_lines``（命中多张凭证即 409 列候选、
  不合并分录），也没有同时比主体 / 日期 / 凭证字（整把凭证键），且不在 ``NUMBER_FILTER_ALLOWED`` 里；
- LEGACY：``legacy_voucher_nos_condition``（旧日志只有凭证号的兼容口径）只许 ``LEGACY_CALLERS`` 调用。

``BASELINE`` 是冻结的现存违规，只许删；任务 6（挂凭按凭证键）已清空，保持为空。
"""

from __future__ import annotations

import ast
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "app"

MODULES = (
    "services/voucher_identity.py",
    "services/ledger_penetration_service.py",
    "services/drilldown_service.py",
    "routers/ledger_penetration.py",
    "routers/voucher_links.py",
    "routers/drilldown.py",
    "services/ledger_sampling_service.py",
    "routers/voucher_sampling.py",
    "routers/cutoff_sampling.py",
    "services/sampling_registry_service.py",
    "services/sampled_voucher_queries.py",
    "services/voucher_sampling_exclusion.py",
)

#: 允许按凭证号比较、又不走 single_voucher_lines 的函数（理由必填）
NUMBER_FILTER_ALLOWED: dict[tuple[str, str], str] = {
    ("services/drilldown_service.py", "drill_to_ledger"): "下钻明细页的「凭证号」筛选条件：列出分录供人看，不定位一张凭证",
}

#: 旧口径（按凭证号整张匹配 / 排除）只用于兼容只有凭证号的旧数据，且调用方须回报 legacy
LEGACY_CALLERS: dict[tuple[str, str], str] = {
    ("services/ledger_sampling_service.py", "build_ledger_query"): "旧回填日志只有凭证号：exclude_voucher_nos，统计回 legacy_exclusion",
    ("services/sampled_voucher_queries.py", "cross_workpaper_duplicate_vouchers"): "V210 前的登记行没有日期：命中结果标 legacy",
}

#: 冻结的现存违规（只许删，不许加）。任务 6 删掉最后一条（挂凭去重只按号 + 日期）后为空。
BASELINE: set[tuple[str, str, str]] = set()
_BASELINE_MAX = 0

_KEY_PARTS = {"company_code", "voucher_date", "voucher_type"}


def _attr(node: ast.AST) -> str | None:
    return node.attr if isinstance(node, ast.Attribute) else None


def _call_name(node: ast.Call) -> str | None:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def _owners(tree: ast.AST) -> dict[int, str]:
    """节点 → 最内层所在函数名（模块级为 <module>）。"""
    out: dict[int, str] = {}

    def visit(node: ast.AST, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else owner
            out[id(child)] = name
            visit(child, name)

    visit(tree, "<module>")
    return out


def scan(source: str, rel: str) -> set[tuple[str, str, str]]:
    tree = ast.parse(source)
    owners = _owners(tree)
    func_calls: dict[str, set[str]] = {}
    func_attrs: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        owner = owners.get(id(node), "<module>")
        if isinstance(node, ast.Call):
            func_calls.setdefault(owner, set()).add(_call_name(node) or "")
        elif isinstance(node, ast.Attribute):
            func_attrs.setdefault(owner, set()).add(node.attr)
    found: set[tuple[str, str, str]] = set()
    for node in ast.walk(tree):
        fn = owners.get(id(node), "<module>")
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in ("in_", "notin_", "not_in") and _attr(node.func.value) == "voucher_no":
                found.add((rel, fn, "IN"))
            elif name == "group_by":
                cols = {_attr(n) for a in node.args for n in ast.walk(a)}
                calls = {_call_name(n) for a in node.args for n in ast.walk(a) if isinstance(n, ast.Call)}
                if "voucher_no" in cols and not (_KEY_PARTS <= cols or "voucher_key_sql" in calls):
                    found.add((rel, fn, "GROUP"))
            elif name == "distinct" and any(_attr(a) == "voucher_no" for a in node.args):
                found.add((rel, fn, "DISTINCT"))
            elif name == "legacy_voucher_nos_condition" and (rel, fn) not in LEGACY_CALLERS:
                found.add((rel, fn, "LEGACY"))
        elif isinstance(node, ast.Compare) and any(
            _attr(x) == "voucher_no" for x in (node.left, *node.comparators)
        ):
            whole_key = _KEY_PARTS <= func_attrs.get(fn, set())
            resolved = "single_voucher_lines" in func_calls.get(fn, set())
            if not (whole_key or resolved) and (rel, fn) not in NUMBER_FILTER_ALLOWED:
                found.add((rel, fn, "EQ"))
    return found


def _scan_all() -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for rel in MODULES:
        out |= scan((_APP / rel).read_text(encoding="utf-8"), rel)
    return out


def _func_source(rel: str, fn: str) -> str:
    tree = ast.parse((_APP / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn:
            return ast.unparse(node)
    return ""


def test_modules_exist():
    missing = [rel for rel in MODULES if not (_APP / rel).exists()]
    assert missing == [], f"守卫扫描的模块不存在（改名后要同步 MODULES）：{missing}"


def test_no_new_number_only_voucher_lookup():
    new = _scan_all() - BASELINE
    assert new == set(), (
        "出现只按凭证号定位凭证的写法（同号别日 / 同日同号别凭证字会被当成一张）：\n"
        + "\n".join(f"  {rel} · {fn} · {kind}" for rel, fn, kind in sorted(new))
        + "\n改用 voucher_identity 的 voucher_keys_in / voucher_keys_not_in / voucher_key_sql / single_voucher_lines；"
        "旧数据兼容只走 legacy_voucher_nos_condition 并登记 LEGACY_CALLERS"
    )


def test_baseline_only_shrinks():
    stale = BASELINE - _scan_all()
    assert stale == set(), f"基线里的违规已修掉，请从 BASELINE 删除并调低 _BASELINE_MAX：{sorted(stale)}"
    assert len(BASELINE) <= _BASELINE_MAX


def test_allowlists_are_still_needed():
    """豁免清单的每一项都必须真的有那种写法，否则是失效豁免（该删）。"""
    for (rel, fn), reason in NUMBER_FILTER_ALLOWED.items():
        assert reason
        src = _func_source(rel, fn)
        assert src and ".voucher_no ==" in src, f"{rel} · {fn} 已不再按凭证号比较，删掉豁免"
    for (rel, fn), reason in LEGACY_CALLERS.items():
        assert reason
        assert "legacy_voucher_nos_condition(" in _func_source(rel, fn), f"{rel} · {fn} 已不调旧口径，删掉登记"


def test_scanner_catches_every_pattern():
    """反向自检：每种旧写法单独成段都必须被判出；同一段写成凭证键的形式不判。"""
    bad = {
        "IN": "def f(t, nos):\n    return t.c.voucher_no.in_(nos)\n",
        "IN_NOT": "def f(t, nos):\n    return t.c.voucher_no.notin_(nos)\n",
        "GROUP": "def f(s, t):\n    return s.group_by(t.c.voucher_no, t.c.voucher_date)\n",
        "DISTINCT": "def f(sa, t):\n    return sa.func.count(sa.distinct(t.c.voucher_no))\n",
        "EQ": "def f(t, no):\n    return t.c.voucher_no == no\n",
        # 旧挂凭去重：号 + 日期，没有凭证字与主体
        "EQ_DATE": "def f(t, no, d):\n    return [t.c.voucher_no == no, t.c.voucher_date == d]\n",
        "LEGACY": "def f(t, nos):\n    return legacy_voucher_nos_condition(t.c.voucher_no, nos, exclude=True)\n",
    }
    kinds = {"IN": "IN", "IN_NOT": "IN", "GROUP": "GROUP", "DISTINCT": "DISTINCT", "EQ": "EQ", "EQ_DATE": "EQ",
             "LEGACY": "LEGACY"}
    for label, src in bad.items():
        assert scan(src, "x.py") == {("x.py", "f", kinds[label])}, label
    good = (
        "def g(s, t, keys, no):\n"
        "    s = s.where(voucher_keys_not_in(t, keys)).group_by(*voucher_key_sql(t))\n"
        "    s = s.group_by(t.c.company_code, t.c.voucher_date, t.c.voucher_type, t.c.voucher_no)\n"
        "    rows = s.where(t.c.voucher_no == no)\n"
        "    return single_voucher_lines(rows)\n"
        "def k(t, vk):\n"
        "    return [t.c.voucher_no == vk.no, t.c.voucher_date == vk.d, t.c.voucher_type == vk.t,\n"
        "            t.c.company_code == vk.c]\n"
        "def h(t):\n"
        '    """说明里写 t.c.voucher_no.in_(nos) 不算"""\n'
        "    # t.c.voucher_no.notin_(nos)\n"
        "    return t.c.voucher_date\n"
    )
    assert scan(good, "x.py") == set()
