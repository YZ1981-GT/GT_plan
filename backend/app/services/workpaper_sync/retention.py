# -*- coding: utf-8 -*-
"""版本化 `RetentionPolicyService`：dry-run → 二次引用复核 → 逐对象删除审计。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 11
Requirements: 5.11, 9.6, 9.7, 10.7, 10.8
Properties: P5 / P17

═══ 为什么必须「dry-run + 二次查引用 + 不确定即保留」三件一起 ═══

GC 是本 spec 里唯一**主动删文件**的路径，而文件系统与 PostgreSQL 不是同一事务
（Task 7 db2/db6）。于是：

* **只有 dry-run 而没有二次复核** ⇒ 计划与执行之间的空窗里新出现的引用（新 application
  绑定了这个 durable incoming、新 representation 引用了这个 artifact）会被删掉，
  表现为「pointer 指向缺失 artifact」—— 正是 Requirement 5.9 禁止的半成功态；
* **只有二次复核而没有 dry-run** ⇒ 无法在删之前审阅清单，Requirement 5.11 要求
  「策略必须有版本、dry-run、引用复核与删除结果证据」；
* **不确定时不保留** ⇒ 任何一处 FK 忘了登记就等于静默删除生产数据。

因此 :attr:`REFERENCE_SOURCES` 是**声明式清单 + 守卫双向锁死**：守卫从 V151 DDL 里抓出
所有引用 `working_paper_artifact(id)` 的列，与本清单比对，多一列少一列都打红。将来新增
迁移加了新 FK 而忘了登记，CI 立刻红 —— 而不是等到某天 GC 把还在用的文件删掉。

═══ 审计为什么落成内容寻址 evidence artifact ═══

「逐对象删除审计」必须持久化且不可被下一轮 GC 抹掉。这里把每轮判定清单序列化成 JSON，
按 `retention_class='retention_audit'` + `legal_hold=true` 内容寻址发布 ——
`retention_audit` 类在策略里 `deletable=false`，形成自证闭环。
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import WorkpaperArtifact
from app.services.workpaper_sync.artifacts import (
    ArtifactPathError,
    CanonicalArtifactRepository,
    FileInUseError,
)
from app.services.workpaper_sync.models import ArtifactState, SyncDomainError

#: 策略配置真源。
RETENTION_CONFIG_PATH: Final[Path] = (
    Path(__file__).resolve().parents[3] / "data" / "workpaper_sync_retention_policy.json"
)


class RetentionConfigError(SyncDomainError):
    """策略配置缺失/非法。**不 fallback** —— 无策略必须表现为「全部保留 + 告警」，
    而不是「按某个内置默认值删」。"""

    error_code = "retention_config_invalid"


class RetentionUsageError(SyncDomainError):
    """调用协议违规（例如未先 dry-run 就 apply、跨 scope 传 plan）。"""

    error_code = "retention_usage_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 引用来源声明（与 V151 DDL 双向锁死）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ReferenceSource:
    """一处「可能引用 artifact」的表/列。"""

    table: str
    column: str
    why: str


#: 🔴 单一真源：所有引用 `working_paper_artifact(id)` 的列。
#: 守卫 `test_reference_sources_match_v151_ddl` 从迁移文本反向抓取并双向比对。
REFERENCE_SOURCES: Final[tuple[ReferenceSource, ...]] = (
    ReferenceSource(
        "working_paper_sync_definition_artifact", "blob_artifact_id",
        "immutable definition 的字节本体；历史 operation/retry 按 digest 只读它",
    ),
    ReferenceSource(
        "working_paper_sync_definition_bundle", "canonical_payload_artifact_id",
        "bundle canonical bytes；bundle digest 的可复算来源",
    ),
    ReferenceSource(
        "working_paper_content_version", "projection_artifact_id",
        "业务 projection 权威字节",
    ),
    ReferenceSource(
        "working_paper_content_version", "authoritative_artifact_id",
        "custom 底稿的 xlsx 本体权威字节",
    ),
    ReferenceSource(
        "working_paper_content_representation", "artifact_id",
        "published representation 的 OOXML 本体（resolver 唯一读路径）",
    ),
    ReferenceSource(
        "working_paper_representation_upgrade_candidate", "staged_artifact_id",
        "non-current candidate 的 staged 字节；rollback target 也引用它",
    ),
    ReferenceSource(
        "working_paper_pending_mutation", "payload_artifact_id",
        "HTML flush 的 pending mutation 载荷",
    ),
    ReferenceSource(
        "working_paper_content_application", "incoming_artifact_id",
        "application 固定的 durable incoming substrate",
    ),
    ReferenceSource(
        "working_paper_callback_recovery_case", "incoming_artifact_id",
        "recovery case 的 durable incoming（claim 或 download-only 都要读它）",
    ),
    ReferenceSource(
        "working_paper_callback_delivery", "incoming_artifact_id",
        "delivery 证据链",
    ),
    ReferenceSource(
        "working_paper_sync_test_run", "run_manifest_artifact_id",
        "test run manifest（evidence 服务端重算的输入）",
    ),
    ReferenceSource(
        "working_paper_entry_evidence_scenario", "trace_bundle_artifact_id",
        "逐 scenario trace bundle",
    ),
)

#: operation 的非终态集合（in-flight ⇒ 保留）。与 `models.OperationState` 的 terminal 对齐。
_IN_FLIGHT_OPERATION_STATES: Final[tuple[str, ...]] = (
    "created", "command_pending", "accepted", "waiting_application",
    "application_bound", "extracting", "merging", "conflict",
    "rematerializing", "applying", "error",
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 策略模型
# ═══════════════════════════════════════════════════════════════════════════

_AGE_ANCHORS: Final[frozenset[str]] = frozenset(
    {"created_at", "published_at", "durable_at", "quarantined_at", "orphaned_at"}
)


@dataclass(frozen=True)
class RetentionClass:
    """一个 artifact class 的保留规则。"""

    retention_class: str
    sensitivity: str
    applies_to_kinds: frozenset[str]
    applies_to_states: frozenset[str]
    age_anchor: str
    ttl_hours: int
    grace_hours: int
    deletable: bool
    honor_legal_hold: bool
    requires_orphaned_at: bool
    access_roles: tuple[str, ...]


@dataclass(frozen=True)
class RetentionPolicy:
    """版本化策略快照（进审计与 evidence）。"""

    policy_id: str
    policy_version: str
    schema_version: int
    dry_run_required_before_apply: bool
    second_reference_recheck_required: bool
    retain_on_uncertainty: bool
    alert_retain_reasons: frozenset[str]
    classes: dict[str, RetentionClass]

    def klass(self, name: str) -> RetentionClass | None:
        return self.classes.get(name)


@dataclass
class RetentionDecision:
    """逐对象判定（进审计清单）。"""

    artifact_id: str
    relative_path: str
    kind: str
    state: str
    retention_class: str
    sensitivity: str
    decision: str
    reason: str
    legal_hold: bool
    age_hours: float | None
    ttl_hours: int | None
    grace_hours: int | None
    access_roles: tuple[str, ...]
    referenced_by: tuple[str, ...] = ()
    alert: bool = False


@dataclass
class RetentionPlan:
    """dry-run 结果。**永不删除任何文件**。"""

    policy_version: str
    project_id: str
    wp_id: str
    planned_at: str
    dry_run: bool = True
    decisions: list[RetentionDecision] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    audit_relative_path: str | None = None
    audit_sha256: str | None = None

    @property
    def deletions(self) -> list[RetentionDecision]:
        return [d for d in self.decisions if d.decision == "delete"]


@dataclass
class RetentionOutcome:
    """apply 结果：逐对象二次复核后的最终判定。"""

    policy_version: str
    project_id: str
    wp_id: str
    applied_at: str
    dry_run: bool = False
    deleted: list[RetentionDecision] = field(default_factory=list)
    retained_on_recheck: list[RetentionDecision] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    audit_relative_path: str | None = None
    audit_sha256: str | None = None


_CACHE: dict[str, Any] = {"mtime": None, "value": None}
_LOCK = threading.Lock()


def _parse_policy(raw: dict[str, Any]) -> RetentionPolicy:
    for key in ("policy_id", "policy_version", "schema_version", "classes", "invariants"):
        if key not in raw:
            raise RetentionConfigError(f"retention 策略缺少必填键 {key!r}")
    inv = raw["invariants"]
    if not isinstance(inv, dict):
        raise RetentionConfigError("retention 策略的 invariants 必须是对象")
    for flag in (
        "dry_run_required_before_apply", "dry_run_never_deletes",
        "second_reference_recheck_required", "retain_on_uncertainty",
        "audit_row_per_object", "audit_persists_dry_run_flag",
    ):
        if inv.get(flag) is not True:
            raise RetentionConfigError(
                f"retention 策略的 invariants.{flag} 必须显式为 true —— "
                "这些不变式不是可选项（Requirement 5.11）"
            )
    classes_raw = raw["classes"]
    if not isinstance(classes_raw, dict) or not classes_raw:
        raise RetentionConfigError("retention 策略的 classes 必须是非空对象")

    classes: dict[str, RetentionClass] = {}
    for name, body in classes_raw.items():
        if not isinstance(body, dict):
            raise RetentionConfigError(f"retention class {name!r} 必须是对象")
        anchor = str(body.get("age_anchor", ""))
        if anchor not in _AGE_ANCHORS:
            raise RetentionConfigError(
                f"retention class {name!r} 的 age_anchor={anchor!r} 非法"
                f"（允许 {sorted(_AGE_ANCHORS)}）"
            )
        for flag in ("deletable", "honor_legal_hold", "requires_orphaned_at"):
            if not isinstance(body.get(flag), bool):
                raise RetentionConfigError(f"retention class {name!r}.{flag} 必须是布尔值")
        for num in ("ttl_hours", "grace_hours"):
            value = body.get(num)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise RetentionConfigError(
                    f"retention class {name!r}.{num} 必须是非负整数，实得 {value!r}"
                )
        kinds = body.get("applies_to_kinds") or []
        states = body.get("applies_to_states") or []
        if not kinds or not states:
            raise RetentionConfigError(
                f"retention class {name!r} 必须声明非空 applies_to_kinds / applies_to_states"
            )
        roles = body.get("access_roles") or []
        if not roles:
            raise RetentionConfigError(
                f"retention class {name!r} 必须声明 access_roles（Requirement 10.7 最小权限）"
            )
        classes[str(name)] = RetentionClass(
            retention_class=str(name),
            sensitivity=str(body.get("sensitivity") or ""),
            applies_to_kinds=frozenset(str(k) for k in kinds),
            applies_to_states=frozenset(str(s) for s in states),
            age_anchor=anchor,
            ttl_hours=int(body["ttl_hours"]),
            grace_hours=int(body["grace_hours"]),
            deletable=bool(body["deletable"]),
            honor_legal_hold=bool(body["honor_legal_hold"]),
            requires_orphaned_at=bool(body["requires_orphaned_at"]),
            access_roles=tuple(str(r) for r in roles),
        )
        if not classes[str(name)].sensitivity:
            raise RetentionConfigError(f"retention class {name!r} 缺 sensitivity（敏感级别）")

    alerts = raw.get("alert_retain_reasons") or []
    if not alerts:
        raise RetentionConfigError(
            "retention 策略必须声明 alert_retain_reasons —— 『不确定即保留告警』的告警集合"
            "不能由代码硬编码"
        )
    return RetentionPolicy(
        policy_id=str(raw["policy_id"]),
        policy_version=str(raw["policy_version"]),
        schema_version=int(raw["schema_version"]),
        dry_run_required_before_apply=True,
        second_reference_recheck_required=True,
        retain_on_uncertainty=True,
        alert_retain_reasons=frozenset(str(a) for a in alerts),
        classes=classes,
    )


def load_retention_policy(path: Path | None = None, *, force: bool = False) -> RetentionPolicy:
    """读取（mtime 缓存）版本化 retention 策略。缺失/非法抛异常，不 fallback。"""
    target = path or RETENTION_CONFIG_PATH
    if path is not None or force:
        return _parse_policy(_read_json(target))
    with _LOCK:
        try:
            mtime = target.stat().st_mtime_ns
        except OSError as exc:
            raise RetentionConfigError(f"retention 策略不可读: {target}") from exc
        if _CACHE["mtime"] != mtime or _CACHE["value"] is None:
            _CACHE["value"] = _parse_policy(_read_json(target))
            _CACHE["mtime"] = mtime
        value = _CACHE["value"]
    assert isinstance(value, RetentionPolicy)
    return value


def _read_json(target: Path) -> dict[str, Any]:
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RetentionConfigError(f"retention 策略不存在: {target}") from exc
    except json.JSONDecodeError as exc:
        raise RetentionConfigError(f"retention 策略不是合法 JSON: {target} ({exc})") from exc
    if not isinstance(raw, dict):
        raise RetentionConfigError(f"retention 策略根必须是对象: {target}")
    return raw


# ═══════════════════════════════════════════════════════════════════════════
# 3. 服务
# ═══════════════════════════════════════════════════════════════════════════


class RetentionPolicyService:
    """按 class/敏感级别/TTL/grace/access/legal hold 判定，二次复核后逐对象删除并审计。

    只 flush 不 commit（与 `WorkpaperSyncRepository` 同一事务边界约定）。
    """

    def __init__(
        self,
        session: AsyncSession,
        artifacts: CanonicalArtifactRepository,
        *,
        policy: RetentionPolicy | None = None,
    ) -> None:
        self._session = session
        self._artifacts = artifacts
        self._policy = policy or load_retention_policy()

    @property
    def policy(self) -> RetentionPolicy:
        return self._policy

    # ── 引用扫描 ──────────────────────────────────────────────────────

    async def references_of(self, artifact_id: uuid.UUID) -> tuple[str, ...]:
        """逐表逐列查引用。**每张表单独一条 SQL 并单独记名**。

        刻意不写成一个大 UNION：命中哪张表必须能进审计（Requirement 5.11「删除结果证据」），
        而 UNION 只能回答「有没有」。逐表查也让「某张表拼错列名」表现为 ProgrammingError
        而不是静默 0 行 —— 这一层**不设 `except Exception`**，SQL 错误必须炸出来。
        """
        hits: list[str] = []
        for src in REFERENCE_SOURCES:
            row = (
                await self._session.execute(
                    sa.text(
                        f"SELECT 1 FROM {src.table} WHERE {src.column} = :aid LIMIT 1"  # noqa: S608
                    ),
                    {"aid": str(artifact_id)},
                )
            ).first()
            if row is not None:
                hits.append(f"{src.table}.{src.column}")
        return tuple(hits)

    async def in_flight_operation_of(self, artifact_id: uuid.UUID) -> str | None:
        """artifact 的 `created_by_operation_id` 是否指向非终态 operation。"""
        row = (
            await self._session.execute(
                sa.text(
                    "SELECT o.id, o.state FROM working_paper_artifact a "
                    "JOIN working_paper_sync_operation o ON o.id = a.created_by_operation_id "
                    "WHERE a.id = :aid AND o.state = ANY(:states) LIMIT 1"
                ),
                {"aid": str(artifact_id), "states": list(_IN_FLIGHT_OPERATION_STATES)},
            )
        ).first()
        if row is None:
            return None
        return f"operation:{row[0]}:{row[1]}"

    # ── dry-run ───────────────────────────────────────────────────────

    async def plan(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        now: datetime | None = None,
        write_audit: bool = True,
    ) -> RetentionPlan:
        """dry-run：逐对象判定并落审计清单，**绝不删除任何文件**。"""
        moment = now or datetime.now(timezone.utc)
        plan = RetentionPlan(
            policy_version=self._policy.policy_version,
            project_id=str(project_id),
            wp_id=str(wp_id),
            planned_at=moment.isoformat(),
        )
        rows = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperArtifact).where(
                        WorkpaperArtifact.project_id == project_id,
                        WorkpaperArtifact.wp_id == wp_id,
                        WorkpaperArtifact.state != ArtifactState.deleted.value,
                    )
                )
            ).scalars()
        )
        for row in rows:
            decision = await self._decide(row, moment, recheck=False)
            plan.decisions.append(decision)
            if decision.alert:
                plan.alerts.append(f"{decision.reason}:{decision.relative_path}")
        if write_audit:
            audit = await self._write_audit(
                project_id=project_id, wp_id=wp_id, dry_run=True,
                decisions=plan.decisions, alerts=plan.alerts, at=moment,
            )
            plan.audit_relative_path, plan.audit_sha256 = audit
        return plan

    # ── apply ─────────────────────────────────────────────────────────

    async def apply(
        self, plan: RetentionPlan, *, now: datetime | None = None
    ) -> RetentionOutcome:
        """执行 plan 中的 delete 判定，**每个对象删前再查一次引用/legal hold/状态**。

        二次复核发现任何变化即改判 retain：
        `reference_found_on_recheck` / `legal_hold` / `state_changed_on_recheck` /
        `in_flight_operation`。这正是 Task 7 db5 观测到的「引用重现 ⇒ 保留」分支。
        """
        if not self._policy.dry_run_required_before_apply:
            raise RetentionUsageError("策略要求 apply 之前必须先 dry-run")
        if not plan.dry_run:
            raise RetentionUsageError("apply 只接受 dry-run 产生的 plan")
        if plan.policy_version != self._policy.policy_version:
            raise RetentionUsageError(
                f"plan 的 policy_version={plan.policy_version} 与当前策略 "
                f"{self._policy.policy_version} 不符 —— 策略换版必须重新 dry-run"
            )
        moment = now or datetime.now(timezone.utc)
        outcome = RetentionOutcome(
            policy_version=self._policy.policy_version,
            project_id=plan.project_id,
            wp_id=plan.wp_id,
            applied_at=moment.isoformat(),
        )
        for planned in plan.deletions:
            row = (
                await self._session.execute(
                    sa.select(WorkpaperArtifact).where(
                        WorkpaperArtifact.id == uuid.UUID(planned.artifact_id)
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                outcome.alerts.append(f"artifact_row_vanished:{planned.relative_path}")
                continue
            if row.state != planned.state:
                retained = self._retain(
                    row, reason="state_changed_on_recheck", age_hours=planned.age_hours
                )
                outcome.retained_on_recheck.append(retained)
                outcome.alerts.append(f"state_changed_on_recheck:{row.relative_path}")
                continue
            fresh = await self._decide(row, moment, recheck=True)
            if fresh.decision != "delete":
                outcome.retained_on_recheck.append(fresh)
                if fresh.alert:
                    outcome.alerts.append(f"{fresh.reason}:{fresh.relative_path}")
                continue
            try:
                self._artifacts.delete_artifact_file(
                    row.relative_path, project_id=uuid.UUID(str(row.project_id))
                )
            except (FileInUseError, ArtifactPathError) as exc:
                # 不确定即保留：删不掉不是「已删」，也不能静默跳过。
                retained = self._retain(row, reason="delete_failed", age_hours=fresh.age_hours)
                retained.alert = True
                outcome.retained_on_recheck.append(retained)
                outcome.alerts.append(f"delete_failed:{row.relative_path}:{exc.error_code}")
                continue
            row.state = ArtifactState.deleted.value
            row.deleted_at = moment
            fresh.decision = "delete"
            outcome.deleted.append(fresh)
        await self._session.flush()
        audit = await self._write_audit(
            project_id=uuid.UUID(plan.project_id), wp_id=uuid.UUID(plan.wp_id),
            dry_run=False,
            decisions=list(outcome.deleted) + list(outcome.retained_on_recheck),
            alerts=outcome.alerts, at=moment,
        )
        outcome.audit_relative_path, outcome.audit_sha256 = audit
        return outcome

    # ── 判定核心 ──────────────────────────────────────────────────────

    def _retain(
        self, row: WorkpaperArtifact, *, reason: str, age_hours: float | None
    ) -> RetentionDecision:
        klass = self._policy.klass(row.retention_class)
        return RetentionDecision(
            artifact_id=str(row.id),
            relative_path=row.relative_path,
            kind=row.kind,
            state=row.state,
            retention_class=row.retention_class,
            sensitivity=klass.sensitivity if klass else "unknown",
            decision="retain",
            reason=reason,
            legal_hold=bool(row.legal_hold),
            age_hours=age_hours,
            ttl_hours=klass.ttl_hours if klass else None,
            grace_hours=klass.grace_hours if klass else None,
            access_roles=klass.access_roles if klass else (),
            alert=reason in self._policy.alert_retain_reasons,
        )

    async def _decide(
        self, row: WorkpaperArtifact, moment: datetime, *, recheck: bool
    ) -> RetentionDecision:
        """单个 artifact 的判定。判定顺序即语义顺序，每一步都有独立 reason。"""
        klass = self._policy.klass(row.retention_class)
        if klass is None:
            return self._retain(row, reason="no_policy_retain_and_alert", age_hours=None)
        if row.kind not in klass.applies_to_kinds or row.state not in klass.applies_to_states:
            return self._retain(row, reason="class_scope_mismatch", age_hours=None)
        if row.legal_hold and klass.honor_legal_hold:
            return self._retain(row, reason="legal_hold", age_hours=None)
        if not klass.deletable:
            return self._retain(row, reason="class_not_deletable", age_hours=None)
        if klass.requires_orphaned_at and row.orphaned_at is None:
            return self._retain(row, reason="orphaned_at_missing", age_hours=None)

        anchor: datetime | None = getattr(row, klass.age_anchor, None)
        if anchor is None:
            return self._retain(row, reason="age_anchor_missing", age_hours=None)
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        age_hours = (moment - anchor).total_seconds() / 3600.0
        if age_hours < klass.ttl_hours:
            return self._retain(row, reason="ttl_not_elapsed", age_hours=age_hours)
        if age_hours < klass.ttl_hours + klass.grace_hours:
            return self._retain(row, reason="grace_not_elapsed", age_hours=age_hours)

        in_flight = await self.in_flight_operation_of(uuid.UUID(str(row.id)))
        if in_flight is not None:
            decision = self._retain(row, reason="in_flight_operation", age_hours=age_hours)
            decision.referenced_by = (in_flight,)
            return decision

        refs = await self.references_of(uuid.UUID(str(row.id)))
        if refs:
            decision = self._retain(
                row,
                reason="reference_found_on_recheck" if recheck else "reference_found_on_plan",
                age_hours=age_hours,
            )
            decision.referenced_by = refs
            return decision

        return RetentionDecision(
            artifact_id=str(row.id),
            relative_path=row.relative_path,
            kind=row.kind,
            state=row.state,
            retention_class=row.retention_class,
            sensitivity=klass.sensitivity,
            decision="delete",
            reason="grace_elapsed_and_unreferenced",
            legal_hold=bool(row.legal_hold),
            age_hours=age_hours,
            ttl_hours=klass.ttl_hours,
            grace_hours=klass.grace_hours,
            access_roles=klass.access_roles,
        )

    # ── 审计 ──────────────────────────────────────────────────────────

    async def _write_audit(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        dry_run: bool,
        decisions: list[RetentionDecision],
        alerts: list[str],
        at: datetime,
    ) -> tuple[str, str]:
        """把逐对象判定清单内容寻址发布为 `retention_audit` evidence artifact。"""
        payload = json.dumps(
            {
                "policy_id": self._policy.policy_id,
                "policy_version": self._policy.policy_version,
                "schema_version": self._policy.schema_version,
                "project_id": str(project_id),
                "wp_id": str(wp_id),
                "dry_run": dry_run,
                "at": at.isoformat(),
                "decision_count": len(decisions),
                "decisions": [asdict(d) for d in decisions],
                "alerts": list(alerts),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        # test_run_id 由 (scope, 时刻, dry_run) 派生 ⇒ 同一轮判定重放落同一目录，
        # 而 dry-run 与 apply 各自留一份（Requirement 5.11「dry-run 真假分别留痕」）。
        run_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"retention:{project_id}:{wp_id}:{at.isoformat()}:{dry_run}",
        )
        published = self._artifacts.publish_evidence_manifest(
            project_id=project_id,
            wp_id=wp_id,
            entry_id="_retention",
            test_run_id=run_id,
            payload=payload,
        )
        existing = (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(
                    WorkpaperArtifact.relative_path == published.relative_path
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(
                WorkpaperArtifact(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    wp_id=wp_id,
                    kind=published.kind.value,
                    state=ArtifactState.published.value,
                    relative_path=published.relative_path,
                    sha256=published.sha256,
                    size_bytes=published.size_bytes,
                    document_type=published.document_type,
                    retention_class="retention_audit",
                    legal_hold=True,
                    published_at=at,
                )
            )
            await self._session.flush()
        return published.relative_path, published.sha256


__all__ = [
    "REFERENCE_SOURCES",
    "RETENTION_CONFIG_PATH",
    "ReferenceSource",
    "RetentionClass",
    "RetentionConfigError",
    "RetentionDecision",
    "RetentionOutcome",
    "RetentionPlan",
    "RetentionPolicy",
    "RetentionPolicyService",
    "RetentionUsageError",
    "load_retention_policy",
]
