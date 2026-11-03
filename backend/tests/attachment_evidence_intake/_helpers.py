"""spec attachment-evidence-intake 测试共用造数（不是测试文件，不被收集）。"""
from __future__ import annotations

import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import FastAPI

from app.core.config import settings
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.wp_optimization_models import EvidenceLink

PDF = b"%PDF-1.4\n%test\n"


def use_local_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "root"
    monkeypatch.setattr(settings, "ATTACHMENT_LOCAL_STORAGE_ROOT", str(root))
    monkeypatch.setattr(settings, "ATTACHMENT_PRIMARY_STORAGE", "local")
    return root


def files_under(base: Path) -> list[str]:
    if not base.exists():
        return []
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())


def pdf(name: str = "证据.pdf", content: bytes = PDF) -> dict:
    return {"file": (name, io.BytesIO(content), "application/pdf")}


async def count(db, model, *where) -> int:
    stmt = sa.select(sa.func.count()).select_from(model)
    for cond in where:
        stmt = stmt.where(cond)
    return int((await db.execute(stmt)).scalar_one())


async def links_of(db, attachment_id) -> tuple[list[AttachmentWorkingPaper], list[EvidenceLink]]:
    wp_links = (await db.execute(
        sa.select(AttachmentWorkingPaper).where(AttachmentWorkingPaper.attachment_id == attachment_id)
    )).scalars().all()
    ev_links = (await db.execute(
        sa.select(EvidenceLink).where(EvidenceLink.attachment_id == attachment_id)
    )).scalars().all()
    return list(wp_links), list(ev_links)


async def attachment_rows(db) -> list[Attachment]:
    return list((await db.execute(sa.select(Attachment))).scalars().all())


def evidence_app() -> FastAPI:
    """``wp_evidence`` 路由按自身前缀与路由级依赖挂载，不附加注册时的 ``dedicated_wp_gate``。

    SQLite 世界没有可见性相关表，统一门恒拒；统一门对编制人 / 复核人的放行与拒绝在
    ``test_evidence_role_matrix_pg.py`` 用真 PG 与生产注册参数测。
    """
    from app.routers.wp_evidence import router

    api = FastAPI()
    api.include_router(router)
    return api


# ─── OCR 路由世界（SQLite + 本地附件存储在临时目录 + 只挂一个路由，不挂统一门）────


class OcrWorld:
    def __init__(self, client, world, wp, user) -> None:
        self.client = client
        self.world = world
        self.wp = wp
        self.user = user

    @property
    def db(self):
        return self.world.db


@asynccontextmanager
async def ocr_world(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, router, *, wp_code: str = "D4-2",
) -> AsyncIterator[OcrWorld]:
    """供 OCR 路由用例：工作目录切到 ``tmp_path``（任何相对路径落盘都会留在这里，便于断言「无旁路文件」）。"""
    from tests.attachment_security_baseline._world import add_wp, sqlite_attachment_world

    monkeypatch.chdir(tmp_path)
    use_local_storage(tmp_path, monkeypatch)
    async with sqlite_attachment_world(monkeypatch) as world:
        who = await world.edit_member()
        wp = await add_wp(world, world.target, wp_code=wp_code)
        api = FastAPI()
        api.include_router(router)
        async with world.client_for_app(api, user=who.user) as client:
            yield OcrWorld(client, world, wp, who.user)


def unwrap(body: dict) -> dict:
    """兼容 ResponseWrapperMiddleware 信封（最小应用不挂中间件时原样返回）。"""
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, dict) else body
