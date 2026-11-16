"""Chat Run 的「当前未保存草稿」契约（draft overlay）

Feature: chat-host-draft-overlay
Requirements:
  - 2.2：纳入时必须携带 ``host_type`` / ``host_id`` / ``baseline_version`` /
    ``content_hash`` / ``content_length``。
  - 3：第一批只做**底稿**宿主；附注宿主已有 ``routers/note_ai.py`` 的 overlay，
    字段命名与校验口径必须与之一致（全平台只有一套 overlay 契约）。
  - 4.1：草稿按不可信内容处理（包装在 Task 3，本模块只负责形状与校验）。
  - 4.3：草稿内容不得写入 metrics / 日志 / 审计链 payload（只存 hash 与长度）——
    因此本模块**只暴露** ``content_hash`` 与 ``content_length`` 两个派生量，
    并刻意不提供任何"打印正文"的 ``__repr__`` / ``__str__`` 覆盖。

Design: §2 请求契约 / §3 服务端校验顺序（fail-closed）。

## 为什么正文必须由客户端提交

未保存正文只存在于编辑器内存里（design 基线 B5）；库里 ``checklist_responses`` /
``disclosure_notes`` 存的都是**已保存**值。服务端读库拿不到未保存内容，所以
"把未保存草稿纳入上下文"这件事在结构上要求前端提交正文。

这也是 ``content`` 在 ``run_contract.PRIVILEGED_REQUEST_FIELDS`` 里的**唯一**豁免来源
（见该模块的 ``_PRIVILEGED_EXEMPT_PATHS``）：豁免窄到 ``draft_overlay.content``
这一条键路径，顶层 / ``host`` 内 / ``mentions`` 内的 ``content`` 照旧拒绝。

## 为什么不采信客户端 hash 与长度

两者都是客户端可自由填写的量：长度可谎报成 1 而正文 10MB（绕过上限），
hash 可填成任意值（让"内容未变"的判定失效）。所以两个派生值一律服务端重算，
客户端值只留在诊断字段里，任何判定都不得读它。

## 为什么超限直接拒绝而不是裁剪

静默裁剪会让模型看到半截正文并据此作答，用户却以为整份草稿都进了上下文。
这种"看起来成功"的降级比报错危险得多（design §2 明令不裁剪）。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.ai_chat.contracts import HostType

__all__ = [
    "MAX_DRAFT_OVERLAY_CHARS",
    "DRAFT_OVERLAY_HOST_TYPES",
    "WORKPAPER_BUSINESS_VERSION_SOURCE",
    "DraftOverlayRef",
    "DraftOverlayDecision",
    "versions_match",
]

#: 未保存草稿正文的字符上限（与附注侧 overlay 同一口径）。
MAX_DRAFT_OVERLAY_CHARS = 200_000

#: 第一批接受 ``draft_overlay`` 的宿主类型。
#:
#: 附注宿主已有自己的 overlay 链路（``routers/note_ai.py`` 的 ``overlay_content``），
#: 语义已在、不重复建设；报表 / TB / 合并宿主的"未保存"语义尚未定义（多为只读派生
#: 视图），需独立设计。字段命名与校验口径仍与附注侧保持一致，避免出现两套 overlay 契约。
DRAFT_OVERLAY_HOST_TYPES: frozenset[HostType] = frozenset({HostType.workpaper})

#: 底稿宿主「当前业务版本」的权威来源（**单一真源**，前端 ``openedBaselineVersion()``
#: 必须镜像这一列）。
#:
#: = ``working_paper.updated_at``，序列化为 ISO-8601（带时区，UTC）。
#:
#: ## 为什么是 ``updated_at`` 而不是 ``content_revision``
#:
#: ``content_revision`` 是平台声明的「唯一 business content revision 域」，看起来更像
#: "业务版本"，但**不能**用于本判定，两个理由都是致命的：
#:
#: 1. **它在多条保存路径上根本不推进** —— ``univer-save`` 传 ``content_revision=None``
#:    （尚未迁入 ``ContentMutationService``）、``checklist-responses`` PUT 走裸 SQL 只写
#:    自己的 ``updated_at``。拿它当版本号会让"某人刚保存过"被判成"版本未变"，
#:    于是旧草稿被**静默纳入** —— 正是需求 6.3 明令禁止的形态（fail-open）。
#: 2. **前端读不到它**：没有任何通用端点把 ``content_revision`` 返回给页面
#:    （``store-projection`` 只服务 store-backed entry，覆盖率不是全集）。
#:    ``openedBaselineVersion()`` 因此无法镜像一个前端不可见的量。
#:
#: 而 ``updated_at``：
#:
#: * 被四条内容写路径**全部**推进（``wp_html_save`` / ``wp_editor_router.univer_save`` /
#:   ``wp_onlyoffice_router`` 回调 / ``custom_query`` 回写 均经
#:   ``workpaper_save_orchestrator.after_save`` 的 Step 2 写它），也覆盖 WOPI 落盘；
#: * 已经由 ``GET /api/projects/{pid}/working-papers/{wid}`` 返回给前端（字段
#:   ``updated_at``）—— 编辑器打开时本来就会取这条详情，零新增端点；
#: * 与附注侧 overlay 同口径（``note_ai.py`` 用的就是 ``note.updated_at.isoformat()``），
#:   满足需求 3「全平台只有一套 overlay 契约」。
#:
#: ## 已知边界（有意接受，方向是安全的）
#:
#: * 只改 ``checklist_responses`` 的保存不推进 ``updated_at`` ⇒ 这类并发改动**检测不到**。
#:   收窄它的正确做法是让 checklist 保存也推进 ``working_paper.updated_at``（跨模块改动，
#:   另立任务），本 spec 不顺手改写入方。
#: * 复核状态 / 分派变更也会推进 ``updated_at`` ⇒ 会多判一些 ``denied``。方向是
#:   **拒绝纳入**（保守），绝不会静默使用旧草稿。
WORKPAPER_BUSINESS_VERSION_SOURCE = "working_paper.updated_at"


class DraftOverlayRef(BaseModel):
    """客户端提交的「当前未保存草稿」引用（design §2）。

    ``host_id`` 必须等于 ``request.host.id`` —— 该一致性由
    :class:`app.services.ai_chat.run_contract.ChatRunRequest` 校验，因为本模型看不到
    宿主。不允许借 overlay 把别的宿主内容塞进本轮上下文：鉴权过的是 ``host``，
    内容却来自别处等于绕过宿主鉴权。

    ``model_config = frozen`` 让"校验后还能改正文"这件事在类型层面不成立；
    服务端重算的派生值用 ``object.__setattr__`` 在校验期写入。
    """

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    host_type: HostType = Field(..., description="宿主类型；第一批只接受 workpaper")
    host_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="宿主稳定 ID，须等于 request.host.id",
    )
    baseline_version: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="编辑器打开该宿主时的业务版本，用于判定草稿基于哪一版",
    )
    content: str = Field(..., description="未保存正文；服务端重新计算 hash 与长度")
    content_length: int | None = Field(
        None,
        ge=0,
        description="客户端自算的正文长度，只作诊断；上限校验以服务端实际长度为准",
    )
    #: 线上字段名仍是 ``content_hash``（与附注侧 overlay 同名），但 Python 侧显式叫
    #: ``client_content_hash``：让"读它的人"一眼看出这是**客户端**值。
    #: 权威摘要只能经 :attr:`content_hash` 取（服务端重算）。
    client_content_hash: str | None = Field(
        None,
        alias="content_hash",
        max_length=200,
        description="客户端自算的 sha256，只作诊断比对；服务端一律重算，不采信此值",
    )

    @field_validator("host_type")
    @classmethod
    def _must_be_supported(cls, value: HostType) -> HostType:
        if value not in DRAFT_OVERLAY_HOST_TYPES:
            raise ValueError(
                f"draft_overlay 暂不支持 {value.value} 宿主（当前支持："
                f"{sorted(t.value for t in DRAFT_OVERLAY_HOST_TYPES)}）"
            )
        return value

    @field_validator("content")
    @classmethod
    def _content_must_be_usable(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "draft_overlay.content 不能为空（没有未保存正文时不要提交该字段）"
            )
        # 🔴 用**实际**长度判上限，不看客户端传来的 content_length：后者可伪造为 1
        #    而正文 10MB，那样上限就形同虚设。
        if len(value) > MAX_DRAFT_OVERLAY_CHARS:
            raise ValueError(
                f"draft_overlay.content 长度 {len(value)} 超过上限 "
                f"{MAX_DRAFT_OVERLAY_CHARS} 字符，请先保存或缩小范围（不做静默裁剪）"
            )
        return value

    @model_validator(mode="after")
    def _recompute_server_derived_fields(self) -> "DraftOverlayRef":
        """服务端按**实际正文**重算长度，覆盖客户端声明值。

        覆盖而不是并存：若保留客户端值，下游任何一处误读 ``content_length`` 都会拿到
        可伪造的数；重算后该字段只剩一个含义 —— 服务端量出来的长度。
        """
        object.__setattr__(self, "content_length", len(self.content))
        return self

    @property
    def content_hash(self) -> str:
        """服务端重算的正文摘要（``sha256:<hex>``），**唯一**权威值。

        前缀与 manifest 契约（design §4 ``"content_hash": "sha256:…"``）一致。
        客户端送来的 ``content_hash`` 落在 :attr:`client_content_hash`，只作诊断，
        任何判定都不得读它 —— 两者不共用一个名字就是为了让误用读不到值。
        """
        return "sha256:" + hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def __repr_args__(self):
        """``repr`` / ``str`` 把正文替换成占位（需求 4.3）。

        🔴 Pydantic 的默认 ``__repr__`` 会打出 ``content='<整段草稿>'``，而它出现在
        任何一条 ``logger.error("…%s…", exc)`` / 异常链 / ``print`` / 调试器里就把
        未保存正文写进了日志。仅供排查的字段换成 hash 与长度即可定位问题，
        不需要原文。

        实测泄漏面（2026-11-15）：``repr(overlay)``、``str(overlay)``、
        ``repr({"draft_overlay": overlay})``、``repr(ChatRunRequest(...))`` 四处
        都会带出原文；``__repr_args__`` 一处覆盖全部（它们都经它渲染）。
        """
        for key, value in super().__repr_args__():
            if key == "content":
                yield (key, f"<已隐藏 {self.content_length} 字符 {self.content_hash}>")
            else:
                yield (key, value)


# ---------------------------------------------------------------------------
# 版本核对与纳入判定（design §3 步骤 6~7 / §4 manifest 条目）
# ---------------------------------------------------------------------------


def normalize_business_version(raw: object) -> str:
    """把宿主业务版本渲染成**可逐字比对**的 canonical 字符串。

    ``updated_at`` 是 ``timestamptz``：同一时刻从 PG 取回可能是 ``+00:00``，从前端
    JSON 回来可能是 ``Z`` 或带毫秒，直接字符串比会**假冲突**（同一版本被判成过期）。
    因此这里统一转成 UTC 的 ISO-8601（秒级截断，与 ``datetime.isoformat()`` 同形）。

    ``None``（宿主确实没有该列的值）渲染成空串 —— 由调用方决定如何判定，本函数不猜。
    认不出是时间的字符串**原样返回**（宁可比对失败判 ``denied``，也不要静默当成一致）。
    """
    if raw is None:
        return ""
    if isinstance(raw, datetime):
        value = raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    text = str(raw).strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def versions_match(baseline_version: str, current_version: object) -> bool:
    """``baseline_version`` 是否仍是宿主的当前业务版本。

    🔴 任一侧为空即判**不匹配**（fail-closed）：服务端读不出当前版本、或客户端没给基线时，
    "放行"等于在无法证明草稿新鲜的情况下静默使用它（需求 6.3 禁止）。
    """
    baseline = normalize_business_version(baseline_version)
    if not baseline:
        return False
    return baseline == normalize_business_version(current_version)


class DraftOverlayDecision(BaseModel):
    """一轮 Run 对 ``draft_overlay`` 的最终裁决（design §4 manifest 条目的来源）。

    ``status`` 只有两个取值，与 ``ContextManifestEntry`` 的 ``included`` / ``denied``
    语义一致：

    * ``included`` —— 版本一致，正文进入 system message，``used_tokens`` 计入预算；
    * ``denied`` —— 版本过期 / 读不出当前版本 / 宿主不支持，正文**不进入** system message，
      ``reason`` 为中文可读原因（前端在消息下方展示，不弹窗、不阻断）。

    ``content_hash`` / ``baseline_version`` **不论何种状态都填**：需求 6.2 要求 manifest
    能区分"已保存内容"与"未保存草稿"，而 ``denied`` 时同样需要让人看得出"拒绝的是哪一份
    草稿、基于哪一版"。两者都是派生量（hash 与时间戳），不含正文 —— 满足需求 4.3。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str = Field(..., description="included | denied")
    label: str = Field(..., description="中文展示名（底稿 xxx）")
    content_hash: str = Field(..., description="服务端重算的 sha256:<hex>")
    baseline_version: str = Field(..., description="草稿基于的宿主业务版本")
    content_length: int = Field(..., ge=0, description="正文字符数（不是正文）")
    reason: str = Field("", description="denied 时的中文原因")
    current_version: str = Field(
        "", description="服务端读到的宿主当前版本（denied 用于说明差异）"
    )

    @property
    def included(self) -> bool:
        return self.status == "included"

    def manifest_entry(self, *, used_tokens: int = 0) -> dict[str, object]:
        """转成 manifest 条目（``ContextManifestEntry`` 的额外字段 + 基字段）。

        ``source_type`` 由调用方给（``draft_overlay:workpaper``）—— 本模型不认识宿主类型，
        硬编码会把将来的 note 宿主写错。
        """
        return {
            "label": self.label,
            "status": self.status,
            "used_tokens": used_tokens,
            "reason": self.reason,
            "content_hash": self.content_hash,
            "baseline_version": self.baseline_version,
        }


def decide_draft_overlay(
    overlay: DraftOverlayRef,
    *,
    current_version: object,
    host_label: str = "",
) -> DraftOverlayDecision:
    """版本核对（design §3 步骤 6~7）：一致 → ``included``，否则 ``denied`` + 中文原因。

    **不抛异常**：任何失败都只降级为 ``denied``。design §3 明文要求"任何一步失败都不阻断
    整轮对话"，若这里抛出去，engine 的 ``except Exception`` 会把整轮 Run 变成
    ``context_build_failed`` —— 用户为了多问一句草稿反而彻底问不了话。

    ``host_label`` 是已授权的 ``AuthorizedHostContext.display_label``（如 ``B1-1 货币资金``），
    只用于 manifest 展示名；缺省时退回宿主稳定 ID（不猜、不额外查库）。
    """
    baseline = normalize_business_version(overlay.baseline_version)
    current = normalize_business_version(current_version)
    label = overlay_label(
        overlay.host_type, host_label or overlay.host_id, named=bool(host_label)
    )

    if versions_match(overlay.baseline_version, current_version):
        return DraftOverlayDecision(
            status="included",
            label=label,
            content_hash=overlay.content_hash,
            baseline_version=baseline,
            content_length=int(overlay.content_length or 0),
            current_version=current,
        )

    if not current:
        # 读不出当前版本 ⇒ 无法证明草稿新鲜。说法与服务端故障一致，避免"版本是空串"外泄。
        reason = (
            f"草稿基于版本 v{baseline or '（未知）'}，但服务端读不到该底稿的当前版本，"
            "本轮未纳入这份草稿；请先保存后重试"
        )
    else:
        reason = (
            f"草稿基于旧版本 v{baseline or '（未知）'}，当前 v{current}，请先保存或刷新"
        )
    return DraftOverlayDecision(
        status="denied",
        label=label,
        content_hash=overlay.content_hash,
        baseline_version=baseline,
        content_length=int(overlay.content_length or 0),
        reason=reason,
        current_version=current,
    )


def overlay_label(host_type: HostType, host_ref: str, *, named: bool = False) -> str:
    """manifest 展示名（design §4 ``"当前未保存草稿（底稿 B1-1）"``）。

    只用宿主类型与宿主标识，**不查库**：``display_label`` 已由
    ``HostContextResolver`` 在授权后加载，调用方直接传进来即可。
    """
    kind = {
        HostType.workpaper: "底稿",
        HostType.note: "附注",
        HostType.report: "报表",
    }.get(host_type, host_type.value)
    # named=True 表示 host_ref 是展示名（可能自带底稿编码），不再拼 "底稿" 前缀两次。
    target = host_ref if named else f"{kind} {host_ref}"
    return f"当前未保存草稿（{target}）"

