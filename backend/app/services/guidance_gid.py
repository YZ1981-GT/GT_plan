"""G-ID milestone: stable template/sheet identity + SourceRef registry.

Spec: workpaper-guidance-content-closure Task 4
Requirements: 2.1, 2.3, 5.3, 5.4, 5.5, 8.1, 8.2, 8.3, 8.5, 15.2

本模块是 ``G-ID`` 的对外消费面：

* 六类 locator kind 的唯一 registry（unknown / 生命周期名作 kind → fail-closed）；
* 稳定 sheet identity 投影（不以名称/下标为主键）；
* 里程碑 evidence 路径与版本常量。

真源校验实现仍在 ``guidance_source_refs``；本模块提供 Protocol + Registry 抽象，
并保证「未登记 kind」不能绕过分派落到 xlsx/docx 默认分支。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from app.services.guidance_source_refs import (
    SourceRefContext,
    SourceRefFacts,
    SourceRefValidation,
    TemplateAuthoritySnapshot,
    _failure,
    _normalize_sha256,
    _RefSchemaError,
    _resolve_repo_path,
    _stable_digest,
    _validate_template_bound_ref,
)

GID_CONTRACT_ID = "G-ID"
GID_CONTRACT_VERSION = "1.0"

#: G-C0 SourceLocator.kind 全集。lifecycle 名（custom_candidate 等）绝不在此。
SUPPORTED_LOCATOR_KINDS: frozenset[str] = frozenset({
    "xlsx",
    "docx",
    "bcd_markdown",
    "methodology_publication",
    "project_evidence",
    "custom_artifact",
})

#: 来源生命周期名 —— 禁止当作 locator kind（Requirement 5.4）。
FORBIDDEN_LIFECYCLE_KIND_NAMES: frozenset[str] = frozenset({
    "custom_candidate",
    "custom_confirmed",
    "methodology_candidate",
    "extraction_candidate",
})

GUIDANCE_SECTION_KEYS: frozenset[str] = frozenset({
    "purpose",
    "materials",
    "data_sources",
    "steps",
    "formulas",
    "judgments",
    "evidence",
    "common_errors",
    "completion",
})


@runtime_checkable
class SourceRefHandler(Protocol):
    """design §5 SourceRefHandler — kind 有效性的唯一分派单元。"""

    kind: str

    def validate(
        self,
        raw: Mapping[str, Any],
        context: SourceRefContext,
    ) -> SourceRefValidation: ...

    def fingerprint(
        self,
        raw: Mapping[str, Any],
        context: SourceRefContext,
    ) -> str: ...


@dataclass(frozen=True)
class StableSheetIdentity:
    """稳定 sheet 身份：名称/顺序只作 display，不进 key。"""

    template_lineage_id: str | None
    template_version_id: str | None
    wp_code: str
    sheet_uid: str | None
    sheet_code: str | None
    null_reason: str | None = None

    @property
    def catalog_key(self) -> str:
        return "|".join([
            self.template_lineage_id or "",
            self.template_version_id or "",
            self.wp_code,
            self.sheet_uid or "",
        ])

    def to_dict(self) -> dict[str, Any]:
        return {
            "templateLineageId": self.template_lineage_id,
            "templateVersionId": self.template_version_id,
            "wpCode": self.wp_code,
            "sheetUid": self.sheet_uid,
            "sheetCode": self.sheet_code,
            "nullReason": self.null_reason,
            "catalogKey": self.catalog_key,
        }


def sheet_identity_from_authority(
    *,
    wp_code: str,
    sheet_uid: str | None,
    sheet_code: str | None,
    snapshot: TemplateAuthoritySnapshot | None,
    null_reason: str | None = None,
) -> StableSheetIdentity:
    """从 authority snapshot 投影稳定 identity；缺 uid 时诚实带 null_reason。"""
    lineage = None
    version = None
    if snapshot is not None and snapshot.authorities:
        auth = snapshot.authorities[0]
        lineage = auth.canonical_path
        version = auth.version
    reason = null_reason
    if not sheet_uid and reason is None:
        reason = "sheet_uid_unavailable"
    return StableSheetIdentity(
        template_lineage_id=lineage,
        template_version_id=version,
        wp_code=wp_code,
        sheet_uid=sheet_uid,
        sheet_code=sheet_code,
        null_reason=reason,
    )


class SourceRefRegistry:
    """locator kind → handler。未登记 / 生命周期名 → fail-closed。"""

    def __init__(self) -> None:
        self._handlers: dict[str, SourceRefHandler] = {}

    def register(self, handler: SourceRefHandler) -> None:
        key = handler.kind.strip().lower()
        if key in FORBIDDEN_LIFECYCLE_KIND_NAMES:
            raise ValueError(f"lifecycle name 不得注册为 locator kind: {key}")
        if key not in SUPPORTED_LOCATOR_KINDS:
            raise ValueError(f"不可注册未知 locator kind: {key}")
        if key in self._handlers:
            raise ValueError(f"locator kind 重复注册: {key}")
        self._handlers[key] = handler

    def get(self, kind: str) -> SourceRefHandler | None:
        return self._handlers.get((kind or "").strip().lower())

    @property
    def registered_kinds(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def validate(
        self,
        raw: Mapping[str, Any] | Any,
        context: SourceRefContext,
    ) -> SourceRefValidation:
        facts = SourceRefFacts()
        if not isinstance(raw, Mapping):
            return _failure("invalid", "ref_not_object", "source_ref 必须是对象", facts)
        # 支持 G-C0 nested locator 与既有扁平 kind
        locator = raw.get("locator") if isinstance(raw.get("locator"), Mapping) else None
        kind_raw = (locator or raw).get("kind")
        if not isinstance(kind_raw, str) or not kind_raw.strip():
            return _failure("invalid", "kind_missing", "source_ref.kind 不得为空", facts, field="kind")
        kind = kind_raw.strip().lower()
        facts = SourceRefFacts(kind=kind, document_type=kind)
        if kind in FORBIDDEN_LIFECYCLE_KIND_NAMES:
            return _failure(
                "invalid",
                "kind_is_lifecycle_not_locator",
                f"{kind} 是来源生命周期，不是 locator kind（Requirement 5.4）",
                facts,
                field="kind",
            )
        handler = self._handlers.get(kind)
        if handler is None:
            return _failure(
                "invalid",
                "kind_unknown",
                f"未知 source_ref.kind={kind}（fail-closed）",
                facts,
                field="kind",
            )
        # 扁平化：若有 nested locator，合并顶层 digest/refId 供 handler
        payload: dict[str, Any] = dict(locator) if locator is not None else dict(raw)
        if locator is not None:
            for key in ("digest", "contentDigest", "authorityDigest", "refId", "contractVersion"):
                if key in raw and key not in payload:
                    payload[key] = raw[key]
            if "digest" not in payload and "contentDigest" in payload:
                payload["digest"] = payload["contentDigest"]
        return handler.validate(payload, context)


def _fp(raw: Mapping[str, Any], extra: Mapping[str, Any] | None = None) -> str:
    payload = {"raw": dict(raw), **(dict(extra) if extra else {})}
    return _stable_digest(payload)


class _XlsxHandler:
    kind = "xlsx"

    def validate(self, raw: Mapping[str, Any], context: SourceRefContext) -> SourceRefValidation:
        return _validate_template_bound_ref(raw, context, kind="xlsx")

    def fingerprint(self, raw: Mapping[str, Any], context: SourceRefContext) -> str:
        return _fp(raw, {"kind": self.kind, "wp": context.target_wp_code})


class _DocxHandler:
    kind = "docx"

    def validate(self, raw: Mapping[str, Any], context: SourceRefContext) -> SourceRefValidation:
        return _validate_template_bound_ref(raw, context, kind="docx")

    def fingerprint(self, raw: Mapping[str, Any], context: SourceRefContext) -> str:
        return _fp(raw, {"kind": self.kind, "wp": context.target_wp_code})


class _BcdMarkdownHandler:
    kind = "bcd_markdown"

    def validate(self, raw: Mapping[str, Any], context: SourceRefContext) -> SourceRefValidation:
        facts = SourceRefFacts(kind=self.kind, document_type=self.kind)
        try:
            expected = _normalize_sha256(raw.get("digest") or raw.get("contentDigest"), field="digest")
            path, normalized = _resolve_repo_path(raw.get("path"), context, template_only=False)
        except _RefSchemaError as exc:
            return _failure("invalid", exc.code, exc.detail, facts, field=exc.field)
        heading = raw.get("headingPath") or raw.get("heading_path")
        anchor = raw.get("anchor")
        if not isinstance(heading, (list, tuple)) or not heading:
            return _failure("invalid", "heading_path_missing", "bcd_markdown 需要 headingPath[]", facts, field="headingPath")
        if not isinstance(anchor, str) or not anchor.strip():
            return _failure("invalid", "anchor_missing", "bcd_markdown 需要 anchor", facts, field="anchor")
        if not path.is_file():
            return _failure("missing", "source_not_found", "bcd markdown 文件不存在", facts, field="path")
        try:
            text = path.read_text(encoding="utf-8")
            observed = hashlib.sha256(text.encode("utf-8")).hexdigest()
        except OSError as exc:
            return _failure("missing", "source_unreadable", type(exc).__name__, facts, field="path")
        facts = SourceRefFacts(
            kind=self.kind,
            document_type=self.kind,
            normalized_path=normalized,
            expected_digest=expected,
            observed_digest=observed,
            anchor_type="heading",
            authority_root="repo",
        )
        if expected != observed:
            return _failure("stale", "digest_mismatch", "bcd digest 与文件不一致", facts, field="digest")
        # heading 唯一性：统计 markdown AT 行
        titles = [line.lstrip("#").strip() for line in text.splitlines() if line.startswith("#")]
        target = str(heading[-1]).strip()
        count = sum(1 for t in titles if t == target)
        facts = SourceRefFacts(**{**facts.__dict__, "anchor_match_count": count})
        if count != 1:
            return _failure(
                "invalid",
                "heading_not_unique",
                f"heading {target!r} 命中 {count} 次，必须唯一",
                facts,
                field="headingPath",
            )
        return SourceRefValidation(status="valid", issues=(), facts=facts)

    def fingerprint(self, raw: Mapping[str, Any], context: SourceRefContext) -> str:
        return _fp(raw, {"kind": self.kind})


class _MethodologyPublicationHandler:
    kind = "methodology_publication"

    def validate(self, raw: Mapping[str, Any], context: SourceRefContext) -> SourceRefValidation:
        facts = SourceRefFacts(kind=self.kind, document_type=self.kind)
        pub_id = raw.get("publicationId") or raw.get("publication_id")
        version = raw.get("version")
        section = raw.get("sectionKey") or raw.get("section_key")
        if not isinstance(pub_id, str) or not pub_id.strip():
            return _failure("invalid", "publication_id_missing", "需要 publicationId", facts, field="publicationId")
        if not isinstance(version, int) or version < 1:
            return _failure("invalid", "publication_version_invalid", "version 必须为正整数", facts, field="version")
        if section not in GUIDANCE_SECTION_KEYS:
            return _failure("invalid", "section_key_invalid", f"非法 sectionKey={section!r}", facts, field="sectionKey")
        lookup = getattr(context, "publication_lookup", None)
        if lookup is None:
            # fail-closed：没有 lookup 不得假装 active publication 有效
            return _failure(
                "invalid",
                "publication_lookup_unavailable",
                "methodology_publication 需要 active publication lookup，禁止无权威放行",
                facts,
                field="publicationId",
            )
        try:
            record = lookup(pub_id.strip(), version)  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001
            return _failure("invalid", "publication_lookup_error", type(exc).__name__, facts, field="publicationId")
        if record is None:
            return _failure("missing", "publication_not_found", "publication 不存在或未 active", facts, field="publicationId")
        status = str(getattr(record, "status", "") or record.get("status") if isinstance(record, Mapping) else "")
        if status and status not in {"published", "active", "ACTIVE", "PUBLISHED"}:
            return _failure("stale", "publication_not_active", f"publication status={status}", facts, field="publicationId")
        return SourceRefValidation(status="valid", issues=(), facts=facts)

    def fingerprint(self, raw: Mapping[str, Any], context: SourceRefContext) -> str:
        return _fp(raw, {"kind": self.kind})


class _ProjectEvidenceHandler:
    kind = "project_evidence"

    def validate(self, raw: Mapping[str, Any], context: SourceRefContext) -> SourceRefValidation:
        facts = SourceRefFacts(kind=self.kind, document_type=self.kind)
        project_id = raw.get("projectId") or raw.get("project_id")
        evidence_id = raw.get("evidenceId") or raw.get("evidence_id")
        revision = raw.get("revision")
        if not isinstance(project_id, str) or not project_id.strip():
            return _failure("invalid", "project_id_missing", "需要 projectId", facts, field="projectId")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            return _failure("invalid", "evidence_id_missing", "需要 evidenceId", facts, field="evidenceId")
        if not isinstance(revision, str) or not revision.strip():
            return _failure("invalid", "revision_missing", "需要 revision", facts, field="revision")
        visible = getattr(context, "visible_project_ids", None)
        if visible is None:
            return _failure(
                "invalid",
                "project_visibility_unavailable",
                "project_evidence 必须先过 project visibility gate",
                facts,
                field="projectId",
            )
        if project_id.strip() not in set(visible):
            return _failure(
                "invalid",
                "project_not_visible",
                "无权引用该项目证据（不泄漏是否存在）",
                facts,
                field="projectId",
            )
        return SourceRefValidation(status="valid", issues=(), facts=facts)

    def fingerprint(self, raw: Mapping[str, Any], context: SourceRefContext) -> str:
        return _fp(raw, {"kind": self.kind})


class _CustomArtifactHandler:
    kind = "custom_artifact"

    def validate(self, raw: Mapping[str, Any], context: SourceRefContext) -> SourceRefValidation:
        facts = SourceRefFacts(kind=self.kind, document_type=self.kind)
        authority_id = raw.get("authorityId") or raw.get("authority_id")
        sha = raw.get("artifactSha256") or raw.get("artifact_sha256")
        sheet_uid = raw.get("sheetUid") or raw.get("sheet_uid")
        locator = raw.get("locator")
        if not isinstance(authority_id, str) or not authority_id.strip():
            return _failure("invalid", "authority_id_missing", "需要 authorityId", facts, field="authorityId")
        try:
            digest = _normalize_sha256(sha, field="artifactSha256")
        except _RefSchemaError as exc:
            return _failure("invalid", exc.code, exc.detail, facts, field=exc.field)
        if not isinstance(sheet_uid, str) or not sheet_uid.strip():
            return _failure("invalid", "sheet_uid_missing", "需要 sheetUid", facts, field="sheetUid")
        if not isinstance(locator, str) or not locator.strip():
            return _failure("invalid", "locator_missing", "需要 locator", facts, field="locator")
        # 禁止暴露物理 storage path / URI
        lowered = locator.casefold()
        for banned in ("..", "sharedfs://", "file:", ":\\", "\\\\"):
            if banned in locator or banned in lowered:
                return _failure(
                    "invalid",
                    "locator_exposes_storage",
                    "custom_artifact.locator 不得含物理路径/URI",
                    facts,
                    field="locator",
                )
        if any(k in raw for k in ("path", "storageKey", "storage_key", "absolutePath")):
            return _failure(
                "invalid",
                "physical_path_forbidden",
                "custom_artifact 不得携带物理 path/storageKey",
                facts,
                field="path",
            )
        facts = SourceRefFacts(
            kind=self.kind,
            document_type=self.kind,
            expected_digest=digest,
            observed_digest=digest,
            sheet=sheet_uid.strip(),
            cell_range=locator.strip(),
            authority_root=authority_id.strip(),
        )
        return SourceRefValidation(status="valid", issues=(), facts=facts)

    def fingerprint(self, raw: Mapping[str, Any], context: SourceRefContext) -> str:
        return _fp(raw, {"kind": self.kind})


def build_default_registry() -> SourceRefRegistry:
    registry = SourceRefRegistry()
    for handler in (
        _XlsxHandler(),
        _DocxHandler(),
        _BcdMarkdownHandler(),
        _MethodologyPublicationHandler(),
        _ProjectEvidenceHandler(),
        _CustomArtifactHandler(),
    ):
        registry.register(handler)
    assert registry.registered_kinds == SUPPORTED_LOCATOR_KINDS
    return registry


DEFAULT_SOURCE_REF_REGISTRY = build_default_registry()


def validate_source_ref_via_registry(
    raw: Mapping[str, Any] | Any,
    context: SourceRefContext,
    *,
    registry: SourceRefRegistry | None = None,
) -> SourceRefValidation:
    """G-ID 对外入口：一律经 registry（unknown kind fail-closed）。"""
    return (registry or DEFAULT_SOURCE_REF_REGISTRY).validate(raw, context)


def gid_evidence_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "guidance" / "contracts" / "gid"


def build_gid_evidence_payload() -> dict[str, Any]:
    """构造可落盘的 G-ID EvidenceEnvelope（subject=contract）。"""
    root = gid_evidence_dir()
    root.mkdir(parents=True, exist_ok=True)
    registry = build_default_registry()
    source_digests = {
        "registered_kinds": hashlib.sha256(
            json.dumps(sorted(registry.registered_kinds), separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "module": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    return {
        "contractVersion": "1.0",
        "evidenceId": "evidence-gid-milestone-1",
        "runId": "run-gid-milestone-1",
        "subject": {"kind": "contract", "contractId": GID_CONTRACT_ID},
        "contractVersions": {
            "G-C0": "1.0",
            GID_CONTRACT_ID: GID_CONTRACT_VERSION,
        },
        "inventoryDigest": None,
        "sourceDigests": source_digests,
        "operationIds": {"publish": "op-publish-gid-2026-09-08"},
        "artifacts": [
            {
                "kind": "report",
                "uri": "backend/app/services/guidance_gid.py",
                "sha256": source_digests["module"],
            }
        ],
        "verdict": "PASS",
        "recordedAt": "2026-09-08T00:00:00Z",
        "registeredKinds": sorted(registry.registered_kinds),
    }
