"""按服务端工作表版本预览并生成草稿抵销分录。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_worksheet_data_models import ConsolWorksheetData
from app.models.consolidation_models import EliminationEntry, ReviewStatusEnum
from app.services.consol_version_vector import canonical_json, digest_payload
from app.services.consol_worksheet_group_builder import (
    ORIGIN_SHEETS,
    SOURCE_SHEETS,
    build_groups_from_worksheet,
)
from app.services.consol_tree_service import build_tree

TOKEN_TTL_SECONDS = 15 * 60


class WorksheetGenerationError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, detail: dict[str, Any] | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


@dataclass(frozen=True)
class WorksheetSnapshot:
    contents: dict[str, dict[str, Any]]
    versions: dict[str, int]
    source_digest: str
    groups: list[Any]
    origins: list[str]
    summary: dict[str, Any]


def _secret() -> bytes:
    from app.core.config import settings
    value = str(getattr(settings, "JWT_SECRET_KEY", ""))
    if not value:
        raise WorksheetGenerationError(503, "SIGNING_KEY_MISSING", "服务端未配置预览签名密钥")
    return value.encode("utf-8")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_preview_token(payload: dict[str, Any]) -> str:
    body = {**payload, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    encoded = _b64(canonical_json(body).encode("utf-8"))
    signature = _b64(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def verify_preview_token(token: str, expected: dict[str, Any]) -> None:
    try:
        encoded, supplied = token.split(".", 1)
        actual = _b64(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied, actual):
            raise ValueError("signature")
        payload = json.loads(_unb64(encoded).decode("utf-8"))
        if int(payload.get("exp") or 0) < int(time.time()):
            raise WorksheetGenerationError(409, "PREVIEW_EXPIRED", "预览已过期，请重新预览")
        for key, value in expected.items():
            if payload.get(key) != value:
                raise WorksheetGenerationError(409, "PREVIEW_CHANGED", "预览来源已变化，请重新预览")
    except WorksheetGenerationError:
        raise
    except Exception as exc:
        raise WorksheetGenerationError(409, "PREVIEW_INVALID", "预览凭证无效，请重新预览") from exc


def _normalize_sheet_keys(source_sheet_keys: Iterable[str] | None) -> list[str]:
    keys = list(dict.fromkeys(source_sheet_keys or SOURCE_SHEETS))
    invalid = sorted(set(keys) - set(SOURCE_SHEETS))
    if invalid:
        raise WorksheetGenerationError(422, "INVALID_SOURCE_SHEETS", f"不支持的来源工作表：{invalid}")
    return keys


async def load_snapshot(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    source_sheet_keys: Iterable[str] | None,
    expected_versions: dict[str, int] | None,
    for_update: bool,
) -> WorksheetSnapshot:
    keys = _normalize_sheet_keys(source_sheet_keys)
    query_keys = ["info", *keys]
    stmt = sa.select(ConsolWorksheetData).where(
        ConsolWorksheetData.project_id == project_id,
        ConsolWorksheetData.year == year,
        ConsolWorksheetData.sheet_key.in_(query_keys),
    ).order_by(ConsolWorksheetData.sheet_key)
    if for_update:
        stmt = stmt.with_for_update()
    records = {row.sheet_key: row for row in (await db.execute(stmt)).scalars().all()}
    versions = {key: int(records[key].version or 0) if key in records else 0 for key in keys}
    if expected_versions is not None:
        wanted = {key: int(expected_versions.get(key, 0)) for key in keys}
        if set(expected_versions) - set(keys):
            raise WorksheetGenerationError(
                422, "VERSION_SCOPE_MISMATCH", "期望版本包含了本次来源范围之外的工作表",
            )
        if wanted != versions:
            changed = sorted(key for key in keys if wanted.get(key) != versions.get(key))
            raise WorksheetGenerationError(
                409, "WORKSHEET_VERSION_CONFLICT", "工作表已变化，请重新预览",
                {"expected_versions": wanted, "actual_versions": versions, "changed_sheets": changed},
            )
    contents = {
        key: dict(records[key].data or {}) if key in records else {}
        for key in query_keys
    }
    tree = await build_tree(db, project_id)
    if tree is None:
        raise WorksheetGenerationError(409, "CONSOL_TREE_MISSING", "当前项目没有可计算的企业树")
    scoped_contents = {key: contents[key] for key in ["info", *keys] if key in contents}
    groups, all_origins, summary = build_groups_from_worksheet(scoped_contents, tree)
    allowed_origins = {SHEET_ORIGIN for SHEET_ORIGIN, sheet in ORIGIN_SHEETS.items() if sheet in keys}
    groups = [group for group in groups if group.origin in allowed_origins]
    origins = [origin for origin in all_origins if origin in allowed_origins]
    payload = {
        "project_id": str(project_id), "year": year,
        "versions": versions,
        "groups": [group.model_dump(mode="json") for group in groups],
        "origins": origins,
    }
    return WorksheetSnapshot(
        contents=scoped_contents,
        versions=versions,
        source_digest=digest_payload(payload),
        groups=groups,
        origins=origins,
        summary={**summary, "source_sheet_keys": keys},
    )


async def preview_generation(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    source_sheet_keys: Iterable[str] | None,
    expected_versions: dict[str, int] | None,
) -> dict[str, Any]:
    from app.services.consol_elimination_sheet_service import generate_from_worksheet

    snapshot = await load_snapshot(
        db, project_id=project_id, year=year, source_sheet_keys=source_sheet_keys,
        expected_versions=expected_versions, for_update=False,
    )
    result = await generate_from_worksheet(
        db, project_id, year, snapshot.groups, origins=snapshot.origins, dry_run=True,
    )
    token_payload = {
        "project_id": str(project_id), "year": year,
        "source_digest": snapshot.source_digest, "versions": snapshot.versions,
    }
    return {
        **result.to_dict(),
        "preview_token": issue_preview_token(token_payload),
        "source_versions": snapshot.versions,
        "source_digest": snapshot.source_digest,
        "source_summary": snapshot.summary,
    }


async def generate_from_server_worksheets(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    source_sheet_keys: Iterable[str] | None,
    expected_versions: dict[str, int],
    preview_token: str,
    user_id: UUID | None,
) -> dict[str, Any]:
    from app.services.consol_elimination_sheet_service import generate_from_worksheet

    snapshot = await load_snapshot(
        db, project_id=project_id, year=year, source_sheet_keys=source_sheet_keys,
        expected_versions=expected_versions, for_update=True,
    )
    verify_preview_token(preview_token, {
        "project_id": str(project_id), "year": year,
        "source_digest": snapshot.source_digest, "versions": snapshot.versions,
    })
    result = await generate_from_worksheet(
        db, project_id, year, snapshot.groups, origins=snapshot.origins,
        dry_run=False, user_id=user_id,
    )
    produced = {(group.origin, group.origin_key) for group in snapshot.groups}
    entries = (await db.execute(sa.select(EliminationEntry).where(
        EliminationEntry.project_id == project_id,
        EliminationEntry.year == year,
        EliminationEntry.origin.in_(snapshot.origins) if snapshot.origins else sa.false(),
        EliminationEntry.is_deleted == sa.false(),
    ))).scalars().all()
    for entry in entries:
        if (entry.origin, entry.origin_key) not in produced:
            continue
        if entry.review_status not in {ReviewStatusEnum.draft, ReviewStatusEnum.rejected}:
            continue
        entry.source_version = {
            "worksheet_versions": snapshot.versions,
            "source_sheet_keys": snapshot.summary["source_sheet_keys"],
        }
        entry.source_digest = snapshot.source_digest
    await db.flush()
    return {
        **result.to_dict(),
        "source_versions": snapshot.versions,
        "source_digest": snapshot.source_digest,
        "source_summary": snapshot.summary,
    }
