"""高级查询历史与证据接口（AQF §7；10 个端点）。

前缀 ``/api/custom-query``，紧随 cq_router 在 router_registry/system.py 注册。
所有端点先按 ``id + user_id`` 取对象（取不到 → 404），再重验访问（R7.1/R7.2）。
迁移未落库时返回 503 QUERY_EVIDENCE_UNAVAILABLE（R8.2）。
只读端点不提交；DELETE 与 clear 由路由提交。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.custom_query.query_evidence import query_evidence_available
from app.services.custom_query.ownership_guard import ownership_guard

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/custom-query", tags=["高级查询历史与证据"])


# ─── 503 辅助 ─────────────────────────────────────────────────────────────────

def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail={
        "error_code": "QUERY_EVIDENCE_UNAVAILABLE",
        "message": "查询证据功能尚未启用（数据库迁移未执行）",
    })


def _not_found(kind: str = "run") -> HTTPException:
    codes = {"run": "QUERY_RUN_NOT_FOUND", "artifact": "QUERY_ARTIFACT_NOT_FOUND"}
    msgs = {"run": "查询运行记录不存在", "artifact": "查询证据不存在"}
    return HTTPException(status_code=404, detail={
        "error_code": codes.get(kind, "NOT_FOUND"),
        "message": msgs.get(kind, "不存在"),
    })


# ─── 运行记录相关端点 ─────────────────────────────────────────────────────────

@router.get("/runs")
async def list_runs(
    entry: str | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, le=100, ge=1),
    before: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """本人历史（按定义去重，返回各定义最近一次）。"""
    if not await query_evidence_available(db):
        raise _unavailable()

    conds = ["user_id = :uid", "hidden_at IS NULL"]
    params: dict[str, Any] = {"uid": str(current_user.id), "lim": limit}
    if entry:
        conds.append("entry = :entry")
        params["entry"] = entry
    if project_id:
        conds.append("project_id = :pid")
        params["pid"] = str(project_id)
    if before:
        conds.append("last_executed_at < :before")
        params["before"] = before

    where = " AND ".join(conds)
    rows = (await db.execute(text(f"""
        SELECT id, entry, origin, project_id, year, source_key,
               definition_hash, definition_version, labels, scope,
               version_vector, vector_hash, vector_weak,
               captured_at, execution_count, last_executed_at, last_total
          FROM (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY definition_hash ORDER BY last_executed_at DESC) AS rn
              FROM query_runs
             WHERE {where}
          ) t
         WHERE t.rn = 1
         ORDER BY last_executed_at DESC
         LIMIT :lim
    """), params)).fetchall()

    result = []
    for r in rows:
        obj = dict(zip(
            ["id", "entry", "origin", "project_id", "year", "source_key",
             "definition_hash", "definition_version", "labels", "scope",
             "version_vector", "vector_hash", "vector_weak",
             "captured_at", "execution_count", "last_executed_at", "last_total"],
            r,
        ))
        # 证据数
        cnt = (await db.execute(text(
            "SELECT count(*) FROM query_artifacts WHERE user_id=:u AND definition_hash=:d"
        ), {"u": str(current_user.id), "d": obj["definition_hash"]})).scalar_one()
        obj["artifact_count"] = cnt
        result.append(obj)
    return {"runs": result}


@router.get("/runs/{run_id}")
async def get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """运行详情：定义、范围、版本分量、该定义下的证据列表。"""
    if not await query_evidence_available(db):
        raise _unavailable()
    run = await _get_run_or_404(db, run_id, current_user)
    await _check_run_access(db, run, current_user)

    # 该定义下的证据
    artifacts = (await db.execute(text("""
        SELECT id, status, file_name, byte_size, sha256, row_count, created_at
          FROM query_artifacts WHERE user_id=:u AND definition_hash=:d ORDER BY created_at DESC
    """), {"u": str(current_user.id), "d": run["definition_hash"]})).fetchall()

    run["artifacts"] = [
        dict(zip(["id", "status", "file_name", "byte_size", "sha256", "row_count", "created_at"], a))
        for a in artifacts
    ]
    return run


@router.get("/runs/{run_id}/freshness")
async def get_run_freshness(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """过期判定：按运行记录保存的分量范围重新采集并比较。"""
    if not await query_evidence_available(db):
        raise _unavailable()
    run = await _get_run_or_404(db, run_id, current_user)
    await _check_run_access(db, run, current_user)
    return await _freshness_for_vector(db, run.get("version_vector") or {})


@router.delete("/runs/{run_id}", status_code=204)
async def hide_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """隐藏运行记录（软删除）。"""
    if not await query_evidence_available(db):
        raise _unavailable()
    result = await db.execute(text("""
        UPDATE query_runs SET hidden_at=now(), updated_at=now()
         WHERE id=:id AND user_id=:uid
    """), {"id": str(run_id), "uid": str(current_user.id)})
    await db.commit()
    if result.rowcount == 0:
        raise _not_found("run")


@router.post("/runs/clear")
async def clear_runs(
    entry: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """隐藏本人全部运行记录（`entry` 可选）。"""
    if not await query_evidence_available(db):
        raise _unavailable()
    params: dict[str, Any] = {"uid": str(current_user.id)}
    extra = ""
    if entry:
        extra = " AND entry=:entry"
        params["entry"] = entry
    result = await db.execute(text(
        f"UPDATE query_runs SET hidden_at=now(), updated_at=now() WHERE user_id=:uid AND hidden_at IS NULL{extra}"
    ), params)
    await db.commit()
    return {"hidden": result.rowcount}


# ─── 证据相关端点 ─────────────────────────────────────────────────────────────

@router.get("/artifacts")
async def list_artifacts(
    entry: str | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, le=100, ge=1),
    before: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """本人证据列表（含已清理的，标明状态）。"""
    if not await query_evidence_available(db):
        raise _unavailable()

    conds = ["user_id = :uid"]
    params: dict[str, Any] = {"uid": str(current_user.id), "lim": limit}
    if entry:
        conds.append("entry = :entry")
        params["entry"] = entry
    if project_id:
        conds.append("project_id = :pid")
        params["pid"] = str(project_id)
    if before:
        conds.append("created_at < :before")
        params["before"] = before
    where = " AND ".join(conds)

    rows = (await db.execute(text(f"""
        SELECT id, entry, status, source_key, file_name, byte_size,
               row_count, sha256, vector_hash, created_at, retention_until, purged_at
          FROM query_artifacts WHERE {where}
         ORDER BY created_at DESC LIMIT :lim
    """), params)).fetchall()
    return {"artifacts": [
        dict(zip(["id", "entry", "status", "source_key", "file_name", "byte_size",
                  "row_count", "sha256", "vector_hash", "created_at", "retention_until", "purged_at"], r))
        for r in rows
    ]}


@router.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """证据详情（不含文件）。"""
    if not await query_evidence_available(db):
        raise _unavailable()
    art = await _get_artifact_or_404(db, artifact_id, current_user)
    await _check_artifact_access(db, art, current_user)
    return art


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: uuid.UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载证据文件（先重验摘要）。"""
    if not await query_evidence_available(db):
        raise _unavailable()
    art = await _get_artifact_or_404(db, artifact_id, current_user)
    await _check_artifact_access(db, art, current_user)

    from app.services.custom_query.query_artifacts import verify_and_stream
    from app.services.custom_query import audit_helper
    file_path, file_name, content_disp = await verify_and_stream(db, artifact_id, user=current_user)

    # 审计（R7.3）
    try:
        await audit_helper.record_export(
            user_id=current_user.id,
            project_id=art.get("project_id"),
            details={"action": "custom_query.artifact_download", "artifact_id": str(artifact_id)},
        )
    except Exception:
        pass

    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": content_disp},
    )


@router.get("/artifacts/{artifact_id}/manifest")
async def get_artifact_manifest(
    artifact_id: uuid.UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回清单 JSON，响应头 X-Manifest-SHA256。"""
    if not await query_evidence_available(db):
        raise _unavailable()
    art = await _get_artifact_or_404(db, artifact_id, current_user)
    await _check_artifact_access(db, art, current_user)

    manifest = art.get("manifest") or {}
    from app.services.custom_query.query_artifacts import manifest_sha256, canonical_manifest_json
    msha = art.get("manifest_sha256") or manifest_sha256(manifest)
    response.headers["X-Manifest-SHA256"] = msha
    return manifest


@router.get("/artifacts/{artifact_id}/freshness")
async def get_artifact_freshness(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按证据记录的版本向量判定时效。"""
    if not await query_evidence_available(db):
        raise _unavailable()
    art = await _get_artifact_or_404(db, artifact_id, current_user)
    await _check_artifact_access(db, art, current_user)
    return await _freshness_for_vector(db, art.get("version_vector") or {})


# ─── 内部工具 ─────────────────────────────────────────────────────────────────

async def _get_run_or_404(db: AsyncSession, run_id: uuid.UUID, user: User) -> dict:
    row = (await db.execute(text("""
        SELECT id, user_id, entry, origin, project_id, year, source_key,
               definition, definition_hash, scope, labels,
               version_vector, vector_hash, vector_weak, captured_at,
               execution_count, last_executed_at, last_total, hidden_at
          FROM query_runs WHERE id=:id LIMIT 1
    """), {"id": str(run_id)})).first()
    if row is None or str(row[1]) != str(user.id):
        raise _not_found("run")
    keys = ["id", "user_id", "entry", "origin", "project_id", "year", "source_key",
            "definition", "definition_hash", "scope", "labels",
            "version_vector", "vector_hash", "vector_weak", "captured_at",
            "execution_count", "last_executed_at", "last_total", "hidden_at"]
    return dict(zip(keys, row))


async def _get_artifact_or_404(db: AsyncSession, artifact_id: uuid.UUID, user: User) -> dict:
    row = (await db.execute(text("""
        SELECT id, user_id, entry, project_id, year, source_key,
               definition_hash, version_vector, vector_hash, scope,
               status, file_name, storage_key, byte_size, sha256, row_count,
               manifest, manifest_sha256, retention_until, purged_at, created_at
          FROM query_artifacts WHERE id=:id LIMIT 1
    """), {"id": str(artifact_id)})).first()
    if row is None or str(row[1]) != str(user.id):
        raise _not_found("artifact")
    keys = ["id", "user_id", "entry", "project_id", "year", "source_key",
            "definition_hash", "version_vector", "vector_hash", "scope",
            "status", "file_name", "storage_key", "byte_size", "sha256", "row_count",
            "manifest", "manifest_sha256", "retention_until", "purged_at", "created_at"]
    return dict(zip(keys, row))


async def _check_run_access(db: AsyncSession, run: dict, user: User) -> None:
    """重验运行记录的项目访问权（R7.2）。"""
    project_id = run.get("project_id")
    if not project_id:
        return
    try:
        await ownership_guard.assert_target_accessible(user=user, project_id=str(project_id), db=db)
    except HTTPException as exc:
        if exc.status_code in (403, 404):
            raise HTTPException(status_code=403, detail={
                "error_code": "FORBIDDEN_PROJECT", "message": "您已失去该项目的访问权限",
            })
        raise


async def _check_artifact_access(db: AsyncSession, art: dict, user: User) -> None:
    """重验证据的项目访问权（R7.2）。"""
    project_id = art.get("project_id")
    if not project_id:
        return
    try:
        await ownership_guard.assert_target_accessible(user=user, project_id=str(project_id), db=db)
    except HTTPException as exc:
        if exc.status_code in (403, 404):
            raise HTTPException(status_code=403, detail={
                "error_code": "FORBIDDEN_PROJECT", "message": "您已失去该项目的访问权限",
            })
        raise


async def _freshness_for_vector(db: AsyncSession, version_vector: dict) -> dict:
    """按版本向量重新采集并比较，返回时效判定结果（R3.1/R3.2）。"""
    try:
        from app.services.custom_query.version_compare import compare_vector
        from app.services.custom_query.version_capture import recapture_vector
        components = version_vector.get("components", [])
        if not components:
            return {"status": "unknown", "reason": "版本向量为空，无法判定"}
        recaptured = await recapture_vector(db, components)
        return compare_vector(components, recaptured)
    except Exception as exc:
        logger.warning("freshness check error: %s", exc)
        return {"status": "unknown", "reason": f"判定失败：{type(exc).__name__}"}
