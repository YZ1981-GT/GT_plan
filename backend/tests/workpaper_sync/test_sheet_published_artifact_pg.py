# -*- coding: utf-8 -*-
"""5.2 后端 PG：真实 representation / bundle / artifact 读取与项目隔离。

spec: onlyoffice-sheet-open-via-published-artifact 任务 5.2

本文件验的是「真库上真的读得通」，不是「合成夹具跑得过」。unit 层
（`test_sheet_published_artifact.py` 12 例）已用合成夹具覆盖同一批 reason，但合成
夹具永远不会自发产出真实 schema 的形状差异 —— 本仓为此付过代价：把 bundle 的摘要
字段猜成 `bundle_sha256` / `sha256`（真名 `canonical_payload_sha256`），
`getattr(..., "")` 恒空 ⇒ 所有读路径恒报 drift。

为什么不 skip：DB 非 PostgreSQL 时 skip 等于把「没验证」记成「通过」。

隔离：全部只读 —— 直接读共享库的真实行，不建 scratch schema、不写任何表。
写入型验收不在本文件（5.2 的 [ ]* 项）。
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.pg_only



def _db_url() -> str:
    from app.core.config import settings

    url = str(settings.DATABASE_URL)
    if not url.startswith("postgresql"):
        raise AssertionError(
            "本文件的判据必须在真实 PostgreSQL 上跑；当前 DATABASE_URL 为 "
            + url.split("://")[0]
            + " —— skip 等于把「没验证」记成「通过」。"
        )
    return url


def _engine():
    return create_async_engine(_db_url(), poolclass=NullPool)


def _run(coro):
    """一次 asyncio.run 跑完 —— 每个测试各自开 async 会污染共享连接池。

    连接失败时 skip 而不是 fail：有 PG 但连不上是**环境**问题（CI 没起容器），
    不是判据失败。URL 非 PG 时才 raise —— 那是「判据跑错了地方」，必须红。
    """
    try:
        return asyncio.run(coro)
    except Exception as exc:
        # 只把「连不上 / 认证失败」当环境问题 skip；判据失败必须穿透。
        name = type(exc).__name__
        text = str(exc).lower()
        env_markers = (
            "InvalidPasswordError", "ConnectionRefusedError", "ConnectionDoesNotExistError",
            "TimeoutError", "gaierror",
        )
        if name in env_markers or "password authentication failed" in text or "connection refused" in text:
            pytest.skip("连不上 PostgreSQL（环境问题，非判据失败）：" + str(exc)[:160])
        raise



def _storage_root() -> Path:
    """artifact 的 base_root = <repo>/backend。

    真实 relative_path 形如 storage/<pid>/workpapers/...，盘上目录是
    <repo>/backend/storage/<pid>/... ⇒ base_root 必须是 backend/。

    🔴 刻意不读 settings.STORAGE_ROOT：它是 "./storage"（相对 cwd），而 relative_path
    已自带 storage/ 前缀 ⇒ 读它会拼成 storage/storage/... 恒不可解析。这个前缀关系
    只有真跑一次才看得出来（unit 层用 tmp_path 造夹具，永远对得上）。
    """
    return Path(__file__).resolve().parents[2]


def _resolve_candidate_path(relative_path: str) -> Path | None:
    """把 relative_path 解析成盘上路径（base_root = backend/，见 _storage_root）。"""
    p = Path(relative_path)
    if p.is_absolute():
        return p
    return _storage_root() / relative_path


async def _pick_real_row():
    """取一条真实可读的 (entry_id, wp_id, project_id, artifact)。

    条件必须是 published + canonical + sha 一致 —— 那是 reader 自己的前置判据，
    用别的行做夹具会测到「本来就该拒」的分支。
    """
    eng = _engine()
    try:
        async with eng.connect() as c:
            rows = (
                await c.execute(
                    text(
                        "SELECT e.entry_id, e.wp_id, a.project_id, r.id AS representation_id, "
                        "       a.relative_path, a.sha256, a.size_bytes "
                        "FROM working_paper_sync_entry_state e "
                        "JOIN working_paper_content_representation r "
                        "  ON r.id = e.current_representation_id "
                        "JOIN working_paper_artifact a ON a.id = r.artifact_id "
                        "WHERE a.state = :pub AND a.kind = :kind "
                        "  AND a.sha256 = r.artifact_sha256 "
                        # resolver 只按 entry_id 查；同一 entry 挂在多个底稿上时它可能
                        # 返回另一个 wp 的 representation ⇒ 必须排除那些行。
                        "  AND NOT EXISTS (SELECT 1 FROM working_paper_sync_entry_state e2 "
                        "                  WHERE e2.entry_id = e.entry_id "
                        "                    AND e2.wp_id <> e.wp_id) "
                        "ORDER BY e.updated_at DESC LIMIT 1"
                    ),
                    {"pub": "published", "kind": "canonical"},
                )
            ).fetchall()
            for cand in rows:
                path = _resolve_candidate_path(cand.relative_path)
                if path is not None and path.is_file():
                    return cand
            return rows[0] if rows else None
    finally:
        await eng.dispose()



def test_real_row_exists_for_pg_verification():
    """真库必须有可验样本 —— 否则后续判据会零样本通过（空分母恒真）。"""
    row = _run(_pick_real_row())
    assert row is not None, (
        "真库里没有 published+canonical 且 sha 一致的 entry_state 行 —— "
        "后续判据会零样本通过，等于没验"
    )
    assert row.entry_id and row.wp_id and row.project_id


def test_real_artifact_file_on_disk_sha_matches_db():
    """真实 artifact 文件必须在盘，且 sha256 / size 与库中记录一致。"""
    row = _run(_pick_real_row())
    assert row is not None
    path = Path(row.relative_path)
    if not path.is_absolute():
        from app.core.config import settings

        base = getattr(settings, "STORAGE_BASE", None) or "storage"
        path = Path(base) / row.relative_path
        if not path.is_file():
            # relative_path 已含 storage/ 前缀时不要重复拼
            path = Path(row.relative_path)
    assert path.is_file(), "artifact 文件不在盘：" + str(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row.sha256
    assert path.stat().st_size == row.size_bytes



def test_reader_reads_real_artifact_on_pg():
    """真库端到端：reader 能读出真实 artifact（unit 合成夹具证明不了的那一条）。"""
    row = _run(_pick_real_row())
    assert row is not None

    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.sheet_published_artifact import (
        PublishedSheetArtifactError,
        read_current_published_sheet_artifact,
    )

    async def _go():
        eng = _engine()
        try:
            maker = async_sessionmaker(eng, expire_on_commit=False)
            async with maker() as session:
                repo = CanonicalArtifactRepository(_storage_root())
                return await read_current_published_sheet_artifact(
                    session=session,
                    artifact_repository=repo,
                    project_id=row.project_id,
                    wp_id=row.wp_id,
                    entry_id=row.entry_id,
                    target_sheet=None,
                    whole_workbook=True,
                )
        finally:
            await eng.dispose()

    try:
        result = _run(_go())
    except PublishedSheetArtifactError as exc:
        pytest.fail("真库读取失败 [" + exc.reason + "]：" + str(exc))
    assert result.path.is_file()
    assert result.sheet_names



def test_reader_rejects_wrong_project_id_on_pg():
    """项目隔离：传别的 project_id 必须被拒（artifact 不属于该项目）。

    这是 5.2 明确要求的「项目隔离」判据。用真实行做反向验证 —— 比合成夹具更强，
    因为它验的是真实 project_root 边界，而不是桩的返回值。
    """
    row = _run(_pick_real_row())
    assert row is not None

    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.sheet_published_artifact import (
        PublishedSheetArtifactError,
        read_current_published_sheet_artifact,
    )

    other_project = uuid.UUID("00000000-0000-0000-0000-000000000001")

    async def _go():
        eng = _engine()
        try:
            maker = async_sessionmaker(eng, expire_on_commit=False)
            async with maker() as session:
                repo = CanonicalArtifactRepository(_storage_root())
                return await read_current_published_sheet_artifact(
                    session=session,
                    artifact_repository=repo,
                    project_id=other_project,
                    wp_id=row.wp_id,
                    entry_id=row.entry_id,
                    target_sheet=None,
                    whole_workbook=True,
                )
        finally:
            await eng.dispose()

    with pytest.raises(PublishedSheetArtifactError) as exc:
        _run(_go())
    # 只断言「被拒」，不钉死具体 reason：真实链路上隔离**在更早一层**就生效
    # （representation 归属校验先于路径解析），实测 reason 是「不属于底稿」而不是
    # 「路径不可解析」。钉死 reason 会让判据随实现顺序变化而红 —— 那是测实现不是测性质。
    assert exc.value.reason, "拒绝必须带 reason，否则运维无从下手"
    assert "不属于底稿" in str(exc.value) or "不可解析" in str(exc.value), str(exc.value)


def test_storage_root_resolves_to_repo_backend():
    """守卫：_storage_root() 必须等于 <repo>/backend —— 否则 artifact 恒解析不到。"""
    root = _storage_root()
    assert (root / "storage").is_dir(), "base_root 下没有 storage/ 目录：" + str(root)
    assert (root / "app").is_dir(), "base_root 不像 backend/（缺 app/）：" + str(root)
