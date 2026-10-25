"""合并企业树的三码推导 —— spec consol-tree-three-code-autobuild 任务 5（树）/ 任务 6（派生链接）。

真源（ADR-CTREE-001）：各项目的企业代码、上级代码、最终控制方代码与「与上级关系」。
``parent_project_id`` 只是派生值（``derive_parent_links``），树构建不读它。

分两层：
- 纯函数：``build_entity_graph`` / ``derive_group_tree`` / ``derive_parent_links`` 只吃
  ``ProjectRecord``，不连库，属性测试直接喂记录；
- 薄装载：``load_year_records`` / ``build_group_tree`` 从库里取同年度记录后调纯函数。

节点模型（design §二）——有合并项目的企业一次生成三个节点：
  {名称}（合并）          aggregate，合并项目
    ├ {名称}（合并差额）   elim，分录承载 = 本合并项目
    ├ {名称}（母公司）     无分公司：data = 单体项目；有分公司：aggregate
    │    ├ {名称}（母分差额） elim
    │    ├ {名称}（本部）     data = 单体项目
    │    └ 各分公司（再有分公司时同样展开为「汇总」）
    └ 各子公司（有合并项目的递归生成三节点；没有的取单体，并把它的下级提升上来，标「经 X 间接持有」）

上级代码等于本企业代码 = 本企业就是上级企业（需求 1.5），一律经
``group_relation.effective_parent_code`` 判定为「没有另外的上级」，不建自环边。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services.consol_tree_service import TreeNode, iter_nodes
from app.services.group_relation import (
    RELATION_BRANCH,
    RELATION_SUBSIDIARY,
    effective_parent_code,
    normalize_relation,
)
from app.services.note_section_catalog import normalize_report_scope
from app.services.project_audit_year import resolve_project_audit_year

# ─────────────────────────────── 角色 / 类型 / 合并方式 ───────────────────────────────

ROLE_CONSOL = "consol"
ROLE_CONSOL_ELIM = "consol_elim"
ROLE_PARENT = "parent"
ROLE_HQ = "hq"
ROLE_BRANCH_ELIM = "branch_elim"
ROLE_SUBSIDIARY = "subsidiary"
ROLE_BRANCH = "branch"
ELIM_ROLES = frozenset({ROLE_CONSOL_ELIM, ROLE_BRANCH_ELIM})
# 代表「一个企业在树里的位置」的角色（统计合并方式、判断企业是否在树中用）
ENTITY_ROLES = frozenset({ROLE_CONSOL, ROLE_PARENT, ROLE_SUBSIDIARY, ROLE_BRANCH})

KIND_AGGREGATE = "aggregate"  # Σ 直接子节点
KIND_ELIM = "elim"            # 归属本节点的已审批分录
KIND_DATA = "data"            # 单体项目审定数

MODE_SUBSIDIARY = "subsidiary"
MODE_BRANCH = "branch"
MODE_MIXED = "mixed"
MODE_NONE = "none"
MODE_LABELS: dict[str, str] = {
    MODE_SUBSIDIARY: "母子合并",
    MODE_BRANCH: "总分汇总",
    MODE_MIXED: "母子合并＋总分汇总",
    MODE_NONE: "未识别到下级",
}

_ROLE_SUFFIX: dict[str, str] = {
    ROLE_CONSOL: "（合并）",
    ROLE_CONSOL_ELIM: "（合并差额）",
    ROLE_PARENT: "（母公司）",
    ROLE_HQ: "（本部）",
    ROLE_BRANCH_ELIM: "（母分差额）",
}

_DIAG_ORDER = (
    "year_unresolved", "root_no_company_code", "root_not_consolidated", "duplicate_project",
    "cycle_break", "detached", "parent_missing", "relation_conflict", "relation_defaulted",
    "standalone_missing", "branch_consol_ignored", "via", "orphan_entries", "link_mismatch",
)


def node_key(company_code: str, role: str) -> str:
    return f"{company_code}:{role}"


def display_name(name: str, role: str, kind: str) -> str:
    """带角色后缀的展示名；子公司/分公司有分公司时显示「（汇总）」。"""
    if role in _ROLE_SUFFIX:
        return f"{name}{_ROLE_SUFFIX[role]}"
    return f"{name}（汇总）" if kind == KIND_AGGREGATE else name


def _clean(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _safe_relation(value: str | None) -> str | None:
    try:
        return normalize_relation(value)
    except ValueError:
        return None


# ─────────────────────────────── 输入 / 输出结构 ───────────────────────────────


@dataclass(frozen=True)
class ProjectRecord:
    """构建企业树所需的项目字段（与 ORM 解耦：纯函数与属性测试直接构造）。"""

    id: UUID
    company_code: str | None
    client_name: str
    report_scope: str | None
    audit_year: int | None
    parent_company_code: str | None = None
    ultimate_company_code: str | None = None
    relation_to_parent: str | None = None
    parent_project_id: UUID | None = None
    status: str | None = None
    consol_level: int = 1


def record_from_project(p: Project, audit_year: int | None) -> ProjectRecord:
    """ORM 项目（或只带部分属性的 Project-like 对象，如批量导入预览行）→ ``ProjectRecord``。

    除 ``id`` 外一律按属性缺省取空：森林与批量预览喂的是轻量对象，不能因少一个属性就整棵树失败。
    """
    raw_status = getattr(p, "status", None)
    status = getattr(raw_status, "value", raw_status)
    return ProjectRecord(
        id=p.id,
        company_code=getattr(p, "company_code", None),
        client_name=getattr(p, "client_name", None) or "",
        report_scope=getattr(p, "report_scope", None),
        audit_year=audit_year,
        parent_company_code=getattr(p, "parent_company_code", None),
        ultimate_company_code=getattr(p, "ultimate_company_code", None),
        relation_to_parent=getattr(p, "relation_to_parent", None),
        parent_project_id=getattr(p, "parent_project_id", None),
        status=str(status) if status is not None else None,
        consol_level=getattr(p, "consol_level", None) or 1,
    )


@dataclass(frozen=True)
class Diagnostic:
    """企业树诊断（design §3.4）：用标记代替静默丢弃。"""

    code: str
    message: str
    company_code: str | None = None
    node_key: str | None = None
    level: str = "warning"  # warning / info

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "company_code": self.company_code,
            "node_key": self.node_key,
            "level": self.level,
        }


def sort_diagnostics(diags: Iterable[Diagnostic]) -> list[Diagnostic]:
    """去重 + 按诊断类别固定顺序排序（企业树与接口追加的分录诊断共用，结果确定）。"""
    order = {c: i for i, c in enumerate(_DIAG_ORDER)}
    unique = set(diags)
    return sorted(
        unique,
        key=lambda d: (order.get(d.code, len(order)), d.company_code or "", d.node_key or "", d.message),
    )


@dataclass
class Entity:
    """企业实体 = 同代码同年度的合并项目 + 单体项目。"""

    code: str
    name: str
    consol: ProjectRecord | None
    standalone: ProjectRecord | None
    raw_parent_code: str | None   # 有效上级代码（可能指向未建项企业）
    ultimate_code: str | None
    relation: str | None          # 有有效上级时恒非空（未填按子公司，并记诊断）
    parent_code: str | None = None  # 集内上级（脱挂为 None；断环后为 None）
    flags: set[str] = field(default_factory=set)


@dataclass
class EntityGraph:
    year: int | None
    entities: dict[str, Entity]
    children: dict[str, list[str]]  # 上级代码 → 下级代码（按名称、代码排序）
    diagnostics: list[Diagnostic]
    duplicates: list[tuple[str, str, ProjectRecord]]  # (企业代码, 口径, 未入树的重复项目)
    # 没有集内上级的企业按最终控制方挂靠：企业代码 → 控制方企业代码（控制方有合并项目；
    # 与上级边合起来无环，见 _attach_by_ultimate）
    orphan_hosts: dict[str, str] = field(default_factory=dict)

    def placement_parent(self, code: str) -> str | None:
        """企业在树里的放置上级：集内上级优先，否则按最终控制方挂靠的合并企业。"""
        return self.entities[code].parent_code or self.orphan_hosts.get(code)


@dataclass
class GroupTreeResult:
    root: TreeNode | None
    year: int | None
    mode: str
    diagnostics: list[Diagnostic]


# ─────────────────────────────── 实体图 ───────────────────────────────


def _make_entity(
    code: str,
    consol: ProjectRecord | None,
    standalone: ProjectRecord | None,
    diags: list[Diagnostic],
) -> Entity:
    name = (standalone.client_name if standalone else "") or (consol.client_name if consol else "") or code
    s_parent = effective_parent_code(code, standalone.parent_company_code) if standalone else None
    c_parent = effective_parent_code(code, consol.parent_company_code) if consol else None
    # 集团关系取单体项目；单体缺失或其上级代码为空取合并项目（design §3.1）
    if standalone is not None and s_parent is not None:
        src, other = standalone, consol
    elif consol is not None:
        src, other = consol, standalone
    else:
        src, other = standalone, None
    assert src is not None
    parent = effective_parent_code(code, src.parent_company_code)
    relation = _safe_relation(src.relation_to_parent) if parent else None
    ultimate = _clean(src.ultimate_company_code) or (_clean(other.ultimate_company_code) if other else None)
    flags: set[str] = set()

    if standalone is not None and consol is not None:
        s_ult, c_ult = _clean(standalone.ultimate_company_code), _clean(consol.ultimate_company_code)
        parents_differ = s_parent is not None and c_parent is not None and (
            s_parent != c_parent
            or _safe_relation(standalone.relation_to_parent) != _safe_relation(consol.relation_to_parent)
        )
        if parents_differ or (s_ult and c_ult and s_ult != c_ult):
            flags.add("relation_conflict")
            source = "单户" if src is standalone else "合并"
            diags.append(Diagnostic(
                "relation_conflict",
                f"「{name}」的合并项目与单户项目集团关系不一致（上级代码、关系或控制方），企业树按{source}项目取值",
                company_code=code,
            ))
    if parent is not None and relation is None:
        relation = RELATION_SUBSIDIARY
        flags.add("relation_defaulted")
        diags.append(Diagnostic(
            "relation_defaulted", f"「{name}」未填与上级关系，暂按子公司处理", company_code=code,
        ))
    return Entity(
        code=code, name=name, consol=consol, standalone=standalone,
        raw_parent_code=parent, ultimate_code=ultimate, relation=relation, flags=flags,
    )


def _break_cycles(entities: dict[str, Entity], diags: list[Diagnostic]) -> None:
    """上级关系成环 ⇒ 断开环内企业代码最小者的上级边（与遍历顺序无关，design §3.2）。"""
    state: dict[str, int] = {}  # 1 = 在当前路径上；2 = 已处理
    for start in sorted(entities):
        if state.get(start):
            continue
        path: list[str] = []
        pos: dict[str, int] = {}
        cur: str | None = start
        while cur is not None and not state.get(cur):
            state[cur] = 1
            pos[cur] = len(path)
            path.append(cur)
            cur = entities[cur].parent_code
        if cur is not None and state.get(cur) == 1:
            cycle = path[pos[cur]:]
            breaker = entities[min(cycle)]
            upper = entities[breaker.parent_code] if breaker.parent_code else None
            chain = " → ".join(entities[c].name for c in cycle)
            diags.append(Diagnostic(
                "cycle_break",
                f"上级关系成环（{chain}），已断开「{breaker.name}」与上级「{upper.name if upper else ''}」的连接",
                company_code=breaker.code,
            ))
            breaker.parent_code = None
            breaker.flags.add("cycle_break")
        for c in path:
            state[c] = 2


def build_entity_graph(
    records: Iterable[ProjectRecord],
    year: int | None,
    prefer_ids: Iterable[UUID] = (),
) -> EntityGraph:
    """同年度项目 → 企业实体图（纯函数）。其他年度、无企业代码的记录一律不进图（需求 3.8）。"""
    preferred = set(prefer_ids)
    diags: list[Diagnostic] = []
    grouped: dict[str, dict[str, list[ProjectRecord]]] = {}
    for r in records:
        code = _clean(r.company_code)
        if code is None or year is None or r.audit_year != year:
            continue
        scope = normalize_report_scope(r.report_scope)
        grouped.setdefault(code, {}).setdefault(scope, []).append(r)

    entities: dict[str, Entity] = {}
    duplicates: list[tuple[str, str, ProjectRecord]] = []
    for code in sorted(grouped):
        picked: dict[str, ProjectRecord] = {}
        for scope, rows in sorted(grouped[code].items()):
            rows = sorted(rows, key=lambda r: (r.id not in preferred, str(r.id)))
            picked[scope] = rows[0]
            for extra in rows[1:]:
                duplicates.append((code, scope, extra))
                diags.append(Diagnostic(
                    "duplicate_project",
                    f"「{extra.client_name}」与「{rows[0].client_name}」企业代码、年度、报表类型都相同，只取后者进入企业树",
                    company_code=code,
                ))
        entities[code] = _make_entity(code, picked.get("consolidated"), picked.get("standalone"), diags)

    for e in entities.values():
        if e.raw_parent_code is None:
            continue
        if e.raw_parent_code in entities:
            e.parent_code = e.raw_parent_code
        else:
            e.flags.add("detached")
            diags.append(Diagnostic(
                "detached",
                f"「{e.name}」的上级代码 {e.raw_parent_code} 在 {year} 年度没有项目，暂作为脱挂企业",
                company_code=e.code,
            ))
    _break_cycles(entities, diags)
    orphan_hosts = _attach_by_ultimate(entities, diags)

    children: dict[str, list[str]] = {code: [] for code in entities}
    for e in entities.values():
        if e.parent_code is not None:
            children[e.parent_code].append(e.code)
    for kids in children.values():
        kids.sort(key=lambda c: (entities[c].name, c))
    return EntityGraph(
        year=year, entities=entities, children=children, diagnostics=diags,
        duplicates=duplicates, orphan_hosts=orphan_hosts,
    )


def _controller_hosts(entities: dict[str, Entity], *, require_consol: bool) -> dict[str, str]:
    """没有集内上级（未填、填为本企业、脱挂、断环）的企业 → 其最终控制方企业（在集内且不是自己）。"""
    hosts: dict[str, str] = {}
    for code in sorted(entities):
        e = entities[code]
        if e.parent_code is not None or not e.ultimate_code or e.ultimate_code == code:
            continue
        host = entities.get(e.ultimate_code)
        if host is not None and (host.consol is not None or not require_consol):
            hosts[code] = host.code
    return hosts


def _attach_by_ultimate(entities: dict[str, Entity], diags: list[Diagnostic]) -> dict[str, str]:
    """没有集内上级（未填、填为本企业、脱挂、断环）的企业按最终控制方挂到其合并节点下。

    控制方须有合并项目。挂靠边与上级边合起来仍可能成环（如两家互为控制方，或控制方其实
    是它的下级）：沿「放置上级」检测，环内取有挂靠边的企业代码最小者不挂靠 —— 与遍历顺序无关。
    上级边在 _break_cycles 后已无环，故任何环至少含一条挂靠边。
    """
    return _acyclic_attachments(entities, _controller_hosts(entities, require_consol=True), diags)


def attach_to_controllers(entities: dict[str, Entity]) -> dict[str, str]:
    """集团架构森林用（需求 8）：没有集内上级的企业挂到最终控制方企业下 —— **不要求**控制方有合并项目
    （森林展示的是集团架构，不是合并范围）。成环规则与合并树的挂靠相同（``_acyclic_attachments``）。

    返回 企业代码 → 控制方企业代码；被断开挂靠的企业不在结果中。合并树不调用本函数。
    """
    return _acyclic_attachments(entities, _controller_hosts(entities, require_consol=False), [])


def _acyclic_attachments(
    entities: dict[str, Entity], hosts: dict[str, str], diags: list[Diagnostic],
) -> dict[str, str]:
    """挂靠边与上级边合起来无环：沿「放置上级」检测，环内取有挂靠边的企业代码最小者不挂靠（就地修改 hosts）。"""
    state: dict[str, int] = {}
    for start in sorted(entities):
        if state.get(start):
            continue
        path: list[str] = []
        pos: dict[str, int] = {}
        cur: str | None = start
        while cur is not None and not state.get(cur):
            state[cur] = 1
            pos[cur] = len(path)
            path.append(cur)
            cur = entities[cur].parent_code or hosts.get(cur)
        if cur is not None and state.get(cur) == 1:
            breaker = min(c for c in path[pos[cur]:] if c in hosts)
            host = entities[hosts.pop(breaker)]
            diags.append(Diagnostic(
                "cycle_break",
                f"「{entities[breaker].name}」按最终控制方挂到「{host.name}」下会与其下级成环，已不挂靠",
                company_code=breaker,
            ))
        for c in path:
            state[c] = 2
    return hosts


# ─────────────────────────────── 树构建 ───────────────────────────────


class _TreeBuilder:
    def __init__(self, graph: EntityGraph) -> None:
        self.g = graph
        self.placed: set[str] = set()
        self.diags: list[Diagnostic] = []
        self.orphans: dict[str, list[str]] = {}
        for code, host in graph.orphan_hosts.items():
            self.orphans.setdefault(host, []).append(code)
        for codes in self.orphans.values():
            codes.sort(key=lambda c: (graph.entities[c].name, c))

    # ── 节点工厂 ──
    def _node(
        self, e: Entity, role: str, kind: str, *, project: ProjectRecord | None,
        relation: str | None = None, via: list[str] | None = None, extra_flags: Iterable[str] = (),
    ) -> TreeNode:
        flags = sorted(set(e.flags) | set(extra_flags)) if role in ENTITY_ROLES else []
        return TreeNode(
            project_id=project.id if project else None,
            company_code=e.code,
            company_name=e.name,
            parent_company_code=e.raw_parent_code,
            ultimate_company_code=e.ultimate_code,
            consol_level=project.consol_level if project else 1,
            is_detached="detached" in flags,
            is_cycle_break="cycle_break" in flags,
            status=project.status if project else None,
            report_scope=project.report_scope if project else None,
            node_key=node_key(e.code, role),
            role=role,
            kind=kind,
            display_name=display_name(e.name, role, kind),
            relation=relation,
            flags=flags,
            via=list(via or []),
        )

    def _elim(self, e: Entity, role: str, host: UUID) -> TreeNode:
        node = self._node(e, role, KIND_ELIM, project=None)
        node.host_project_id = host
        return node

    def _data(
        self, e: Entity, role: str, *, relation: str | None = None,
        via: list[str] | None = None, extra_flags: Iterable[str] = (),
    ) -> TreeNode:
        node = self._node(
            e, role, KIND_DATA, project=e.standalone, relation=relation, via=via, extra_flags=extra_flags,
        )
        if e.standalone is None:
            node.flags.append("standalone_missing")
            self.diags.append(Diagnostic(
                "standalone_missing",
                f"「{e.name}」没有 {self.g.year} 年度单户项目，「{node.display_name}」节点金额按 0 计",
                company_code=e.code, node_key=node.node_key,
            ))
        return node

    # ── 结构 ──
    def consol_node(
        self, e: Entity, *, relation: str | None, via: list[str], extra_flags: Iterable[str] = (),
    ) -> TreeNode:
        assert e.consol is not None
        self.placed.add(e.code)
        host = e.consol.id
        node = self._node(
            e, ROLE_CONSOL, KIND_AGGREGATE, project=e.consol, relation=relation, via=via,
            extra_flags=extra_flags,
        )
        node.children.append(self._elim(e, ROLE_CONSOL_ELIM, host))
        node.children.append(self.figures(e, ROLE_PARENT, host))
        node.children.extend(self.members(e, host, via_prefix=[], with_orphans=True))
        node.mode = self._mode_of(node, e.code)
        return node

    def figures(
        self, e: Entity, role: str, host: UUID, *, relation: str | None = None,
        via: list[str] | None = None, extra_flags: Iterable[str] = (),
    ) -> TreeNode:
        """企业 e 的「本企业数据」节点：有分公司时展开为 本部 + 母分差额 + 各分公司。"""
        self.placed.add(e.code)
        if role == ROLE_BRANCH and e.consol is not None:
            self.diags.append(Diagnostic(
                "branch_consol_ignored",
                f"「{e.name}」是分公司，按汇总并入上级；它自己的合并项目不在本树中单列",
                company_code=e.code, level="info",
            ))
        branches = [
            self.g.entities[c] for c in self.g.children[e.code]
            if self.g.entities[c].relation == RELATION_BRANCH and c not in self.placed
        ]
        if not branches:
            return self._data(e, role, relation=relation, via=via, extra_flags=extra_flags)
        agg = self._node(
            e, role, KIND_AGGREGATE, project=None, relation=relation, via=via, extra_flags=extra_flags,
        )
        agg.children.append(self._elim(e, ROLE_BRANCH_ELIM, host))
        agg.children.append(self._data(e, ROLE_HQ))
        for b in branches:
            agg.children.append(self.figures(b, ROLE_BRANCH, host, relation=RELATION_BRANCH))
        return agg

    def _subsidiaries_of_closure(self, e: Entity) -> list[Entity]:
        """e 及其分公司闭包内全部企业的「子公司」下级（按名称、代码排序）。"""
        closure = [e]
        i = 0
        while i < len(closure):
            x = closure[i]
            i += 1
            closure.extend(
                self.g.entities[c] for c in self.g.children[x.code]
                if self.g.entities[c].relation == RELATION_BRANCH
            )
        subs = [
            self.g.entities[c] for x in closure for c in self.g.children[x.code]
            if self.g.entities[c].relation != RELATION_BRANCH
        ]
        return sorted(subs, key=lambda s: (s.name, s.code))

    def members(self, e: Entity, host: UUID, *, via_prefix: list[str], with_orphans: bool) -> list[TreeNode]:
        out: list[TreeNode] = []
        for s in self._subsidiaries_of_closure(e):
            if s.code in self.placed:
                continue
            out.extend(self._member(s, host, via=via_prefix, relation=s.relation))
        if with_orphans:
            for code in self.orphans.get(e.code, []):
                x = self.g.entities[code]
                if x.code in self.placed:
                    continue
                extra: tuple[str, ...] = ()
                if "detached" not in x.flags:
                    extra = ("parent_missing",)
                    self.diags.append(Diagnostic(
                        "parent_missing",
                        f"「{x.name}」没有填写上级代码（或填为本企业），按最终控制方代码挂在「{e.name}（合并）」下",
                        company_code=x.code, level="info",
                    ))
                out.extend(self._member(x, host, via=[], relation=x.relation, extra_flags=extra))
        return out

    def _member(
        self, s: Entity, host: UUID, *, via: list[str], relation: str | None, extra_flags: Iterable[str] = (),
    ) -> list[TreeNode]:
        """一个成员企业：有合并项目 ⇒ 三节点；没有 ⇒ 数据节点 + 提升它的下级（标经其间接持有）。"""
        role = ROLE_BRANCH if relation == RELATION_BRANCH else ROLE_SUBSIDIARY
        if s.consol is not None and role == ROLE_SUBSIDIARY:
            return [self.consol_node(s, relation=relation, via=via, extra_flags=extra_flags)]
        nodes = [self.figures(s, role, host, relation=relation, via=via, extra_flags=extra_flags)]
        promoted = self.members(s, host, via_prefix=via + [s.code], with_orphans=False)
        if promoted:
            self.diags.append(Diagnostic(
                "via",
                f"「{s.name}」没有合并项目，其 {len(promoted)} 个下级节点提升到上层合并节点，标注经其间接持有",
                company_code=s.code, level="info",
            ))
        return nodes + promoted

    def _mode_of(self, consol: TreeNode, own_code: str) -> str:
        has_sub = has_branch = False
        for n in iter_nodes(consol):
            if n.role not in ENTITY_ROLES or n.company_code == own_code:
                continue
            if self.g.entities[n.company_code].relation == RELATION_BRANCH:
                has_branch = True
            else:
                has_sub = True
        if has_sub and has_branch:
            return MODE_MIXED
        if has_sub:
            return MODE_SUBSIDIARY
        if has_branch:
            return MODE_BRANCH
        return MODE_NONE


def _lone_node(root: ProjectRecord) -> TreeNode:
    code = _clean(root.company_code) or str(root.id)[:8]
    consolidated = normalize_report_scope(root.report_scope) == "consolidated"
    role = ROLE_CONSOL if consolidated else ROLE_PARENT
    kind = KIND_AGGREGATE if consolidated else KIND_DATA
    return TreeNode(
        project_id=root.id,
        company_code=code,
        company_name=root.client_name,
        parent_company_code=_clean(root.parent_company_code),
        ultimate_company_code=_clean(root.ultimate_company_code),
        consol_level=root.consol_level or 1,
        status=root.status,
        report_scope=root.report_scope,
        node_key=node_key(code, role),
        role=role,
        kind=kind,
        display_name=display_name(root.client_name, role, kind),
        mode=MODE_NONE if consolidated else None,
    )


# ─────────────────────────────── 派生链接 ───────────────────────────────


def _nearest_consol_above(graph: EntityGraph, e: Entity) -> UUID | None:
    """沿放置上级（上级边 + 按最终控制方挂靠，子公司与分公司都算）找最近的合并项目。"""
    seen = {e.code}
    cur = e
    while True:
        nxt = graph.placement_parent(cur.code)
        if nxt is None or nxt in seen:
            return None
        cur = graph.entities[nxt]
        if cur.consol is not None:
            return cur.consol.id
        seen.add(cur.code)


def _derive_links(graph: EntityGraph) -> dict[UUID, UUID | None]:
    links: dict[UUID, UUID | None] = {}
    for e in graph.entities.values():
        above = _nearest_consol_above(graph, e)
        if e.standalone is not None:
            links[e.standalone.id] = e.consol.id if e.consol is not None else above
        if e.consol is not None:
            links[e.consol.id] = above
    for code, scope, rec in graph.duplicates:
        e = graph.entities[code]
        if scope == "standalone" and e.consol is not None:
            links[rec.id] = e.consol.id
        else:
            links[rec.id] = _nearest_consol_above(graph, e)
    return links


def derive_parent_links(records: Iterable[ProjectRecord], year: int | None) -> dict[UUID, UUID | None]:
    """全年度派生链接（需求 7.1）：项目 id → 直接消费它的合并项目 id。

    单体项目 ⇒ 本企业合并项目；本企业没有合并项目 ⇒ 沿上级链最近的合并项目；
    合并项目 ⇒ 从上级开始沿链最近的合并项目；都没有 ⇒ None。与记录顺序无关（P5）。
    """
    return _derive_links(build_entity_graph(records, year))


def would_form_cycle(
    records: Iterable[ProjectRecord], year: int | None, company_code: str, new_parent_code: str | None,
) -> bool:
    """把 ``company_code`` 的上级改为 ``new_parent_code`` 是否会让它成为自己的祖先（同年度）。

    上级 = 本企业是合法的「本企业就是上级企业」，不算环。库存数据里原有的环先按确定性规则断开再判断。
    """
    target = effective_parent_code(company_code, new_parent_code)
    if target is None:
        return False
    graph = build_entity_graph(records, year)
    seen: set[str] = set()
    cur: str | None = target
    while cur is not None and cur not in seen:
        if cur == company_code:
            return True
        seen.add(cur)
        e = graph.entities.get(cur)
        cur = e.parent_code if e is not None else None
    return False


# ─────────────────────────────── 入口 ───────────────────────────────


def derive_group_tree(
    records: Iterable[ProjectRecord],
    root: ProjectRecord,
    year: int | None,
) -> GroupTreeResult:
    """以合并项目 ``root`` 为根推导企业树（纯函数，design §三）。"""
    if year is None:
        return GroupTreeResult(
            root=_lone_node(root), year=None, mode=MODE_NONE,
            diagnostics=[Diagnostic(
                "year_unresolved", "无法确定本项目的审计年度，企业树只显示本项目",
                company_code=_clean(root.company_code),
            )],
        )
    code = _clean(root.company_code)
    if code is None:
        return GroupTreeResult(
            root=_lone_node(root), year=year, mode=MODE_NONE,
            diagnostics=[Diagnostic("root_no_company_code", "本项目未填企业代码，无法按三码生成企业树")],
        )
    if normalize_report_scope(root.report_scope) != "consolidated":
        return GroupTreeResult(
            root=_lone_node(root), year=year, mode=MODE_NONE,
            diagnostics=[Diagnostic(
                "root_not_consolidated", "本项目不是合并报表项目，企业树只显示本项目", company_code=code,
            )],
        )
    pool = [r for r in records if r.id != root.id] + [root]
    graph = build_entity_graph(pool, year, prefer_ids=[root.id])
    builder = _TreeBuilder(graph)
    tree = builder.consol_node(graph.entities[code], relation=None, via=[])

    placed = builder.placed
    diags = [d for d in graph.diagnostics if d.company_code in placed] + builder.diags
    links = _derive_links(graph)
    for c in sorted(placed):
        e = graph.entities[c]
        for p in (e.consol, e.standalone):
            if p is not None and links.get(p.id) != p.parent_project_id:
                diags.append(Diagnostic(
                    "link_mismatch",
                    f"「{p.client_name}」库存的上级合并项目链接与三码推导不一致，保存基本信息或运行链接重算后自动更正",
                    company_code=c, level="info",
                ))
    return GroupTreeResult(root=tree, year=year, mode=tree.mode or MODE_NONE, diagnostics=sort_diagnostics(diags))


_RECORD_COLUMNS = (
    Project.id, Project.company_code, Project.client_name, Project.report_scope,
    Project.parent_company_code, Project.ultimate_company_code, Project.relation_to_parent,
    Project.parent_project_id, Project.status, Project.consol_level,
)


async def load_year_records(db: AsyncSession, year: int) -> list[ProjectRecord]:
    """同审计年度、未删、有企业代码的全部项目（需求 3.1 / 3.8；年度按平台统一解析）。"""
    base = (
        Project.is_deleted == sa.false(),
        Project.company_code.isnot(None),
        Project.company_code != "",
    )
    rows = (await db.execute(sa.select(*_RECORD_COLUMNS).where(*base, Project.audit_year == year))).all()
    records = [
        ProjectRecord(
            id=r.id, company_code=r.company_code, client_name=r.client_name or "",
            report_scope=r.report_scope, audit_year=year,
            parent_company_code=r.parent_company_code, ultimate_company_code=r.ultimate_company_code,
            relation_to_parent=r.relation_to_parent, parent_project_id=r.parent_project_id,
            status=str(getattr(r.status, "value", r.status)) if r.status is not None else None,
            consol_level=r.consol_level or 1,
        )
        for r in rows
    ]
    # 物化年度列为空的旧项目：按统一年度解析兜底（需 ORM 对象；数量少）
    legacy = (await db.execute(sa.select(Project).where(*base, Project.audit_year.is_(None)))).scalars().all()
    records.extend(record_from_project(p, year) for p in legacy if resolve_project_audit_year(p) == year)
    return records


async def build_group_tree(db: AsyncSession, root_project_id: UUID) -> GroupTreeResult | None:
    """装载同年度记录后推导企业树；根项目不存在返回 None。"""
    root = (await db.execute(
        sa.select(Project).where(Project.id == root_project_id, Project.is_deleted == sa.false())
    )).scalar_one_or_none()
    if root is None:
        return None
    year = resolve_project_audit_year(root)
    records = await load_year_records(db, year) if year is not None else []
    return derive_group_tree(records, record_from_project(root, year), year)


__all__ = [
    "ELIM_ROLES",
    "ENTITY_ROLES",
    "KIND_AGGREGATE",
    "KIND_DATA",
    "KIND_ELIM",
    "MODE_LABELS",
    "ROLE_BRANCH",
    "ROLE_BRANCH_ELIM",
    "ROLE_CONSOL",
    "ROLE_CONSOL_ELIM",
    "ROLE_HQ",
    "ROLE_PARENT",
    "ROLE_SUBSIDIARY",
    "Diagnostic",
    "EntityGraph",
    "GroupTreeResult",
    "ProjectRecord",
    "build_entity_graph",
    "build_group_tree",
    "derive_group_tree",
    "derive_parent_links",
    "display_name",
    "load_year_records",
    "node_key",
    "record_from_project",
    "sort_diagnostics",
    "would_form_cycle",
]
