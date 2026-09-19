"""OO 编辑器启动面的服务层：contents token、contents 解析、launch config 签名。

═══ 为什么单独一个模块（G4-3）═══

G4-0d 为了让 DocServer 能拉到文件、并让 callback 带齐 room-bound 四项，把三件事直接
写进了 `wp_sync_router.py`：

1. `document.url` 用的短 TTL token 的签发与验签（`jwt.encode` / `jwt.decode`）；
2. 送进 DocEditor 的 OnlyOffice launch config 的组装与整体签名；
3. contents 端点的 room → representation → artifact → 磁盘路径解析（含 4 个裸 404）。

这三件都是**业务判定**，不是参数搬运。Task 28 对 router 的三条形态约束因此同时被违反：

* `test_the_router_never_decodes_a_jwt` —— 验签只许在 service 层（callback 侧在
  `callback_route`，启动侧就是本模块）；
* `test_the_router_builds_no_second_onlyoffice_config` —— router 里出现完整 config
  字面量就等于 descriptor 有了第二个来源，两份迟早漂移；
* `test_404_has_exactly_one_construction_site` —— 多份 404 文案迟早分化出「资源不存在」
  与「无权访问」两种措辞，那就是存在性预言机。

本模块只抛**类型化域异常**，绝不构造 `HTTPException`：状态码映射是 router 的事，
域判定是本模块的事。两者混在一起，就没法在不启动 FastAPI 的情况下测这些判定。

═══ 签名顺序的硬约束（踩过坑，勿动）═══

JWT 必须对**最终**送进 DocEditor 的字段签名，且签名后**只**允许再加 `token` 本身。
在签名后再改 `type` / `user` 会让 DocsAPI 客户端校验失败并静默丢掉 token，OO 侧表现为
`jwt must be provided token=undefined` / `editor_error_-20`。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.workpaper_sync.models import SyncDomainError

#: contents token 的用途标记。换值即换协议，旧 token 一律失效。
CONTENTS_TOKEN_PURPOSE: Final[str] = "room_contents"

#: 短 TTL：只够 DocServer 拉一次文件，与 descriptor 生命周期解耦（AC 10.7）。
DEFAULT_CONTENTS_TTL_SECONDS: Final[int] = 600

_XLSX_MEDIA: Final[str] = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


# ═══════════════════════════════════════════════════════════════════════════
# 类型化域异常
# ═══════════════════════════════════════════════════════════════════════════


class RoomLaunchError(SyncDomainError):
    """启动面失败基类。"""

    error_code = "sync_room_launch_invalid"


class RoomLaunchSecretMissingError(RoomLaunchError):
    """未配置 `ONLYOFFICE_JWT_SECRET`。

    **不放行**：签发无签名的 contents URL 等于把 representation 字节暴露给任何知道
    room_id 的人；验签侧缺 secret 时放行同理。两侧都必须 fail closed。
    """

    error_code = "sync_room_launch_secret_missing"


class RoomContentsTokenInvalidError(RoomLaunchError):
    """token 缺失、签名不符、过期或用途不符。映射到 401。"""

    error_code = "sync_room_contents_token_invalid"


class RoomContentsTokenScopeError(RoomContentsTokenInvalidError):
    """token 合法但绑的不是这个 room。

    单独一类而不是复用上面那个：它区分「伪造/过期」与「拿 A room 的 token 去要 B room」
    —— 后者是横向越权尝试，值得单独可查。**对外响应体仍与上面一致**，不做措辞区分。
    """

    error_code = "sync_room_contents_token_scope_mismatch"


class RoomContentsUnavailableError(RoomLaunchError):
    """room / representation / artifact / 磁盘文件任一环缺失。

    四种缺失**刻意合成一类**：对外必须是同一个不可见响应，否则 DocServer 侧（以及任何
    能构造 token 的人）可以据文案差异反推「这个 representation 存在但文件没了」。
    `reason` 只进服务端日志与 evidence，不进响应体。
    """

    error_code = "sync_room_contents_unavailable"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class RoomContentsDigestMismatchError(RoomLaunchError):
    """token 里冻结的 `artifact_sha256` 与当前 representation 不符 ⇒ 代际已变。映射到 409。"""

    error_code = "sync_room_contents_digest_mismatch"


# ═══════════════════════════════════════════════════════════════════════════
# contents token：签发与验签
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RoomContentsClaims:
    """已验签的 contents token claim。"""

    room_id: uuid.UUID
    representation_id: uuid.UUID
    artifact_sha256: str
    #: 本次打开要定位到的工作表全名（整册 workbook 用；空串 = 不定位，保持原 activeTab）。
    sheet: str = ""


def sign_room_contents_token(
    *,
    secret: str,
    room_id: uuid.UUID,
    representation_id: uuid.UUID,
    artifact_sha256: str,
    sheet: str = "",
    ttl_seconds: int = DEFAULT_CONTENTS_TTL_SECONDS,
) -> str:
    """签发 `document.url` 用的短 TTL token。

    `artifact_sha256` 进 claim 是为了让**代际**也被冻结：光有 representation_id 时，
    该 representation 若被重新物化成新字节，旧 URL 仍能拉到新内容，OO 侧就会拿到一份
    与 descriptor 不同代的文件而毫无察觉。
    """
    from jose import jwt

    if not str(secret or "").strip():
        raise RoomLaunchSecretMissingError(
            "缺少 ONLYOFFICE_JWT_SECRET —— 不得签发无签名的 room contents URL"
        )
    now = int(time.time())
    payload: dict[str, Any] = {
        "pur": CONTENTS_TOKEN_PURPOSE,
        "room_id": str(room_id),
        "representation_id": str(representation_id),
        "artifact_sha256": str(artifact_sha256),
        "iat": now,
        "exp": now + int(ttl_seconds),
    }
    # 🔴 目标 sheet 进 claim（而不是 query 参数）：它必须与 room/representation 一起被签名，
    #    否则任何人都能改 URL 让 OO 打开另一张 sheet 的定位（虽只是视图状态，但 URL 可篡改
    #    这件事本身不该存在）。空串不写进 claim，保持旧 token 形态与向后兼容。
    if str(sheet or "").strip():
        payload["sheet"] = str(sheet).strip()
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_room_contents_token(
    token: str, *, secret: str, expected_room_id: uuid.UUID
) -> RoomContentsClaims:
    """验签并把 claim 与路径上的 room 对齐。任何一步不符即抛，绝不返回半个 claim。"""
    from jose import JWTError, jwt

    if not str(secret or "").strip():
        raise RoomLaunchSecretMissingError(
            "缺少 ONLYOFFICE_JWT_SECRET —— 无法校验 room contents token"
        )
    if not str(token or "").strip():
        raise RoomContentsTokenInvalidError("缺少 contents token")
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError as exc:
        raise RoomContentsTokenInvalidError("contents token 验签失败或已过期") from exc
    if not isinstance(claims, Mapping):
        raise RoomContentsTokenInvalidError("contents token 载荷不是对象")
    if claims.get("pur") != CONTENTS_TOKEN_PURPOSE:
        raise RoomContentsTokenInvalidError("contents token 用途不符")
    if str(claims.get("room_id") or "") != str(expected_room_id):
        raise RoomContentsTokenScopeError("contents token 绑定的不是该 room")
    try:
        return RoomContentsClaims(
            room_id=uuid.UUID(str(claims["room_id"])),
            representation_id=uuid.UUID(str(claims["representation_id"])),
            artifact_sha256=str(claims.get("artifact_sha256") or ""),
            sheet=str(claims.get("sheet") or ""),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise RoomContentsTokenInvalidError(f"contents token claim 非法：{exc}") from exc


# ═══════════════════════════════════════════════════════════════════════════
# contents 解析：token → room → representation → artifact → 磁盘路径
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ResolvedRoomContents:
    """可以直接交给 `FileResponse` 的三件套。

    `data` 非 None 时调用方必须回**字节流**而不是 `FileResponse(path)`：那是「按本次打开的
    目标 sheet 设了 activeTab」的派生字节（见 :func:`resolve_room_contents`）。
    磁盘上的 canonical artifact 永不被改写。
    """

    path: Path
    media_type: str
    filename: str
    #: 视图定位后的派生字节（None = 直接发磁盘原文件）。
    data: bytes | None = None


async def resolve_room_contents(
    session: AsyncSession,
    *,
    room_id: uuid.UUID,
    token: str,
    secret: str,
    artifacts: Any,
) -> ResolvedRoomContents:
    """把一枚 contents token 解析成磁盘上的 representation 字节。

    :param artifacts: `CanonicalArtifactRepository` —— 路径解析**只**走它，
        禁止在此自拼 `backend/storage`（总控 §3.3 的路径安全唯一真源）。

    校验顺序刻意是「先验签、再对 room、再对 representation 归属、最后对 digest」：
    每一步都缩小可见面，任一步失败都在拿到磁盘路径之前。
    """
    from app.models.workpaper_sync_models import (
        WorkpaperArtifact,
        WorkpaperContentRepresentation,
        WorkpaperOoRoom,
    )

    claims = verify_room_contents_token(token, secret=secret, expected_room_id=room_id)

    room = (
        await session.execute(sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room_id))
    ).scalar_one_or_none()
    if room is None:
        raise RoomContentsUnavailableError("room 不存在")

    rep = (
        await session.execute(
            sa.select(WorkpaperContentRepresentation).where(
                WorkpaperContentRepresentation.id == claims.representation_id
            )
        )
    ).scalar_one_or_none()
    if rep is None:
        raise RoomContentsUnavailableError("representation 不存在")
    if str(rep.wp_id) != str(room.wp_id):
        # 跨 wp 取 representation：与横向越权同型，不得因「token 验签通过」放行。
        raise RoomContentsUnavailableError("representation 不属于该 room 的底稿")
    if claims.artifact_sha256 and str(rep.artifact_sha256) != claims.artifact_sha256:
        raise RoomContentsDigestMismatchError(
            "representation 字节已变 —— 该 contents URL 属于上一代际"
        )

    artifact = (
        await session.execute(
            sa.select(WorkpaperArtifact).where(WorkpaperArtifact.id == rep.artifact_id)
        )
    ).scalar_one_or_none()
    if artifact is None:
        raise RoomContentsUnavailableError("artifact 行不存在")

    path = artifacts.resolve_relative_path(str(artifact.relative_path))
    if not path.is_file():
        raise RoomContentsUnavailableError("artifact 文件不在磁盘上")

    document_type = str(artifact.document_type or "")
    media_type = _XLSX_MEDIA if document_type == "xlsx" else "application/octet-stream"
    filename = f"{str(rep.entry_id).replace('/', '_')}.{document_type}"

    # ── 整册 workbook 的「打开即定位」：按 token 里冻结的目标 sheet 设 activeTab ──
    #
    # 🔴 为什么在**这里**做，而不是在物化时写进 artifact：
    #   1. 一份 artifact 被**多张受管 sheet 共享**（D4 的 D4-2/25/26/27/28 同一 entry 同一
    #      workbook）。把 activeTab 写进 artifact 只能有一个值，D4-26 打开就会停在 D4-25。
    #   2. activeTab 是**打开时的视图状态**，不是内容。物化只在内容变更时发生，复用既有
    #      artifact 的打开（幂等复用路径）根本不会经过物化 ⇒ 绑在物化上必然漏。
    #   3. canonical artifact 的 `artifact_sha256` 被 descriptor / digest 校验锁死，
    #      事后改写文件会让 digest 不符。故这里只产**派生字节**，磁盘原文件一个字节不动。
    #
    # 尽力而为：任何异常都退回原文件（定位失败最多是「没帮用户跳过去」，不影响可编辑性）。
    data: bytes | None = None
    if document_type == "xlsx" and str(claims.sheet or "").strip():
        try:
            from app.services.workpaper_sync.excel_sheet_visibility import (
                derive_bytes_with_active_sheet,
            )

            data = derive_bytes_with_active_sheet(path.read_bytes(), claims.sheet.strip())
        except Exception:  # noqa: BLE001 - 视图定位失败不得影响内容可达性
            data = None

    return ResolvedRoomContents(
        path=path, media_type=media_type, filename=filename, data=data
    )


# ═══════════════════════════════════════════════════════════════════════════
# launch config：组装 + 整体签名
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class LaunchUserIdentity:
    """OO 协同身份。缺它时 DocsAPI 日志里会落到字面量 `userId`，协作贡献者分不开。"""

    id: str
    name: str


def build_signed_launch_config(
    *,
    raw_config: Mapping[str, Any] | None,
    document_url: str,
    callback_url: str,
    document_type: str,
    user: LaunchUserIdentity,
    secret: str,
    lang: str = "zh-CN",
) -> dict[str, Any]:
    """在 coordinator 产出的 config 上补齐短 TTL URL 与协同身份，然后整体签名。

    coordinator 的 `onlyoffice_config` **刻意不含** URL（避免与 descriptor 生命周期绑死），
    所以补键这一步必须有；但它只允许**在既有结构上补**，产出的仍是同一份 config，
    不是第二份真源。

    `autosave` 必须保持开启：关掉它本地改格不会到达 DocServer，随后 CS forcesave 会回
    `error=4`（无未保存改动），表现为「明明改了却同步不回来」。
    `forcesave=false` 是因为强制保存由平台在 room 层显式发起，不交给编辑器自作主张。
    """
    from jose import jwt

    raw: Mapping[str, Any] = raw_config or {}

    document = dict(raw.get("document") or {})
    document["url"] = document_url

    editor = dict(raw.get("editorConfig") or {})
    editor["callbackUrl"] = callback_url
    if not editor.get("lang"):
        editor["lang"] = lang
    if not isinstance(editor.get("user"), dict) or not editor["user"]:
        editor["user"] = {"id": user.id, "name": user.name}
    customization = dict(editor.get("customization") or {})
    customization["autosave"] = True
    customization["forcesave"] = False
    editor["customization"] = customization

    # 只保留 OO 认识的顶层键（generation / write_fence_epoch 已在 descriptor 顶层）
    config: dict[str, Any] = {
        "document": document,
        "documentType": raw.get("documentType")
        or ("cell" if str(document_type or "") == "xlsx" else "word"),
        "editorConfig": editor,
        "type": "desktop",
    }

    if str(secret or "").strip():
        encoded = jwt.encode(config, secret, algorithm="HS256")
        if isinstance(encoded, bytes):
            encoded = encoded.decode("ascii")
        # 🔴 签名后唯一允许新增的字段。再动任何一个键都会让 DocsAPI 丢 token。
        config["token"] = encoded
    return config


# ═══════════════════════════════════════════════════════════════════════════
# 打开即定位：(entry, sheet_key) → 工作簿内的物理 sheet 名
# ═══════════════════════════════════════════════════════════════════════════


def resolve_launch_target_sheet(*, contract: Any, sheet_key: str) -> str:
    """本次打开要定位到的**物理** sheet 名；解析不到返回 `""`（= 不定位）。

    唯一真源是该 entry 的 **approved 契约** ``sheets[].sheet_key → excel_name``。
    不从 ``sheet_key`` 反推名字（``d4-26-managed`` 与 ``境外销售收入检查D4-26`` 之间
    没有任何可推导关系），也不去模板目录里猜文档。

    🔴 为什么必须按 **entry 的契约** 查，而不是按 wp_code 去模板目录找：
    一个 wp_code 在磁盘上可能有**多份文档**。``backend/wp_templates/D`` 下 D4 就有 9 份
    xlsx，其中 ``D4-1至D4-4 …（Leap-常规程序）.xlsx`` 只有 10 张 sheet、**根本不含**
    ``境外销售收入检查D4-26``（它在 ``D4-22至D4-32…IPO…xlsx`` 与整册本里）。
    契约把 entry 钉在唯一一份工作簿上（``xlsx/gt-d4-operating-revenue`` →
    ``D/D4 收入底稿.xlsx``，46 张 sheet、13 张受管），所以它声明的 ``excel_name``
    **必然**落在本次要下发的那份 artifact 里 —— 文档与定位一次解析同时确定，
    不存在「定位到一张不在这本工作簿里的 sheet」。

    解析不到即返回空串（**不抛**）：定位是视图便利，不该让整条打开链路失败。
    未登记契约的 entry、未声明的 sheet_key、单 sheet 契约都落这条，行为与改动前一致。
    """
    key = str(sheet_key or "").strip()
    if not key or contract is None:
        return ""
    for sheet in getattr(contract, "sheets", ()) or ():
        if str(getattr(sheet, "sheet_key", "") or "").strip() == key:
            return str(getattr(sheet, "excel_name", "") or "").strip()
    return ""


def build_contents_url(*, base_url: str, room_id: uuid.UUID, token: str) -> str:
    """`document.url` 的唯一拼装点 —— 路径与 `public_router` 上那条路由必须同源。"""
    return (
        f"{str(base_url).rstrip('/')}"
        f"/api/workpaper-sync/rooms/{room_id}/contents?token={token}"
    )


__all__ = [
    "CONTENTS_TOKEN_PURPOSE",
    "DEFAULT_CONTENTS_TTL_SECONDS",
    "LaunchUserIdentity",
    "ResolvedRoomContents",
    "RoomContentsClaims",
    "RoomContentsDigestMismatchError",
    "RoomContentsTokenInvalidError",
    "RoomContentsTokenScopeError",
    "RoomContentsUnavailableError",
    "RoomLaunchError",
    "RoomLaunchSecretMissingError",
    "build_contents_url",
    "build_signed_launch_config",
    "resolve_launch_target_sheet",
    "resolve_room_contents",
    "sign_room_contents_token",
    "verify_room_contents_token",
]
