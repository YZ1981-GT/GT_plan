"""读取 sheet 级当前 published representation 的唯一入口。

spec: `onlyoffice-sheet-open-via-published-artifact` task 2.3

该模块只读 current pointer + published artifact。它不找模板、不复制文件、不隐藏 sheet。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState
from app.services.workpaper_sync.projection_target_resolution import (
    resolve_visible_current_representation_id,
)
from app.models.workpaper_sync_models import WorkpaperArtifact, WorkpaperContentRepresentation


class PublishedSheetArtifactError(RuntimeError):
    """当前 published sheet artifact 不能安全读取。

    `error_code` 是**机器可读**的封闭域；`reason` 是可直接展示的中文原因。两者都必须
    存在 —— 只给 code 会让前端 `catch` 后无话可说，只给中文会让调用方无法分支。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = code
        self.reason = PUBLISHED_SHEET_ARTIFACT_REASONS.get(code, DEFAULT_UNKNOWN_REASON)

    def as_dict(self) -> dict[str, str]:
        """端点直接回给前端的形态（`Requirement 2.3` / `3.3` 的 typed reason）。"""
        return {
            "error_code": self.error_code,
            "reason": self.reason,
            "detail": str(self),
        }


#: published sheet artifact 读取失败的**封闭**原因表。
#:
#: 🔴 每条都要能回答「用户下一步做什么」：`current_representation_missing` 与
#: `artifact_not_published` 看起来都是「没有文件」，但前者要「先在结构化视图里保存一次以
#: 发布首版」，后者要「等审批/发布流程完成」。合成一句话的后果是用户照着错误提示做了
#: 一件不该做的事。同理 `artifact_digest_drift` 不是「重试就好」（那只会一直漂），
#: 必须报给人看。
PUBLISHED_SHEET_ARTIFACT_REASONS: dict[str, str] = {
    "current_representation_missing": (
        "该底稿还没有已发布的在线编辑版本 —— 请先在结构化视图里保存一次以发布首版"
    ),
    "representation_row_missing": (
        "当前在线编辑版本与底稿/入口对不上 —— 可能是入口映射过期，请刷新页面重试；"
        "仍然失败请联系管理员核对入口映射"
    ),
    "artifact_not_published": (
        "该版本尚未通过发布流程 —— 请等待审批完成后再进入在线编辑"
    ),
    "artifact_candidate_rejected": (
        "该入口指向的是候选版本而非已发布版本 —— 候选版本不参与在线编辑，"
        "请等待发布完成或改选已发布版本"
    ),
    "artifact_path_unresolvable": (
        "已发布文件的位置无法解析 —— 请联系管理员检查存储配置"
    ),
    "artifact_missing": (
        "已发布的文件在磁盘上不存在 —— 请联系管理员恢复该版本文件"
    ),
    "artifact_digest_drift": (
        "已发布文件的内容与登记不一致（可能被外部修改）—— 请联系管理员核对；"
        "在核对前不要继续编辑，否则改动可能丢失"
    ),
    "artifact_ooxml_unreadable": (
        "已发布的工作簿无法解析 —— 文件可能损坏，请联系管理员重新发布"
    ),
    "target_sheet_not_in_published_artifact": (
        "已发布的工作簿里没有该入口声明的目标工作表 —— 可能是模板或映射已变更，"
        "请刷新页面重试；仍然失败请联系管理员核对入口映射"
    ),
    "target_sheet_document_type_mismatch": (
        "该入口声明的目标工作表与文件类型不匹配 —— 请刷新页面重试；"
        "仍然失败请联系管理员核对入口映射"
    ),
    "definition_bundle_drift": (
        "该版本冻结的定义包内容已被替换 —— 请重新进入在线编辑以刷新版本；"
        "如果打开后仍看到旧内容，请联系管理员"
    ),
}

#: 未登记 error_code 的兜底文案。刻意指向「联系管理员」而不是「重试」：
#: 未登记意味着我们不知道该怎么修，让用户反复重试只是消耗他自己的时间。
DEFAULT_UNKNOWN_REASON = "在线编辑暂时不可用 —— 请联系管理员并告知具体操作步骤"


@dataclass(frozen=True)
class PublishedSheetArtifact:
    project_id: UUID
    wp_id: UUID
    entry_id: str
    representation_id: UUID
    generation: int
    artifact_id: UUID
    artifact_sha256: str
    relative_path: str
    path: Path
    document_type: str
    target_sheet: str | None
    whole_workbook: bool
    sheet_names: tuple[str, ...]
    definition_bundle_id: UUID
    definition_bundle_sha256: str
    adapter_id: str


ResolveRepresentation = Callable[..., Awaitable[Any | None]]


async def read_current_published_sheet_artifact(
    *,
    session: Any,
    artifact_repository: CanonicalArtifactRepository,
    project_id: UUID,
    wp_id: UUID,
    entry_id: str,
    target_sheet: str | None,
    whole_workbook: bool,
    resolve_representation: ResolveRepresentation = resolve_visible_current_representation_id,
) -> PublishedSheetArtifact:
    """按 entry 读取可见 current representation，并验证 artifact 与 target sheet。

    顺序固定：current pointer → representation/artifact row → canonical visibility/path
    → sha256/size → OOXML target sheet。任何一步失败都不回退模板。
    """
    representation_id = await resolve_representation(session, entry_id=entry_id)
    if representation_id is None:
        raise PublishedSheetArtifactError(
            "current_representation_missing",
            f"entry {entry_id!r} 没有可见 current published representation",
        )

    from sqlalchemy import select

    result = await session.execute(
        select(WorkpaperContentRepresentation, WorkpaperArtifact)
        .join(WorkpaperArtifact, WorkpaperArtifact.id == WorkpaperContentRepresentation.artifact_id)
        .where(
            WorkpaperContentRepresentation.id == representation_id,
            WorkpaperContentRepresentation.wp_id == wp_id,
            WorkpaperContentRepresentation.entry_id == entry_id,
        )
    )
    row = result.first()
    if row is None:
        raise PublishedSheetArtifactError(
            "representation_row_missing",
            f"current representation {representation_id} 不属于底稿 {wp_id} / entry {entry_id}",
        )
    representation, artifact = row

    # candidate 拒绝（R2.3 / design §4.2）：候选版本不参与在线编辑。它与
    # `artifact_not_published` 分两类 —— 「state=candidate」是**正常流程中的中间态**
    # （用户自己的编辑还没发布），「state 不是 published」可能是配置错。
    if str(getattr(artifact, "state", "") or "") == ArtifactState.candidate.value:
        raise PublishedSheetArtifactError(
            "artifact_candidate_rejected",
            f"artifact {artifact.id} 处于 candidate 状态 —— 候选版本不得作为在线编辑文件",
        )
    if artifact.kind != ArtifactKind.canonical.value or artifact.state != ArtifactState.published.value:
        raise PublishedSheetArtifactError(
            "artifact_not_published",
            f"artifact {artifact.id} 不可解析：kind={artifact.kind!r} state={artifact.state!r}",
        )

    # bundle drift（R2.3 / AC 2.10）：representation 上冻结的 bundle digest 必须与它
    # FK 指向的那份 bundle 现算值一致。不一致说明 bundle 在发布后被 alias 换了内容 ⇒
    # 此时打开会让 descriptor 冻结一份「id 相同、内容已换」的假身份。
    await _assert_definition_bundle_frozen(session, representation)

    try:
        path = artifact_repository.resolve_published_artifact(
            project_id=project_id,
            kind=ArtifactKind.canonical,
            state=ArtifactState.published,
            relative_path=artifact.relative_path,
        )
    except Exception as exc:  # noqa: BLE001 — 保留 canonical resolver 的 error_code 在链路日志
        raise PublishedSheetArtifactError(
            "artifact_path_unresolvable", f"published artifact 路径不可解析: {exc}"
        ) from exc

    # 路径解析成功但文件不在：与「路径不可解析」分两类 —— 前者是配置/越权问题（管理员改），
    # 后者是文件被删/未落盘（要恢复文件）。合成一条会让运维去改根本没坏的配置。
    if not path.is_file():
        raise PublishedSheetArtifactError(
            "artifact_missing",
            f"published artifact 登记为 {artifact.relative_path!r} 但磁盘上没有该文件",
        )

    digest, size = artifact_repository.sha256_of_file(path)
    if digest != artifact.sha256 or size != int(artifact.size_bytes):
        raise PublishedSheetArtifactError(
            "artifact_digest_drift",
            f"artifact {artifact.relative_path} 内容漂移：登记 {artifact.sha256}/{artifact.size_bytes}，"
            f"现读 {digest}/{size}",
        )

    sheet_names: tuple[str, ...] = ()
    if artifact.document_type in {"xlsx", "xlsm"}:
        try:
            from openpyxl import load_workbook

            workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
            try:
                sheet_names = tuple(workbook.sheetnames)
            finally:
                workbook.close()
        except Exception as exc:  # noqa: BLE001
            raise PublishedSheetArtifactError(
                "artifact_ooxml_unreadable", f"published workbook 无法读取: {exc}"
            ) from exc
        if not whole_workbook and target_sheet not in sheet_names:
            raise PublishedSheetArtifactError(
                "target_sheet_not_in_published_artifact",
                f"published artifact 没有目标 sheet {target_sheet!r}；实际 sheet={list(sheet_names)!r}",
            )
    elif target_sheet and not whole_workbook:
        raise PublishedSheetArtifactError(
            "target_sheet_document_type_mismatch",
            f"document_type={artifact.document_type!r} 不支持 xlsx target sheet {target_sheet!r}",
        )

    return PublishedSheetArtifact(
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        representation_id=representation.id,
        generation=int(representation.generation),
        artifact_id=artifact.id,
        artifact_sha256=artifact.sha256,
        relative_path=artifact.relative_path,
        path=path,
        document_type=artifact.document_type,
        target_sheet=target_sheet,
        whole_workbook=whole_workbook,
        sheet_names=sheet_names,
        definition_bundle_id=representation.definition_bundle_id,
        definition_bundle_sha256=representation.definition_bundle_sha256,
        adapter_id=representation.adapter_id,
    )


__all__ = [
    "DEFAULT_UNKNOWN_REASON",
    "PUBLISHED_SHEET_ARTIFACT_REASONS",
    "PublishedSheetArtifact",
    "PublishedSheetArtifactError",
    "read_current_published_sheet_artifact",
]


async def _assert_definition_bundle_frozen(
    session: Any, representation: Any
) -> None:
    """representation 冻结的 bundle digest 必须等于 FK 指向那份的现算 digest。

    ═══ 为什么这条必须在这里（而不是只在 room 打开时）═══

    room 打开时有同样的校验，但**读 artifact 本身**是更早的一步：`/sync/entry-identity`
    这类只读端点只读文件、不开 room。少了这一步，`entry-identity` 会对一份「bundle 已被
    alias 换掉内容」的 representation 报 `room_ready`，随后真正 materialize 时才在 room
    打开处失败 —— 用户看到的是「说是能用、点进去报错」。

    ═══ 为什么直接比 digest 而不是复用 `RoomService.frozen_bundle_identity` ═══

    后者需要 `WorkpaperSyncRepository` + session 两件东西，而本模块的契约是「只拿 session」。
    为了复用它在 reader 里装配一个 repo 会把「只读文件」变成「装配半套服务」。所以这里做
    的判据**刻意更窄**：只比 representation 上冻结的 digest 与 bundle 行的现算 digest。

    ═══ 读不到 bundle 行怎么办 ═══

    不 fail-closed：bundle 行不存在是 `artifact_not_published` / `representation_row_missing`
    那一类的问题，而本函数的职责只是「已经有的那一行有没有漂」。读不到就跳过 —— 但要让
    调用方能分辨，所以异常类型与 message 都点名 bundle。
    """
    bundle_id = getattr(representation, "definition_bundle_id", None)
    frozen_digest = str(getattr(representation, "definition_bundle_sha256", "") or "")
    if bundle_id is None or not frozen_digest:
        raise PublishedSheetArtifactError(
            "definition_bundle_drift",
            f"representation {getattr(representation, 'id', '?')} 没有冻结 bundle "
            "id/digest —— 无法证明打开的是已批准的权威定义",
        )

    from sqlalchemy import select

    from app.models.workpaper_sync_models import WorkpaperSyncDefinitionBundle

    bundle = (
        await session.execute(
            select(WorkpaperSyncDefinitionBundle).where(
                WorkpaperSyncDefinitionBundle.id == bundle_id
            )
        )
    ).scalar_one_or_none()
    if bundle is None:
        # 见 docstring：这不是「漂移」，是「那一行不存在」，交给上游的 missing 类判据。
        return

    # ═══ 字段名必须现读，不能按命名习惯推 ═══
    # `WorkpaperSyncDefinitionBundle` 的列是 `canonical_payload_sha256`（不是
    # `bundle_sha256` / `sha256`）。按猜的字段名写 `getattr(..., "")` 会恒得空串
    # ⇒ 下面的「读不出 digest」分支恒触发 ⇒ 所有读路径都报 bundle drift。
    live_digest = str(getattr(bundle, "canonical_payload_sha256", "") or "")
    if not live_digest:
        # 行在但 digest 字段读法变了 ⇒ 不许静默通过（否则「改名就绕过漂移检测」）。
        raise PublishedSheetArtifactError(
            "definition_bundle_drift",
            f"bundle 行 {bundle_id} 读不出 canonical_payload_sha256 —— 漂移检测无法执行",
        )
    if live_digest != frozen_digest:
        raise PublishedSheetArtifactError(
            "definition_bundle_drift",
            f"representation 冻结的 bundle digest {frozen_digest[:12]}… 与 bundle 行现算 "
            f"{live_digest[:12]}… 不一致 —— bundle 在发布之后被替换过内容",
        )
