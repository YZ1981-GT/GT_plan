# -*- coding: utf-8 -*-
"""OnlyOffice 编辑器 **room 身份** 的唯一生产接线点（Task 21 / AC 2.7 / Property 6）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 21

═══ 一、这个模块存在的理由 ═══

Task 21 把 room 身份（doc_key / generation / route credential）收敛进
:mod:`app.services.workpaper_sync.rooms`，但在本模块出现之前，那套策略层在
`workpaper_sync` 包**之外零调用点** —— 也就是典型的 additive 死代码（假绿第①源）：
守卫全绿、registry 的 RoomFacts 探针全绿，而生产 `/onlyoffice-config` 端点仍在用
`hash(wp_code + st_mtime_ns)` 派生 doc_key。

`entry_source_facts.room_service_wiring()` 用 AST 实扫 `backend/app/**`（排除
`workpaper_sync`）里 `derive_doc_key` / `RoomService` 的调用点，正是为了让「接没接线」
成为**机器可读事实**而不是一句声明。本模块是那个事实的落点，它必须真的被 router 调用。

═══ 二、为什么 mtime 一定要拿掉，以及拿掉之后会发生什么 ═══

旧实现 `_generate_doc_key(file_path, wp_code) = md5(wp_code + st_mtime_ns)` 的真实后果
不是「不好看」：

* **任何一次写盘都会轮转 doc_key**。OO 把新 key 当成另一个文档，进行中的协同会话被
  切断，已连接用户的编辑落到旧 key 的房间里再也回不来。
* 两个用户在**不同时刻**打开同一底稿会拿到**不同** key（各自一间房），于是最后一个
  保存的人静默覆盖另一个人的全部改动 —— AC 2.8「同一 generation 的协同用户可进入同一
  active room」在旧实现下**不可能**成立。

拿掉 mtime 之后，doc_key 只随 `(wp_id, entry_id, generation)` 变化。存量 sheet 端点
有一处**依赖** mtime 轮转的行为：`_hide_non_target_sheets()` 每次请求就地改写共享
workbook 的 sheet 可见性，靠 mtime 变化迫使 OO 重新下载。本模块给出的 entry_id 把
**sheet 名（以及「完整 Excel」这个视图）算进 room 身份**，所以切换 sheet 依然换 key、
依然重新下载；而「同一个人反复打开同一 sheet」不再无谓轮转。

存量那处就地改写共享 artifact 的做法本身违反 Requirement 9.12（「不得用 openpyxl 原地
修改共享 current artifact 来隐藏其他 sheet」），修它属于 Task 25/26 的 staged artifact
范围，本模块**不动**它，也不动下载、callback、`file_version` 与席位限流。

═══ 三、generation 从哪来（以及为什么不能从 `file_version` 来）═══

generation 是 **representation generation**：只有 Task 25/26 发布新 representation /
显式 supersede 旧 room 时才推进。所以本模块的取法是：

1. 该 `(wp_id, entry_id)` 已有存活 room ⇒ 用 **room 行自己的 doc_key**（并交叉校验它
   确实由 :func:`derive_doc_key` 派生，防止某处写进了别的格式）；
2. 没有 room ⇒ 用 generation 1 派生。这是迁移前的基线代际，不是猜测：V151 的
   `uq_wpoor_generation (wp_id, entry_id, generation)` 决定了「一个代际一间房」，
   generation 1 就是尚未发布过任何新代际时的那一间。

**不用** `working_paper.file_version`：Requirement 2.1 明文禁止 `file_version` 推进或
充当跨通道同步版本。旧 `wp_editor_router` 的 `f"wp-{wp_id}-{wp.file_version}-…"` 正是
这种误用（它同时也让「预填/未预填」这种展示态进了文档身份），本模块一并取代。
"""
from __future__ import annotations

import logging
import re
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import WorkpaperOoRoom
from app.services.workpaper_sync.models import RoomState
from app.services.workpaper_sync.rooms import (
    RoomService,
    RouteCredential,
    derive_doc_key,
    doc_key_matches,
    mint_route_credential,
)

logger = logging.getLogger(__name__)

#: 尚未发布任何新 representation 代际时使用的基线代际。
BASELINE_GENERATION = 1

#: 「完整 Excel」视图在 entry_id 里的固定 slot 名。整册视图与单 sheet 视图是**两个**
#: 文档视图（前者全部 sheet 可见、后者只留一张），必须是两个 room 身份，否则 OO 会把
#: 缓存的单 sheet 副本当成整册返回。
WHOLE_WORKBOOK_SLOT = "__whole__"

#: Word 模板入口在 entry_id 里的固定 slot 名。与 `wp_editor_router` 的 callback URL
#: 里那个 `__word__` sheet 标识同名，避免同一入口在两处各有一套拼法。
WORD_TEMPLATE_SLOT = "__word__"

#: entry_id 里禁止出现的字符（`|` 是 doc_key 摘要的分隔符，`/` 是 slot 分隔符）。
_ENTRY_SANITIZE_RE = re.compile(r"[|\s]+")


def _slug(value: str) -> str:
    """把 sheet 名规范成 entry_id 片段：折叠空白、去掉分隔符冲突字符。

    只做**保守**规范化（不做大小写折叠、不做 unicode 归一）：entry_id 进 doc_key 摘要，
    过度规范化会让两个真实不同的 sheet 撞成同一间房。
    """
    return _ENTRY_SANITIZE_RE.sub("_", str(value or "").strip()).replace("/", "_")


def sheet_entry_id(*, wp_code: str, sheet_name: str, whole_workbook: bool) -> str:
    """`/sheets/{sheet_name}/onlyoffice-config` 的 room entry_id（唯一派生点）。

    形如 ``xlsx-sheet/{wp_code}/{sheet_slug}`` 或 ``xlsx-sheet/{wp_code}/__whole__``。

    🔴 `wp_code` 用的必须是路由算出来的 `_sheet_wp_code`（聚合包内独立子码会被换掉），
    否则同一 wp 下两个走不同模板的 sheet 会共享 room 身份。
    """
    code = _slug(wp_code)
    if not code:
        raise ValueError("wp_code 不得为空 —— room 身份必须能定位到底稿编码")
    slot = WHOLE_WORKBOOK_SLOT if whole_workbook else _slug(sheet_name)
    if not slot:
        raise ValueError("sheet_name 不得为空 —— 单 sheet 视图必须能定位到具体 sheet")
    return f"xlsx-sheet/{code}/{slot}"


def word_template_entry_id(*, wp_id: UUID) -> str:
    """`/working-papers/{wp_id}/onlyoffice-config` 的 room entry_id。

    该端点是整份 Word 底稿（A16 声明书一类），没有 sheet 维度，故 slot 固定。
    刻意**不**把 `version` / `prefilled` 算进去：它们是展示态与历史视图，不是文档身份；
    把「预填/未预填」写进 doc_key 会让同一份文件在两个房间里被并行编辑。
    """
    return f"docx-template/{wp_id}/{WORD_TEMPLATE_SLOT}"


async def resolve_room_doc_key(
    db: AsyncSession, *, wp_id: UUID, entry_id: str
) -> str:
    """room 身份派生的 doc_key。**与文件 mtime、路径、用户、时间戳全部无关**。

    已有存活 room 时返回 room 行上的 doc_key（并校验其归属），否则按基线代际派生。
    只读，不建 room —— 真正建 room 是 Task 25 materialize coordinator 的事，config
    端点不得顺手建。
    """
    row = (
        await db.execute(
            sa.select(WorkpaperOoRoom)
            .where(
                WorkpaperOoRoom.wp_id == wp_id,
                WorkpaperOoRoom.entry_id == entry_id,
                WorkpaperOoRoom.state.in_(_LIVE_ROOM_STATES),
            )
            .order_by(WorkpaperOoRoom.generation.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return derive_doc_key(
            wp_id=wp_id, entry_id=entry_id, generation=BASELINE_GENERATION
        )
    if not doc_key_matches(doc_key=row.doc_key, wp_id=wp_id, entry_id=entry_id):
        # room 行上的 key 不是本域派生的 ⇒ 不沿用它（沿用等于把一个来源不明的身份
        # 交给 OO），改按 room 自己的 generation 重新派生并留下告警。
        logger.warning(
            "room %s 的 doc_key=%r 不由 derive_doc_key 派生 —— 按 generation %s 重新派生",
            row.id,
            row.doc_key,
            row.generation,
        )
        return derive_doc_key(
            wp_id=wp_id, entry_id=entry_id, generation=int(row.generation)
        )
    return row.doc_key


async def resolve_room_route_credential(
    db: AsyncSession, *, wp_id: UUID, entry_id: str
) -> RouteCredential | None:
    """已有存活 room 时给出其 callback route credential（AC 2.6 末句）。

    没有 room 就返回 ``None`` —— 这是诚实的「本入口还没有 room」，而不是签一个凭证
    去指向不存在的房间。凭证本身由 :func:`mint_route_credential` 确定性派生，因此
    Task 22 的 callback 校验可以重算，不需要查表。
    """
    row = (
        await db.execute(
            sa.select(WorkpaperOoRoom)
            .where(
                WorkpaperOoRoom.wp_id == wp_id,
                WorkpaperOoRoom.entry_id == entry_id,
                WorkpaperOoRoom.state.in_(_LIVE_ROOM_STATES),
            )
            .order_by(WorkpaperOoRoom.generation.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return mint_route_credential(
        room_id=row.id, generation=int(row.generation), doc_key=row.doc_key
    )


def room_service(db: AsyncSession) -> RoomService:
    """生产侧构造 :class:`RoomService` 的唯一入口。

    Task 25/26 的 coordinator 从这里取服务实例，从而与 config 端点共用同一套 room 身份
    与资格判定；各自 `RoomService(WorkpaperSyncRepository(db))` 一遍会让「接线点」散落。
    """
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    return RoomService(WorkpaperSyncRepository(db))


#: 仍可承载编辑会话的 room 状态。终态（superseded/closed）不再提供身份 ——
#: 让它们继续给出 doc_key 等于把已作废代际重新挂给 OO（AC 2.8）。
_LIVE_ROOM_STATES = tuple(
    state.value
    for state in (
        RoomState.opening,
        RoomState.active,
        RoomState.close_barrier,
        RoomState.closing,
    )
)


__all__ = [
    "BASELINE_GENERATION",
    "WHOLE_WORKBOOK_SLOT",
    "WORD_TEMPLATE_SLOT",
    "sheet_entry_id",
    "word_template_entry_id",
    "resolve_room_doc_key",
    "resolve_room_route_credential",
    "room_service",
]
