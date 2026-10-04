"""集团架构森林 —— ``GET /api/projects/tree`` 与批量导入预览共用（spec consol-tree-three-code-autobuild 任务 9.2 / 需求 8）。

与合并企业树（``consol_group_tree``）用同一套企业实体与上级边：
- 企业实体 = 同代码、同年度的合并项目 + 单户项目，节点列出全部项目（``projects``），不因同代码丢项目（需求 8.1）；
- 上级边、上级=本企业、脱挂、断环与合并树完全相同（``build_entity_graph``）；没有集内上级的企业按最终控制方
  挂到控制方企业下（``attach_to_controllers``：不要求控制方有合并项目 —— 森林展示集团架构，不是合并范围）；
- 年度按平台统一解析（``resolve_project_audit_year``，属性缺省安全，需求 8.2）；未传年度时按（控制方, 年度）分树，
  年度无法解析的项目自成一组，绝不与有年度的项目混建；
- 报表类型筛选在建树之后做：只保留有该口径项目的企业，被筛掉的中间企业由其最近的保留上级接替并在 ``via``
  列出，不会因中间企业只有另一口径项目就把下级误标脱挂；
- 可见性（需求 8.3）在装载时过滤（``load_forest``）：纯函数 ``build_forest`` 只看到调用方给的项目。

节点字段兼容旧前端（``id/label/companyCode/…/isDetached/isCycleBreak/hasNoCompanyCode/children``），
另加 ``relation/flags/via/year/projects/consolidatedProjectId/standaloneProjectId``；树加 ``key/year``。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, ProjectUser
from app.services.consol_group_tree import (
    Entity,
    ProjectRecord,
    attach_to_controllers,
    build_entity_graph,
    record_from_project,
)
from app.services.note_section_catalog import normalize_report_scope
from app.services.project_audit_year import resolve_project_audit_year

logger = logging.getLogger(__name__)

# build_entity_graph 要求年度非空：年度无法解析的项目用哨兵值自成一组，输出时还原为 None
_NO_YEAR = 0
# 与 deps.get_visible_project_ids 同一口径：这两类角色看全部项目，其余角色只看参与的项目
_SEE_ALL_ROLES = frozenset({"admin", "partner"})


def project_year(p: Any) -> int | None:
    """审计年度（平台统一 5 级解析）；批量预览等轻量对象缺哪个属性就当它为空。"""
    view = SimpleNamespace(
        audit_year=getattr(p, "audit_year", None),
        audit_period_end=getattr(p, "audit_period_end", None),
        audit_period_start=getattr(p, "audit_period_start", None),
        wizard_state=getattr(p, "wizard_state", None),
        name=getattr(p, "name", None),
    )
    return resolve_project_audit_year(view)  # type: ignore[arg-type]


def _clean(value: object) -> str | None:
    s = str(value).strip() if value is not None else ""
    return s or None


def _scope(rec: ProjectRecord) -> str:
    return normalize_report_scope(rec.report_scope)


def _project_item(rec: ProjectRecord, *, duplicate: bool = False) -> dict:
    return {"id": str(rec.id), "reportScope": _scope(rec), "status": rec.status, "duplicate": duplicate}


def _base_node(rec: ProjectRecord, year: int | None) -> dict:
    """旧前端依赖的键（to_dict_v2 形态）+ 新增键的默认值。"""
    return {
        "id": str(rec.id),
        "label": rec.client_name,
        "companyCode": _clean(rec.company_code) or "",
        "companyName": rec.client_name,
        "parentCompanyCode": _clean(rec.parent_company_code),
        "ultimateCompanyCode": _clean(rec.ultimate_company_code),
        "consolLevel": rec.consol_level,
        "status": rec.status,
        "reportScope": rec.report_scope,
        "isDetached": False,
        "isIndependent": False,
        "isCycleBreak": False,
        "hasNoCompanyCode": False,
        "shareholding": None,
        "consolMethod": None,
        "relation": None,
        "flags": [],
        "via": [],
        "year": year,
        "projects": [_project_item(rec)],
        "consolidatedProjectId": str(rec.id) if _scope(rec) == "consolidated" else None,
        "standaloneProjectId": str(rec.id) if _scope(rec) == "standalone" else None,
        "children": [],
    }


def _entity_node(
    e: Entity, projects: list[ProjectRecord], duplicate_ids: set[UUID], year: int | None, via: list[Entity],
    hidden_parent_codes: frozenset[str],
) -> dict:
    """企业节点：代表项目取合并项目（没有则单户），``projects`` 列出该企业在本口径下的全部项目。

    上级企业本年度有项目、只是当前用户看不到 ⇒ 标 ``parent_hidden`` 而不是「脱挂」（数据没有问题，
    是可见性所致）；只给标记，不透露上级项目的任何信息。
    """
    ordered = sorted(projects, key=lambda r: (_scope(r) != "consolidated", r.id in duplicate_ids, str(r.id)))
    node = _base_node(ordered[0], year)
    flags = set(e.flags)
    if "detached" in flags and e.raw_parent_code in hidden_parent_codes:
        flags.discard("detached")
        flags.add("parent_hidden")
    if any(r.id in duplicate_ids for r in ordered):
        flags.add("duplicate_project")
    primary = [r for r in ordered if r.id not in duplicate_ids]
    consol = next((r for r in primary if _scope(r) == "consolidated"), None)
    standalone = next((r for r in primary if _scope(r) == "standalone"), None)
    node.update({
        "label": e.name,
        "companyCode": e.code,
        "companyName": e.name,
        "parentCompanyCode": e.raw_parent_code,
        "ultimateCompanyCode": e.ultimate_code,
        "isDetached": "detached" in flags,
        "isCycleBreak": "cycle_break" in flags,
        "relation": e.relation,
        "flags": sorted(flags),
        "via": [{"companyCode": v.code, "companyName": v.name} for v in via],
        "projects": [_project_item(r, duplicate=r.id in duplicate_ids) for r in ordered],
        "consolidatedProjectId": str(consol.id) if consol else None,
        "standaloneProjectId": str(standalone.id) if standalone else None,
    })
    return node


def _node_order(node: dict) -> tuple[str, str, str]:
    return (node["companyName"] or "", node["companyCode"] or "", node["id"])


def _forest_of_year(
    records: list[ProjectRecord], bucket: int, year: int | None, wanted: str | None,
    controller_names: dict[str, str], existing_codes: frozenset[str] | None,
) -> tuple[list[dict], list[dict]]:
    """同一年度（或「年度无法解析」组）的全部企业 → (集团树, 独立企业)。"""
    graph = build_entity_graph(records, bucket)
    ents = graph.entities
    # 上级代码在本年度确有项目（全库）但不在可见集合里 ⇒ 不是脱挂，是看不到
    hidden_parent_codes = frozenset((existing_codes or frozenset()) - set(ents))
    projects_of: dict[str, list[ProjectRecord]] = {
        code: [p for p in (e.consol, e.standalone) if p is not None] for code, e in ents.items()
    }
    duplicate_ids: set[UUID] = set()
    for code, _scope_name, rec in graph.duplicates:
        projects_of[code].append(rec)
        duplicate_ids.add(rec.id)

    hosts = attach_to_controllers(ents)
    kids: dict[str, list[str]] = {code: [] for code in ents}
    roots: list[str] = []
    for code in sorted(ents):
        upper = ents[code].parent_code or hosts.get(code)
        if upper is None:
            roots.append(code)
        else:
            kids[upper].append(code)
    for codes in kids.values():
        codes.sort(key=lambda c: (ents[c].name, c))

    def kept(code: str) -> list[ProjectRecord]:
        ps = projects_of[code]
        return ps if wanted is None else [r for r in ps if _scope(r) == wanted]

    def project_subtree(code: str, via: list[Entity]) -> list[dict]:
        """企业 code 的子树投影到「保留企业」：本企业保留 ⇒ 一个节点；被筛掉 ⇒ 由其保留后代接替（via 记下它）。"""
        ps = kept(code)
        if not ps:
            out: list[dict] = []
            for k in kids[code]:
                out.extend(project_subtree(k, via + [ents[code]]))
            return out
        node = _entity_node(ents[code], ps, duplicate_ids, year, via, hidden_parent_codes)
        for k in kids[code]:
            node["children"].extend(project_subtree(k, []))
        node["children"].sort(key=_node_order)
        return [node]

    def root_subtree(code: str) -> list[dict]:
        """顶层企业：被筛掉时下级直接接到树上 —— 它本身就是树头（集团名），不再记进下级的 via。"""
        if kept(code):
            return project_subtree(code, [])
        out: list[dict] = []
        for k in kids[code]:
            out.extend(project_subtree(k, []))
        return out

    groups: dict[str, dict] = {}
    independents: list[dict] = []
    for code in roots:
        e = ents[code]
        nodes = root_subtree(code)
        if not nodes:
            continue
        ultimate = e.ultimate_code
        if ultimate and ultimate != code and ultimate not in ents:
            # 控制方在本年度没有（可见的）项目：同一控制方的顶层企业合成一棵无根树
            groups.setdefault(ultimate, {"root": None, "nodes": []})["nodes"].extend(nodes)
            continue
        if not kids[code] and not ultimate:
            # 没有上级、没有下级、没有控制方 ⇒ 独立企业
            for n in nodes:
                n["isIndependent"] = True
            independents.extend(nodes)
            continue
        groups[code] = {"root": code, "nodes": nodes}

    trees: list[dict] = []
    for key, group in groups.items():
        root_code = group["root"]
        nodes = sorted(group["nodes"], key=_node_order)
        if root_code is not None:
            root_kept = bool(kept(root_code))
            name = ents[root_code].name
            root_pid = nodes[0]["id"] if root_kept else None
        else:
            name = controller_names.get(key) or key
            root_pid = None
        trees.append({
            "key": f"{key}@{year if year is not None else ''}",
            "ultimateCode": key,
            "ultimateName": name,
            "rootProjectId": root_pid,
            "year": year,
            "children": nodes,
        })
    trees.sort(key=lambda t: (t["ultimateName"] or "", t["ultimateCode"]))
    independents.sort(key=_node_order)
    return trees, independents


def build_forest(
    projects: Iterable[Any],
    year: int | None = None,
    *,
    scope: str | None = None,
    existing_codes: Mapping[int | None, Iterable[str]] | None = None,
) -> dict:
    """扁平项目 → 集团架构森林（纯函数，与输入顺序无关）。

    ``year`` 非空 ⇒ 只取该审计年度；为空 ⇒ 每个年度各自成树（新年度在前，年度无法解析的组最后）。
    ``scope`` 为 ``consolidated`` / ``standalone`` 时只保留有该口径项目的企业；其他值 ⇒ 空森林（与旧实现一致）。
    ``existing_codes``（年度 → 该年度全库有项目的企业代码）只在按可见性过滤后传入：上级不可见 ≠ 脱挂。
    返回 ``{"trees": [...], "independents": [...]}``；缺企业代码的项目逐个进 ``independents``。
    """
    wanted = (scope or "").strip().lower() or None
    buckets: dict[int, list[ProjectRecord]] = {}
    no_code: list[tuple[ProjectRecord, int | None]] = []
    names_by_bucket: dict[int, dict[str, set[str]]] = {}
    for p in projects:
        y = project_year(p)
        if year is not None and y != year:
            continue
        bucket = y if y is not None else _NO_YEAR
        rec = record_from_project(p, bucket)
        if _clean(rec.company_code) is None:
            no_code.append((rec, y))
            continue
        buckets.setdefault(bucket, []).append(rec)
        ultimate, uname = _clean(rec.ultimate_company_code), _clean(getattr(p, "ultimate_company_name", None))
        if ultimate and uname:
            names_by_bucket.setdefault(bucket, {}).setdefault(ultimate, set()).add(uname)

    trees: list[dict] = []
    independents: list[dict] = []
    for bucket in sorted(buckets, reverse=True):
        names = {code: min(ns) for code, ns in names_by_bucket.get(bucket, {}).items()}
        bucket_year = None if bucket == _NO_YEAR else bucket
        existing = None
        if existing_codes is not None:
            existing = frozenset(c for c in (_clean(x) for x in existing_codes.get(bucket_year, ())) if c)
        year_trees, year_indep = _forest_of_year(
            buckets[bucket], bucket, bucket_year, wanted, names, existing,
        )
        trees.extend(year_trees)
        independents.extend(year_indep)

    loose: list[dict] = []
    for rec, y in no_code:
        if wanted is not None and _scope(rec) != wanted:
            continue
        node = _base_node(rec, y)
        node.update({"isIndependent": True, "hasNoCompanyCode": True, "flags": ["no_company_code"]})
        loose.append(node)
    loose.sort(key=lambda n: (-(n["year"] or 0), *_node_order(n)))
    return {"trees": trees, "independents": independents + loose}


async def load_forest(
    db: AsyncSession, *, year: int | None = None, scope: str | None = None, user: Any = None,
) -> dict:
    """装载可见项目后构建森林并富集持股比例 / 合并方式。

    ``user`` 为空 ⇒ 不做可见性过滤（内部调用）；admin/partner 看全部，其余角色只看自己参与的项目（需求 8.3）。
    """
    stmt = sa.select(Project).where(Project.is_deleted == sa.false())
    if year is not None:
        # 物化年度列是主来源；只有它为空的旧项目才需要按其余字段兜底（与 load_year_records 同口径）
        stmt = stmt.where(sa.or_(Project.audit_year == year, Project.audit_year.is_(None)))
    existing_codes: dict[int | None, set[str]] | None = None
    if user is not None:
        role = getattr(getattr(user, "role", None), "value", getattr(user, "role", None))
        if role not in _SEE_ALL_ROLES:
            existing_codes = await _existing_codes_by_year(db, year)
            stmt = stmt.where(Project.id.in_(
                sa.select(ProjectUser.project_id).where(
                    ProjectUser.user_id == user.id,
                    ProjectUser.is_deleted == sa.false(),
                )
            ))
    projects = list((await db.execute(stmt)).scalars().all())
    forest = build_forest(projects, year=year, scope=scope, existing_codes=existing_codes)
    await enrich_with_company_info(db, forest)
    return forest


async def _existing_codes_by_year(db: AsyncSession, year: int | None) -> dict[int | None, set[str]]:
    """年度 → 该年度全库（未删）有项目的企业代码。只读代码与年度字段，不把不可见项目的其他信息放进结果。

    先取轻量列解析年度；只有它们都解析不出年度的少数旧项目才补读向导状态（与统一年度解析同口径）。
    """
    cols = (
        Project.id, Project.company_code, Project.audit_year, Project.audit_period_end,
        Project.audit_period_start, Project.name,
    )
    stmt = sa.select(*cols).where(
        Project.is_deleted == sa.false(), Project.company_code.isnot(None), Project.company_code != "",
    )
    if year is not None:
        stmt = stmt.where(sa.or_(Project.audit_year == year, Project.audit_year.is_(None)))
    out: dict[int | None, set[str]] = {}
    unresolved: dict[UUID, Any] = {}
    for row in (await db.execute(stmt)).all():
        # 前三级（年度列 / 期末日 / 期初日）先判；向导状态排在项目名之前，所以这里不能先用项目名兜底
        y = project_year(SimpleNamespace(
            audit_year=row.audit_year, audit_period_end=row.audit_period_end,
            audit_period_start=row.audit_period_start,
        ))
        if y is None:
            unresolved[row.id] = row
            continue
        out.setdefault(y, set()).add(row.company_code.strip())
    if unresolved:
        states = (await db.execute(
            sa.select(Project.id, Project.wizard_state).where(Project.id.in_(list(unresolved)))
        )).all()
        for pid, wizard_state in states:
            row = unresolved[pid]
            view = SimpleNamespace(
                audit_year=row.audit_year, audit_period_end=row.audit_period_end,
                audit_period_start=row.audit_period_start, wizard_state=wizard_state, name=row.name,
            )
            out.setdefault(project_year(view), set()).add(row.company_code.strip())
    return out


async def enrich_with_company_info(db: AsyncSession, forest: dict) -> None:
    """从 companies 表按企业代码富集 shareholding / consolMethod（就地修改节点字典）。

    查询失败（表不可用等）或无匹配 ⇒ 节点保持 None，不影响树形。查询放在 SAVEPOINT 里：
    失败只回滚这一步，不把请求事务留在 aborted 状态。
    """
    codes: set[str] = set()

    def _collect(nodes: list[dict]) -> None:
        for n in nodes:
            if n.get("companyCode"):
                codes.add(n["companyCode"])
            _collect(n.get("children") or [])

    for tree in forest.get("trees", []):
        _collect(tree.get("children") or [])
    _collect(forest.get("independents") or [])
    if not codes:
        return

    from app.models.consolidation_models import Company

    info_map: dict[str, dict] = {}
    try:
        async with db.begin_nested():
            rows = (await db.execute(
                sa.select(Company.company_code, Company.shareholding, Company.consol_method).where(
                    Company.company_code.in_(sorted(codes)),
                    Company.is_active == sa.true(),
                    Company.is_deleted == sa.false(),
                ).order_by(Company.company_code, Company.id)
            )).all()
    except Exception as exc:  # noqa: BLE001 — 富集是展示增强，失败降级为不富集
        logger.warning("集团架构森林富集持股信息失败，按无数据展示: %s", exc)
        return
    for company_code, shareholding, consol_method in rows:
        if not company_code or company_code in info_map:
            continue
        method = getattr(consol_method, "value", consol_method)
        info_map[company_code] = {
            "shareholding": float(shareholding) if shareholding is not None else None,
            "consolMethod": str(method) if method is not None else None,
        }
    if not info_map:
        return

    def _apply(nodes: list[dict]) -> None:
        for n in nodes:
            info = info_map.get(n.get("companyCode") or "")
            if info:
                n.update(info)
            _apply(n.get("children") or [])

    for tree in forest.get("trees", []):
        _apply(tree.get("children") or [])
    _apply(forest.get("independents") or [])


__all__ = ["build_forest", "enrich_with_company_info", "load_forest", "project_year"]
