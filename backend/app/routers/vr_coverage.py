"""VR 规则覆盖度统计 API — Phase 7 F6

GET /api/qc/vr-coverage: 返回各循环 VR 规则覆盖度统计
- 运行时扫描各循环 *_cycle_validation_rules.json 文件
- 统计每循环 blocking/warning/info 条数
- 达标标准：blocking ≥ 3 AND warning ≥ 2
- 计算缺口数：gap_blocking = max(0, 3 - blocking_count)
- 返回汇总：total_rules / compliant_cycles / non_compliant_cycles
- 权限：仅 qc/admin 可访问

注册到 router_registry 协作域 §110。

Validates: Requirements F6.1, F6.2, F6.3, F6.6
"""

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(
    prefix="/api/qc/vr-coverage",
    tags=["qc-vr-coverage"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class CycleCoverage(BaseModel):
    cycle_name: str
    blocking_count: int
    warning_count: int
    info_count: int
    total_count: int
    meets_standard: bool
    gap_blocking: int
    gap_warning: int


class VRCoverageResponse(BaseModel):
    cycles: list[CycleCoverage]
    total_rules: int
    compliant_cycles: int
    non_compliant_cycles: int


# ---------------------------------------------------------------------------
# Permission check
# ---------------------------------------------------------------------------


def _check_qc_admin(user: User) -> None:
    """仅 qc/admin 可访问"""
    if user.role.value not in ("qc", "admin"):
        raise HTTPException(status_code=403, detail="仅 QC/管理员可访问")


# ---------------------------------------------------------------------------
# Data directory resolution
# ---------------------------------------------------------------------------


def _resolve_data_dir() -> Path:
    """Resolve the backend/data directory path."""
    env_path = os.environ.get("VR_RULES_DATA_DIR")
    if env_path:
        return Path(env_path)
    # Default: relative to this file
    return Path(__file__).resolve().parents[2] / "data"


# ---------------------------------------------------------------------------
# VR rules scanning
# ---------------------------------------------------------------------------

# Mapping from file prefix to cycle display name
_CYCLE_FILE_MAP = {
    "bcas": "B/C",
    "d": "D",
    "efghijklmn": "EFGHIJKLMN",
    "f": "F",
    "g": "G",
    "h": "H",
    "i": "I",
    "j": "J",
    "k": "K",
    "l": "L",
    "m": "M",
    "n": "N",
}


def _scan_vr_rules(data_dir: Path) -> list[CycleCoverage]:
    """Scan all *_cycle_validation_rules.json files and compute coverage."""
    cycles: list[CycleCoverage] = []

    # Find all matching files
    for json_file in sorted(data_dir.glob("*_cycle_validation_rules.json")):
        filename = json_file.name
        # Extract cycle prefix from filename (e.g., "d_cycle_validation_rules.json" -> "d")
        prefix = filename.replace("_cycle_validation_rules.json", "")

        cycle_name = _CYCLE_FILE_MAP.get(prefix, prefix.upper())

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        rules = data.get("rules", [])

        blocking_count = sum(1 for r in rules if r.get("severity") == "blocking")
        warning_count = sum(1 for r in rules if r.get("severity") == "warning")
        info_count = sum(1 for r in rules if r.get("severity") == "info")
        total_count = len(rules)

        meets_standard = blocking_count >= 3 and warning_count >= 2
        gap_blocking = max(0, 3 - blocking_count)
        gap_warning = max(0, 2 - warning_count)

        cycles.append(
            CycleCoverage(
                cycle_name=cycle_name,
                blocking_count=blocking_count,
                warning_count=warning_count,
                info_count=info_count,
                total_count=total_count,
                meets_standard=meets_standard,
                gap_blocking=gap_blocking,
                gap_warning=gap_warning,
            )
        )

    return cycles


# ---------------------------------------------------------------------------
# GET /api/qc/vr-coverage
# ---------------------------------------------------------------------------


@router.get("", response_model=VRCoverageResponse)
async def get_vr_coverage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VRCoverageResponse:
    """返回各循环 VR 规则覆盖度统计"""
    _check_qc_admin(current_user)

    data_dir = _resolve_data_dir()
    if not data_dir.is_dir():
        raise HTTPException(status_code=503, detail="VR 规则数据目录不可用")

    cycles = _scan_vr_rules(data_dir)

    total_rules = sum(c.total_count for c in cycles)
    compliant_cycles = sum(1 for c in cycles if c.meets_standard)
    non_compliant_cycles = sum(1 for c in cycles if not c.meets_standard)

    return VRCoverageResponse(
        cycles=cycles,
        total_rules=total_rules,
        compliant_cycles=compliant_cycles,
        non_compliant_cycles=non_compliant_cycles,
    )
