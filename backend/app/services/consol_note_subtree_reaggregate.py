"""合并附注「🔄 重新汇总」= 所选节点子树逐节点更新 + 自下而上汇总。

spec: consol-note-header-library-and-node-reaggregate（R3 / design §8）

所选节点子树按后序（下级先于上级）逐节点处理，每个章节一个 SAVEPOINT：

- 数据叶子：按已确认映射从本企业单体附注拉数（``apply_detail_refresh(node_key=叶子)``）；
- 差额节点：按抵销 / 调整分录算差额（``fill_by_formula(node_key=差额节点)``）；本章节没有公式 ⇒ 不写，
  汇总时用已保存的数（手工录的差额）；
- 汇总节点：Σ 直接下级已保存附注数（下级汇总节点用本轮汇总结果）+ 差额节点；合计 / 小计按本表重算
  （``build_note_rows``，与明细映射拉数同一函数；「……」占位行没有数不写）；手工 / 锁定格不动；写来源标记 ``subtree_aggregate``
  与下级构成 ``_subtree_provenance``。

个别数只从单体附注来：来源是试算表公式（``formula``）的非差额下级不计入并回报原因；没有任何非差额下级
数据时汇总节点不写（不把只有差额的结果当合并数）。下级按原因跳过（未绑定 / 待确认映射 / 锁定 …）时用它
已保存的数；下级出错（差额没算出，如合并范围未确认）时上级本章不汇总，逐级向上。写入后记录本节点公式值
快照，供后台按公式刷新判断是否过期（design §9）。与合并推送共用进程锁 + PG 事务级咨询锁。只 flush，路由 commit。
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_note_mapping_models import (
    ConsolNoteDetailTemplateVersion,
    ConsolNoteMappingBinding,
    ConsolNoteTemplateBinding,
)
from app.services.consol_calc_basis import node_measures
from app.services.consol_group_tree import KIND_AGGREGATE, KIND_ELIM, ROLE_CONSOL
from app.services.consol_note_detail_apply_service import (
    ApplyError,
    _parse_locked_cells,
    _parse_manual_cells,
    apply_detail_refresh,
    placeholder_rows,
    remap_protected,
)
from app.services.consol_note_detail_source_service import _row_type
from app.services.consol_note_formula_service import (
    NoteFormulaError,
    _copy_note_data_record,
    _first_cell,
    _is_embedded_header_row,
    _note_data_record,
    _row_to_list,
    consol_note_tables,
    ensure_seeded,
    fill_by_formula,
    find_table,
    formula_snapshot,
    label_key,
    note_cell_values,
    record_write_source,
    resolve_note_template_type,
    section_formulas,
)
from app.services.consol_note_detail_suggest import is_placeholder_label
from app.services.consol_note_table_totals import TOTAL_ROW_TYPES, build_note_rows, to_decimal
from app.services.consol_note_topn import (
    group_unit_names,
    rerank,
    section_topn_limit,
    topn_denominator,
    topn_entries,
    topn_table,
    write_topn,
)
from app.services.consol_tree_service import TreeNode, build_tree, find_node_by_key, iter_nodes

logger = logging.getLogger(__name__)

__all__ = ["WRITE_SOURCE", "reaggregate_subtree"]

#: 汇总节点写入来源标记（ConsolNoteTab 据此显示「🔄 子树汇总」）
WRITE_SOURCE = "subtree_aggregate"
ACTION_PULL, ACTION_ELIM, ACTION_AGGREGATE = "pull", "elim", "aggregate"
_PERSISTED, _SKIPPED, _FAILED = "persisted", "skipped", "failed"
#: 这些拉数失败要用户去「📋 明细映射」处理（列入待确认映射企业）
_PENDING_APPLY_CODES = frozenset({
    "NO_BINDINGS", "UNMAPPED_ROWS", "SOURCE_CHANGED", "VERSION_MISSING", "TEMPLATE_BINDING_MISMATCH",
})


async def reaggregate_subtree(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    node_key: str | None = None,
    section_ids: Sequence[str] | None = None,
    template_type: str | None = None,
    tree: TreeNode | None = None,
) -> dict[str, Any]:
    """所选节点（缺省 = 根合并节点）子树逐节点更新并自下而上汇总；返回逐节点 / 逐章节结果。

    ``tree``：调用方已按本项目本年度建好的企业树（路由校验节点时建过），不传则现建。
    """
    from app.services.consol_push_service import _advisory_lock, _process_lock

    async with _process_lock("target", project_id, year):
        await _advisory_lock(db, project_id, year)
        run = await _Run.prepare(
            db, project_id, year, node_key=node_key, section_ids=section_ids, template_type=template_type,
            tree=tree,
        )
        for section_id in run.section_ids:
            await run.process_section(section_id)
        return run.result()


# ─────────────────────────────── 结果 ───────────────────────────────


@dataclass
class _Outcome:
    section_id: str
    node: TreeNode
    action: str
    status: str
    reason: str | None = None
    pending: bool = False
    detail: dict[str, Any] = field(default_factory=dict)
    #: 本节点这一章没算完整（自身失败，或因下级失败而没汇总）⇒ 上级也不汇总
    incomplete: bool = False

    def to_dict(self) -> dict[str, Any]:
        out = {
            "section_id": self.section_id,
            "node_key": self.node.node_key,
            "action": self.action,
            "status": self.status,
            "reason": self.reason,
        }
        out.update(self.detail)
        return out


@dataclass
class _NodeTally:
    node: TreeNode
    action: str
    written: int = 0
    skipped: int = 0
    failed: int = 0
    reasons: Counter = field(default_factory=Counter)

    def add(self, outcome: _Outcome) -> None:
        if outcome.status == _PERSISTED:
            self.written += 1
        elif outcome.status == _FAILED:
            self.failed += 1
        else:
            self.skipped += 1
        if outcome.reason and outcome.status != _PERSISTED:
            self.reasons[outcome.reason] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_key": self.node.node_key,
            "kind": self.node.kind,
            "action": self.action,
            "label": _label(self.node),
            "written": self.written,
            "skipped": self.skipped,
            "failed": self.failed,
            "reasons": [{"reason": r, "count": n} for r, n in self.reasons.most_common()],
        }


def _label(node: TreeNode) -> str:
    return node.display_name or node.company_name or node.node_key


def _action(node: TreeNode) -> str:
    if node.kind == KIND_ELIM:
        return ACTION_ELIM
    if node.kind == KIND_AGGREGATE or node.children:
        return ACTION_AGGREGATE
    return ACTION_PULL


def _row_cells(row: Any) -> list[str]:
    """已保存行 → [行名, 第 1 列, …]（与「按公式填入」同一行形态解析 ``_row_to_list``）。"""
    if isinstance(row, (list, tuple)):
        width = len(row)
    elif isinstance(row, dict):
        vals = row.get("values") or row.get("cells") or {}
        if isinstance(vals, dict):
            width = max((int(k) for k in vals if str(k).isdigit()), default=0) + 1
        else:
            width = len(vals) if isinstance(vals, (list, tuple)) else 0
    else:
        return []
    return _row_to_list(row, width)


# ─────────────────────────────── 编排 ───────────────────────────────


class _Run:
    """一次重新汇总：树 / 模板口径 / 绑定 / 公式 / 计算口径都只装载一次。"""

    def __init__(self, db: AsyncSession, project_id: UUID, year: int, tree: TreeNode, node: TreeNode,
                 template_type: str, section_ids: list[str]):
        self.db, self.project_id, self.year = db, project_id, year
        self.tree, self.node, self.template_type = tree, node, template_type
        self.section_ids = section_ids
        # 后序：先序倒过来 = 每个节点都排在它全部下级之后
        self.order = [n for n in reversed(list(iter_nodes(node))) if n.node_key]
        self.tallies = {n.node_key: _NodeTally(n, _action(n)) for n in self.order}
        self.skeletons: dict[str, list[tuple[str, str | None]]] = {}
        self.placeholders: dict[str, list[int]] = {}   # 骨架里的「……」占位行（R15：没有数不写）
        self.bound_sections: set[str] = set()
        self.mapping: dict[tuple[str, str], str] = {}
        self.formulas: dict[str, list[Any]] = {}
        self.view: Any = None
        self.view_error: str | None = None
        self.measures: dict[str, Any] = {}
        self.selected: list[_Outcome] = []
        self.failures: list[dict[str, Any]] = []
        self.pending: dict[str, dict[str, Any]] = {}
        self.incomplete: dict[str, TreeNode] = {}   # 当前章节没算完整的节点

    @classmethod
    async def prepare(cls, db: AsyncSession, project_id: UUID, year: int, *, node_key: str | None,
                      section_ids: Sequence[str] | None, template_type: str | None,
                      tree: TreeNode | None) -> "_Run":
        if tree is None:
            tree = await build_tree(db, project_id)
        if tree is None or tree.role != ROLE_CONSOL:
            raise NoteFormulaError("只有合并报表项目能按企业树重新汇总附注（项目不存在、不是合并项目或企业树为空）", status=404)
        node = tree if not node_key else find_node_by_key(tree, node_key)
        if node is None:
            raise NoteFormulaError(f"节点 {node_key} 不在当前企业树中", status=404)
        tt = await resolve_note_template_type(db, project_id, template_type)
        all_sections = [str(t["section_id"]) for t in consol_note_tables(tt)
                        if t.get("section_id") and t.get("enabled", True) is not False]
        run = cls(db, project_id, year, tree, node, tt,
                  list(dict.fromkeys(str(s) for s in section_ids)) if section_ids else all_sections)
        await run._load_bindings()
        await ensure_seeded(db, tt)
        for sid in run.section_ids:
            run.formulas[sid] = await section_formulas(db, project_id, tt, sid)
        if any(run.formulas.values()):
            await run._load_view()
        return run

    async def _load_bindings(self) -> None:
        bindings = (await self.db.execute(sa.select(ConsolNoteTemplateBinding).where(
            ConsolNoteTemplateBinding.project_id == self.project_id,
        ))).scalars().all()
        version_ids = {b.template_version_id for b in bindings}
        versions = {v.id: v for v in (await self.db.execute(sa.select(ConsolNoteDetailTemplateVersion).where(
            ConsolNoteDetailTemplateVersion.id.in_(version_ids),
        ))).scalars().all()} if version_ids else {}
        for b in bindings:
            self.bound_sections.add(b.section_id)
            version = versions.get(b.template_version_id)
            rows = version.rows if version is not None and isinstance(version.rows, list) else []
            if rows:
                self.skeletons[b.section_id] = [(str(r.get("canonical_name") or ""), r.get("row_type")) for r in rows]
                self.placeholders[b.section_id] = placeholder_rows(rows)
        for sid, key, status in (await self.db.execute(sa.select(
            ConsolNoteMappingBinding.section_id, ConsolNoteMappingBinding.entity_node_key,
            ConsolNoteMappingBinding.status,
        ).where(ConsolNoteMappingBinding.project_id == self.project_id))).all():
            self.mapping[(sid, key)] = status

    async def _load_view(self) -> None:
        """差额与公式值快照共用的合并计算口径；装载失败只让这两步不可用，拉数与汇总照常。"""
        from app.services.consol_report_view_service import load_view_context

        try:
            async with self.db.begin_nested():
                self.view = await load_view_context(self.db, self.project_id, self.year, tree=self.tree)
        except Exception as exc:  # noqa: BLE001 —— 口径装载失败要回报，不能中断拉数 / 汇总
            detail = getattr(exc, "detail", None)   # 合并范围未确认等计算门是 HTTPException（409）
            message = detail.get("message") if isinstance(detail, dict) else detail if isinstance(detail, str) else None
            self.view, self.view_error = None, message or f"{type(exc).__name__}: {exc}"
            logger.warning("重新汇总装载合并计算口径失败 project=%s: %s", self.project_id, self.view_error)
            return
        if self.view is None:
            self.view_error = "合并计算口径为空（没有审计年度或合并试算）"
            return
        self.measures = node_measures(self.view.basis)

    # ── 逐章节 ──

    async def process_section(self, section_id: str) -> None:
        if find_table(self.template_type, section_id) is None and section_id not in self.skeletons:
            self.failures.append({"section_id": section_id, "node_key": self.node.node_key, "status": _FAILED,
                                  "error": f"合并附注模板（{self.template_type}）中没有表格 {section_id}"})
            return
        outcomes: list[_Outcome] = []
        current: TreeNode | None = None
        self.incomplete: dict[str, TreeNode] = {}
        try:
            async with self.db.begin_nested():
                for n in self.order:
                    current = n
                    outcome = await self._process_node(section_id, n)
                    if outcome.status == _FAILED or outcome.incomplete:
                        self.incomplete[n.node_key] = n
                    outcomes.append(outcome)
        except Exception as exc:  # noqa: BLE001 —— 意外异常整章节回滚，继续下一章节（ADR-RA-003）
            logger.exception("重新汇总章节失败 project=%s section=%s node=%s", self.project_id, section_id,
                             current.node_key if current else None)
            error = f"{type(exc).__name__}: {exc}"
            self.failures.append({"section_id": section_id, "node_key": current.node_key if current else None,
                                  "status": _FAILED, "error": error})
            outcomes = [
                _Outcome(section_id, n, _action(n), _FAILED,
                         f"本章节出错已整章节回滚：{error}" if n is current else "同章节其他节点出错，本章节已回滚")
                for n in self.order
            ]
        for outcome in outcomes:
            self._record(outcome)

    def _record(self, outcome: _Outcome) -> None:
        self.tallies[outcome.node.node_key].add(outcome)
        if outcome.node is self.node:
            self.selected.append(outcome)
        if outcome.status == _FAILED and outcome.reason and not outcome.reason.startswith(("本章节出错", "同章节")):
            self.failures.append({"section_id": outcome.section_id, "node_key": outcome.node.node_key,
                                  "status": _FAILED, "error": outcome.reason})
        if outcome.pending:
            item = self.pending.setdefault(outcome.node.node_key, {
                "node_key": outcome.node.node_key, "label": _label(outcome.node),
                "section_count": 0, "sections": [], "reasons": [],
            })
            item["section_count"] += 1
            if len(item["sections"]) < 20:
                item["sections"].append(outcome.section_id)
            if outcome.reason and outcome.reason not in item["reasons"]:
                item["reasons"].append(outcome.reason)

    async def _process_node(self, section_id: str, node: TreeNode) -> _Outcome:
        action = _action(node)
        if action == ACTION_ELIM:
            return await self._elim(section_id, node)
        if action == ACTION_AGGREGATE:
            return await self._aggregate(section_id, node)
        return await self._pull(section_id, node)

    # ── 数据叶子：按已确认映射从单体附注拉数 ──

    async def _pull(self, sid: str, node: TreeNode) -> _Outcome:
        def skip(reason: str, *, pending: bool = False) -> _Outcome:
            return _Outcome(sid, node, ACTION_PULL, _SKIPPED, reason, pending=pending, incomplete=pending)

        # 「前 N 名」表不经明细模板与映射（R10）：按单位重排，只看映射里是否排除了该企业
        topn = section_topn_limit(self.template_type, sid)
        if not topn and sid not in self.bound_sections:
            return skip("本章节未绑定明细模板（在「📋 明细映射」绑定模板并确认映射后才能从单体附注拉数）")
        if node.project_id is None:
            return skip("没有单体项目，无单体附注可拉")
        status = self.mapping.get((sid, node.node_key))
        if status is None and not topn:
            return skip("未确认映射（或单体附注没有该表）", pending=True)
        if status == "stale" and not topn:
            return skip("单体附注结构已变化，需重新确认映射", pending=True)
        if status == "excluded":
            return skip("映射中已排除该企业，不计入")
        try:
            res = await apply_detail_refresh(
                self.db, project_id=self.project_id, section_id=sid, year=self.year, node_key=node.node_key,
                scope_leaves=[node], template_type=self.template_type,
            )
        except ApplyError as exc:  # 全部在写库前抛出
            return skip(exc.message, pending=exc.code in _PENDING_APPLY_CODES)
        if res.get("status") == "skipped_locked":
            return skip("整节锁定，未覆盖")
        record = await self._exact_record(sid, node.node_key)
        await self._snapshot(sid, node, record)
        missing = [e.get("reason") for e in res.get("skipped_entities") or [] if e.get("node_key") == node.node_key]
        return _Outcome(sid, node, ACTION_PULL, _PERSISTED,
                        f"单体附注没有读到该表：{missing[0]}" if missing else None, detail={
                            "filled_count": res.get("filled_count", 0),
                            "kept_manual_count": res.get("kept_manual_count", 0),
                        })

    # ── 差额节点：按抵销 / 调整分录（公式内核） ──

    async def _elim(self, sid: str, node: TreeNode) -> _Outcome:
        if not self.formulas.get(sid):
            return _Outcome(sid, node, ACTION_ELIM, _SKIPPED, "本章节没有差额公式（汇总用已保存的差额数）")
        if self.view is None:
            return _Outcome(sid, node, ACTION_ELIM, _FAILED, f"无法计算差额：{self.view_error}")
        try:
            res = await fill_by_formula(
                self.db, self.project_id, self.year, sid, node_key=node.node_key,
                template_type=self.template_type, _view_context=self.view,
            )
        except NoteFormulaError as exc:
            return _Outcome(sid, node, ACTION_ELIM, _FAILED, str(exc))
        if res.get("status") == "skipped_locked":
            return _Outcome(sid, node, ACTION_ELIM, _SKIPPED, "整节锁定，未覆盖")
        return _Outcome(sid, node, ACTION_ELIM, _PERSISTED, detail={
            "filled_count": len(res.get("filled") or []),
            "kept_manual_count": res.get("kept_manual_count", 0),
        })

    # ── 汇总节点：Σ 直接下级已保存数 + 差额 ──

    def _skeleton(self, sid: str) -> tuple[list[tuple[str, str | None]], dict[int, list[str]], list[int]]:
        """骨架行（行名, 行类型）+ 原样保留的行 + 「……」占位行号：有明细模板绑定用绑定版本的行；没有用合并附注模板行
        （行类型与「从来源建议模板」同一判定 ``_row_type``；表内嵌的子表头行原样保留，不参与求和）。"""
        if sid in self.skeletons:
            return self.skeletons[sid], {}, self.placeholders.get(sid, [])
        table = find_table(self.template_type, sid) or {}
        headers = table.get("headers") or []
        skeleton: list[tuple[str, str | None]] = []
        verbatim: dict[int, list[str]] = {}
        for i, row in enumerate(table.get("rows") or []):
            embedded = i <= 2 and i == len(verbatim) and _is_embedded_header_row(row, headers)
            # 表内子表头不参与合计构成（标 header，合计构成按结构行跳过）
            skeleton.append((_first_cell(row).strip(), "header" if embedded else _row_type(row)))
            if embedded:
                verbatim[i] = [str(v) if v is not None else "" for v in row]
        placeholders = [i for i, (name, _rt) in enumerate(skeleton) if i not in verbatim and is_placeholder_label(name)]
        return skeleton, verbatim, placeholders

    async def _aggregate(self, sid: str, node: TreeNode) -> _Outcome:
        def skip(reason: str) -> _Outcome:
            return _Outcome(sid, node, ACTION_AGGREGATE, _SKIPPED, reason)

        # 下级出错（差额没算出、更下层没汇总成）⇒ 不在半截数据上汇总；按原因跳过的下级不影响（用已保存的数）
        broken = [c for c in node.children if c.node_key in self.incomplete]
        if broken:
            return _Outcome(sid, node, ACTION_AGGREGATE, _SKIPPED,
                            f"下级「{_label(broken[0])}」本章没算出，本节点不汇总", incomplete=True)
        is_root = node is self.tree
        source = await _note_data_record(self.db, self.project_id, self.year, sid,
                                         node_key=node.node_key, is_root_consol=is_root)
        if source is not None and getattr(source, "cell_state", "auto") == "locked":
            return skip("整节锁定，未覆盖")
        topn = section_topn_limit(self.template_type, sid)
        if topn:
            return await self._aggregate_topn(sid, node, topn, source)
        skeleton, verbatim, placeholders = self._skeleton(sid)
        if not skeleton:
            return skip("没有可用的表格行（模板为空）")
        index: dict[tuple[str, int], int] = {}
        seen: Counter = Counter()
        for i, (name, _rt) in enumerate(skeleton):
            key = label_key(name)
            index[(key, seen[key])] = i
            seen[key] += 1

        children = await self._records(sid, [c.node_key for c in node.children if c.node_key])
        amounts: dict[int, dict[int, Decimal]] = {}
        provenance: list[dict[str, Any]] = []
        unplaced: list[dict[str, Any]] = []
        headers = list((find_table(self.template_type, sid) or {}).get("headers") or [])
        width = max(len(headers), 2)
        entity_data = False
        for child in node.children:
            entry: dict[str, Any] = {"node_key": child.node_key, "kind": child.kind, "label": _label(child),
                                     "included": False}
            record = children.get(child.node_key)
            is_leaf = _action(child) == ACTION_PULL
            if is_leaf and self.mapping.get((sid, child.node_key)) == "excluded":
                entry["reason"] = "映射中已排除"
            elif record is None or not isinstance(record.data, dict) or not record.data.get("rows"):
                entry["reason"] = "没有数据"
            else:
                entry["source"] = record_write_source(record)
                if child.kind != KIND_ELIM and entry["source"] == "formula":
                    entry["reason"] = "来源是试算表公式（按公式填入），个别数只从单体附注取，未计入"
                else:
                    added, row_width = self._accumulate(record.data["rows"], index, skeleton, amounts,
                                                        unplaced, child)
                    width = max(width, row_width)
                    entry.update(included=True, has_values=added)
                    entity_data = entity_data or (added and child.kind != KIND_ELIM)
            provenance.append(entry)
        if not entity_data:
            excluded = [e for e in provenance if e.get("source") == "formula" and not e["included"]]
            return skip("下级企业都没有可汇总的单体附注数据" + (
                f"（{len(excluded)} 个下级是试算表公式数，未计入）" if excluded else ""))

        record = await self._writable_record(sid, node, source)
        data = dict(record.data) if isinstance(record.data, dict) else {}
        existing_rows = data.get("rows") if isinstance(data.get("rows"), list) else []
        if existing_rows and isinstance(existing_rows[0], (list, tuple)):
            width = max(width, len(existing_rows[0]))
        manual, locked = _parse_manual_cells(data), _parse_locked_cells(record)
        for i in verbatim:
            amounts.pop(i, None)
        # 「……」占位行没有下级数、也没有手填值就不写；手工 / 锁定格按行名对到新行号（R15）
        built = build_note_rows(skeleton, amounts, width=width, protected=manual | locked,
                                existing_rows=existing_rows, placeholders=placeholders)
        new_rows, filled, kept = built.rows, built.filled, built.kept
        lost_protected = remap_protected(data, record, manual, locked, built.old_to_new)
        for i, cells in verbatim.items():
            new_rows[built.kept_index[i]] = (cells + [""] * width)[:width]
        now = datetime.now(timezone.utc)
        for stale_key in ("_detail_provenance", "_detail_entity_count", "_detail_applied_at"):
            data.pop(stale_key, None)
        data.update({
            "rows": new_rows,
            "headers": data.get("headers") or headers or ["项目"] + [f"列{c}" for c in range(1, width)],
            "_last_write_source": WRITE_SOURCE,
            # 计入了数的非差额下级个数（ConsolNoteTab「🔄 子树汇总（N 个下级 + 差额）」）
            "_subtree_child_count": sum(1 for e in provenance
                                        if e["included"] and e.get("has_values") and e["kind"] != KIND_ELIM),
            "_subtree_provenance": {"children": provenance, "unplaced": unplaced[:50], "aggregated_at": now.isoformat()},
        })
        record.data = data
        record.is_stale = False
        record.updated_at = now
        await self._snapshot(sid, node, record)
        await self.db.flush()
        return _Outcome(sid, node, ACTION_AGGREGATE, _PERSISTED, detail={
            "filled_count": len(filled),
            "kept_manual_count": len(kept),
            "dropped_placeholders": built.dropped_placeholders,
            "lost_protected": lost_protected[:50],
            "unplaced_count": len(unplaced),
            "children": [{k: e.get(k) for k in ("node_key", "included", "reason")} for e in provenance],
        })

    async def _aggregate_topn(self, sid: str, node: TreeNode, limit: int, source: ConsolNoteData | None) -> _Outcome:
        """「前 N 名」表：下级已保存的前 N 名按单位合并重排（R10）。下级第 N 名之后的单位看不到 ⇒ 近似（写进 ``_topn``）。"""
        headers, columns = topn_table(self.template_type, sid)
        if columns is None:
            return _Outcome(sid, node, ACTION_AGGREGATE, _SKIPPED, f"前 {limit} 名表认不出期末余额列，无法重排")
        children = await self._records(sid, [c.node_key for c in node.children if c.node_key])
        entries: list[Any] = []
        provenance: list[dict[str, Any]] = []
        for child in node.children:
            entry: dict[str, Any] = {"node_key": child.node_key, "kind": child.kind, "label": _label(child),
                                     "included": False}
            record = children.get(child.node_key)
            if child.kind == KIND_ELIM:
                entry["reason"] = "差额户不参与前 N 名重排"
            elif _action(child) == ACTION_PULL and self.mapping.get((sid, child.node_key)) == "excluded":
                entry["reason"] = "映射中已排除"
            elif record is None or not isinstance(record.data, dict) or not record.data.get("rows"):
                entry["reason"] = "没有数据"
            elif record_write_source(record) == "formula":
                entry["reason"] = "来源是试算表公式（按公式填入），个别数只从单体附注取，未计入"
            else:
                units = topn_entries(record.data["rows"], child.node_key)
                entries.extend(units)
                entry.update(included=True, has_values=bool(units))
            provenance.append(entry)
        if not entries:
            return _Outcome(sid, node, ACTION_AGGREGATE, _SKIPPED, f"下级企业都没有可重排的前 {limit} 名数据")
        record = await self._writable_record(sid, node, source)
        denominator, note = await topn_denominator(self.db, project_id=self.project_id, year=self.year,
                                                   template_type=self.template_type, section_id=sid,
                                                   node_key=node.node_key)
        result = rerank(entries, columns=columns, limit=limit, width=max(len(headers), 2),
                        exclude=group_unit_names(self.tree), denominator=denominator, denominator_reason=note)
        now = datetime.now(timezone.utc)
        summary = write_topn(record, headers=headers, result=result, limit=limit, approximate=True,
                             denominator=denominator, denominator_note=note, data_updates={
                                 "_last_write_source": WRITE_SOURCE,
                                 "_subtree_child_count": sum(1 for e in provenance if e["included"] and e.get("has_values")),
                                 "_subtree_provenance": {"children": provenance, "unplaced": [],
                                                         "aggregated_at": now.isoformat()}})
        for stale_key in ("_detail_provenance", "_detail_entity_count", "_detail_applied_at"):
            record.data.pop(stale_key, None)
        await self._snapshot(sid, node, record)
        await self.db.flush()
        return _Outcome(sid, node, ACTION_AGGREGATE, _PERSISTED, detail={
            "filled_count": sum(1 for row in result.rows for cell in row[1:] if str(cell).strip()),
            "kept_manual_count": len(summary["kept"]), "lost_protected": summary["lost_protected"][:50],
            "topn": summary, "children": [{k: e.get(k) for k in ("node_key", "included", "reason")} for e in provenance],
        })

    def _accumulate(self, rows: list[Any], index: dict[tuple[str, int], int],
                    skeleton: list[tuple[str, str | None]], amounts: dict[int, dict[int, Decimal]],
                    unplaced: list[dict[str, Any]], child: TreeNode) -> tuple[bool, int]:
        """下级已保存行按（规范化行名, 同名序号）对到骨架行逐列相加。合计 / 小计行也加（判得准的由本表按合计构成重算、
        不用它；判不准的用各下级之和），但只有合计行有数不算「有可汇总的数据」。"""
        added, width = False, 0
        seen: Counter = Counter()
        for row in rows:
            cells = _row_cells(row)
            if not cells:
                continue
            width = max(width, len(cells))
            name = str(cells[0] or "").strip()
            key = label_key(name)
            idx = index.get((key, seen[key]))
            seen[key] += 1
            values = {c: v for c in range(1, len(cells)) if (v := to_decimal(cells[c])) is not None}
            if idx is None:
                if values and _row_type([name]) not in TOTAL_ROW_TYPES:
                    unplaced.append({"node_key": child.node_key, "label": name or "（空行名）"})
                continue
            is_total = skeleton[idx][1] in TOTAL_ROW_TYPES
            bucket = amounts.setdefault(idx, {})
            for col, value in values.items():
                bucket[col] = bucket.get(col, Decimal("0")) + value
                added = added or not is_total
        return added, width

    # ── 记录读写 ──

    async def _records(self, sid: str, node_keys: list[str]) -> dict[str, ConsolNoteData]:
        if not node_keys:
            return {}
        rows = (await self.db.execute(sa.select(ConsolNoteData).where(
            ConsolNoteData.project_id == self.project_id,
            ConsolNoteData.year == self.year,
            ConsolNoteData.section_id == sid,
            ConsolNoteData.node_key.in_(node_keys),
        ))).scalars().all()
        return {r.node_key: r for r in rows}

    async def _exact_record(self, sid: str, node_key: str) -> ConsolNoteData | None:
        return (await self._records(sid, [node_key])).get(node_key)

    async def _writable_record(self, sid: str, node: TreeNode, source: ConsolNoteData | None) -> ConsolNoteData:
        """写入目标永远是节点专属行；根节点只有项目级兼容行时先复制（保住其中的手工格）。"""
        if source is not None and source.node_key == node.node_key:
            return source
        if source is not None:
            return await _copy_note_data_record(self.db, source, project_id=self.project_id, year=self.year,
                                                section_id=sid, node_key=node.node_key)
        record = ConsolNoteData(project_id=self.project_id, year=self.year, section_id=sid,
                                node_key=node.node_key, data={}, is_stale=False)
        self.db.add(record)
        await self.db.flush()
        return record

    async def _snapshot(self, sid: str, node: TreeNode, record: ConsolNoteData | None) -> None:
        """拉数 / 汇总写入后记录本节点公式值，后台按公式刷新据此判断是否过期（章节没有公式不算）。"""
        formulas = self.formulas.get(sid)
        if record is None or not formulas or self.view is None or node.node_key not in self.measures:
            return
        cells = await note_cell_values(self.view.rows, formulas, self.measures[node.node_key],
                                       categories=self.view.basis.categories)
        record.last_formula_value = formula_snapshot(cells, datetime.now(timezone.utc))

    # ── 汇总结果 ──

    def result(self) -> dict[str, Any]:
        written_any = any(t.written for t in self.tallies.values())
        if self.failures:
            status = "partial" if written_any else _FAILED
        else:
            status = _PERSISTED if written_any else _SKIPPED
        nodes = [self.tallies[n.node_key].to_dict() for n in iter_nodes(self.node) if n.node_key in self.tallies]
        return {
            "mode": "subtree",
            "project_id": str(self.project_id),
            "year": self.year,
            "node_key": self.node.node_key,
            "template_type": self.template_type,
            "status": status,
            "sections_processed": len(self.section_ids),
            "sections_updated": sum(1 for o in self.selected if o.status == _PERSISTED),
            "results": [o.to_dict() for o in self.selected],
            "failures": self.failures,
            "nodes": nodes,
            "pending_entities": list(self.pending.values()),
        }
