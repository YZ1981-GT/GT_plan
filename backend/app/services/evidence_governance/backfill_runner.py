"""可恢复/可重复 M1 checkpoint backfill runner（Task 8.1）。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 8.1 (Wave 7 — M0–M4)
Requirements: R14（迁移兼容与可恢复回填）, R16（历史覆盖）
Design: §8.2 M1 backfill、§4.1 Attachment 聚合与旧 ID 解析、§4.3 AttachmentVersion、
        §Data Models（actor XOR / migration identity / original_creator_unknown）
Properties: P3（创建主体完备）, P4（版本不可变/递增）, P28（迁移幂等守恒）

职责（编排层，复用既有治理表；不重造附件存储/OCR/引擎）：

M1 把既有 legacy ``attachments`` 行回填为治理聚合根 + 不可变 ``AttachmentVersion`` +
``legacy_attachment_alias``，**只补可证明字段**：

- ``byte_size`` / ``media_type`` / ``storage_type`` / ``storage_key`` 来自既有记录（可证明）。
- ``content_hash`` **不臆造**（历史行无哈希、无字节可复算 → 保持 NULL）。
- ``version_no`` 来自可证明的版本链顺序（1..N）；链不可证明则单行成根 ``version_no=1``。
- 未知 ``created_by`` → migration Service Identity（``actor_type='service'``）+
  ``original_creator_unknown=true``，**不冒充人工用户**（design §Data Models / R14.4）。
- legacy 版本链不可证明 → ``config_snapshot.legacy_unverified_chain=true``（design §8.2）。

**可恢复/可重复（R14.3 / P28）**：
- 每次上传行经 ``legacy_attachment_alias`` 存在性判定是否已回填；已回填的行跳过。
- checkpoint 按 ``(migration_version, batch_key)`` 幂等；``batch_key`` 含
  migration version / project / partition / input hash（design §8.2）。
- 重跑不新增聚合根/版本/引用/Job/Writeback，不修改历史字节与 legacy 列（legacy 列永久保留）。

纯链分析函数（``build_backfill_aggregates``）与 IO 分离，便于 PBT。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: M1 backfill 的稳定逻辑迁移版本（checkpoint batch_key 用；非 DDL 版本号）。
#: 绑定引入 attachment_versions 的迁移 V106，保证跨迁移重跑 batch_key 稳定（P28）。
BACKFILL_MIGRATION_VERSION = "V106"

#: 迁移专用 Service Identity 的稳定键（V106 seed）。
MIGRATION_IDENTITY_KEY = "migration"

#: 默认小批大小（design §8.2：按 project/year/id 小批 checkpoint）。
DEFAULT_BATCH_SIZE = 200


# ---------------------------------------------------------------------------
# 纯链分析：把 legacy attachment 行分组为可回填聚合（root + 有序版本 + 可证明性）
# ---------------------------------------------------------------------------


@dataclass
class BackfillAggregate:
    """一个可回填聚合：root 行 + 有序版本行 + legacy 版本链是否可证明。"""

    versions: list[dict]              # 有序 legacy 行（root 在 [0]，current 在 [-1]）
    unverified_chain: bool            # legacy 版本链不可证明（标 legacy_unverified_chain）

    @property
    def root(self) -> dict:
        return self.versions[0]


def _order_component(members: list[dict], member_ids: set[UUID]) -> tuple[list[dict], bool]:
    """把一个连通分量（按 previous_version_id 相连）排序并判定可证明性。

    可证明要求（design §4.1）：单一 root、线性（无分叉）、无环、全连通、
    version 严格递增、同 project 与 audit_year。任一不满足 → 不可证明。
    """
    if len(members) == 1:
        r = members[0]
        prev = r.get("previous_version_id")
        # 单行：无 prev = 可证明的独立根；prev 指向集合外（悬空）= 不可证明链。
        provable = prev is None
        return list(members), provable

    by_id = {m["id"]: m for m in members}
    ids = set(by_id)
    # root = prev 为 None 或指向分量外
    roots = [m for m in members if m.get("previous_version_id") is None or m.get("previous_version_id") not in ids]
    if len(roots) != 1:
        return list(members), False
    # 后继映射：prev_id -> [子]；分叉（>1 后继）不可证明
    succ: dict[UUID, list[dict]] = {}
    for m in members:
        p = m.get("previous_version_id")
        if p in ids:
            succ.setdefault(p, []).append(m)
    if any(len(v) > 1 for v in succ.values()):
        return list(members), False
    # 从 root 线性游走
    ordered: list[dict] = []
    seen: set[UUID] = set()
    cur: dict | None = roots[0]
    while cur is not None:
        if cur["id"] in seen:  # 环
            return list(members), False
        seen.add(cur["id"])
        ordered.append(cur)
        nxt = succ.get(cur["id"])
        cur = nxt[0] if nxt else None
    if len(ordered) != len(members):  # 未全连通
        return list(members), False
    # 同 scope + version 严格递增
    proj = ordered[0].get("project_id")
    yr = ordered[0].get("audit_year")
    last_v: int | None = None
    for m in ordered:
        if m.get("project_id") != proj or m.get("audit_year") != yr:
            return list(members), False
        v = m.get("version")
        if v is not None:
            if last_v is not None and v <= last_v:
                return list(members), False
            last_v = v
    return ordered, True


def build_backfill_aggregates(rows: list[dict]) -> list[BackfillAggregate]:
    """把待回填 legacy 行分组为聚合（纯函数，无 IO；便于 PBT）。

    - 按 ``previous_version_id`` 求连通分量（仅计集合内的链接）。
    - 可证明分量 → 单个多版本聚合。
    - 不可证明分量（分叉/环/悬空/跨 scope/version 乱序）→ 拆为每行独立单版本聚合，
      标记 ``unverified_chain=True``（不臆造链关系）。
    """
    if not rows:
        return []
    by_id = {r["id"]: r for r in rows}
    id_set = set(by_id)

    # union-find（仅合并集合内 prev 链接）
    parent: dict[UUID, UUID] = {rid: rid for rid in id_set}

    def find(x: UUID) -> UUID:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: UUID, b: UUID) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for r in rows:
        p = r.get("previous_version_id")
        if p is not None and p in id_set:
            union(r["id"], p)

    comps: dict[UUID, list[dict]] = {}
    for rid in id_set:
        comps.setdefault(find(rid), []).append(by_id[rid])

    aggregates: list[BackfillAggregate] = []
    for members in comps.values():
        ordered, provable = _order_component(members, id_set)
        if provable:
            aggregates.append(BackfillAggregate(versions=ordered, unverified_chain=False))
        else:
            # 不可证明：每行独立单版本聚合，标记 unverified（保守，不臆造链）。
            for m in sorted(members, key=lambda x: str(x["id"])):
                aggregates.append(BackfillAggregate(versions=[m], unverified_chain=True))
    # 稳定排序：按 root id
    aggregates.sort(key=lambda a: str(a.root["id"]))
    return aggregates


def compute_input_hash(attachment_ids: list[UUID]) -> str:
    """batch 的 input hash = 排序后 attachment id 的 SHA-256（可复算，幂等 batch_key）。"""
    h = hashlib.sha256()
    for aid in sorted(str(a) for a in attachment_ids):
        h.update(aid.encode("ascii"))
        h.update(b"|")
    return h.hexdigest()


def build_batch_key(project_id: UUID, audit_year: int | None, partition: str, input_hash: str) -> str:
    """batch_key = migration version / project / audit_year / partition / input hash（design §8.2）。"""
    return f"{BACKFILL_MIGRATION_VERSION}:{project_id}:{audit_year if audit_year is not None else '-'}:{partition}:{input_hash}"


def _opaque_storage_key(row: dict) -> str | None:
    """从 legacy 行推导内部 opaque storage_key（可证明；绝不返回原始绝对路径给客户端）。

    - paperless 存储 → paperless_document_id（内部键）。
    - 其它 → 既有 file_path（内部存储键；响应层永不裸返回，见 SecureAttachmentGateway）。
    """
    storage_type = (row.get("storage_type") or "").lower()
    if storage_type == "paperless" and row.get("paperless_document_id") is not None:
        return f"paperless:{row['paperless_document_id']}"
    fp = row.get("file_path")
    return str(fp) if fp else None


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------


@dataclass
class BackfillReport:
    project_id: str
    audit_year: int | None = None
    scanned: int = 0                      # 扫描到的待回填 legacy 行
    aggregates: int = 0                   # 聚合数
    versions_created: int = 0             # 新建 AttachmentVersion 数
    aliases_created: int = 0              # 新建 legacy_attachment_alias 数
    roots_updated: int = 0                # 设置 current_version/actor 的根 attachment 数
    unverified_chains: int = 0            # 标记 legacy_unverified_chain 的聚合数
    unknown_creator: int = 0             # 未知 creator（用 migration identity）行数
    skipped_no_audit_year: int = 0        # audit_year 未知 → 跳过（不臆造）
    skipped_existing: int = 0             # 已回填（alias 存在）→ 跳过（幂等）
    checkpoints_done: int = 0
    checkpoints_skipped: int = 0
    batches: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "audit_year": self.audit_year,
            "scanned": self.scanned,
            "aggregates": self.aggregates,
            "versions_created": self.versions_created,
            "aliases_created": self.aliases_created,
            "roots_updated": self.roots_updated,
            "unverified_chains": self.unverified_chains,
            "unknown_creator": self.unknown_creator,
            "skipped_no_audit_year": self.skipped_no_audit_year,
            "skipped_existing": self.skipped_existing,
            "checkpoints_done": self.checkpoints_done,
            "checkpoints_skipped": self.checkpoints_skipped,
            "batch_count": len(self.batches),
            "batches": self.batches,
        }


class EvidenceBackfillRunner:
    """M1 checkpoint backfill 编排器（可恢复/可重复；runner 显式 commit）。"""

    def __init__(self, db: AsyncSession, *, batch_size: int = DEFAULT_BATCH_SIZE):
        self.db = db
        self.batch_size = max(1, int(batch_size))
        self._migration_svc_id: UUID | None = None

    # -- migration Service Identity ------------------------------------------

    async def _get_migration_identity(self) -> UUID:
        if self._migration_svc_id is None:
            from app.models.evidence_governance_models import ServiceIdentity

            sid = (
                await self.db.execute(
                    sa.select(ServiceIdentity.id).where(
                        ServiceIdentity.identity_key == MIGRATION_IDENTITY_KEY
                    )
                )
            ).scalar_one_or_none()
            if sid is None:
                raise RuntimeError(
                    "migration Service Identity 未 seed（V106）；无法安全回填未知创建者"
                )
            self._migration_svc_id = sid
        return self._migration_svc_id

    # -- 装载待回填 legacy 行（无 alias = 未回填；幂等真源） -------------------

    async def _load_pending(self, project_id: UUID, audit_year: int | None) -> list[dict]:
        """加载 project(+year) 下尚无 alias 的非删除 legacy attachment 行。"""
        from app.models.attachment_models import Attachment
        from app.models.evidence_governance_models import LegacyAttachmentAlias

        conds = [
            Attachment.project_id == project_id,
            Attachment.is_deleted == sa.false(),
        ]
        if audit_year is not None:
            conds.append(Attachment.audit_year == audit_year)
        stmt = (
            sa.select(
                Attachment.id,
                Attachment.project_id,
                Attachment.audit_year,
                Attachment.version,
                Attachment.previous_version_id,
                Attachment.created_by,
                Attachment.file_size,
                Attachment.file_type,
                Attachment.storage_type,
                Attachment.file_path,
                Attachment.paperless_document_id,
                Attachment.current_version_id,
            )
            .select_from(Attachment)
            .outerjoin(
                LegacyAttachmentAlias,
                LegacyAttachmentAlias.old_attachment_id == Attachment.id,
            )
            .where(*conds, LegacyAttachmentAlias.old_attachment_id.is_(None))
            .order_by(Attachment.id)
        )
        rows = (await self.db.execute(stmt)).mappings().all()
        return [dict(r) for r in rows]

    # -- checkpoint upsert（幂等 batch_key） --------------------------------

    async def _claim_checkpoint(
        self, project_id: UUID, audit_year: int | None, partition: str, input_hash: str
    ) -> tuple[UUID | None, bool]:
        """按 (migration_version, batch_key) upsert checkpoint。

        返回 (checkpoint_id, should_process)。已 ``done`` 的相同 batch_key → should_process=False。
        """
        from app.models.evidence_governance_models import EvidenceMigrationCheckpoint

        batch_key = build_batch_key(project_id, audit_year, partition, input_hash)
        svc_id = await self._get_migration_identity()
        existing = (
            await self.db.execute(
                sa.select(
                    EvidenceMigrationCheckpoint.id,
                    EvidenceMigrationCheckpoint.status,
                ).where(
                    EvidenceMigrationCheckpoint.migration_version == BACKFILL_MIGRATION_VERSION,
                    EvidenceMigrationCheckpoint.batch_key == batch_key,
                )
            )
        ).first()
        if existing is not None:
            cp_id, status = existing
            if status == "done":
                return cp_id, False
            # 恢复：running/pending/failed → 重新置 running 继续
            await self.db.execute(
                sa.update(EvidenceMigrationCheckpoint)
                .where(EvidenceMigrationCheckpoint.id == cp_id)
                .values(status="running", updated_at=sa.func.now())
            )
            return cp_id, True
        cp_id = uuid4()
        await self.db.execute(
            sa.insert(EvidenceMigrationCheckpoint).values(
                id=cp_id,
                migration_version=BACKFILL_MIGRATION_VERSION,
                batch_key=batch_key,
                project_id=project_id,
                audit_year=audit_year,
                partition_key=partition,
                input_hash=input_hash,
                status="running",
                processed_count=0,
                actor_type="service",
                actor_service_identity_id=svc_id,
            )
        )
        return cp_id, True

    async def _finish_checkpoint(self, cp_id: UUID, processed: int) -> None:
        from app.models.evidence_governance_models import EvidenceMigrationCheckpoint

        await self.db.execute(
            sa.update(EvidenceMigrationCheckpoint)
            .where(EvidenceMigrationCheckpoint.id == cp_id)
            .values(status="done", processed_count=processed, updated_at=sa.func.now())
        )

    # -- 单聚合回填 ----------------------------------------------------------

    async def _backfill_aggregate(self, agg: BackfillAggregate, report: BackfillReport) -> int:
        """回填一个聚合：创建有序 AttachmentVersion + alias + 更新根 attachment。

        返回本聚合创建的 version 数。audit_year 未知的根 → 跳过（不臆造 alias NOT NULL）。
        """
        from app.models.attachment_models import Attachment
        from app.models.evidence_governance_models import AttachmentVersion, LegacyAttachmentAlias

        root = agg.root
        root_id = root["id"]
        project_id = root["project_id"]
        audit_year = root["audit_year"]
        svc_id = await self._get_migration_identity()

        if audit_year is None:
            # alias.audit_year NOT NULL；无法证明 scope → 保守跳过（不臆造）。
            report.skipped_no_audit_year += len(agg.versions)
            return 0

        created = 0
        prev_av_id: UUID | None = None
        last_av_id: UUID | None = None
        n = len(agg.versions)
        for idx, vrow in enumerate(agg.versions):
            legacy_version = vrow.get("version")
            created_by = vrow.get("created_by")
            unknown = created_by is None
            if unknown:
                report.unknown_creator += 1
            actor_type = "user" if not unknown else "service"

            av_id = uuid4()
            await self.db.execute(
                sa.insert(AttachmentVersion).values(
                    id=av_id,
                    attachment_id=root_id,        # 聚合根 id（链折叠到 root）
                    project_id=project_id,
                    audit_year=audit_year,        # 用根 scope（可证明链同 scope）
                    version_no=idx + 1,           # 由可证明顺序派生（严格递增，P4）
                    storage_type=vrow.get("storage_type") or "paperless",
                    storage_key=_opaque_storage_key(vrow),
                    media_type=vrow.get("file_type"),      # 可证明（既有记录）
                    byte_size=vrow.get("file_size"),       # 可证明
                    content_hash=None,                     # 不臆造（无字节可复算）
                    config_snapshot={
                        "backfill": {
                            "phase": "M1",
                            "source": "legacy_attachment",
                            "legacy_attachment_id": str(vrow["id"]),
                            "legacy_version": legacy_version,
                            "legacy_unverified_chain": agg.unverified_chain,
                        }
                    },
                    availability="available",
                    previous_version_id=prev_av_id,
                    actor_type=actor_type,
                    actor_user_id=created_by if not unknown else None,
                    actor_service_identity_id=svc_id if unknown else None,
                    original_creator_unknown=unknown,
                )
            )
            # alias：每个 legacy 行 → (root, 本版本, resolution_kind)
            if n == 1 or idx == 0:
                resolution_kind = "root"
            elif idx == n - 1:
                resolution_kind = "current_version"
            else:
                resolution_kind = "historical_version"
            await self.db.execute(
                sa.insert(LegacyAttachmentAlias).values(
                    old_attachment_id=vrow["id"],
                    attachment_id=root_id,
                    attachment_version_id=av_id,
                    project_id=project_id,
                    audit_year=audit_year,
                    resolution_kind=resolution_kind,
                )
            )
            report.aliases_created += 1
            prev_av_id = av_id
            last_av_id = av_id
            created += 1

        if agg.unverified_chain:
            report.unverified_chains += 1

        # 更新根 attachment：actor + current_version（仅未设置时；legacy 列不动）。
        root_created_by = root.get("created_by")
        root_unknown = root_created_by is None
        await self.db.execute(
            sa.update(Attachment)
            .where(Attachment.id == root_id, Attachment.current_version_id.is_(None))
            .values(
                current_version_id=last_av_id,
                actor_type="user" if not root_unknown else "service",
                actor_user_id=root_created_by if not root_unknown else None,
                actor_service_identity_id=svc_id if root_unknown else None,
                original_creator_unknown=root_unknown,
                updated_at=sa.func.now(),
            )
        )
        report.roots_updated += 1
        return created

    # -- 主入口：显式 commit（可恢复/可重复） --------------------------------

    async def run(
        self,
        project_id: UUID,
        *,
        audit_year: int | None = None,
        commit: bool = True,
    ) -> BackfillReport:
        """执行一次 M1 checkpoint backfill；返回 coverage/idempotency 报告。

        小批 checkpoint（batch_size 聚合/批）；每批一个幂等 checkpoint。runner 显式 commit
        （每批提交，确保 deferrable 约束触发器在批边界校验 + 断点续跑）。
        """
        report = BackfillReport(project_id=str(project_id), audit_year=audit_year)
        pending = await self._load_pending(project_id, audit_year)
        report.scanned = len(pending)
        if not pending:
            if commit:
                await self.db.commit()
            return report

        aggregates = build_backfill_aggregates(pending)
        report.aggregates = len(aggregates)

        # 小批：每 batch_size 个聚合一个 checkpoint（按 root id 稳定切批）。
        for start in range(0, len(aggregates), self.batch_size):
            batch = aggregates[start : start + self.batch_size]
            member_ids = [v["id"] for agg in batch for v in agg.versions]
            input_hash = compute_input_hash(member_ids)
            partition = f"p{start // self.batch_size:04d}"
            # 该批 scope：若单一 year 则用之，否则用根 year（scope 已按 project 过滤）。
            batch_year = audit_year if audit_year is not None else batch[0].root.get("audit_year")
            cp_id, should = await self._claim_checkpoint(project_id, batch_year, partition, input_hash)
            batch_info = {
                "partition": partition,
                "input_hash": input_hash,
                "aggregates": len(batch),
                "processed": should,
            }
            if not should:
                report.checkpoints_skipped += 1
                report.skipped_existing += len(member_ids)
                report.batches.append(batch_info)
                continue
            processed = 0
            for agg in batch:
                processed += await self._backfill_aggregate(agg, report)
            report.versions_created += processed
            if cp_id is not None:
                await self._finish_checkpoint(cp_id, processed)
            report.checkpoints_done += 1
            report.batches.append(batch_info)
            if commit:
                await self.db.commit()

        if commit:
            await self.db.commit()

        logger.info(
            "evidence M1 backfill project=%s year=%s scanned=%d aggregates=%d versions=%d "
            "aliases=%d unverified=%d unknown_creator=%d skipped_no_year=%d cp_done=%d cp_skip=%d",
            project_id,
            audit_year,
            report.scanned,
            report.aggregates,
            report.versions_created,
            report.aliases_created,
            report.unverified_chains,
            report.unknown_creator,
            report.skipped_no_audit_year,
            report.checkpoints_done,
            report.checkpoints_skipped,
        )
        return report
