"""离屏披露手工触发命令行：不开页面，把底稿披露表刷进附注（spec note-disclosure-pull-regression-and-headless-backend 任务 13，
design §5.2 / §5.4）。

与端点 ``POST /api/disclosure-notes/{project_id}/{year}/headless-refresh`` 同一实现（``note_headless_refresh_service``）：
以 ``--user`` 指定的用户身份跑（先过与端点相同的附注编辑门禁），Node 执行器回连 ``--api-base`` 上**正在运行**的后端，
写入走现有的取数 / 披露同步 / 重算端点（四层人工保护与推送 ownership 重放照常生效）。本脚本自己不写库。

用法（cwd=backend，后端已启动）：
    python scripts/ops/note_headless_refresh.py --project <项目id> --year 2025 --user <用户名> [--section 五、5]
        [--api-base http://127.0.0.1:9980] [--timeout 300]

退出码：0 = 跑完且结果 ok；1 = 跑完但有失败（结果 ok 为假）或执行器出错 / 超时；2 = 参数错误；3 = 用户 / 权限不符，
或服务器上跑不起来（无 Node / 未构建 / 构建过期 / 正在运行）。结果 JSON 打到 stdout。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import pkgutil
import sys
from pathlib import Path
from uuid import UUID

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import sqlalchemy as sa  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import app.models  # noqa: E402
from app.core.database import async_session  # noqa: E402
from app.models.core import User  # noqa: E402
from app.services import note_headless_refresh_service as headless  # noqa: E402
from app.services.note_edit_gate import assert_note_edit_access, note_edit_rejection_reason  # noqa: E402

for _m in pkgutil.walk_packages(app.models.__path__, "app.models."):
    importlib.import_module(_m.name)

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_DENIED = 0, 1, 2, 3


async def _authorize(username: str, project_id: UUID) -> UUID:
    """按用户名找在用账号并过附注编辑门禁（与端点同一判定）；返回用户 id。不通过抛 ``PermissionError``（中文原因）。"""
    async with async_session() as db:
        user = (await db.execute(sa.select(User).where(
            User.username == username, User.is_active == sa.true(), User.is_deleted == sa.false(),
        ))).scalar_one_or_none()
        if user is None:
            raise PermissionError(f"没有在用的用户：{username}")
        try:
            await assert_note_edit_access(db, user, project_id, consol_lock=False)
        except HTTPException as exc:
            raise PermissionError(f"{username} 不能刷新该项目附注：{note_edit_rejection_reason(exc)}") from None
        user_id = user.id
    return user_id  # 只读判定：会话关闭即结束事务，执行器跑的几十秒里不占连接


def _emit(text: str) -> None:
    """结果按 UTF-8 输出（Windows 控制台缺省 GBK，中文章节号会乱码或报错）。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    print(text, flush=True)


async def run(args: argparse.Namespace) -> int:
    try:
        user_id = await _authorize(args.user, args.project)
    except PermissionError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_DENIED
    try:
        result = await headless.run_headless_refresh(
            project_id=args.project, year=args.year, user_id=user_id, section=args.section,
            api_base=args.api_base, timeout=args.timeout,
        )
    except (headless.HeadlessRefreshUnavailable, headless.HeadlessRefreshBusy) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_DENIED
    except (headless.HeadlessRefreshTimeout, headless.HeadlessRefreshFailed) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_FAILED
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    _emit(json.dumps(result, ensure_ascii=False, indent=1))
    return EXIT_OK if result.get("ok") else EXIT_FAILED


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="离屏披露手工触发：不开页面把底稿披露表刷进附注")
    parser.add_argument("--project", type=UUID, required=True, help="项目 id")
    parser.add_argument("--year", type=int, required=True, help="审计年度")
    parser.add_argument("--user", required=True, help="以哪个用户的身份跑（用户名；须能编辑该项目附注）")
    parser.add_argument("--section", default=None, help="只刷一个章节（如 五、5）；不传 = 全部刷新")
    parser.add_argument("--api-base", default=headless.loopback_api_base(None), help="正在运行的后端（只认本机环回）")
    parser.add_argument("--timeout", type=float, default=headless.RUN_TIMEOUT_SECONDS, help="超时秒数")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
