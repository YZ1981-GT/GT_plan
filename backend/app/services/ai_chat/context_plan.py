"""AI Chat 的可信上下文计划。

把宿主正文、知识检索、显式引用、会话附件和复核提示词在服务端重新授权后，
按一个预算裁剪并产出同一份 system message 与 Context Manifest。Native/DSH 只消费
本计划，不再分别猜测客户端提交的资源。
"""

from __future__ import annotations

import dataclasses
import inspect
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import AttachmentOcrStatus
from app.services.ai_chat.attachment_service import AttachmentService
from app.services.ai_chat.audit_relation_context import (
    AuditRelationItem,
    build_audit_relation_context,
)
from app.services.ai_chat.context_budget import (
    ContextBudgetPolicy,
    ContextManifestEntry,
)
from app.services.ai_chat.mention_service import MentionContentItem, load_mention_context
from app.services.ai_chat.note_service import knowledge_jump_route
from app.services.ai_chat.run_resource_service import (
    AiRunResourceService,
    ProjectAttachmentContextItem,
)
from app.services.ai_chat.review_mode import SystemMessageAssembler, resolve_review_mode
from app.services.doc_ai_context_builder import ChatContext, ContextBuilder, SearchHit


@dataclass(frozen=True)
class ContextPlan:
    """一次 Run 最终送给引擎的可信材料。"""

    context: ChatContext
    system_message: str
    manifest: dict[str, Any]
    citations: tuple[dict[str, Any], ...]

    def agent_prompt(self, query: str) -> str:
        """DSH 的单文本入口：平台政策和已定界数据在前，用户问题在后。"""
        return f"{self.system_message}\n\n【用户问题】\n{query}"


async def build_context_plan(
    db: AsyncSession,
    *,
    request: Any,
    context_builder: ContextBuilder | None = None,
) -> ContextPlan:
    """构造 Native/DSH 共用的上下文计划。任何接线错误都向上抛出并终止 Run。"""
    principal = getattr(request, "principal", None)
    if principal is None:
        from app.models.core import User

        principal = await db.get(User, request.host.principal_id)
    if principal is None:
        raise RuntimeError("当前用户记录缺失，无法构建 AI 上下文")

    builder = context_builder or ContextBuilder(db)
    build_kwargs = {
        "host": request.host,
        "query": request.query,
        "user": principal,
    }
    if "enforce_budget" in inspect.signature(builder.build).parameters:
        build_kwargs["enforce_budget"] = False
    base = await builder.build(**build_kwargs)
    relation_items: list[AuditRelationItem] = []
    relation_error: str | None = None
    try:
        relation_items = await build_audit_relation_context(
            db, host=request.host, user=principal
        )
    except Exception as exc:  # 关系图是附加上下文；失败须在 manifest 留痕，不伪装为空。
        relation_error = type(exc).__name__
    review = await resolve_review_mode(
        db,
        host=request.host,
        review_mode=bool(getattr(request, "review_mode", False)),
        sheet_name=getattr(request, "sheet_name", None),
    )
    mentions = await load_mention_context(
        db,
        user=principal,
        host=request.host,
        mentions=list(getattr(request, "mentions", ()) or ()),
    )
    requested_attachment_ids = list(getattr(request, "attachment_ids", ()) or ())
    attachments = await AttachmentService(db).validate_for_run(
        attachment_ids=requested_attachment_ids,
        owner_id=request.host.principal_id,
        session_id=request.session_id,
    )
    requested_project_attachment_ids = list(
        getattr(request, "project_attachment_ids", ()) or ()
    )
    project_attachments = await AiRunResourceService(db).load_project_attachment_context(
        run_id=request.run_id,
        session_id=request.session_id,
        actor_user_id=request.host.principal_id,
        project_id=request.host.project_id,
        requested_ids=requested_project_attachment_ids,
    )

    policy = ContextBudgetPolicy(
        total_budget=int(getattr(builder, "token_budget", 8000) or 8000),
        review_mode=review is not None,
    )
    allocation = policy.allocate()

    summary_budget = min(int(policy.total_budget * 0.10), allocation.doc_excerpt)
    doc_budget = max(0, allocation.doc_excerpt - summary_budget)
    summary, summary_used = policy.truncate_to_budget(base.project_summary, summary_budget)
    host_sources = list(getattr(base, "host_sources", []) or [])
    if host_sources:
        doc_excerpt = _budget_host_sources(policy, host_sources, doc_budget)
    else:
        doc_excerpt, doc_used = policy.truncate_to_budget(base.doc_excerpt, doc_budget)
        _add_text_entry(
            policy,
            source_type=request.host.resource_type.value,
            source_id=request.host.resource_id,
            label=request.host.display_label,
            original=base.doc_excerpt,
            rendered=doc_excerpt,
            used=doc_used,
            budget=doc_budget,
        )
    if base.project_summary:
        _add_text_entry(
            policy,
            source_type="project_summary",
            source_id=str(request.host.project_id or ""),
            label="项目摘要",
            original=base.project_summary,
            rendered=summary,
            used=summary_used,
            budget=summary_budget,
        )

    review_for_prompt = review
    if review is not None:
        rendered, used = policy.truncate_to_budget(
            review.prompt_content, allocation.review_prompt
        )
        review_for_prompt = dataclasses.replace(review, prompt_content=rendered)
        _add_text_entry(
            policy,
            source_type="review_prompt",
            source_id=f"{review.wp_code}:{review.sheet_name or ''}",
            label=f"复核提示词 {review.wp_code}",
            original=review.prompt_content,
            rendered=rendered,
            used=used,
            budget=allocation.review_prompt,
            version=review.version,
        )
    elif bool(getattr(request, "review_mode", False)):
        policy.manifest.add(
            ContextManifestEntry(
                source_type="review_prompt",
                source_id=str(getattr(request, "sheet_name", "") or ""),
                label="复核提示词",
                status="unavailable",
                reason="unsupported_host",
            )
        )

    mention_texts = _budget_mentions(policy, mentions, allocation.mentions)
    attachment_count = len(requested_attachment_ids)
    project_attachment_count = len(requested_project_attachment_ids)
    combined_attachment_count = attachment_count + project_attachment_count
    session_attachment_budget = allocation.attachments
    if combined_attachment_count and project_attachment_count:
        session_attachment_budget = int(
            allocation.attachments * attachment_count / combined_attachment_count
        )
    project_attachment_budget = allocation.attachments - session_attachment_budget
    attachment_texts = _budget_attachments(
        policy,
        requested_attachment_ids,
        attachments,
        session_attachment_budget,
    )
    attachment_texts.extend(_budget_project_attachments(
        policy,
        requested_project_attachment_ids,
        project_attachments,
        project_attachment_budget,
    ))
    relation_budget = allocation.knowledge // 3 if relation_items else 0
    relation_texts = _budget_relations(policy, relation_items, relation_budget)
    if relation_error:
        policy.manifest.add(ContextManifestEntry(
            source_type="audit_relation_graph",
            source_id=str(request.host.resource_id),
            label="审计关系上下文",
            status="unavailable",
            reason=f"load_failed:{relation_error}",
        ))
    knowledge_hits = _budget_knowledge(
        policy, base.knowledge_hits, allocation.knowledge - relation_budget
    )

    if hasattr(builder, "build_citations"):
        final_citations = builder.build_citations(knowledge_hits)
    else:
        allowed_sources = {(h.source_type, h.source_id) for h in knowledge_hits}
        final_citations = [
            c
            for c in list(getattr(base, "citations", []) or [])
            if (getattr(c, "source_type", ""), getattr(c, "source_id", ""))
            in allowed_sources
        ]
    project_context = "\n\n".join(
        part for part in (
            summary,
            "【审计关系上下文】\n" + "\n".join(relation_texts)
            if relation_texts else "",
        ) if part
    )
    context = ChatContext(
        doc_excerpt=doc_excerpt,
        project_summary=project_context,
        knowledge_hits=knowledge_hits,
        citations=final_citations,
        token_estimate=policy.manifest.total_used,
        host_sources=host_sources,
    )
    citations = tuple(_citation_payload(c) for c in context.citations)
    system_message = SystemMessageAssembler().assemble(
        review_context=review_for_prompt,
        project_summary=context.project_summary,
        doc_excerpt=context.doc_excerpt,
        knowledge_hits=context.knowledge_hits,
        mention_texts=mention_texts,
        attachment_texts=attachment_texts,
    )
    manifest = policy.manifest.as_dict()
    manifest.update(
        {
            "manifest_version": "context-plan-v1",
            "citation_count": len(citations),
            "project_tools_enabled": request.host.project_tools_enabled,
            "review_mode": review_for_prompt is not None,
        }
    )
    return ContextPlan(context, system_message, manifest, citations)


def _add_text_entry(
    policy: ContextBudgetPolicy,
    *,
    source_type: str,
    source_id: str,
    label: str,
    original: str,
    rendered: str,
    used: int,
    budget: int,
    version: str = "",
    stale: bool = False,
    jump_route: str = "",
) -> None:
    if not original:
        policy.manifest.add(
            ContextManifestEntry(
                source_type=source_type,
                source_id=source_id,
                label=label,
                status="unavailable",
                reason="empty_content",
                version=version,
                stale=stale,
                jump_route=jump_route,
            )
        )
        return
    policy.manifest.add(
        ContextManifestEntry(
            source_type=source_type,
            source_id=source_id,
            label=label,
            status="included" if rendered == original else "trimmed",
            budget_tokens=budget,
            used_tokens=used,
            reason="" if rendered == original else "budget_exceeded",
            version=version,
            stale=stale,
            jump_route=jump_route,
        )
    )


def _budget_host_sources(
    policy: ContextBudgetPolicy,
    sources: list[dict[str, Any]],
    budget: int,
) -> str:
    """逐项裁剪聚合宿主的授权后子来源，并重建模型实际看到的正文。"""
    remaining = budget
    rendered_parts: list[str] = []
    for source in sources:
        original = str(source.get("content") or "")
        rendered, used = policy.truncate_to_budget(original, max(0, remaining))
        _add_text_entry(
            policy,
            source_type=str(source.get("source_type") or "host_source"),
            source_id=str(source.get("source_id") or ""),
            label=str(source.get("label") or ""),
            original=original,
            rendered=rendered,
            used=used,
            budget=budget,
            version=str(source.get("version") or ""),
            stale=bool(source.get("stale", False)),
            jump_route=str(source.get("jump_route") or ""),
        )
        if rendered:
            rendered_parts.append(rendered)
            remaining -= used
    return "\n\n".join(rendered_parts)


def _budget_mentions(
    policy: ContextBudgetPolicy,
    items: list[MentionContentItem],
    budget: int,
) -> list[tuple[str, str]]:
    remaining = budget
    rendered_items: list[tuple[str, str]] = []
    for item in items:
        if item.status != "included" or not item.content:
            policy.manifest.add(
                ContextManifestEntry(
                    source_type=f"mention:{item.type}",
                    source_id=item.id,
                    label=item.label,
                    status=item.status if item.status in {"denied", "unavailable"} else "unavailable",
                    reason="access_denied" if item.status == "denied" else "empty_content",
                )
            )
            continue
        rendered, used = policy.truncate_to_budget(item.content, max(0, remaining))
        _add_text_entry(
            policy,
            source_type=f"mention:{item.type}",
            source_id=item.id,
            label=item.label,
            original=item.content,
            rendered=rendered,
            used=used,
            budget=budget,
            jump_route=_jump_route(item.type, item.id),
        )
        if rendered:
            rendered_items.append((item.label or item.id, rendered))
            remaining -= used
    return rendered_items


def _budget_attachments(
    policy: ContextBudgetPolicy,
    requested_ids: list[UUID],
    rows: list[Any],
    budget: int,
) -> list[tuple[str, str]]:
    by_id = {row.id: row for row in rows}
    remaining = budget
    rendered_items: list[tuple[str, str]] = []
    for attachment_id in requested_ids:
        row = by_id.get(attachment_id)
        if row is None:
            policy.manifest.add(
                ContextManifestEntry(
                    source_type="attachment",
                    source_id=str(attachment_id),
                    status="denied",
                    reason="access_denied",
                )
            )
            continue
        if row.ocr_status != AttachmentOcrStatus.succeeded.value or not row.ocr_text_protected:
            policy.manifest.add(
                ContextManifestEntry(
                    source_type="attachment",
                    source_id=str(row.id),
                    label=row.original_name,
                    status="unavailable",
                    reason=f"ocr_{row.ocr_status}",
                )
            )
            continue
        text = str(row.ocr_text_protected)
        rendered, used = policy.truncate_to_budget(text, max(0, remaining))
        _add_text_entry(
            policy,
            source_type="attachment",
            source_id=str(row.id),
            label=row.original_name,
            original=text,
            rendered=rendered,
            used=used,
            budget=budget,
        )
        if rendered:
            rendered_items.append((row.original_name, rendered))
            remaining -= used
    return rendered_items


def _budget_project_attachments(
    policy: ContextBudgetPolicy,
    requested_ids: list[UUID],
    items: list[ProjectAttachmentContextItem],
    budget: int,
) -> list[tuple[str, str]]:
    by_id = {item.id: item for item in items}
    remaining = budget
    rendered_items: list[tuple[str, str]] = []
    for attachment_id in requested_ids:
        item = by_id.get(attachment_id)
        if item is None:
            policy.manifest.add(ContextManifestEntry(
                source_type="project_attachment",
                source_id=str(attachment_id),
                status="denied",
                reason="pin_missing",
            ))
            continue
        if item.status != "included" or not item.content:
            policy.manifest.add(ContextManifestEntry(
                source_type="project_attachment",
                source_id=str(item.id),
                label=item.label,
                status="unavailable",
                reason=item.reason or "no_extractable_text",
                version=item.version,
            ))
            continue
        rendered, used = policy.truncate_to_budget(item.content, max(0, remaining))
        _add_text_entry(
            policy,
            source_type="project_attachment",
            source_id=str(item.id),
            label=item.label,
            original=item.content,
            rendered=rendered,
            used=used,
            budget=budget,
            version=item.version,
        )
        if rendered:
            rendered_items.append((f"项目附件：{item.label}", rendered))
            remaining -= used
    return rendered_items


def _budget_relations(
    policy: ContextBudgetPolicy,
    items: list[AuditRelationItem],
    budget: int,
) -> list[str]:
    remaining = budget
    rendered_items: list[str] = []
    for item in items:
        rendered, used = policy.truncate_to_budget(item.content, max(0, remaining))
        _add_text_entry(
            policy,
            source_type=item.source_type,
            source_id=item.source_id,
            label=item.label,
            original=item.content,
            rendered=rendered,
            used=used,
            budget=budget,
            version=item.version,
            jump_route=item.jump_route,
        )
        if rendered:
            rendered_items.append(f"【{item.label}】{rendered}")
            remaining -= used
    return rendered_items


def _budget_knowledge(
    policy: ContextBudgetPolicy,
    hits: list[SearchHit],
    budget: int,
) -> list[SearchHit]:
    remaining = budget
    rendered_hits: list[SearchHit] = []
    for hit in hits:
        rendered, used = policy.truncate_to_budget(hit.content, max(0, remaining))
        _add_text_entry(
            policy,
            source_type=hit.source_type,
            source_id=hit.source_id,
            label=hit.source_name or hit.source_id,
            original=hit.content,
            rendered=rendered,
            used=used,
            budget=budget,
            version=str(getattr(hit, "doc_version", None) or ""),
            stale=bool(getattr(hit, "is_stale", False)),
            jump_route=_jump_route(hit.source_type, hit.source_id),
        )
        if rendered:
            if dataclasses.is_dataclass(hit):
                rendered_hits.append(dataclasses.replace(hit, content=rendered))
            else:
                rendered_hits.append(
                    SearchHit(
                        source_type=hit.source_type,
                        source_id=hit.source_id,
                        content=rendered,
                        score=float(getattr(hit, "score", 0.0) or 0.0),
                        chunk_index=getattr(hit, "chunk_index", None),
                        source_name=getattr(hit, "source_name", "") or "",
                        doc_version=getattr(hit, "doc_version", None),
                        is_stale=bool(getattr(hit, "is_stale", False)),
                    )
                )
            remaining -= used
    return rendered_hits


def _jump_route(source_type: str, source_id: str) -> str:
    if source_type == "knowledge_doc":
        return knowledge_jump_route(doc_id=source_id)
    if source_type == "knowledge_folder":
        return knowledge_jump_route(folder_id=source_id)
    if source_type == "workpaper":
        return f"/workpapers/{source_id}"
    if source_type == "note":
        return f"/disclosure-notes/{source_id}"
    if source_type == "report":
        return f"/reports/{source_id}"
    return ""


def _citation_payload(citation: Any) -> dict[str, Any]:
    source_type = str(getattr(citation, "source_type", "unknown"))
    source_id = str(getattr(citation, "source_id", ""))
    return {
        "source_type": source_type,
        "source_id": source_id,
        "source_name": getattr(citation, "source_name", None),
        "paragraph_index": getattr(citation, "paragraph_index", None),
        "excerpt": getattr(citation, "excerpt", "") or "",
        "doc_version": getattr(citation, "doc_version", None),
        "is_stale": bool(getattr(citation, "is_stale", False)),
        "jump_route": _jump_route(source_type, source_id),
    }
