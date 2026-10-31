"""需求 1.10 的**独立金标准**：不 import 任何生产公式模块，在测试内自算 29 条的期望结果。

spec formula-hub-integrity-closure 任务 25 / 需求 1.10；独立性由 `test_runtime_replay_29_pg.py`
的 AST 守卫钉住（本文件只许 import 标准库）。不被 pytest 收集。

判定顺序照 ADR-FHIC-06（第 4~6 点）在测试里**重新实现一遍**，不调用 `typed_eval`：

1. 目标表校验：公式的 ``stable_sheet_key`` 必须命中所在底稿 ``html_data`` 的某个键 ⇒ 否则 ``blocked``；
2. 引用解析：只认 ``WP('<wp_code>','<cell>')`` 两参单元格写法（其余写法记入 ``unknown``，断言为 0）；
3. 依赖图：引用命中「同 wp_code、同格键」的批内目标 ⇒ 依赖边；含自环的强连通分量一律 ``blocked``；
4. 拓扑求值：批内引用取上游算出的值，批外引用取该底稿 ``parsed_data`` 里的存值。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

#: 只认两参单元格写法：WP('CODE','B5')
_WP2 = re.compile(r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)", re.I)
#: 去掉全部 WP(...) 之后，剩下的必须只由数字 / + - * / / 括号 / 空白组成
_ARITH_ONLY = re.compile(r"^[\d\s.+\-*/()]*$")
_CELL = re.compile(r"^([A-Za-z]+)(\d+)$")


@dataclass
class GoldOutcome:
    state: str                       # "ok" | "blocked"
    value: Decimal | None = None
    reason: str = ""
    refs: list[tuple[str, str]] = field(default_factory=list)


def cell_key(cell: str) -> str:
    """``B5`` → ``B5``（列字母大写 + 行号）；不是 A1 形态就原样大写。"""
    m = _CELL.match((cell or "").strip())
    return f"{m.group(1).upper()}{m.group(2)}" if m else (cell or "").strip().upper()


def _stored(cells: dict[str, Any], cell: str) -> Decimal | None:
    """从 ``html_data[sheet].cells`` 取一个格的数值；支持纯量与 ``{"v":…,"value":…}`` 两种形态。"""
    raw = cells.get(cell) if isinstance(cells, dict) else None
    if isinstance(raw, dict):
        raw = raw.get("value", raw.get("v"))
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return Decimal(str(raw).strip())
    except Exception:  # noqa: BLE001
        return None


def _eval_arith(expr: str) -> Decimal:
    """只对「数字 + 四则 + 括号」求值（WP 已被替换成字面数字）。禁用任何名字。"""
    if not _ARITH_ONLY.match(expr):
        raise ValueError(f"金标准不支持的表达式：{expr!r}")
    return Decimal(str(eval(expr, {"__builtins__": {}}, {})))  # noqa: S307 —— 已按字符白名单限死


def evaluate(rows: list[Any]) -> tuple[dict[str, GoldOutcome], list[str]]:
    """返回 ``{formula_id: GoldOutcome}`` 与 ``unknown``（未识别写法的说明，必须为空）。

    ``rows`` 是 ``_replay29_world.ReplayRow`` 列表（只读属性，不反向依赖生产代码）。
    """
    unknown: list[str] = []
    by_id = {str(r.formula_id): r for r in rows}

    # ① 目标表校验
    out: dict[str, GoldOutcome] = {}
    alive: dict[str, Any] = {}
    for fid, r in by_id.items():
        key = (r.stable_sheet_key or "").strip()
        if key not in {k.strip() for k in r.html_keys}:
            out[fid] = GoldOutcome("blocked", reason="目标工作表不存在")
        else:
            alive[fid] = r

    # ② 解析引用（只认两参单元格）
    refs: dict[str, list[tuple[str, str]]] = {}
    for fid, r in alive.items():
        found = _WP2.findall(r.expression)
        rest = _WP2.sub("1", r.expression)
        if not _ARITH_ONLY.match(rest):
            unknown.append(f"{r.wp_code}/{r.target_cell}: {r.expression!r}")
        refs[fid] = [(code.upper(), cell_key(cell)) for code, cell in found]

    # ③ 依赖图：identity = (wp_code.upper(), field_key + row_key)
    ident: dict[str, tuple[str, str]] = {
        fid: (r.wp_code.upper(), r.identity_cell) for fid, r in alive.items()
    }
    by_ident: dict[tuple[str, str], list[str]] = {}
    for fid, key in ident.items():
        by_ident.setdefault(key, []).append(fid)

    graph: dict[str, list[str]] = {fid: [] for fid in alive}
    for fid in alive:
        for code, ck in refs[fid]:
            cands = by_ident.get((code, ck), [])
            if len(cands) == 1:
                graph[fid].append(cands[0])
            elif len(cands) > 1:
                out[fid] = GoldOutcome("blocked", reason="引用有歧义")

    # 含自环的强连通分量 ⇒ blocked（测试内用 Kosaraju，和生产的 Tarjan 不同实现）
    cyclic = _cyclic_nodes(graph)
    for fid in cyclic:
        out.setdefault(fid, GoldOutcome("blocked", reason="循环引用"))

    # ④ 拓扑求值
    computed: dict[tuple[str, str], Decimal] = {}
    for fid in _topo(graph, skip=set(out)):
        r = alive[fid]
        expr = r.expression
        blocked = False
        for code, ck in refs[fid]:
            cands = by_ident.get((code, ck), [])
            if len(cands) == 1 and ident[cands[0]] in computed:
                val = computed[ident[cands[0]]]
            else:
                donor = next((x for x in alive.values() if x.wp_code.upper() == code), None)
                val = _stored(donor.cells, ck) if donor else None
            if val is None:
                out[fid] = GoldOutcome("blocked", reason=f"WP('{code}','{ck}') 取值失败")
                blocked = True
                break
            expr = _WP2.sub(lambda m, v=val: str(v)
                            if (m.group(1).upper(), cell_key(m.group(2))) == (code, ck)
                            else m.group(0), expr, count=0)
        if blocked:
            continue
        value = _eval_arith(expr)
        out[fid] = GoldOutcome("ok", value=value, refs=refs[fid])
        computed[ident[fid]] = value

    for fid in by_id:
        out.setdefault(fid, GoldOutcome("blocked", reason="未能计划"))
    return out, unknown


def _cyclic_nodes(graph: dict[str, list[str]]) -> set[str]:
    """返回落在环上的节点（含自环）。测试内用「逐节点 DFS 找回边」，与生产 Tarjan 不同实现。"""
    cyclic: set[str] = set()
    for start in graph:
        stack = [(start, [start])]
        seen: set[str] = set()
        while stack:
            node, path = stack.pop()
            for nxt in graph.get(node, []):
                if nxt == start:
                    cyclic.update(path)
                    cyclic.add(start)
                elif nxt not in seen:
                    seen.add(nxt)
                    stack.append((nxt, path + [nxt]))
    return cyclic


def _topo(graph: dict[str, list[str]], *, skip: set[str]) -> list[str]:
    """被依赖者在前的顺序（跳过 ``skip`` 与其不可达分支）。"""
    order: list[str] = []
    state: dict[str, int] = {}

    def visit(node: str) -> None:
        if node in skip or state.get(node) == 2:
            return
        if state.get(node) == 1:
            return
        state[node] = 1
        for nxt in graph.get(node, []):
            visit(nxt)
        state[node] = 2
        order.append(node)

    for node in graph:
        visit(node)
    return [n for n in order if n not in skip]
