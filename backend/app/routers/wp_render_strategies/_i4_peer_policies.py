"""I4 长期待摊费用 — 同业摊销政策公开年报摘录库

GET /api/workpapers/i4/peer-ltpa-policies
  ?industry=retail|manufacturing|property
  &year=2024（可选，按 peer.year 过滤，缺省返回该行业全部）

数据来源：backend/data/peer_ltpa_policies.json（公开年报附注摘录库）。
说明：为审计底稿起步对标数据；引用前须核对手工年报原文，不得直接作为最终证据。
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["i4-peer-policies"])

_DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "peer_ltpa_policies.json"


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, Any]:
    if not _DATA_PATH.exists():
        logger.warning("peer_ltpa_policies.json missing: %s", _DATA_PATH)
        return {"version": 0, "industries": []}
    with _DATA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/api/workpapers/i4/peer-ltpa-policies")
async def get_peer_ltpa_policies(
    industry: str = Query(..., description="行业 id：retail / manufacturing / property"),
    year: int | None = Query(None, description="可选：按年报年度过滤"),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    catalog = _load_catalog()
    industries = catalog.get("industries") or []
    matched = next((i for i in industries if i.get("id") == industry), None)
    if not matched:
        ids = [i.get("id") for i in industries]
        raise HTTPException(
            status_code=404,
            detail=f"未知行业「{industry}」，可选：{ids}",
        )

    peers: list[dict[str, Any]] = list(matched.get("peers") or [])
    if year is not None:
        peers = [p for p in peers if int(p.get("year") or 0) == int(year)]

    return {
        "industry": matched.get("id"),
        "label": matched.get("label"),
        "year_filter": year,
        "updated_at": catalog.get("updated_at"),
        "disclaimer": (
            "数据来自公开年报附注摘录库，便于同业对标起步；"
            "引用前须核对手工年报原文并填写信息来源，不得直接作为最终审计证据。"
        ),
        "peers": peers,
        "industries": [
            {"id": i.get("id"), "label": i.get("label"), "peer_count": len(i.get("peers") or [])}
            for i in industries
        ],
    }


@router.get("/api/workpapers/i4/peer-ltpa-industries")
async def list_peer_ltpa_industries(
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    catalog = _load_catalog()
    industries = catalog.get("industries") or []
    return {
        "updated_at": catalog.get("updated_at"),
        "industries": [
            {
                "id": i.get("id"),
                "label": i.get("label"),
                "peer_count": len(i.get("peers") or []),
            }
            for i in industries
        ],
    }
