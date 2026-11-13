"""离屏披露手工触发端点（spec note-disclosure-pull-regression-and-headless-backend 任务 13，design §5.2 / §5.4）。

POST /api/disclosure-notes/{project_id}/{year}/headless-refresh[?note_section=]

不开附注页、不开底稿披露 Tab：后端拉起 Node 执行器跑附注页「全部刷新」（或单章节「刷新」）的同一套前端代码，经现有的
取数 / 披露同步 / 重算端点写入附注（实现见 ``note_headless_refresh_service``）。门禁与「刷新」链路的取数端点
``pull-from-workpapers`` 相同（附注编辑门禁，不判合并锁）；子进程以触发人本人的身份发请求，每个请求再过各自端点的门禁。

同步执行、跑完才返回（全部刷新实测几十秒级，上限 ``RUN_TIMEOUT_SECONDS``）。期 3 改为事件触发的后台任务（platform_jobs）。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.core import User
from app.services import note_headless_refresh_service as headless
from app.services.note_edit_gate import require_note_edit_access

router = APIRouter(prefix="/api/disclosure-notes", tags=["note-headless-refresh"])

_STATUS = (
    (headless.HeadlessRefreshBusy, 409),
    (headless.HeadlessRefreshUnavailable, 503),
    (headless.HeadlessRefreshTimeout, 504),
    (headless.HeadlessRefreshFailed, 502),
)


@router.post("/{project_id}/{year}/headless-refresh")
async def headless_refresh(
    project_id: UUID,
    year: int,
    request: Request,
    note_section: str | None = Query(None, min_length=1, max_length=64, description="只刷一个章节；不传 = 全部刷新"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_note_edit_access(consol_lock=False)),
):
    """离屏刷新附注（底稿披露表 → 附注），返回执行器逐章节结果：``ok`` / ``stage`` / ``outcomes`` / ``pending`` / ``push`` /
    ``refresh`` / ``elapsed_ms``。409 = 本项目本年度正在跑或已达并发上限；503 = 服务器上跑不起来（无 Node / 未构建 /
    构建过期）；504 = 超时已终止；502 = 执行器出错。"""
    user_id = current_user.id
    # 门禁查询的事务先结束：子进程要跑几十秒，期间不占连接（子进程的请求另取连接）
    await db.commit()
    try:
        return await headless.run_headless_refresh(
            project_id=project_id, year=year, user_id=user_id, section=note_section,
            api_base=headless.loopback_api_base(request.scope.get("server")),
        )
    except headless.HeadlessRefreshError as exc:
        status = next((code for kind, code in _STATUS if isinstance(exc, kind)), 500)
        raise HTTPException(status_code=status, detail=str(exc)) from exc
