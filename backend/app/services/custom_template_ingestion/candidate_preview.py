"""Immutable candidate 静态预览与 candidate guidance（Task 9）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 6.2, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6

## design §9 硬裁决

candidate 尚未 ACTIVE → **只**输出经 sanitizer 的静态 HTML、不可执行图片或
结构化 JSON 报告。**绝不**产生生产 OnlyOffice config、WOPI URL 或可编辑 iframe。

这里用**结构性保证**锁死（不是散落 if）：

* 本模块没有任何产出生产 OO/WOPI config 的函数 —— ``test_candidate_preview.py``
  用 AST 扫描本模块，禁止出现 ``documentserver`` / ``wopi`` / ``document_key`` /
  ``editorConfig`` / editable-iframe emitter，并断言所有 ``PreviewSurface.kind``
  只落在 ``{static_html, noneexecutable_image, structure_json}``；
* 公式/链接/comments/names/properties 一律经 :func:`sanitize_cell_text` 转义为
  文本 —— 用真实危险载荷（``=cmd|``、DDE、``<script>``、外链 http）验证输出被
  转义、且不含任何可执行 sink。

## Requirement 9.5/9.6：digest 变化 / 过期即 stale

预览 token 绑定 candidate digest + 五个输入 digest（artifact/policy/scanner/
mapping/guidance）。任一 digest 变化 → token 失效 + 所有预览/确认 evidence stale。
candidate 过期 / 被拒绝 / superseded → token 失效 **且** runtime discoverability=0。

## 消费 G-C0（不复制）

guidance 预览通过 :mod:`guidance_gc0_contract` 的 candidate handoff variant
构建；**by-reference**：validate 走 ``validate_contract_version``，discriminator
取 ``GC0_DISCRIMINATORS``，禁止本地重定义任何 C0 top-level schema
（``test_gc0_reverse_dup_scan`` + 本模块 guidance builder 只填 candidate 字段）。
"""
from __future__ import annotations

import hashlib
import html
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping, Sequence

from app.services.custom_template_ingestion.lifecycles import (
    Clock,
    SystemClock,
    TemplateCandidate,
)
from app.services.custom_template_ingestion.mapping import (
    CustomProjectionManifest,
    ProjectionMode,
)

__all__ = [
    "PreviewSurfaceKind",
    "ALLOWED_PREVIEW_SURFACE_KINDS",
    "FORBIDDEN_PRODUCTION_SINKS",
    "PreviewError",
    "sanitize_cell_text",
    "PreviewSurface",
    "SheetPreview",
    "MappingPreview",
    "PreviewToken",
    "CandidatePreview",
    "CandidatePreviewService",
    "PREVIEW_TOKEN_TTL_SECONDS",
]


PREVIEW_TOKEN_TTL_SECONDS: float = 900.0  # 短期、一次性、candidate-scoped


class PreviewSurfaceKind(str, Enum):
    """允许的预览产物形态（Requirement 9.1）。

    仅这三种；**没有** onlyoffice_config / wopi_url / editable_iframe 成员 ——
    枚举本身就是结构性保证：本模块无法产出生产 OO/WOPI config。
    """

    STATIC_HTML = "static_html"
    NONEXECUTABLE_IMAGE = "nonexecutable_image"
    STRUCTURE_JSON = "structure_json"


#: 供 AST 守卫读取的允许集合（唯一真源）。
ALLOWED_PREVIEW_SURFACE_KINDS: frozenset[str] = frozenset(
    k.value for k in PreviewSurfaceKind
)

#: 生产 OO/WOPI/可执行 sink 的字面量黑名单（供 AST/文本守卫扫描本模块源码）。
#: 出现任意一条即视为「本模块能产出生产 config」——结构性 RED。
FORBIDDEN_PRODUCTION_SINKS: tuple[str, ...] = (
    "documentserver",
    "document_key",
    "documentkey",
    "editorconfig",
    "wopi",
    "callbackurl",
    "onlyoffice_config",
    "<iframe",
    "<script",
)


class PreviewError(ValueError):
    """预览无法安全生成（token stale / candidate 非可预览态等）。"""


# ─────────────────────────────────────────────────────────────────────────────
# Sanitizer（Requirement 9.2）
# ─────────────────────────────────────────────────────────────────────────────


def sanitize_cell_text(raw: Any) -> str:
    """把任意 cell / 公式 / 链接 / comment / name / property 值转义为纯文本。

    * 使用 stdlib ``html.escape(quote=True)`` —— 转义 ``& < > " '``；
    * 公式前导 ``=`` / ``+`` / ``-`` / ``@`` 不在服务端执行，只作文本展示；
    * 结果**永不**含可执行 sink：无 ``<script>``、无外链跳转、无 DDE 触发。

    该函数是纯函数、幂等在「已转义文本」上不会二次破坏语义（只会再转义 ``&`` 为
    ``&amp;``，仍是文本安全的）。
    """
    if raw is None:
        return ""
    text = raw if isinstance(raw, str) else str(raw)
    # html.escape 处理 XSS 关键字符；formula/DDE/external-link 全部沦为字面文本。
    return html.escape(text, quote=True)


# ─────────────────────────────────────────────────────────────────────────────
# 预览数据结构
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PreviewSurface:
    """一个静态预览面。``kind`` 必须落在 :data:`ALLOWED_PREVIEW_SURFACE_KINDS`。"""

    kind: PreviewSurfaceKind
    #: 已 sanitize 的载荷（HTML 字符串 / 结构 JSON 字符串 / 图片描述占位）。
    content: str
    #: 该面的媒体类型（仅描述，不产生可执行资源）。
    media_type: str

    def __post_init__(self) -> None:
        if self.kind not in PreviewSurfaceKind:
            raise PreviewError(f"非法预览面 kind: {self.kind!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "content": self.content,
            "mediaType": self.media_type,
        }


@dataclass(frozen=True, slots=True)
class MappingPreview:
    """mapping 预览：分别展示 managed/unmanaged、editable/read-only、mode、
    稳定身份与 preservation 风险（Requirement 9.3）。"""

    sheet_uid: str
    projection_mode: str
    editable: bool
    managed_field_ids: tuple[str, ...]
    unmanaged_field_ids: tuple[str, ...]
    stable_identities: tuple[str, ...]
    preservation_risks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheetUid": self.sheet_uid,
            "projectionMode": self.projection_mode,
            "editable": self.editable,
            "managedFieldIds": list(self.managed_field_ids),
            "unmanagedFieldIds": list(self.unmanaged_field_ids),
            "stableIdentities": list(self.stable_identities),
            "preservationRisks": list(self.preservation_risks),
        }


@dataclass(frozen=True, slots=True)
class SheetPreview:
    sheet_uid: str
    surfaces: tuple[PreviewSurface, ...]
    mapping: MappingPreview

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheetUid": self.sheet_uid,
            "surfaces": [s.to_dict() for s in self.surfaces],
            "mapping": self.mapping.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PreviewToken:
    """一次性、短期、candidate-scoped token；**不是** WOPI/OO config。

    token 绑定 candidate digest 与五个输入 digest 的组合指纹；任一变化 → token
    fingerprint 不匹配 → :meth:`is_valid_for` 返回 False（stale）。
    """

    token_id: str
    candidate_id: str
    bound_fingerprint: str
    issued_at: datetime
    expires_at: datetime

    def is_expired(self, clock: Clock) -> bool:
        return clock.now() >= self.expires_at

    def is_valid_for(
        self,
        *,
        candidate: TemplateCandidate,
        clock: Clock,
        candidate_active_or_pending: bool,
    ) -> bool:
        """token 仍然有效当且仅当：

        * 未过期；
        * candidate 未过期/被拒/superseded（``candidate_active_or_pending``）；
        * 绑定指纹仍等于当前 candidate 派生指纹（digest 未变）。
        """
        if self.candidate_id != candidate.candidate_id:
            return False
        if self.is_expired(clock):
            return False
        if not candidate_active_or_pending:
            return False
        return self.bound_fingerprint == _candidate_fingerprint(candidate)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tokenId": self.token_id,
            "candidateId": self.candidate_id,
            "boundFingerprint": self.bound_fingerprint,
            "issuedAt": self.issued_at.isoformat(),
            "expiresAt": self.expires_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class CandidatePreview:
    """一次预览生成结果：token + 各 sheet 静态面 + guidance 预览 + 输入指纹。"""

    candidate_id: str
    candidate_digest: str
    preview_fingerprint: str
    token: PreviewToken
    sheets: tuple[SheetPreview, ...]
    guidance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidateId": self.candidate_id,
            "candidateDigest": self.candidate_digest,
            "previewFingerprint": self.preview_fingerprint,
            "token": self.token.to_dict(),
            "sheets": [s.to_dict() for s in self.sheets],
            "guidance": self.guidance,
        }


def _candidate_fingerprint(candidate: TemplateCandidate) -> str:
    """由 candidate 的**每一个**输入 digest 派生预览指纹（Requirement 9.5）。

    🔴 指纹**只**由 artifact/policy/scanner/mapping/guidance/adapter 六个输入
    digest 组成，**不**纳入 candidate.digest 这个 rollup —— 因为 rollup 会掩盖
    「某单个 digest 从指纹里被漏掉」的守卫缺陷（rollup 变了就一定被发现，导致
    单点变异永远 GREEN）。逐个列出让「漏掉任一 digest」成为可被变异捕获的真实
    守卫缺口：任一 digest 变化 → 指纹变化 → 预览/token stale。
    """
    payload = json.dumps(
        {
            "artifact": candidate.artifact_sha256,
            "policy": candidate.policy_digest,
            "scanner": candidate.scanner_digest,
            "mapping": candidate.mapping_digest,
            "guidance": candidate.guidance_digest,
            "adapter": candidate.adapter_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# 静态面构建（只经 sanitizer；无任何生产 config）
# ─────────────────────────────────────────────────────────────────────────────


def _build_static_html_surface(
    *,
    sheet_uid: str,
    cell_texts: Sequence[Any],
    formulas: Sequence[Any],
    comments: Sequence[Any],
    defined_names: Sequence[Any],
    properties: Mapping[str, Any],
) -> PreviewSurface:
    """把 cell/formula/comment/name/property 全部 sanitize 后拼成只读 HTML 片段。

    片段没有 ``<script>``、没有 ``<iframe>``、没有事件属性、没有外链 ``href`` 跳转 ——
    只有转义文本包在 ``<div>/<span>`` 里。公式/DDE/外链在这里都是纯文本。
    """
    parts: list[str] = [f'<section data-sheet="{sanitize_cell_text(sheet_uid)}">']
    parts.append('<div class="cells">')
    for value in cell_texts:
        parts.append(f'<span class="cell">{sanitize_cell_text(value)}</span>')
    parts.append("</div>")
    parts.append('<div class="formulas">')
    for fx in formulas:
        # 公式一律作文本；前导 = 不执行。
        parts.append(f'<code class="formula">{sanitize_cell_text(fx)}</code>')
    parts.append("</div>")
    parts.append('<div class="comments">')
    for cm in comments:
        parts.append(f'<span class="comment">{sanitize_cell_text(cm)}</span>')
    parts.append("</div>")
    parts.append('<div class="names">')
    for nm in defined_names:
        parts.append(f'<span class="name">{sanitize_cell_text(nm)}</span>')
    parts.append("</div>")
    parts.append('<dl class="properties">')
    for key, val in properties.items():
        parts.append(
            f"<dt>{sanitize_cell_text(key)}</dt>"
            f"<dd>{sanitize_cell_text(val)}</dd>"
        )
    parts.append("</dl>")
    parts.append("</section>")
    return PreviewSurface(
        kind=PreviewSurfaceKind.STATIC_HTML,
        content="".join(parts),
        media_type="text/html; charset=utf-8",
    )


def _build_structure_surface(structure: Mapping[str, Any]) -> PreviewSurface:
    """结构 JSON 面：只序列化结构描述，字符串值全经 sanitize。"""
    safe = _sanitize_structure(structure)
    return PreviewSurface(
        kind=PreviewSurfaceKind.STRUCTURE_JSON,
        content=json.dumps(safe, sort_keys=True, ensure_ascii=False),
        media_type="application/json",
    )


def _build_image_surface(*, sheet_uid: str, width: int, height: int) -> PreviewSurface:
    """不可执行图片面：只描述服务端已渲染位图的元数据，不含脚本/外链。

    这里返回一个纯文本描述（生产由 server-side rasterizer 产出 PNG 字节，也不含
    任何可执行内容）。绝不返回 SVG 内联脚本或 data-URI 可执行内容。
    """
    descriptor = {
        "sheetUid": sanitize_cell_text(sheet_uid),
        "width": int(width),
        "height": int(height),
        "encoding": "server_rasterized_bitmap",
    }
    return PreviewSurface(
        kind=PreviewSurfaceKind.NONEXECUTABLE_IMAGE,
        content=json.dumps(descriptor, sort_keys=True, ensure_ascii=False),
        media_type="image/png",
    )


def _sanitize_structure(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return {sanitize_cell_text(k): _sanitize_structure(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_structure(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)):
        return obj
    if obj is None:
        return None
    return sanitize_cell_text(obj)


def _mapping_preview(manifest: CustomProjectionManifest) -> MappingPreview:
    editable = manifest.projection_mode is ProjectionMode.EDITABLE_GRID
    identities: list[str] = []
    for fm in manifest.fields:
        identities.append(fm.identity.identity_key)
    if manifest.row_identity is not None:
        identities.append(f"row:{manifest.row_identity.carrier_key}")
    if manifest.column_identity is not None:
        identities.append(f"col:{manifest.column_identity.carrier_key}")
    risks = tuple(
        f"{p.feature}:{p.decision}"
        for p in manifest.preservation_decisions
    )
    return MappingPreview(
        sheet_uid=manifest.sheet_uid,
        projection_mode=manifest.projection_mode.value,
        editable=editable,
        managed_field_ids=tuple(sorted(manifest.managed_field_ids)),
        unmanaged_field_ids=tuple(sorted(manifest.unmanaged_field_ids)),
        stable_identities=tuple(identities),
        preservation_risks=risks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 预览服务
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SheetPreviewInput:
    """预览一个 sheet 需要的原始（不可信）观测值 + 该 sheet 的 manifest。"""

    sheet_uid: str
    manifest: CustomProjectionManifest
    cell_texts: tuple[Any, ...] = ()
    formulas: tuple[Any, ...] = ()
    comments: tuple[Any, ...] = ()
    defined_names: tuple[Any, ...] = ()
    properties: Mapping[str, Any] = field(default_factory=dict)
    structure: Mapping[str, Any] = field(default_factory=dict)
    image_width: int = 800
    image_height: int = 600


class CandidatePreviewService:
    """生成 candidate 静态预览与 candidate guidance 预览。

    职责边界：
      * 只生成 :class:`PreviewSurface`（三种允许 kind）+ guidance 预览；
      * 绑定短期一次性 token；
      * digest 变化 / candidate 非可预览态 → token stale（不返回预览）。

    **不**做：生产 OO/WOPI config、instantiate、finalize。
    """

    def __init__(self, *, clock: Clock | None = None) -> None:
        self.clock: Clock = clock or SystemClock()

    def issue_token(self, candidate: TemplateCandidate) -> PreviewToken:
        now = self.clock.now()
        return PreviewToken(
            token_id=f"prev-{uuid.uuid4().hex[:16]}",
            candidate_id=candidate.candidate_id,
            bound_fingerprint=_candidate_fingerprint(candidate),
            issued_at=now,
            expires_at=now + timedelta(seconds=PREVIEW_TOKEN_TTL_SECONDS),
        )

    def build_preview(
        self,
        *,
        candidate: TemplateCandidate,
        sheets: Sequence[SheetPreviewInput],
        guidance_handoff: Mapping[str, Any],
        candidate_active_or_pending: bool = True,
    ) -> CandidatePreview:
        """生成完整预览。

        * candidate 过期/被拒/superseded（``candidate_active_or_pending`` False）→
          直接 :class:`PreviewError`（token 失效且 discoverability=0，不生成预览）；
        * guidance_handoff 必须是 G-C0 **candidate** handoff variant，经
          :func:`build_candidate_guidance_preview` 校验（拒绝 finalized/confirmed）。
        """
        if not candidate_active_or_pending:
            raise PreviewError(
                "candidate 已过期/被拒/superseded：预览 token 失效，discoverability=0"
            )

        token = self.issue_token(candidate)
        sheet_previews: list[SheetPreview] = []
        for si in sheets:
            surfaces = (
                _build_static_html_surface(
                    sheet_uid=si.sheet_uid,
                    cell_texts=si.cell_texts,
                    formulas=si.formulas,
                    comments=si.comments,
                    defined_names=si.defined_names,
                    properties=si.properties,
                ),
                _build_structure_surface(si.structure),
                _build_image_surface(
                    sheet_uid=si.sheet_uid,
                    width=si.image_width,
                    height=si.image_height,
                ),
            )
            sheet_previews.append(SheetPreview(
                sheet_uid=si.sheet_uid,
                surfaces=surfaces,
                mapping=_mapping_preview(si.manifest),
            ))

        from app.services.custom_template_ingestion.candidate_guidance import (
            build_candidate_guidance_preview,
        )

        guidance = build_candidate_guidance_preview(guidance_handoff)

        return CandidatePreview(
            candidate_id=candidate.candidate_id,
            candidate_digest=candidate.digest,
            preview_fingerprint=_candidate_fingerprint(candidate),
            token=token,
            sheets=tuple(sheet_previews),
            guidance=guidance,
        )

    def is_preview_stale(
        self,
        *,
        token: PreviewToken,
        candidate: TemplateCandidate,
        candidate_active_or_pending: bool,
    ) -> bool:
        """预览/确认 evidence 是否 stale（Requirement 9.5/9.6）。

        token 对当前 candidate 无效即 stale。
        """
        return not token.is_valid_for(
            candidate=candidate,
            clock=self.clock,
            candidate_active_or_pending=candidate_active_or_pending,
        )
