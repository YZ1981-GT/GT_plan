"""底稿编制说明服务：解析、状态、版本和响应契约。

endpoint 当前按请求创建 service；请求级 LRU 只会制造“有缓存”的错觉。本实现不保留
伪缓存，先保证版本与实例隔离。未来如有性能实证，再引入 immutable process cache，
并把 static/template/questions/complexity 全部纳入 fingerprint。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.services.guidance_inventory import (
    CANONICAL_SECTION_KEYS,
    GUIDANCE_DIR,
    analyze_guidance_document,
    stable_digest,
)
from app.services.guidance_resolution_identity import (
    GUIDANCE_CONTRACT_VERSION,
    GUIDANCE_RESOLUTION_SCHEMA_VERSION,
    GuidanceMembershipError,
    ResolutionIdentity,
    ResolutionProvenance,
    ResolutionVerdict,
    ProvenanceSource,
)
from app.services.guidance_api_contract import (
    GUIDANCE_RESPONSE_SCHEMA_VERSION,
    OwnerGate,
    StructuredError,
    compute_response_fingerprint,
    compute_stable_cache_key,
    make_etag,
    response_version_from_fingerprint,
)

logger = logging.getLogger(__name__)

_GUIDANCE_DIR = GUIDANCE_DIR


def get_wp_guidance(wp_code: str) -> dict | None:
    """加载 canonical guidance JSON；损坏时返回 None 并记录可定位日志。"""
    path = _GUIDANCE_DIR / f"{wp_code}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) and "wp_codes" not in data else None
    except Exception as exc:  # noqa: BLE001 — 兼容旧调用，契约测试负责阻断损坏数据
        logger.error("加载 guidance 失败 wp_code=%s path=%s: %s", wp_code, path, exc)
        return None


def _static_contract_state(wp_code: str) -> Literal["absent", "invalid", "incomplete", "exact"]:
    """只读判定 static 文件状态，供 resolution reason 保留真实失败原因。"""
    path = _GUIDANCE_DIR / f"{wp_code}.json"
    if not path.is_file():
        return "absent"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "invalid"
    if not isinstance(data, dict) or "wp_codes" in data:
        return "invalid"
    try:
        analysis = analyze_guidance_document(data, fallback_wp_code=wp_code)
    except (TypeError, ValueError):
        return "invalid"
    if analysis.wp_code and analysis.wp_code != wp_code:
        return "invalid"
    return "exact" if analysis.status == "exact" else "incomplete"


def _child_failure_reason(wp_code: str) -> str:
    state = _static_contract_state(wp_code)
    return {
        "absent": "child_missing",
        "invalid": "child_invalid",
        "incomplete": "child_incomplete",
        # exact 文件仍未被 extractor 接受，通常是 I/O timeout；保持可观察失败态。
        "exact": "child_unavailable",
    }[state]


def _parent_resolution_reason(wp_code: str, source: str) -> str:
    state = _static_contract_state(wp_code)
    if state == "invalid" and source != "static_json":
        return f"parent_invalid:parent_{source}"
    if state == "incomplete" and source == "static_json":
        return "parent_static_incomplete"
    return f"parent_full_chain:{source}"


def list_available_guidance() -> list[str]:
    if not _GUIDANCE_DIR.exists():
        return []
    return sorted(
        file.stem
        for file in _GUIDANCE_DIR.glob("*.json")
        if not file.stem.startswith("_")
    )


def _load_complexity_config() -> dict[str, list[str]]:
    path = _GUIDANCE_DIR / "_complexity.json"
    if not path.exists():
        return {"high": [], "medium": [], "low": []}
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {"high": [], "medium": [], "low": []}
    except Exception as exc:  # noqa: BLE001
        logger.error("加载 _complexity.json 失败: %s", exc)
        return {"high": [], "medium": [], "low": []}


def _load_questions_config() -> dict[str, list[str]]:
    """每次读取以确保版本和实际问题配置一致；文件极小。"""
    path = _GUIDANCE_DIR / "_questions.json"
    if not path.exists():
        return {
            "program": ["这个程序表有哪些关键步骤？"],
            "determination": ["审定表的金额从哪里取数？"],
            "default": ["这个底稿的编制目的是什么？"],
        }
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {"program": [], "determination": [], "default": []}
    except Exception as exc:  # noqa: BLE001
        logger.error("加载 _questions.json 失败: %s", exc)
        return {"program": [], "determination": [], "default": []}


def _matches_pattern(wp_code: str, pattern: str) -> bool:
    if "*" not in pattern:
        return wp_code == pattern
    regex_pattern = pattern.replace("*", ".*")
    if pattern.startswith("*"):
        regex_pattern += "$"
    elif pattern.endswith("*"):
        regex_pattern = "^" + regex_pattern
    else:
        regex_pattern = "^" + regex_pattern + "$"
    return bool(re.match(regex_pattern, wp_code))


class GuidanceService:
    """编排 child exact probe、parent full chain 与版本化响应。"""

    def __init__(self) -> None:
        from app.services.guidance_extractor import GuidanceExtractor

        self._extractor = GuidanceExtractor()

    async def get_guidance(
        self,
        wp_code: str,
        wp_name: str = "",
        template_path: Path | None = None,
        *,
        runtime_entry: Any | None = None,
        inventory_facts_digest: str | None = None,
        inventory_run_id: str | None = None,
    ) -> dict[str, Any]:
        """兼容入口：对当前 code 执行完整链。"""
        result = await self._extractor.extract_full(wp_code, template_path)
        return self._build_response(
            result=result,
            wp_name=wp_name,
            requested_sheet_code=None,
            resolved_wp_code=wp_code,
            inherited_from_parent=False,
            resolution_reason=_parent_resolution_reason(wp_code, result.source),
            force_resolution_status=None,
            runtime_entry=runtime_entry,
            inventory_facts_digest=inventory_facts_digest,
            inventory_run_id=inventory_run_id,
        )

    async def resolve_guidance(
        self,
        *,
        parent_wp_code: str,
        requested_sheet_code: str | None,
        wp_name: str = "",
        parent_template_path: Path | None = None,
        whole_workbook: bool = False,
        runtime_entry: Any | None = None,
        inventory_facts_digest: str | None = None,
        inventory_run_id: str | None = None,
    ) -> dict[str, Any]:
        """执行 ``child exact static → parent full chain``。

        child 只读自己的 JSON，绝不接收 parent template_path，也不进入 typed fallback。
        child 缺失、损坏或九段/source_ref 不完整都必须进入父链。整册上下文固定走
        parent chain，并显式标记为继承，不能伪装成当前 sheet exact。
        """
        requested = (requested_sheet_code or "").strip() or None
        common = {
            "runtime_entry": runtime_entry,
            "inventory_facts_digest": inventory_facts_digest,
            "inventory_run_id": inventory_run_id,
        }

        if whole_workbook:
            parent = await self._extractor.extract_full(parent_wp_code, parent_template_path)
            return self._build_response(
                result=parent,
                wp_name=wp_name,
                requested_sheet_code=None,
                resolved_wp_code=parent_wp_code,
                inherited_from_parent=True,
                resolution_reason="whole_workbook_parent_context",
                force_resolution_status="parent_inherited",
                **common,
            )

        if requested and requested != parent_wp_code:
            child = await self._extractor.extract_exact_static(
                requested,
                validated_entry=runtime_entry,
            )
            if child is not None:
                return self._build_response(
                    result=child,
                    wp_name=wp_name,
                    requested_sheet_code=requested,
                    resolved_wp_code=requested,
                    inherited_from_parent=False,
                    resolution_reason="child_exact_static",
                    force_resolution_status=None,
                    **common,
                )

            parent = await self._extractor.extract_full(parent_wp_code, parent_template_path)
            runtime_failure = getattr(runtime_entry, "exact_status", None)
            child_reason = (
                f"child_{runtime_failure}"
                if runtime_failure in {"missing", "invalid", "stale"}
                else _child_failure_reason(requested)
            )
            parent_reason = _parent_resolution_reason(parent_wp_code, parent.source)
            return self._build_response(
                result=parent,
                wp_name=wp_name,
                requested_sheet_code=requested,
                resolved_wp_code=parent_wp_code,
                inherited_from_parent=True,
                resolution_reason=f"{child_reason}:{parent_reason}",
                force_resolution_status="parent_inherited",
                **common,
            )

        parent = await self._extractor.extract_full(parent_wp_code, parent_template_path)
        return self._build_response(
            result=parent,
            wp_name=wp_name,
            requested_sheet_code=requested,
            resolved_wp_code=parent_wp_code,
            inherited_from_parent=False,
            resolution_reason=_parent_resolution_reason(parent_wp_code, parent.source),
            force_resolution_status=None,
            **common,
        )

    async def resolve_authoritative_exact(
        self,
        *,
        parent_wp_code: str,
        requested_sheet_code: str | None,
        wp_name: str = "",
        parent_template_path: Path | None = None,
        whole_workbook: bool = False,
        runtime_entry: Any | None = None,
        inventory_facts_digest: str | None = None,
        inventory_run_id: str | None = None,
        # membership 校验所需的 authority 上下文
        authority_wp_code: str | None = None,
        authority_sheet_codes: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        """Task 8 顶层解析入口。

        🔴 关键差异（vs 旧 resolve_guidance）：
        1. 先做 **membership fail-closed**：requested sheet 不属于 authority
           时抛 GuidanceMembershipError，route 层映射 403，不泄漏内容
        2. child exact 判定升级为 **三态**：exact / review_candidate / missing
           —— legacy static JSON 若尚未 publication，标记为 review_candidate
           而非 exact（AC#5）
        3. Response 补齐 spec design §7 全字段：contractVersion / schemaVersion /
           requestedIdentity / resolvedIdentity / provenance / resolutionReasons
           （列表，非单串）

        child → parent chain 顺序：
            child exact (active publication / custom-confirmed ACK)
              → parent authoritative exact
              → typed fallback
              → generic fallback
        raw static/template extraction 只作 review candidate，不抢 exact。
        """
        requested = (requested_sheet_code or "").strip() or None

        # ═════════ AC#1 membership fail-closed ═════════
        if requested is not None and requested != parent_wp_code:
            self._assert_sheet_membership(
                requested_sheet_code=requested,
                authority_wp_code=authority_wp_code or parent_wp_code,
                authority_sheet_codes=authority_sheet_codes,
                runtime_entry=runtime_entry,
            )

        common = {
            "runtime_entry": runtime_entry,
            "inventory_facts_digest": inventory_facts_digest,
            "inventory_run_id": inventory_run_id,
        }

        # ═════════ 整册上下文 ═════════
        if whole_workbook:
            parent = await self._extractor.extract_full(parent_wp_code, parent_template_path)
            return self._build_response(
                result=parent,
                wp_name=wp_name,
                requested_sheet_code=None,
                resolved_wp_code=parent_wp_code,
                inherited_from_parent=True,
                resolution_reason="whole_workbook_parent_context",
                force_resolution_status="parent_inherited",
                requested_identity=ResolutionIdentity(wp_code=parent_wp_code),
                resolved_identity=ResolutionIdentity(wp_code=parent_wp_code),
                provenance=self._build_provenance(
                    primary_source=parent,
                    inherited=True,
                ),
                **common,
            )

        # ═════════ child exact probe ═════════
        if requested and requested != parent_wp_code:
            child = await self._extractor.extract_exact_static(
                requested,
                validated_entry=runtime_entry,
            )
            if child is not None:
                # AC#5：legacy static JSON 若 source_ref 未通过则标 review_candidate
                child_is_review_only = not getattr(runtime_entry, "source_ref_status", None)
                child_status = (
                    "review_candidate" if child_is_review_only else None
                )
                return self._build_response(
                    result=child,
                    wp_name=wp_name,
                    requested_sheet_code=requested,
                    resolved_wp_code=requested,
                    inherited_from_parent=False,
                    resolution_reason="child_exact_static",
                    force_resolution_status=child_status,
                    requested_identity=ResolutionIdentity(wp_code=requested),
                    resolved_identity=ResolutionIdentity(wp_code=requested),
                    provenance=self._build_provenance(
                        primary_source=child, inherited=False,
                    ),
                    **common,
                )

            # child miss/invalid/stale → parent chain
            parent = await self._extractor.extract_full(parent_wp_code, parent_template_path)
            runtime_failure = getattr(runtime_entry, "exact_status", None)
            child_reason = (
                f"child_{runtime_failure}"
                if runtime_failure in {"missing", "invalid", "stale"}
                else _child_failure_reason(requested)
            )
            parent_reason = _parent_resolution_reason(parent_wp_code, parent.source)
            return self._build_response(
                result=parent,
                wp_name=wp_name,
                requested_sheet_code=requested,
                resolved_wp_code=parent_wp_code,
                inherited_from_parent=True,
                resolution_reason=f"{child_reason}:{parent_reason}",
                force_resolution_status="parent_inherited",
                requested_identity=ResolutionIdentity(wp_code=requested),
                resolved_identity=ResolutionIdentity(wp_code=parent_wp_code),
                provenance=self._build_provenance(
                    primary_source=parent, inherited=True,
                ),
                **common,
            )

        # ═════════ 直接 parent 请求（requested == parent_wp_code 或 None）═════════
        parent = await self._extractor.extract_full(parent_wp_code, parent_template_path)
        return self._build_response(
            result=parent,
            wp_name=wp_name,
            requested_sheet_code=requested,
            resolved_wp_code=parent_wp_code,
            inherited_from_parent=False,
            resolution_reason=_parent_resolution_reason(parent_wp_code, parent.source),
            force_resolution_status=None,
            requested_identity=ResolutionIdentity(wp_code=parent_wp_code, sheet_code=requested),
            resolved_identity=ResolutionIdentity(wp_code=parent_wp_code),
            provenance=self._build_provenance(
                primary_source=parent, inherited=False,
            ),
            **common,
        )

    @staticmethod
    def _assert_sheet_membership(
        *,
        requested_sheet_code: str,
        authority_wp_code: str,
        authority_sheet_codes: frozenset[str] | None,
        runtime_entry: Any | None,
    ) -> None:
        """AC#1 membership fail-closed。

        判据：
          1. requested_sheet_code 必须非空
          2. 若 authority_sheet_codes 提供（来自 render-config 或 authority identity），
             requested 必须在其中；否则抛 GuidanceMembershipError
          3. runtime_entry 若带 entry.wp_code，也必须与 authority_wp_code 匹配
             （防跨底稿）
        异常 message 不含任何 authority 内容（避免泄漏）。
        """
        if not requested_sheet_code or not str(requested_sheet_code).strip():
            raise GuidanceMembershipError("requested_sheet_code 不可为空")
        if authority_sheet_codes is not None and requested_sheet_code not in authority_sheet_codes:
            raise GuidanceMembershipError("requested sheet 不属于当前 wp authority")
        runtime_wp = getattr(runtime_entry, "wp_code", None)
        if runtime_wp and runtime_wp != authority_wp_code:
            raise GuidanceMembershipError("runtime entry 与 authority wp 不匹配")

    @staticmethod
    def _build_provenance(
        *,
        primary_source: Any,
        inherited: bool,
        overlay_sources: list[Any] | None = None,
    ) -> ResolutionProvenance:
        """构造 Provenance：primary 是最终展示源，overlays 是叠加层。"""
        def _ps(src: Any) -> ProvenanceSource:
            return ProvenanceSource(
                kind="primary" if not inherited else "overlay",
                source=getattr(src, "source", "fallback") or "fallback",
                path=getattr(src, "source_path", None),
                digest=None,
            )
        primary = _ps(primary_source)
        overlays = [_ps(o) for o in (overlay_sources or [])]
        # 整册或 parent-inherited 时，primary 是 parent；child raw 归到 extraction
        extraction: list[ProvenanceSource] = []
        if inherited:
            # primary 变 overlay，占位一个 primary 让消费端总能读到 primary 字段
            primary = ProvenanceSource(
                kind="primary",
                source=getattr(primary_source, "source", "fallback") or "fallback",
                path=getattr(primary_source, "source_path", None),
                digest=None,
            )
            overlays = [_ps(x) for x in (overlay_sources or [])]
        return ResolutionProvenance(
            primary=primary,
            overlays=overlays,
            extraction=extraction,
        )

    def classify_complexity(self, wp_code: str) -> Literal["high", "medium", "low"]:
        config = _load_complexity_config()
        for pattern in config.get("high", []):
            if _matches_pattern(wp_code, pattern):
                return "high"
        for pattern in config.get("medium", []):
            if _matches_pattern(wp_code, pattern):
                return "medium"
        return "low"

    def get_recommended_questions(self, wp_code: str, complexity: str = "") -> list[str]:
        del complexity  # 保留兼容签名；问题组由 code 单一决定
        static_guidance = get_wp_guidance(wp_code)
        if static_guidance and isinstance(static_guidance.get("recommended_questions"), list):
            return [
                str(item)
                for item in static_guidance["recommended_questions"]
                if str(item).strip()
            ]
        config = _load_questions_config()
        if wp_code.endswith("A") and len(wp_code) > 1:
            return config.get("program", [])
        if re.search(r"-1$", wp_code):
            return config.get("determination", [])
        return config.get("default", [])

    @staticmethod
    def _missing_sections(result: Any) -> list[str]:
        valid_with_source = {
            section.key
            for section in result.sections
            if section.key in CANONICAL_SECTION_KEYS and section.source_refs
        }
        return [key for key in CANONICAL_SECTION_KEYS if key not in valid_with_source]

    @staticmethod
    def _source_stat(source_path: str | None) -> dict[str, Any] | None:
        if not source_path:
            return None
        path = Path(source_path)
        try:
            stat = path.stat()
            return {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        except OSError:
            return {"path": str(path), "missing": True}

    def _build_response(
        self,
        *,
        result: Any,
        wp_name: str,
        requested_sheet_code: str | None,
        resolved_wp_code: str,
        inherited_from_parent: bool,
        resolution_reason: str,
        force_resolution_status: str | None,
        runtime_entry: Any | None,
        inventory_facts_digest: str | None,
        inventory_run_id: str | None,
        # Task 8 新增：resolution identity / provenance（兼容旧调用缺省为 None）
        requested_identity: ResolutionIdentity | None = None,
        resolved_identity: ResolutionIdentity | None = None,
        provenance: ResolutionProvenance | None = None,
    ) -> dict[str, Any]:
        complexity = self.classify_complexity(resolved_wp_code)
        questions = self.get_recommended_questions(resolved_wp_code, complexity)
        missing_sections = self._missing_sections(result)
        runtime_status = getattr(runtime_entry, "exact_status", None)
        runtime_missing = list(getattr(runtime_entry, "missing_sections", ()) or ())
        runtime_blockers = list(getattr(runtime_entry, "exact_blockers", ()) or ())
        if runtime_entry is None and result.source == "static_json":
            runtime_blockers.append("source_ref_context_missing")
        runtime_blockers = list(dict.fromkeys(runtime_blockers))
        if runtime_missing:
            missing_sections = runtime_missing

        # 证据失败态必须高于 parent_inherited；否则父链有可展示内容会把 stale/invalid
        # 伪装成成功。无 runtime contract 的 static 同样不得据 shape 判 exact。
        if runtime_status == "stale":
            resolution_status = "stale"
        elif runtime_status in {"missing", "invalid"}:
            resolution_status = runtime_status
        elif runtime_entry is None and result.source == "static_json":
            resolution_status = "invalid"
        elif force_resolution_status:
            resolution_status = force_resolution_status
        elif result.source == "typed_fallback":
            resolution_status = "typed_fallback"
        elif result.source == "fallback":
            resolution_status = "generic_fallback"
        elif missing_sections:
            resolution_status = "missing"
        else:
            resolution_status = "exact"

        # Task 8 AC#5：legacy static JSON 尚未 publication → review_candidate
        # 覆盖上面的 exact/missing 判定，避免"raw static 抢 exact"
        if (
            force_resolution_status == "review_candidate"
            and resolution_status in {"exact", "missing"}
        ):
            resolution_status = "review_candidate"

        # Task 8 AC#6：reasons 列表（非单串），前端可迭代渲染
        resolution_reasons: list[str] = []
        if resolution_reason:
            for chunk in str(resolution_reason).split(":"):
                chunk = chunk.strip()
                if chunk:
                    resolution_reasons.append(chunk)

        sections = [
            {
                "key": section.key,
                "title": section.heading,
                "items": section.content.split("\n") if section.content else [],
                "source_refs": section.source_refs,
            }
            for section in result.sections
        ]
        runtime_version_facts = (
            runtime_entry.version_facts()
            if runtime_entry is not None and hasattr(runtime_entry, "version_facts")
            else None
        )
        digest_facts = {
            "resolved_wp_code": resolved_wp_code,
            "source": result.source,
            "source_stat": self._source_stat(result.source_path),
            "sections": sections,
            "questions": questions,
            "complexity": complexity,
            "runtime_entry": runtime_version_facts,
            "inventory_facts_digest": inventory_facts_digest,
        }
        source_digest = stable_digest(digest_facts)

        # Task 9 AC#1：ETag / response_version / schemaVersion / fingerprint
        # fingerprint 覆盖 subject / inventory / publication / supplement / refs / schema / contract
        response_fingerprint = compute_response_fingerprint(parts={
            "schema_version": GUIDANCE_RESPONSE_SCHEMA_VERSION,
            "contract_version": GUIDANCE_CONTRACT_VERSION,
            "resolved_wp_code": resolved_wp_code,
            "requested_sheet_code": requested_sheet_code,
            "source": result.source,
            "source_path": getattr(result, "source_path", None),
            "source_digest": source_digest,
            "inventory_facts_digest": inventory_facts_digest,
            "inventory_entry_digest": getattr(runtime_entry, "entry_digest", None),
            "sections_keys": sorted({s.get("key") for s in sections if s.get("key")}),
        })
        response_version = response_version_from_fingerprint(response_fingerprint)
        etag = make_etag(response_version)

        # Task 9 AC#2：stable cache key 不含 contextRevision
        stable_cache_key = compute_stable_cache_key(
            project_id=getattr(runtime_entry, "project_id", None),
            wp_code=resolved_wp_code,
            entry_id=getattr(runtime_entry, "entry_id", None),
            sheet_key=requested_sheet_code,
            schema_version=GUIDANCE_RESPONSE_SCHEMA_VERSION,
            inventory_digest=inventory_facts_digest,
            publication_digest=getattr(runtime_entry, "publication_digest", None),
            supplement_digest=getattr(runtime_entry, "supplement_digest", None),
            refs_digest=getattr(runtime_entry, "source_refs_digest", None),
        )

        # Task 9 AC#6：结构化错误返回（invalid/timeout/stale/permission/blocked）
        structured_errors: list[dict[str, Any]] = []
        if resolution_status in {"invalid", "stale", "missing", "blocked"}:
            code = resolution_status if resolution_status in {"invalid", "stale"} else "blocked"
            structured_errors.append(StructuredError(
                code=code,
                message=f"resolution_status={resolution_status}",
                subject=resolved_wp_code,
                operation="guidance.resolve",
                details={
                    "exact_blockers": runtime_blockers,
                    "missing_sections": missing_sections,
                    "stale_reasons": list(getattr(runtime_entry, "stale_reasons", ()) or ()),
                },
            ).to_dict())

        return {
            # Task 9：契约、schema、response version、ETag
            "contractVersion": GUIDANCE_CONTRACT_VERSION,
            "schemaVersion": GUIDANCE_RESOLUTION_SCHEMA_VERSION,
            "responseSchemaVersion": GUIDANCE_RESPONSE_SCHEMA_VERSION,
            "responseVersion": response_version,
            "etag": etag,
            "responseFingerprint": response_fingerprint,
            "stableCacheKey": stable_cache_key,
            # Task 9 AC#6：结构化错误（空列表表示无错）
            "structuredErrors": structured_errors,

            # 兼容旧前端：wp_code 始终等于真实 resolved code。
            "wp_code": resolved_wp_code,
            "wp_name": wp_name or result.wp_name or "",
            "requested_sheet_code": requested_sheet_code,
            "resolved_wp_code": resolved_wp_code,
            "inherited_from_parent": inherited_from_parent,
            "resolution_status": resolution_status,
            "resolution_reason": resolution_reason,
            # Task 8：reasons 列表（非单串）
            "resolution_reasons": resolution_reasons,
            # Task 8：completion 三态
            "completion_status": (
                "complete" if resolution_status == "exact" and not missing_sections
                else "blocked" if resolution_status in {"stale", "invalid"}
                else "partial"
            ),
            "source": result.source,
            "complexity": complexity,
            "guidance_version": f"guidance-v2-{source_digest[:16]}",
            "source_digest": source_digest,
            "generated_at": datetime.now(UTC).isoformat(),
            "missing_sections": missing_sections,
            "exact_blockers": runtime_blockers,
            "guidance": {"sections": sections, "raw_text": result.raw_text},
            "recommended_questions": questions,
            # Task 8 AC#6：identity + provenance
            "requestedIdentity": (requested_identity.to_dict() if requested_identity
                                else {"wp_code": requested_sheet_code or resolved_wp_code}),
            "resolvedIdentity": (resolved_identity.to_dict() if resolved_identity
                                else {"wp_code": resolved_wp_code}),
            "provenance": provenance.to_dict() if provenance else {
                "primary": {"kind": "primary", "source": result.source,
                            "path": getattr(result, "source_path", None), "digest": None},
                "overlays": [], "extraction": [],
            },
            # runtime inventory 元数据；run_id 仅观测，不进入稳定 source_digest。
            "inventory_run_id": inventory_run_id,
            "inventory_facts_digest": inventory_facts_digest,
            "inventory_entry_id": getattr(runtime_entry, "entry_id", None),
            "inventory_entry_digest": getattr(runtime_entry, "entry_digest", None),
            "runtime_guidance_status": runtime_status,
            "stale_reasons": list(getattr(runtime_entry, "stale_reasons", ()) or ()),
            "guidance_required": getattr(runtime_entry, "required", None),
            "guidance_context_kind": getattr(runtime_entry, "context_kind", None),
        }
