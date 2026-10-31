"""Runtime 稳定身份依赖图与严格求值（ADR-FHIC-06 第 4、5、7 点）。

``plan_batch`` 是纯函数（SQL 注入），SQLite 单测直接注入 read_ref / eval_fn。
``evaluate_single`` 是预览端点的批大小 1 包装（任务 26 接线）。
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Protocol, Sequence
from uuid import UUID

from app.services.formula_management.stable_key import (
    derive_stable_key, normalize_sheet_key, parse_cell,
)
from app.services.wp_ref_strict import WpCellRead, classify_wp_ref, _is_dep_edge_kind

__all__ = ["BatchDefinition", "NodeIdentity", "PlanOutcome", "PlanResult", "evaluate_single", "plan_batch"]

NodeIdentity = tuple[str, str, str]  # (wp_code.upper(), stable_sheet_key, field_key+row_key)

_WP3_RE = re.compile(r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")
_WP2_RE = re.compile(r"WP\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")


@dataclass
class WpRef:
    wp_code: str; second: str; third: str | None; kind: str; match_text: str


@dataclass
class BatchDefinition:
    formula_id: str | UUID; wp_code: str; expression: str
    stable_sheet_key: str | None = None; row_key: str | None = None; field_key: str | None = None
    stable_key_needs_review: bool = False
    sheet_name: str | None = None; target_cell: str | None = None
    target_parsed_data: dict | None = None


@dataclass
class PlanOutcome:
    formula_id: str | UUID; identity: NodeIdentity | None = None
    state: str = "ok"; value: Decimal | None = None; reason: str | None = None
    wp_values: dict[str, Decimal] | None = None; errors: list[str] = field(default_factory=list)


@dataclass
class PlanResult:
    outcomes: list[PlanOutcome]; topo_order: list[str | UUID] | None = None

    @property
    def mutations(self) -> list[PlanOutcome]:
        return [o for o in self.outcomes if o.state == "ok" and o.value is not None]


def _parse_wp_refs(expression: str) -> list[WpRef]:
    refs: list[WpRef] = []; consumed: set[int] = set()
    for m in _WP3_RE.finditer(expression):
        consumed.add(m.start())
        refs.append(WpRef(m.group(1), m.group(2), m.group(3), classify_wp_ref(m.group(2), m.group(3)), m.group(0)))
    for m in _WP2_RE.finditer(expression):
        if m.start() not in consumed:
            refs.append(WpRef(m.group(1), m.group(2), None, classify_wp_ref(m.group(2), None), m.group(0)))
    return refs


def _derive_identity(d: BatchDefinition) -> tuple[NodeIdentity | None, str | None]:
    if d.stable_sheet_key is not None and d.field_key is not None:
        if d.stable_key_needs_review:
            return None, "公式位置待复核"
        return (d.wp_code.upper(), d.stable_sheet_key, (d.field_key or "") + (d.row_key or "")), None
    sk = derive_stable_key(d.sheet_name, d.target_cell)
    if sk.needs_review:
        return None, "公式位置待复核"
    return (d.wp_code.upper(), sk.stable_sheet_key, sk.field_key + (sk.row_key or "")), None


def _check_target_sheet(d: BatchDefinition) -> str | None:
    """目标表校验（需求 1.8：目标工作表不存在 ⇒ 计划阶段 blocked）。

    ``target_parsed_data is None`` = 调用方没有提供底稿数据（纯函数调用），不校验；
    提供了（coordinator 已读底稿，含 ``{}`` / 无 ``html_data``）就必须能在 ``html_data`` 里找到目标表。
    🔴 2026-10-30 修：原先 ``parsed_data`` 为空或没有 ``html_data`` 时直接放行，计划照出 mutation，
    再由 adapter 的 ``require_existing_sheet`` 在 apply 时抛 ValueError —— 整批 all_or_nothing 失败，
    而不是本条 blocked 并写明原因。
    """
    pd = d.target_parsed_data
    if pd is None:
        return None
    tsk = d.stable_sheet_key if d.stable_sheet_key is not None else normalize_sheet_key(d.sheet_name)
    if not tsk:
        return None
    hd = pd.get("html_data") if isinstance(pd, dict) else None
    if not hd or not isinstance(hd, dict):
        return "目标工作表不存在"
    hits = [k for k in hd if normalize_sheet_key(k) == tsk]
    if not hits:
        return "目标工作表不存在"
    if len(hits) > 1:
        return "目标工作表名有歧义"
    return None


def _ref_target_ident(ref: WpRef) -> NodeIdentity | None:
    """从引用构建目标身份（仅 cell_3/cell_2 有意义）。"""
    if ref.kind == "cell_3":
        rk, fk, _ = parse_cell(ref.third)
        return (ref.wp_code.upper(), normalize_sheet_key(ref.second), fk + (rk or ""))
    if ref.kind == "cell_2":
        rk, fk, _ = parse_cell(ref.second)
        return None  # cell_2 无 sheet → 不构成完整 identity
    return None


def _tarjan_scc(graph: dict[str, list[str]]) -> list[list[str]]:
    ix = [0]; stk: list[str] = []; on: set[str] = set()
    idx: dict[str, int] = {}; low: dict[str, int] = {}; res: list[list[str]] = []

    def sc(v: str) -> None:
        idx[v] = low[v] = ix[0]; ix[0] += 1; stk.append(v); on.add(v)
        for w in graph.get(v, []):
            if w not in idx:
                sc(w); low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            c: list[str] = []
            while True:
                w = stk.pop(); on.discard(w); c.append(w)
                if w == v: break
            res.append(c)
    for n in graph:
        if n not in idx: sc(n)
    return res


class ReadRefFn(Protocol):
    async def __call__(self, wp_code: str, second: str, third: str | None) -> WpCellRead: ...


async def plan_batch(
    definitions: Sequence[BatchDefinition], *,
    year_verdict: WpCellRead | None, read_ref: ReadRefFn,
    eval_fn: Callable[..., Any] | None = None,
) -> PlanResult:
    """构建依赖图、检环、拓扑求值。year_verdict 与 read_ref 由调用方注入。"""
    out: dict[str, PlanOutcome] = {}
    dmap: dict[str, BatchDefinition] = {}
    imap: dict[NodeIdentity, str] = {}  # identity → fid
    fid_id: dict[str, NodeIdentity] = {}

    # 1. 身份推导 + 目标校验
    for d in definitions:
        fid = str(d.formula_id); dmap[fid] = d
        ident, reason = _derive_identity(d)
        if reason:
            out[fid] = PlanOutcome(fid, None, "blocked", None, reason); continue
        assert ident is not None
        err = _check_target_sheet(d)
        if err:
            out[fid] = PlanOutcome(fid, ident, "blocked", None, err); continue
        fid_id[fid] = ident; imap[ident] = fid

    # 2. 解析引用、建依赖图
    graph: dict[str, list[str]] = defaultdict(list)
    rcache: dict[str, list[WpRef]] = {}
    for fid, ident in fid_id.items():
        refs = _parse_wp_refs(dmap[fid].expression); rcache[fid] = refs; graph.setdefault(fid, [])
        for ref in refs:
            if not _is_dep_edge_kind(ref.kind): continue
            if ref.kind == "cell_3":
                rk, fk, _ = parse_cell(ref.third)
                ti: NodeIdentity = (ref.wp_code.upper(), normalize_sheet_key(ref.second), fk + (rk or ""))
                tfid = imap.get(ti)
                if tfid: graph[fid].append(tfid)
            elif ref.kind == "cell_2":
                rk, fk, _ = parse_cell(ref.second)
                ck = fk + (rk or "")
                cands = [tid for ti, tid in imap.items() if ti[0] == ref.wp_code.upper() and ti[2] == ck]
                if len(cands) == 1: graph[fid].append(cands[0])
                elif len(cands) > 1: out[fid] = PlanOutcome(fid, ident, "blocked", None, "引用有歧义")

    # 3. Tarjan + 环检测
    alive = set(fid_id) - {k for k, v in out.items() if v.state == "blocked"}
    for n in alive: graph.setdefault(n, [])
    sccs = _tarjan_scc(graph)
    cyc: set[str] = set()
    for scc in sccs:
        vs = [n for n in scc if n in alive]
        if len(vs) > 1: cyc.update(vs)
        elif len(vs) == 1 and vs[0] in graph.get(vs[0], []): cyc.add(vs[0])
    for n in cyc:
        out[n] = PlanOutcome(n, fid_id.get(n), "blocked", None, "循环引用")

    # 4. 拓扑序（Tarjan 输出 = 依赖图正确求值序）
    topo = [n for scc in sccs for n in scc if n in alive and n not in cyc]

    # 5. 逐条求值
    computed: dict[NodeIdentity, Decimal] = {}
    for fid in topo:
        if fid in out: continue
        d = dmap[fid]; ident = fid_id[fid]; refs = rcache.get(fid, [])
        wpv: dict[str, Decimal] = {}; errs: list[str] = []; blk = False
        if year_verdict is not None and refs:
            for r in refs: errs.append(f"{r.match_text}：{year_verdict.reason}")
            out[fid] = PlanOutcome(fid, ident, "blocked", None, year_verdict.reason, errors=errs); continue
        for ref in refs:
            if _is_dep_edge_kind(ref.kind):
                # 批内查找
                found_in_batch = False
                if ref.kind == "cell_3":
                    rk, fk, _ = parse_cell(ref.third)
                    ti = (ref.wp_code.upper(), normalize_sheet_key(ref.second), fk + (rk or ""))
                    if ti in computed: wpv[ref.match_text] = computed[ti]; found_in_batch = True
                elif ref.kind == "cell_2":
                    rk, fk, _ = parse_cell(ref.second); ck = fk + (rk or "")
                    bh = [(ti, tid) for ti, tid in imap.items() if ti[0] == ref.wp_code.upper() and ti[2] == ck]
                    if len(bh) == 1 and bh[0][0] in computed:
                        wpv[ref.match_text] = computed[bh[0][0]]; found_in_batch = True
                    elif len(bh) > 1:
                        errs.append(f"{ref.match_text}：引用有歧义"); blk = True; continue
                if found_in_batch: continue
            # 外部读取
            rr = await read_ref(ref.wp_code, ref.second, ref.third)
            if rr.state == "ok" and rr.value is not None:
                wpv[ref.match_text] = rr.value
            else:
                errs.append(f"{ref.match_text}：{rr.reason or '取值失败'}"); blk = True
        if blk:
            out[fid] = PlanOutcome(fid, ident, "blocked", None, errs[0] if errs else "取值失败", wp_values=wpv, errors=errs)
            continue
        if eval_fn is not None:
            try:
                val, ee = await eval_fn(d.expression, wpv); errs.extend(ee)
                out[fid] = PlanOutcome(fid, ident, "ok", val, None, wp_values=wpv, errors=errs); computed[ident] = val
            except Exception as exc:
                out[fid] = PlanOutcome(fid, ident, "blocked", None, f"求值异常：{exc}", wp_values=wpv, errors=[str(exc)])
        else:
            out[fid] = PlanOutcome(fid, ident, "ok", None, None, wp_values=wpv, errors=errs)

    for d in definitions:
        fid = str(d.formula_id)
        if fid not in out: out[fid] = PlanOutcome(fid, None, "blocked", None, "未能计划")
    return PlanResult(outcomes=[out[str(d.formula_id)] for d in definitions], topo_order=topo)


async def evaluate_single(db, formula: Any, *, project_id: UUID, year: int | None = None) -> PlanOutcome:
    """预览端点——批大小 1 的 plan_batch 包装（任务 26 接线）。"""
    from app.services.wp_cell_reader import _year_gate
    from app.services.wp_ref_strict import read_wp_ref_strict
    from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
    import inspect

    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    defn = BatchDefinition(
        formula_id=str(getattr(formula, "id", "preview")), wp_code=getattr(formula, "_wp_code", ""),
        expression=getattr(formula, "expression", ""),
        stable_sheet_key=getattr(formula, "stable_sheet_key", None),
        row_key=getattr(formula, "row_key", None), field_key=getattr(formula, "field_key", None),
        stable_key_needs_review=getattr(formula, "stable_key_needs_review", False),
        sheet_name=getattr(formula, "sheet_name", None), target_cell=getattr(formula, "target_cell", None),
    )
    yv = await _year_gate(db, pid, year)

    async def _read(wp_code: str, second: str, third: str | None) -> WpCellRead:
        return await read_wp_ref_strict(db, pid, None, wp_code, second, third)

    async def _eval(expr: str, wpv: dict[str, Decimal]) -> tuple[Decimal, list[str]]:
        kw: dict[str, Any] = dict(project_id=pid, year=year or 0, expression=expr)
        if "wp_values" in inspect.signature(evaluate_wp_formula_expression).parameters:
            kw["wp_values"] = wpv; kw["strict_wp"] = True
        return await evaluate_wp_formula_expression(db, **kw)

    return (await plan_batch([defn], year_verdict=yv, read_ref=_read, eval_fn=_eval)).outcomes[0]
