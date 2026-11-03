"""项目永久删除的保守事务核心。

本服务只使用调用方提供的 ``AsyncSession``。它负责锁定、预检、规划和数据库删除，
只 ``flush``，不提交；调用方在提交成功后根据返回的 ``file_refs`` 清理物理对象。
任何无法证明安全的关系或依赖图都会在第一条写语句之前被拒绝。
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timezone
from graphlib import CycleError, TopologicalSorter
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utcnow
from app.models.attachment_models import Attachment
from app.models.core import Project
from app.models.evidence_governance_models import AttachmentVersion
from app.services.attachment_storage_resolver import StoredAttachmentRef
from app.services.evidence_governance.retention_legal_hold_service import (
    RetentionLegalHoldService,
)

LegalHoldFactory = Callable[[AsyncSession], Any]

@dataclass(frozen=True)
class ProjectPurgeResult:
    """预检或删除结果；文件引用必须等调用方提交成功后才能处理。"""

    project_id: UUID
    dry_run: bool
    table_counts: Mapping[str, int]
    file_refs: tuple[StoredAttachmentRef, ...]
    delete_order: tuple[str, ...]

@dataclass(frozen=True)
class _TableMeta:
    oid: int
    schema: str
    name: str
    columns: frozenset[str]
    nullable_columns: frozenset[str]

@dataclass(frozen=True)
class _ForeignKey:
    oid: int
    name: str
    child_oid: int
    parent_oid: int
    child_columns: tuple[str, ...]
    parent_columns: tuple[str, ...]
    match_type: str

@dataclass(frozen=True)
class _Scope:
    level: int
    parents: tuple[_ForeignKey, ...] = ()

@dataclass(frozen=True)
class _CycleBreak:
    foreign_key: _ForeignKey
    null_columns: tuple[str, ...]

@dataclass(frozen=True)
class _PreparedPurge:
    project_id: UUID
    tables: Mapping[int, _TableMeta]
    scopes: Mapping[int, _Scope]
    expected_counts: Mapping[int, int]
    delete_oids: tuple[int, ...]
    cycle_breaks: tuple[_CycleBreak, ...]
    file_refs: tuple[StoredAttachmentRef, ...]

_RELATION_CHECKS: tuple[tuple[str, str], ...] = (
    ("attachment_working_paper", """SELECT 1 FROM attachment_working_paper r
     JOIN attachments a ON a.id=r.attachment_id JOIN working_paper w ON w.id=r.wp_id
     WHERE (a.project_id::text=:pid OR w.project_id::text=:pid)
       AND a.project_id IS DISTINCT FROM w.project_id LIMIT 1"""),
    ("attachment_working_paper_legacy", """SELECT 1 FROM attachment_working_paper r
     JOIN attachments a ON a.id=r.attachment_id JOIN working_paper w ON w.id=r.working_paper_id
     WHERE r.working_paper_id IS NOT NULL AND (a.project_id::text=:pid OR w.project_id::text=:pid)
       AND a.project_id IS DISTINCT FROM w.project_id LIMIT 1"""),
    ("evidence_link", """SELECT 1 FROM evidence_links r
     JOIN attachments a ON a.id=r.attachment_id JOIN working_paper w ON w.id=r.wp_id
     WHERE (a.project_id::text=:pid OR w.project_id::text=:pid)
       AND a.project_id IS DISTINCT FROM w.project_id LIMIT 1"""),
    ("confirmation_attachment_link", """SELECT 1 FROM confirmation_attachment_link r
     JOIN confirmations c ON c.id=r.confirmation_id JOIN attachments a ON a.id=r.attachment_id
     WHERE (c.project_id::text=:pid OR a.project_id::text=:pid)
       AND c.project_id IS DISTINCT FROM a.project_id LIMIT 1"""),
    ("confirmation_attachment_pair", """SELECT 1 FROM confirmation_attachment_link r
     JOIN confirmations c ON c.id=r.confirmation_id JOIN attachments a ON a.id=r.attachment_id
     LEFT JOIN attachments p ON p.id=r.paired_outbound_attachment_id
     WHERE r.paired_outbound_attachment_id IS NOT NULL
       AND (c.project_id::text=:pid OR a.project_id::text=:pid OR p.project_id::text=:pid)
       AND (p.id IS NULL OR p.project_id IS DISTINCT FROM c.project_id
            OR p.project_id IS DISTINCT FROM a.project_id) LIMIT 1"""),
    ("attachment_lineage", """SELECT 1 FROM attachment_lineage r
     LEFT JOIN attachments a ON a.id=r.attachment_id
     WHERE (r.project_id::text=:pid OR a.project_id::text=:pid)
       AND (a.id IS NULL OR r.project_id IS DISTINCT FROM a.project_id) LIMIT 1"""),
)

class ProjectPurgeService:
    """在调用方事务内完成一个项目的 fail-closed 永久删除。"""

    def __init__(self, db: AsyncSession, *, legal_hold_factory: LegalHoldFactory = RetentionLegalHoldService) -> None:
        self._db = db
        self._legal_hold_factory = legal_hold_factory
        self._dialect = db.get_bind().dialect
        self._preparer = self._dialect.identifier_preparer

    async def preflight(self, project_id: UUID, *, actor_role: str) -> ProjectPurgeResult:
        prepared = await self._prepare(project_id, actor_role=actor_role)
        return self._public_result(prepared, prepared.expected_counts, dry_run=True)

    async def dry_run(self, project_id: UUID, *, actor_role: str) -> ProjectPurgeResult:
        return await self.preflight(project_id, actor_role=actor_role)

    async def purge(self, project_id: UUID, *, actor_role: str) -> ProjectPurgeResult:
        prepared = await self._prepare(project_id, actor_role=actor_role)
        for item in prepared.cycle_breaks:
            await self._null_cycle_edge(prepared, item)

        actual: dict[int, int] = {}
        for oid in prepared.delete_oids:
            table = prepared.tables[oid]
            predicate = self._scope_sql(oid, "t", prepared.tables, prepared.scopes)
            statement = sa.text(
                f"DELETE FROM {self._qualified(table)} AS {self._quote('t')} "
                f"WHERE {predicate}"
            )
            result = await self._db.execute(statement, {"pid": str(project_id)})
            actual[oid] = int(result.rowcount or 0)
            expected = prepared.expected_counts[oid]
            if actual[oid] != expected:
                self._conflict(
                    "PROJECT_PURGE_STATE_CHANGED",
                    "项目关联数据在删除期间发生变化，永久删除已取消",
                )
        await self._db.flush()
        return self._public_result(prepared, actual, dry_run=False)

    async def purge_one(self, project_id: UUID, *, actor_role: str, dry_run: bool = False) -> ProjectPurgeResult:
        """供后续回收站入口接线的稳定单项目接口。"""
        if dry_run:
            return await self.preflight(project_id, actor_role=actor_role)
        return await self.purge(project_id, actor_role=actor_role)

    async def _prepare(self, project_id: UUID, *, actor_role: str) -> _PreparedPurge:
        self._require_postgresql()
        project = await self._lock_project(project_id)
        self._assert_retention_expired(project)
        attachments, versions = await self._load_attachments_and_versions(project_id)
        await self._authorize_legal_holds(
            project_id, attachments, versions, actor_role=actor_role
        )
        await self._assert_no_cross_project_relations(project_id)

        tables, foreign_keys = await self._load_catalog()
        root_oid, scopes = self._build_scopes(tables, foreign_keys)
        expected_counts = await self._count_scoped_rows(
            project_id, tables, scopes
        )
        internal_edges = await self._assert_fk_boundaries(
            project_id, tables, scopes, foreign_keys, expected_counts
        )
        delete_oids, cycle_breaks = self._plan_delete_order(
            root_oid, tables, expected_counts, internal_edges
        )
        return _PreparedPurge(
            project_id=project_id,
            tables=tables,
            scopes=scopes,
            expected_counts=expected_counts,
            delete_oids=delete_oids,
            cycle_breaks=cycle_breaks,
            file_refs=self._collect_file_refs(project_id, attachments, versions),
        )

    def _require_postgresql(self) -> None:
        if self._dialect.name != "postgresql":
            self._conflict(
                "PROJECT_PURGE_POSTGRESQL_REQUIRED",
                "项目永久删除只允许在 PostgreSQL 的完整外键目录上执行",
            )

    async def _lock_project(self, project_id: UUID) -> Project:
        result = await self._db.execute(
            sa.select(Project)
            .where(Project.id == project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        project = result.scalar_one_or_none()
        if project is None or project.is_deleted is not True:
            self._conflict(
                "PROJECT_PURGE_STATE_CHANGED",
                "项目不存在或已不在回收站，永久删除已取消",
            )
        return project

    @staticmethod
    def _assert_retention_expired(project: Project) -> None:
        retention = project.retention_until
        if retention is None:
            return
        normalized = (
            retention.astimezone(timezone.utc).replace(tzinfo=None)
            if retention.tzinfo is not None
            else retention
        )
        if utcnow() < normalized:
            remaining = normalized - utcnow()
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "RETENTION_LOCKED",
                    "message": "项目数据仍在保留期内，不能永久删除",
                    "retention_until": retention.isoformat(),
                    "remaining_days": max(0, remaining.days),
                },
            )

    async def _load_attachments_and_versions(
        self, project_id: UUID
    ) -> tuple[list[Attachment], list[AttachmentVersion]]:
        attachments = list((await self._db.execute(
            sa.select(Attachment).where(Attachment.project_id == project_id).order_by(Attachment.id)
        )).scalars().all())
        attachment_ids = [row.id for row in attachments]
        version_scope = AttachmentVersion.project_id == project_id
        if attachment_ids:
            version_scope = sa.or_(
                version_scope,
                AttachmentVersion.attachment_id.in_(attachment_ids),
            )
        versions = list((await self._db.execute(
            sa.select(AttachmentVersion).where(version_scope).order_by(AttachmentVersion.id)
        )).scalars().all())
        attachment_projects = {row.id: row.project_id for row in attachments}
        inconsistent = [
            row
            for row in versions
            if row.project_id != project_id
            or attachment_projects.get(row.attachment_id) != project_id
        ]
        if inconsistent:
            self._conflict(
                "PROJECT_PURGE_CROSS_PROJECT_REFERENCE",
                "附件版本的项目作用域不一致，拒绝永久删除",
                relations=["attachment_version"],
            )
        return attachments, versions

    async def _authorize_legal_holds(
        self,
        project_id: UUID,
        attachments: Sequence[Attachment],
        versions: Sequence[AttachmentVersion],
        *,
        actor_role: str,
    ) -> None:
        service = self._legal_hold_factory(self._db)
        nodes = [
            ("project", project_id),
            *(("attachment", row.id) for row in attachments),
            *(("attachment_version", row.id) for row in versions),
        ]
        for node_type, node_id in nodes:
            await service.authorize_destructive(
                actor_role=actor_role,
                operation="purge",
                project_id=project_id,
                node_type=node_type,
                node_id=str(node_id),
            )

    async def _assert_no_cross_project_relations(self, project_id: UUID) -> None:
        found: list[str] = []
        for relation, sql in _RELATION_CHECKS:
            result = await self._db.execute(sa.text(sql), {"pid": str(project_id)})
            if result.first() is not None:
                found.append(relation)
        if found:
            self._conflict(
                "PROJECT_PURGE_CROSS_PROJECT_REFERENCE",
                "项目附件存在跨项目关系，拒绝永久删除",
                relations=found,
            )

    @staticmethod
    def _collect_file_refs(
        project_id: UUID,
        attachments: Sequence[Attachment],
        versions: Sequence[AttachmentVersion],
    ) -> tuple[StoredAttachmentRef, ...]:
        refs = {
            StoredAttachmentRef(project_id, row.storage_type, row.file_path)
            for row in attachments
        }
        for row in versions:
            snapshot = row.config_snapshot if isinstance(row.config_snapshot, dict) else {}
            finalized = snapshot.get("finalized_storage")
            finalized = finalized if isinstance(finalized, dict) else {}
            refs.add(
                StoredAttachmentRef(
                    project_id,
                    finalized.get("storage_type") or row.storage_type,
                    finalized.get("storage_key")
                    or finalized.get("file_path")
                    or row.storage_key,
                )
            )
        return tuple(
            sorted(
                refs,
                key=lambda item: (
                    item.storage_type or "",
                    item.storage_key or "",
                ),
            )
        )

    async def _load_catalog(
        self,
    ) -> tuple[dict[int, _TableMeta], tuple[_ForeignKey, ...]]:
        schema = str(
            (await self._db.execute(sa.text("SELECT current_schema()"))).scalar_one()
        )
        column_rows = (
            await self._db.execute(
                sa.text(
                    """SELECT c.oid::bigint AS table_oid, n.nspname AS schema_name,
                              c.relname AS table_name, a.attname AS column_name,
                              a.attnotnull AS is_not_null
                       FROM pg_class c
                       JOIN pg_namespace n ON n.oid = c.relnamespace
                       JOIN pg_attribute a ON a.attrelid = c.oid
                       WHERE n.nspname = :schema
                         AND c.relkind IN ('r', 'p')
                         AND NOT c.relispartition
                         AND a.attnum > 0 AND NOT a.attisdropped
                       ORDER BY c.oid, a.attnum"""
                ),
                {"schema": schema},
            )
        ).all()
        mutable: dict[int, dict[str, Any]] = {}
        for row in column_rows:
            oid = int(row.table_oid)
            item = mutable.setdefault(
                oid,
                {
                    "schema": str(row.schema_name),
                    "name": str(row.table_name),
                    "columns": set(),
                    "nullable": set(),
                },
            )
            column = str(row.column_name)
            item["columns"].add(column)
            if not bool(row.is_not_null):
                item["nullable"].add(column)
        tables = {
            oid: _TableMeta(
                oid=oid,
                schema=item["schema"],
                name=item["name"],
                columns=frozenset(item["columns"]),
                nullable_columns=frozenset(item["nullable"]),
            )
            for oid, item in mutable.items()
        }

        fk_rows = (
            await self._db.execute(
                sa.text(
                    """SELECT con.oid::bigint AS constraint_oid,
                              con.conname AS constraint_name,
                              con.conrelid::bigint AS child_oid,
                              con.confrelid::bigint AS parent_oid,
                              con.confmatchtype::text AS match_type,
                              ARRAY(SELECT a.attname
                                    FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, pos)
                                    JOIN pg_attribute a
                                      ON a.attrelid = con.conrelid AND a.attnum = k.attnum
                                    ORDER BY k.pos) AS child_columns,
                              ARRAY(SELECT a.attname
                                    FROM unnest(con.confkey) WITH ORDINALITY AS k(attnum, pos)
                                    JOIN pg_attribute a
                                      ON a.attrelid = con.confrelid AND a.attnum = k.attnum
                                    ORDER BY k.pos) AS parent_columns
                       FROM pg_constraint con
                       JOIN pg_class child ON child.oid = con.conrelid
                       JOIN pg_namespace cn ON cn.oid = child.relnamespace
                       JOIN pg_class parent ON parent.oid = con.confrelid
                       JOIN pg_namespace pn ON pn.oid = parent.relnamespace
                       WHERE con.contype = 'f'
                         AND cn.nspname = :schema AND pn.nspname = :schema
                       ORDER BY con.oid"""
                ),
                {"schema": schema},
            )
        ).all()

        foreign_keys: list[_ForeignKey] = []
        for row in fk_rows:
            child_columns = tuple(str(value) for value in (row.child_columns or ()))
            parent_columns = tuple(str(value) for value in (row.parent_columns or ()))
            child_oid, parent_oid = int(row.child_oid), int(row.parent_oid)
            valid = (
                child_oid in tables
                and parent_oid in tables
                and child_columns
                and len(child_columns) == len(parent_columns)
                and set(child_columns) <= tables[child_oid].columns
                and set(parent_columns) <= tables[parent_oid].columns
            )
            if not valid:
                self._conflict(
                    "PROJECT_PURGE_UNSAFE_DEPENDENCY_GRAPH",
                    "数据库外键目录无法安全解析，拒绝永久删除",
                )
            foreign_keys.append(
                _ForeignKey(
                    oid=int(row.constraint_oid),
                    name=str(row.constraint_name),
                    child_oid=child_oid,
                    parent_oid=parent_oid,
                    child_columns=child_columns,
                    parent_columns=parent_columns,
                    match_type=str(row.match_type),
                )
            )
        return tables, tuple(foreign_keys)

    def _build_scopes(
        self,
        tables: Mapping[int, _TableMeta],
        foreign_keys: Sequence[_ForeignKey],
    ) -> tuple[int, dict[int, _Scope]]:
        roots = [
            oid
            for oid, table in tables.items()
            if table.name == "projects" and "id" in table.columns
        ]
        if len(roots) != 1:
            self._conflict(
                "PROJECT_PURGE_UNSAFE_DEPENDENCY_GRAPH",
                "当前 schema 无法唯一定位 projects 表",
            )
        root_oid = roots[0]
        scopes: dict[int, _Scope] = {root_oid: _Scope(0)}
        for oid, table in tables.items():
            if oid != root_oid and "project_id" in table.columns:
                scopes[oid] = _Scope(0)

        by_child: dict[int, list[_ForeignKey]] = {}
        for foreign_key in foreign_keys:
            by_child.setdefault(foreign_key.child_oid, []).append(foreign_key)
        while True:
            additions: dict[int, _Scope] = {}
            for oid in sorted(set(tables) - set(scopes)):
                candidates = [
                    item
                    for item in by_child.get(oid, ())
                    if item.parent_oid in scopes and item.parent_oid != oid
                ]
                if not candidates:
                    continue
                level = min(scopes[item.parent_oid].level for item in candidates) + 1
                additions[oid] = _Scope(level)
            if not additions:
                break
            scopes.update(additions)

        for oid, scope in tuple(scopes.items()):
            if scope.level == 0:
                continue
            parents = tuple(
                sorted(
                    (
                        item
                        for item in by_child.get(oid, ())
                        if item.parent_oid in scopes
                        and scopes[item.parent_oid].level < scope.level
                    ),
                    key=lambda item: item.oid,
                )
            )
            if not parents:
                self._conflict(
                    "PROJECT_PURGE_UNSAFE_DEPENDENCY_GRAPH",
                    "间接项目数据缺少可证明的外键路径",
                )
            scopes[oid] = _Scope(scope.level, parents)
        return root_oid, scopes

    async def _count_scoped_rows(
        self,
        project_id: UUID,
        tables: Mapping[int, _TableMeta],
        scopes: Mapping[int, _Scope],
    ) -> dict[int, int]:
        counts: dict[int, int] = {}
        for oid in sorted(scopes, key=lambda item: (scopes[item].level, tables[item].name)):
            predicate = self._scope_sql(oid, "t", tables, scopes)
            statement = sa.text(
                f"SELECT count(*) FROM {self._qualified(tables[oid])} AS {self._quote('t')} "
                f"WHERE {predicate}"
            )
            counts[oid] = int(
                (await self._db.execute(statement, {"pid": str(project_id)})).scalar_one()
            )
        root_counts = [
            count for oid, count in counts.items() if tables[oid].name == "projects"
        ]
        if root_counts != [1]:
            self._conflict(
                "PROJECT_PURGE_STATE_CHANGED",
                "项目锁定状态发生变化，永久删除已取消",
            )
        return counts

    def _scope_sql(
        self,
        oid: int,
        alias: str,
        tables: Mapping[int, _TableMeta],
        scopes: Mapping[int, _Scope],
    ) -> str:
        table = tables[oid]
        qualified_alias = self._quote(alias)
        if table.name == "projects":
            return f"{qualified_alias}.{self._quote('id')}::text = :pid"
        if "project_id" in table.columns:
            return f"{qualified_alias}.{self._quote('project_id')}::text = :pid"

        terms: list[str] = []
        for foreign_key in scopes[oid].parents:
            parent_alias = f"p_{foreign_key.oid}"
            join = self._join_sql(foreign_key, alias, parent_alias)
            parent_scope = self._scope_sql(
                foreign_key.parent_oid, parent_alias, tables, scopes
            )
            terms.append(
                f"EXISTS (SELECT 1 FROM "
                f"{self._qualified(tables[foreign_key.parent_oid])} AS "
                f"{self._quote(parent_alias)} WHERE {join} AND {parent_scope})"
            )
        if not terms:
            self._conflict(
                "PROJECT_PURGE_UNSAFE_DEPENDENCY_GRAPH",
                f"无法生成表 {table.name} 的项目范围谓词",
            )
        return "(" + " OR ".join(terms) + ")"

    def _join_sql(
        self, foreign_key: _ForeignKey, child_alias: str, parent_alias: str
    ) -> str:
        child = self._quote(child_alias)
        parent = self._quote(parent_alias)
        return " AND ".join(
            f"{child}.{self._quote(child_column)} = "
            f"{parent}.{self._quote(parent_column)}"
            for child_column, parent_column in zip(
                foreign_key.child_columns,
                foreign_key.parent_columns,
                strict=True,
            )
        )

    async def _assert_fk_boundaries(
        self,
        project_id: UUID,
        tables: Mapping[int, _TableMeta],
        scopes: Mapping[int, _Scope],
        foreign_keys: Sequence[_ForeignKey],
        counts: Mapping[int, int],
    ) -> tuple[_ForeignKey, ...]:
        external: list[str] = []
        internal: list[_ForeignKey] = []
        for foreign_key in foreign_keys:
            if (
                foreign_key.child_oid not in scopes
                or foreign_key.parent_oid not in scopes
                or counts[foreign_key.parent_oid] == 0
            ):
                continue
            child = tables[foreign_key.child_oid]
            parent = tables[foreign_key.parent_oid]
            join = self._join_sql(foreign_key, "c", "p")
            child_scope = self._scope_sql(
                foreign_key.child_oid, "c", tables, scopes
            )
            parent_scope = self._scope_sql(
                foreign_key.parent_oid, "p", tables, scopes
            )
            base = (
                f" FROM {self._qualified(child)} AS {self._quote('c')} "
                f"JOIN {self._qualified(parent)} AS {self._quote('p')} ON {join} "
            )
            outside = sa.text(
                "SELECT 1"
                + base
                + f"WHERE {parent_scope} "
                + f"AND NOT COALESCE(({child_scope}), FALSE) LIMIT 1"
            )
            if (
                await self._db.execute(outside, {"pid": str(project_id)})
            ).first() is not None:
                external.append(f"{child.name}.{foreign_key.name}")

            inside = sa.text(
                "SELECT 1"
                + base
                + f"WHERE {child_scope} AND {parent_scope} LIMIT 1"
            )
            if (
                await self._db.execute(inside, {"pid": str(project_id)})
            ).first() is not None:
                internal.append(foreign_key)
        if external:
            self._conflict(
                "PROJECT_PURGE_EXTERNAL_FK_REFERENCE",
                "项目数据仍被项目范围外记录引用，拒绝永久删除",
                constraints=sorted(external),
            )
        return tuple(internal)

    def _plan_delete_order(
        self,
        root_oid: int,
        tables: Mapping[int, _TableMeta],
        counts: Mapping[int, int],
        internal_edges: Sequence[_ForeignKey],
    ) -> tuple[tuple[int, ...], tuple[_CycleBreak, ...]]:
        nodes = set(counts)
        nodes.add(root_oid)
        remaining = [
            edge
            for edge in internal_edges
            if edge.child_oid in nodes
            and edge.parent_oid in nodes
            and edge.child_oid != edge.parent_oid
        ]
        cycle_breaks: list[_CycleBreak] = []
        synthetic = {(oid, root_oid) for oid in nodes if oid != root_oid}
        while True:
            order = self._kahn_order(nodes, remaining, synthetic)
            if len(order) == len(nodes):
                return tuple(order), tuple(cycle_breaks)
            cycle_edges = [
                edge
                for edge in remaining
                if self._path_exists(
                    edge.parent_oid,
                    edge.child_oid,
                    remaining,
                    synthetic,
                )
            ]
            candidates: list[tuple[_ForeignKey, tuple[str, ...]]] = []
            for edge in cycle_edges:
                columns = self._cycle_break_columns(edge, tables[edge.child_oid])
                if columns:
                    candidates.append((edge, columns))
            if not candidates:
                self._conflict(
                    "PROJECT_PURGE_UNSAFE_DEPENDENCY_GRAPH",
                    "项目依赖闭包存在不能安全断开的非空外键循环",
                )
            edge, columns = min(
                candidates,
                key=lambda item: (
                    tables[item[0].child_oid].name,
                    item[0].name,
                ),
            )
            cycle_breaks.append(_CycleBreak(edge, columns))
            remaining.remove(edge)

    @staticmethod
    def _kahn_order(
        nodes: set[int], edges: Sequence[_ForeignKey], synthetic: set[tuple[int, int]]
    ) -> list[int]:
        dependencies: dict[int, set[int]] = {oid: set() for oid in nodes}
        pairs = {(edge.child_oid, edge.parent_oid) for edge in edges} | synthetic
        for child, parent in pairs:
            if child != parent and child in nodes and parent in nodes:
                dependencies[parent].add(child)
        try:
            return list(TopologicalSorter(dependencies).static_order())
        except CycleError:
            return []

    @staticmethod
    def _path_exists(
        start: int,
        target: int,
        edges: Sequence[_ForeignKey],
        synthetic: set[tuple[int, int]],
    ) -> bool:
        outgoing: dict[int, set[int]] = {}
        for edge in edges:
            if edge.child_oid != edge.parent_oid:
                outgoing.setdefault(edge.child_oid, set()).add(edge.parent_oid)
        for child, parent in synthetic:
            outgoing.setdefault(child, set()).add(parent)
        pending = [start]
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current in seen:
                continue
            seen.add(current)
            pending.extend(outgoing.get(current, ()))
        return False

    @staticmethod
    def _cycle_break_columns(
        foreign_key: _ForeignKey, child: _TableMeta
    ) -> tuple[str, ...]:
        nullable = tuple(
            column
            for column in foreign_key.child_columns
            if column in child.nullable_columns
        )
        if foreign_key.match_type == "s" and nullable:
            return (nullable[0],)
        if (
            foreign_key.match_type == "f"
            and len(nullable) == len(foreign_key.child_columns)
        ):
            return nullable
        return ()

    async def _null_cycle_edge(
        self, prepared: _PreparedPurge, item: _CycleBreak
    ) -> None:
        table = prepared.tables[item.foreign_key.child_oid]
        predicate = self._scope_sql(
            table.oid, "t", prepared.tables, prepared.scopes
        )
        assignments = ", ".join(
            f"{self._quote(column)} = NULL" for column in item.null_columns
        )
        await self._db.execute(
            sa.text(
                f"UPDATE {self._qualified(table)} AS {self._quote('t')} "
                f"SET {assignments} WHERE {predicate}"
            ),
            {"pid": str(prepared.project_id)},
        )

    def _public_result(
        self,
        prepared: _PreparedPurge,
        counts: Mapping[int, int],
        *,
        dry_run: bool,
    ) -> ProjectPurgeResult:
        by_name = {
            prepared.tables[oid].name: int(count)
            for oid, count in counts.items()
            if count > 0
        }
        return ProjectPurgeResult(
            project_id=prepared.project_id,
            dry_run=dry_run,
            table_counts=dict(sorted(by_name.items())),
            file_refs=prepared.file_refs,
            delete_order=tuple(
                prepared.tables[oid].name for oid in prepared.delete_oids
            ),
        )

    def _quote(self, identifier: str) -> str:
        return self._preparer.quote_identifier(identifier)

    def _qualified(self, table: _TableMeta) -> str:
        return (
            f"{self._preparer.quote_schema(table.schema)}."
            f"{self._quote(table.name)}"
        )

    @staticmethod
    def _conflict(code: str, message: str, **detail: Any) -> None:
        raise HTTPException(
            status_code=409,
            detail={"error_code": code, "message": message, **detail},
        )
