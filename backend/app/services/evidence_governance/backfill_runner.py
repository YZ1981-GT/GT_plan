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


@dataclass
class ExistingVersionAssessment:
    """既有治理版本与 legacy 根行的安全兼容判定。"""

    safe: bool
    reason: str = ""
    target_version_id: UUID | None = None
    resolution_kind: str | None = None


def assess_existing_version_chain(
    root: dict, versions: list[dict],
) -> ExistingVersionAssessment | None:
    """判定既有版本能否只补 alias，绝不重复创建版本。

    返回 ``None`` 表示该根尚无治理版本，应走正常 M1 创建路径；有版本但
    链条、scope、current 指针或 legacy version 不一致时返回不安全判定，
    由生产 apply 预检阻断，避免静默改写历史链。
    """

    if not versions:
        return None
    ordered = sorted(versions, key=lambda row: int(row["version_no"]))
    expected_numbers = list(range(1, len(ordered) + 1))
    actual_numbers = [int(row["version_no"]) for row in ordered]
    if actual_numbers != expected_numbers:
        return ExistingVersionAssessment(False, "version_no 非连续")
    project_id = root["project_id"]
    audit_year = root.get("audit_year")
    if any(row["project_id"] != project_id or row["audit_year"] != audit_year for row in ordered):
        return ExistingVersionAssessment(False, "既有版本 scope 与附件根不一致")
    for previous, current in zip(ordered, ordered[1:]):
        if current.get("previous_version_id") != previous["id"]:
            return ExistingVersionAssessment(False, "既有版本 previous_version_id 链不一致")
    current_id = root.get("current_version_id")
    if current_id != ordered[-1]["id"]:
        return ExistingVersionAssessment(False, "current_version_id 未指向最高版本")
    if ordered[-1].get("availability") != "available":
        return ExistingVersionAssessment(False, "current 版本不是 available")
    legacy_version = root.get("version")
    if legacy_version is not None and int(legacy_version) != len(ordered):
        return ExistingVersionAssessment(False, "legacy version 与既有版本链长度不一致")
    return ExistingVersionAssessment(
        True,
        target_version_id=ordered[-1]["id"],
        resolution_kind="root" if len(ordered) == 1 else "current_version",
    )


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
    alias_only_roots: int = 0
    aliases_planned: int = 0
    versions_planned: int = 0
    blocked_existing_roots: int = 0
    blocked_reasons: list[dict] = field(default_factory=list)
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
            "alias_only_roots": self.alias_only_roots,
            "aliases_planned": self.aliases_planned,
            "versions_planned": self.versions_planned,
            "blocked_existing_roots": self.blocked_existing_roots,
            "blocked_reasons": self.blocked_reasons,
            "batch_count": len(self.batches),
            "batches": self.batches,
        }


class EvidenceBackfillRunner:
    """M1 checkpoint backfill 编排器（可恢复/可重复；runner 显式 commit）。"""

    def __init__(self, db: AsyncSession, *, batch_size: int = DEFAULT_BATCH_SIZE):
        self.db = db
        self.batch_size = max(1, int(batch_size))
        self._migration_svc_id: UUID | None = None
        self._existing_versions: dict[UUID, list[dict]] = {}
        self._existing_assessments: dict[UUID, ExistingVersionAssessment | None] = {}

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

    async def _preflight_existing_versions(
        self, aggregates: list[BackfillAggregate], report: BackfillReport,
    ) -> None:
        """一次性读取既有版本链，apply 前先发现所有阻断，不边写边撞 FK。"""

        from app.models.evidence_governance_models import AttachmentVersion

        self._existing_versions.clear()
        self._existing_assessments.clear()
        for aggregate in aggregates:
            root = aggregate.root
            root_id = root["id"]
            rows = (
                await self.db.execute(
                    sa.select(
                        AttachmentVersion.id,
                        AttachmentVersion.project_id,
                        AttachmentVersion.audit_year,
                        AttachmentVersion.version_no,
                        AttachmentVersion.previous_version_id,
                        AttachmentVersion.availability,
                    )
                    .where(AttachmentVersion.attachment_id == root_id)
                    .order_by(AttachmentVersion.version_no)
                )
            ).mappings().all()
            existing = [dict(row) for row in rows]
            assessment = assess_existing_version_chain(root, existing)
            self._existing_versions[root_id] = existing
            self._existing_assessments[root_id] = assessment
            if assessment is not None and not assessment.safe:
                report.blocked_existing_roots += 1
                report.blocked_reasons.append(
                    {"attachment_id": str(root_id), "reason": assessment.reason}
                )
            elif assessment is not None and len(aggregate.versions) != 1:
                report.blocked_existing_roots += 1
                report.blocked_reasons.append(
                    {
                        "attachment_id": str(root_id),
                        "reason": "既有版本链与多条 legacy 链无法安全一一映射",
                    }
                )

    async def _checkpoint_done(self, batch_key: str) -> bool:
        """dry-run 只读检查已有完成 checkpoint，不创建或更新 checkpoint。"""

        from app.models.evidence_governance_models import EvidenceMigrationCheckpoint

        return bool(
            await self.db.scalar(
                sa.select(EvidenceMigrationCheckpoint.id).where(
                    EvidenceMigrationCheckpoint.migration_version == BACKFILL_MIGRATION_VERSION,
                    EvidenceMigrationCheckpoint.batch_key == batch_key,
                    EvidenceMigrationCheckpoint.status == "done",
                )
            )
        )


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

    async def _backfill_aggregate(
        self, agg: BackfillAggregate, report: BackfillReport, *, dry_run: bool = False,
    ) -> int:
        """回填一个聚合；既有治理版本只补 alias，不重复插入版本。"""
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

        existing_assessment = self._existing_assessments.get(root_id)
        if existing_assessment is not None:
            if not existing_assessment.safe:
                return 0  # apply 前置检查已记录阻断原因
            if len(agg.versions) != 1:
                return 0  # 既有链与多条 legacy 链的映射需人工复核
            report.alias_only_roots += 1
            report.aliases_planned += 1
            if dry_run:
                return 0
            await self.db.execute(
                sa.insert(LegacyAttachmentAlias).values(
                    old_attachment_id=root_id,
                    attachment_id=root_id,
                    attachment_version_id=existing_assessment.target_version_id,
                    project_id=project_id,
                    audit_year=audit_year,
                    resolution_kind=existing_assessment.resolution_kind,
                )
            )
            report.aliases_created += 1
            return 0

        created = 0
        prev_av_id: UUID | None = None
        last_av_id: UUID | None = None
        n = len(agg.versions)
        if dry_run:
            report.versions_planned += n
            report.aliases_planned += n
            report.unverified_chains += int(agg.unverified_chain)
            report.unknown_creator += sum(
                1 for vrow in agg.versions if vrow.get("created_by") is None
            )
            return 0
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
        dry_run: bool = False,
    ) -> BackfillReport:
        """执行或预览一次 M1 checkpoint backfill。

        ``dry_run=True`` 只读扫描并生成计划，不创建 checkpoint/version/alias；
        ``commit=False`` 保留旧的事务演练语义，由调用方负责 rollback。apply
        前会先完成全部既有版本链预检，任何阻断都不会开始分批写入。
        """
        if dry_run and commit:
            raise ValueError("dry_run 不能与 commit=True 同时使用")
        report = BackfillReport(project_id=str(project_id), audit_year=audit_year)
        pending = await self._load_pending(project_id, audit_year)
        report.scanned = len(pending)
        if not pending:
            if commit:
                await self.db.commit()
            return report

        aggregates = build_backfill_aggregates(pending)
        report.aggregates = len(aggregates)
        await self._preflight_existing_versions(aggregates, report)
        if report.blocked_existing_roots and not dry_run:
            raise RuntimeError(
                "backfill 预检阻断：既有版本链不能安全映射 alias；"
                f" reasons={report.blocked_reasons!r}"
            )

        # 小批：每 batch_size 个聚合一个 checkpoint（按 root id 稳定切批）。
        for start in range(0, len(aggregates), self.batch_size):
            batch = aggregates[start : start + self.batch_size]
            member_ids = [v["id"] for agg in batch for v in agg.versions]
            input_hash = compute_input_hash(member_ids)
            partition = f"p{start // self.batch_size:04d}"
            # 该批 scope：若单一 year 则用之，否则用根 year（scope 已按 project 过滤）。
            batch_year = audit_year if audit_year is not None else batch[0].root.get("audit_year")
            batch_key = build_batch_key(project_id, batch_year, partition, input_hash)
            if dry_run:
                cp_id = None
                should = not await self._checkpoint_done(batch_key)
            else:
                cp_id, should = await self._claim_checkpoint(
                    project_id, batch_year, partition, input_hash
                )
            batch_info = {
                "partition": partition,
                "input_hash": input_hash,
                "aggregates": len(batch),
                "processed": should,
                "dry_run": dry_run,
            }
            if not should:
                report.checkpoints_skipped += 1
                report.skipped_existing += len(member_ids)
                report.batches.append(batch_info)
                continue
            processed = 0
            for agg in batch:
                processed += await self._backfill_aggregate(
                    agg, report, dry_run=dry_run
                )
            report.versions_created += processed
            if cp_id is not None:
                await self._finish_checkpoint(cp_id, processed)
            if not dry_run:
                report.checkpoints_done += 1
            report.batches.append(batch_info)
            if commit and not dry_run:
                await self.db.commit()

        if commit and not dry_run:
            await self.db.commit()

        logger.info(
            "evidence M1 backfill project=%s year=%s dry_run=%s scanned=%d aggregates=%d versions=%d "
            "planned_versions=%d aliases=%d planned_aliases=%d alias_only=%d blocked=%d "
            "unverified=%d unknown_creator=%d skipped_no_year=%d cp_done=%d cp_skip=%d",
            project_id,
            audit_year,
            dry_run,
            report.scanned,
            report.aggregates,
            report.versions_created,
            report.versions_planned,
            report.aliases_created,
            report.aliases_planned,
            report.alias_only_roots,
            report.blocked_existing_roots,
            report.unverified_chains,
            report.unknown_creator,
            report.skipped_no_audit_year,
            report.checkpoints_done,
            report.checkpoints_skipped,
        )
        return report
