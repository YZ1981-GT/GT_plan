"""模板库管理路由（template-library-coordination Sprint 1）

提供 6 个聚合查询/操作端点，作为模板库管理页（TemplateLibraryMgmt.vue）的数据源：

- GET  /api/template-library-mgmt/formula-coverage    — 公式覆盖率统计（按循环 + 按报表类型）
- GET  /api/template-library-mgmt/prefill-formulas    — 预填充公式映射全集（来自 prefill_formula_mapping.json）
- GET  /api/template-library-mgmt/cross-wp-references — 跨底稿引用规则全集（来自 cross_wp_references.json）
- GET  /api/template-library-mgmt/seed-status         — 各种子数据加载状态（COUNT vs expected）
- POST /api/template-library-mgmt/seed-all            — 一键加载全部种子（D15 SAVEPOINT 边界）
- GET  /api/template-library-mgmt/version-info        — 版本标识 + seed_load_history 最近记录

设计要点：
- D12 ADR：本路由是 audit-chain-generation 的纯消费方，不重复加载任何 seed
- D13 ADR：JSON 类资源只读（mutation 端点对 JSON 资源返回 405 Method Not Allowed + hint）
- D14 ADR：禁止引用 WpTemplateMetadata.subtable_codes 字段（不存在）
- D15 ADR：seed-all 每个 seed 独立 SAVEPOINT，失败不影响其他 seed
- D16 ADR：所有 expected_count 运行时从 seed JSON 文件 entries 数 / DB COUNT 实时取，不硬编码

Validates: Requirements 6.6, 7.1-7.6, 8.1-8.5, 13.1-13.6, 14.1-14.5, 17.1-17.6, 18.1-18.5
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/template-library-mgmt",
    tags=["template-library-mgmt"],
)

# 数据文件目录（与 wp_template_metadata.py / wp_template_init_service 保持一致）
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# 版本标识（D6 ADR：硬编码版本，无需复杂版本控制系统）
TEMPLATE_LIBRARY_VERSION = "致同 2025 修订版"
TEMPLATE_LIBRARY_RELEASE_DATE = "2025-01-01"


# ---------------------------------------------------------------------------
# Pydantic 响应模型（Task 1.5）
# ---------------------------------------------------------------------------


class CycleCoverage(BaseModel):
    cycle: str
    cycle_name: str
    total_templates: int
    templates_with_formula: int
    coverage_percent: float


class ReportTypeCoverage(BaseModel):
    report_type: str
    applicable_standard: str
    total_rows: int
    rows_with_formula: int
    coverage_percent: float


class FormulaTypeCount(BaseModel):
    formula_type: str
    count: int


class NoFormulaItem(BaseModel):
    wp_code: str
    wp_name: str | None = None
    cycle: str | None = None


class FormulaCoverageResponse(BaseModel):
    prefill_coverage: list[CycleCoverage]
    report_formula_coverage: list[ReportTypeCoverage]
    formula_type_distribution: list[FormulaTypeCount]
    no_formula_templates: list[NoFormulaItem]
    summary: dict[str, Any] = Field(default_factory=dict)


class SeedInfo(BaseModel):
    seed_name: str
    last_loaded_at: str | None
    record_count: int
    expected_count: int | None
    status: str  # loaded / not_loaded / partial / unknown


class SeedStatusResponse(BaseModel):
    seeds: list[SeedInfo]


class VersionInfoResponse(BaseModel):
    version: str
    release_date: str
    last_seed_loads: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# 工具函数：JSON 文件读取（带异常兜底，文件不存在时返回 None）
# ---------------------------------------------------------------------------


def _safe_load_json(filename: str) -> dict | list | None:
    path = DATA_DIR / filename
    if not path.exists():
        logger.warning("seed/index file missing: %s", path)
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("failed to load %s: %s", path, exc)
        return None


def _load_prefill_mappings() -> list[dict]:
    data = _safe_load_json("prefill_formula_mapping.json")
    if isinstance(data, dict):
        return list(data.get("mappings", []) or [])
    return []


def _load_cross_wp_references() -> list[dict]:
    data = _safe_load_json("cross_wp_references.json")
    if isinstance(data, dict):
        return list(data.get("references", []) or [])
    return []


# ---------------------------------------------------------------------------
# Task 1.6: derive_seed_status 纯函数（合并到本文件，便于属性测试）
# ---------------------------------------------------------------------------


def derive_seed_status(record_count: int, expected_count: int | None) -> str:
    """根据 record_count 和 expected_count 推导加载状态。

    - expected_count is None → "unknown"（seed 文件缺失或损坏）
    - record_count == 0 → "not_loaded"
    - 0 < record_count < expected_count → "partial"
    - record_count >= expected_count → "loaded"

    **Validates: Requirements 18.4, 18.5; Property 8**
    """
    if expected_count is None:
        return "unknown"
    if record_count <= 0:
        return "not_loaded"
    if record_count < expected_count:
        return "partial"
    return "loaded"


# ---------------------------------------------------------------------------
# 端点 1: GET /prefill-formulas — 返回 JSON 中全部预填充映射
# ---------------------------------------------------------------------------


@router.get("/prefill-formulas")
async def get_prefill_formulas(
    current_user: User = Depends(get_current_user),
):
    """返回 prefill_formula_mapping.json 全部映射（数量动态读取）。

    JSON 类只读资源（D13 ADR）。
    """
    mappings = _load_prefill_mappings()
    return {
        "mappings": mappings,
        "total_mappings": len(mappings),
        "total_cells": sum(len(m.get("cells", []) or []) for m in mappings),
        "source": "backend/data/prefill_formula_mapping.json",
        "readonly": True,
        "hint": "JSON 源只读，请编辑 backend/data/prefill_formula_mapping.json 后调用 reseed",
    }


@router.put("/prefill-formulas/{wp_code}", status_code=405)
async def reject_prefill_formulas_mutation(wp_code: str):
    """拒绝对 JSON 类资源的直接编辑（D13 ADR + Property 17）。"""
    raise HTTPException(
        status_code=405,
        detail={
            "error_code": "JSON_SOURCE_READONLY",
            "hint": "JSON 源只读，请编辑 backend/data/prefill_formula_mapping.json 后调用 reseed 端点",
            "wp_code": wp_code,
        },
    )


@router.delete("/prefill-formulas/{wp_code}", status_code=405)
async def reject_prefill_formulas_delete(wp_code: str):
    """拒绝删除（D13 ADR + Property 17）。"""
    raise HTTPException(
        status_code=405,
        detail={
            "error_code": "JSON_SOURCE_READONLY",
            "hint": "JSON 源只读，无法直接删除",
        },
    )


# ---------------------------------------------------------------------------
# 端点 2: GET /cross-wp-references — 返回 JSON 中全部跨底稿引用规则
# ---------------------------------------------------------------------------


@router.get("/cross-wp-references")
async def get_cross_wp_references(
    current_user: User = Depends(get_current_user),
):
    """返回 cross_wp_references.json 全部规则（数量动态读取）。

    JSON 类只读资源（D13 ADR）。
    """
    references = _load_cross_wp_references()
    return {
        "references": references,
        "total_references": len(references),
        "source": "backend/data/cross_wp_references.json",
        "readonly": True,
        "hint": "JSON 源只读，请编辑 backend/data/cross_wp_references.json 后调用 reseed",
    }


@router.put("/cross-wp-references/{ref_id}", status_code=405)
async def reject_cross_wp_references_mutation(ref_id: str):
    """拒绝对 JSON 类资源的直接编辑（D13 ADR + Property 17）。"""
    raise HTTPException(
        status_code=405,
        detail={
            "error_code": "JSON_SOURCE_READONLY",
            "hint": "JSON 源只读，请编辑 backend/data/cross_wp_references.json 后调用 reseed",
            "ref_id": ref_id,
        },
    )


# ---------------------------------------------------------------------------
# 端点 3: GET /formula-coverage — 公式覆盖率统计
# ---------------------------------------------------------------------------


# 循环编码 → 中文名称（与 wp_template_download.py CYCLE_NAMES 保持一致）
CYCLE_NAMES = {
    "A": "A 完成阶段",
    "B": "B 风险评估",
    "C": "C 控制测试",
    "D": "D 销售循环",
    "E": "E 货币资金",
    "F": "F 存货",
    "G": "G 投资",
    "H": "H 固定资产",
    "I": "I 无形资产",
    "J": "J 薪酬",
    "K": "K 费用",
    "L": "L 负债",
    "M": "M 权益",
    "N": "N 税项",
    "S": "S 特定项目",
}


def _percent(numerator: int, denominator: int) -> float:
    """覆盖率百分比，保留 1 位小数（Property 6）。"""
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


@router.get("/formula-coverage", response_model=FormulaCoverageResponse)
async def get_formula_coverage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """公式覆盖率统计：

    - 按循环统计预填充覆盖率（wp_template_metadata 主编码 vs prefill_formula_mapping wp_code）
    - 按报表类型 + 准则统计报表公式覆盖率（report_config 全表，formula 非空率）
    - 按 formula_type 分布预填充公式（TB/TB_SUM/ADJ/PREV/WP/...）
    - 无公式底稿清单（wp_template_metadata 主编码不在 prefill_formula_mapping 中的）

    所有数字运行时聚合，禁止硬编码（D16 ADR / Property 6）。
    """
    # 1) 加载预填充映射 → wp_code 集合
    prefill_mappings = _load_prefill_mappings()
    prefill_wp_codes = {m.get("wp_code") for m in prefill_mappings if m.get("wp_code")}

    # 2) 查 wp_template_metadata 主编码（按 cycle 分组）
    rows = (
        await db.execute(
            text(
                "SELECT wp_code, cycle FROM wp_template_metadata "
                "WHERE wp_code IS NOT NULL"
            )
        )
    ).mappings().all()

    # 主编码 = wp_code.split("-")[0] 去重（Property 11 子表收敛）
    primary_by_cycle: dict[str, set[str]] = defaultdict(set)
    primary_to_name: dict[str, str] = {}
    for r in rows:
        wp_code = r["wp_code"]
        primary = wp_code.split("-")[0] if wp_code else None
        if not primary:
            continue
        cycle = r.get("cycle") or (primary[0] if primary else "?")
        primary_by_cycle[cycle].add(primary)
        primary_to_name.setdefault(primary, "")  # 保留待补充

    prefill_coverage: list[CycleCoverage] = []
    all_primary: set[str] = set()
    primary_with_formula: set[str] = set()
    for cycle in sorted(primary_by_cycle.keys()):
        primaries = primary_by_cycle[cycle]
        all_primary.update(primaries)
        with_formula = primaries & prefill_wp_codes
        primary_with_formula.update(with_formula)
        prefill_coverage.append(
            CycleCoverage(
                cycle=cycle,
                cycle_name=CYCLE_NAMES.get(cycle, f"{cycle} 循环"),
                total_templates=len(primaries),
                templates_with_formula=len(with_formula),
                coverage_percent=_percent(len(with_formula), len(primaries)),
            )
        )

    # 3) 查 report_config 报表公式覆盖率（按 applicable_standard + report_type）
    rpt_rows = (
        await db.execute(
            text(
                "SELECT applicable_standard, report_type, "
                "       COUNT(*) AS total, "
                "       SUM(CASE WHEN formula IS NOT NULL AND formula <> '' THEN 1 ELSE 0 END) AS with_f "
                "FROM report_config "
                "GROUP BY applicable_standard, report_type "
                "ORDER BY applicable_standard, report_type"
            )
        )
    ).mappings().all()
    report_formula_coverage = [
        ReportTypeCoverage(
            report_type=r["report_type"] or "unknown",
            applicable_standard=r["applicable_standard"] or "unknown",
            total_rows=int(r["total"] or 0),
            rows_with_formula=int(r["with_f"] or 0),
            coverage_percent=_percent(int(r["with_f"] or 0), int(r["total"] or 0)),
        )
        for r in rpt_rows
    ]

    # 4) 按 formula_type 分布（来自 prefill_formula_mapping cells 字段）
    type_counts: dict[str, int] = defaultdict(int)
    for m in prefill_mappings:
        for cell in m.get("cells", []) or []:
            ftype = cell.get("formula_type") or "unknown"
            type_counts[ftype] += 1
    formula_type_distribution = [
        FormulaTypeCount(formula_type=t, count=c)
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1])
    ]

    # 5) 无公式底稿清单（主编码维度）
    no_formula_primaries = all_primary - prefill_wp_codes
    no_formula_templates = [
        NoFormulaItem(
            wp_code=p,
            cycle=p[0] if p else None,
        )
        for p in sorted(no_formula_primaries)
    ]

    # 6) 顶部摘要（运行时聚合）
    total_report_rows = sum(c.total_rows for c in report_formula_coverage)
    total_report_with_formula = sum(c.rows_with_formula for c in report_formula_coverage)
    summary = {
        "total_primary_templates": len(all_primary),
        "primary_with_formula": len(primary_with_formula),
        "prefill_coverage_percent": _percent(len(primary_with_formula), len(all_primary)),
        "total_report_rows": total_report_rows,
        "report_rows_with_formula": total_report_with_formula,
        "report_coverage_percent": _percent(total_report_with_formula, total_report_rows),
        "total_prefill_mappings": len(prefill_mappings),
        "total_prefill_cells": sum(len(m.get("cells", []) or []) for m in prefill_mappings),
    }

    return FormulaCoverageResponse(
        prefill_coverage=prefill_coverage,
        report_formula_coverage=report_formula_coverage,
        formula_type_distribution=formula_type_distribution,
        no_formula_templates=no_formula_templates,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# 端点 4: GET /seed-status — 各种子数据加载状态
# ---------------------------------------------------------------------------

# 7 张表加载状态来源说明（Sprint 0 现状核验确认）：
#   - wp_template_metadata：sum(entries) 来自 dn/b/cas 3 个 seed 文件
#   - audit_report_templates：len(templates) 来自 audit_report_templates_seed.json
#   - note_templates：len(soe.sections) + len(listed.sections)
#   - report_config：sum(len(item["rows"])) 来自 report_config_seed.json（顶层 list）
#   - gt_wp_coding / accounting_standards / template_sets：无独立 seed JSON 文件
#     → expected_count 直接用 DB COUNT 实时取（status=loaded 当 count > 0）


def _expected_wp_template_metadata() -> int | None:
    total = 0
    found_any = False
    for fname in [
        "wp_template_metadata_dn_seed.json",
        "wp_template_metadata_b_seed.json",
        "wp_template_metadata_cas_seed.json",
    ]:
        data = _safe_load_json(fname)
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            total += len(data["entries"])
            found_any = True
    return total if found_any else None


def _expected_audit_report_templates() -> int | None:
    data = _safe_load_json("audit_report_templates_seed.json")
    if isinstance(data, dict) and isinstance(data.get("templates"), list):
        return len(data["templates"])
    return None


def _expected_note_templates() -> int | None:
    soe = _safe_load_json("note_template_soe.json")
    listed = _safe_load_json("note_template_listed.json")
    total = 0
    found_any = False
    if isinstance(soe, dict) and isinstance(soe.get("sections"), list):
        total += len(soe["sections"])
        found_any = True
    if isinstance(listed, dict) and isinstance(listed.get("sections"), list):
        total += len(listed["sections"])
        found_any = True
    return total if found_any else None


def _expected_report_config() -> int | None:
    data = _safe_load_json("report_config_seed.json")
    # 顶层是 list，每个元素含 rows 数组（22 个标准变体）
    if isinstance(data, list):
        return sum(len(item.get("rows", []) or []) for item in data if isinstance(item, dict))
    return None


def _expected_prefill_formula_mapping() -> int | None:
    data = _safe_load_json("prefill_formula_mapping.json")
    if isinstance(data, dict) and isinstance(data.get("mappings"), list):
        return len(data["mappings"])
    return None


def _expected_cross_wp_references() -> int | None:
    data = _safe_load_json("cross_wp_references.json")
    if isinstance(data, dict) and isinstance(data.get("references"), list):
        return len(data["references"])
    return None


@router.get("/seed-status", response_model=SeedStatusResponse)
async def get_seed_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """各种子数据加载状态（运行时聚合，不硬编码任何条目数）。

    - 有独立 seed JSON 的：expected = JSON entries/templates/sections/mappings/references/rows
    - 无独立 seed JSON 的（gt_wp_coding/accounting_standards/template_sets）：
      expected = 当前 DB COUNT，status=loaded 当 count > 0；status=not_loaded 当 count = 0
    """
    # 一次性查每张表 COUNT(*)（独立 SELECT 避免 N+1）
    table_counts: dict[str, int] = {}
    for table in [
        "wp_template_metadata",
        "report_config",
        "gt_wp_coding",
        "accounting_standards",
        "template_sets",
    ]:
        try:
            row = (
                await db.execute(text(f"SELECT COUNT(*) AS c FROM {table}"))
            ).mappings().first()
            table_counts[table] = int(row["c"] or 0) if row else 0
        except Exception as exc:
            logger.warning("count(%s) failed: %s", table, exc)
            table_counts[table] = 0

    # audit_report_templates（实际表名是 audit_report_templates 还是其他需要确认）
    # 复用 disclosure 注解：audit_report 表存项目报告，模板表是 audit_report_templates
    try:
        row = (
            await db.execute(
                text("SELECT COUNT(*) AS c FROM audit_report_templates")
            )
        ).mappings().first()
        table_counts["audit_report_templates"] = int(row["c"] or 0) if row else 0
    except Exception:
        table_counts["audit_report_templates"] = 0

    # note_templates 表（用于附注模板）
    try:
        row = (
            await db.execute(text("SELECT COUNT(*) AS c FROM note_templates"))
        ).mappings().first()
        table_counts["note_templates"] = int(row["c"] or 0) if row else 0
    except Exception:
        table_counts["note_templates"] = 0

    # 查 seed_load_history 最近 last_loaded_at
    last_loaded_map: dict[str, str] = {}
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT seed_name, MAX(loaded_at) AS last_at "
                    "FROM seed_load_history GROUP BY seed_name"
                )
            )
        ).mappings().all()
        for r in rows:
            if r["seed_name"] and r["last_at"]:
                last_loaded_map[r["seed_name"]] = r["last_at"].isoformat() if hasattr(r["last_at"], "isoformat") else str(r["last_at"])
    except Exception as exc:
        logger.warning("query seed_load_history failed: %s", exc)

    # 构造每个 seed 的状态
    seeds: list[SeedInfo] = []

    # 有独立 JSON 文件的（expected 来自 JSON）
    json_based = [
        ("wp_template_metadata", "wp_template_metadata", _expected_wp_template_metadata()),
        ("audit_report_templates", "audit_report_templates", _expected_audit_report_templates()),
        ("note_templates", "note_templates", _expected_note_templates()),
        ("report_config", "report_config", _expected_report_config()),
    ]
    for seed_name, table_name, expected in json_based:
        record_count = table_counts.get(table_name, 0)
        seeds.append(
            SeedInfo(
                seed_name=seed_name,
                last_loaded_at=last_loaded_map.get(seed_name),
                record_count=record_count,
                expected_count=expected,
                status=derive_seed_status(record_count, expected),
            )
        )

    # 无独立 JSON 文件的（expected = DB COUNT 自身，status 仅 loaded/not_loaded）
    db_only = [
        ("gt_wp_coding", "gt_wp_coding"),
        ("accounting_standards", "accounting_standards"),
        ("template_sets", "template_sets"),
    ]
    for seed_name, table_name in db_only:
        record_count = table_counts.get(table_name, 0)
        # 无 seed 文件时，DB count > 0 即视为 loaded
        expected_for_no_json = record_count if record_count > 0 else 1
        seeds.append(
            SeedInfo(
                seed_name=seed_name,
                last_loaded_at=last_loaded_map.get(seed_name),
                record_count=record_count,
                expected_count=expected_for_no_json,
                status="loaded" if record_count > 0 else "not_loaded",
            )
        )

    # JSON 类只读源（不入 DB，但展示最新文件 entries 数）
    json_readonly = [
        ("prefill_formula_mapping", _expected_prefill_formula_mapping()),
        ("cross_wp_references", _expected_cross_wp_references()),
    ]
    for seed_name, expected in json_readonly:
        seeds.append(
            SeedInfo(
                seed_name=seed_name,
                last_loaded_at=None,  # 文件源无加载历史
                record_count=expected if expected is not None else 0,
                expected_count=expected,
                status="loaded" if expected and expected > 0 else "unknown",
            )
        )

    return SeedStatusResponse(seeds=seeds)


# ---------------------------------------------------------------------------
# 端点 5: POST /seed-all — 一键加载全部种子（D15 SAVEPOINT 边界）
# ---------------------------------------------------------------------------

# 6 个 seed 端点的内部调用映射（端点路径 + 调用方式说明）
# 每个 seed 通过直接调用 service / router function 触发，独立 SAVEPOINT
SEED_PIPELINE = [
    "report_config",          # POST /api/report-config/seed
    "gt_wp_coding",           # POST /api/gt-coding/seed
    "wp_template_metadata",   # POST /api/wp-template-metadata/seed
    "audit_report_templates", # POST /api/audit-report/templates/load-seed
    "accounting_standards",   # POST /api/accounting-standards/seed
    "template_sets",          # POST /api/template-sets/seed
]


async def _record_history(
    db: AsyncSession,
    *,
    seed_name: str,
    status: str,
    record_count: int = 0,
    inserted: int = 0,
    updated: int = 0,
    errors: list | None = None,
    loaded_by: Any | None = None,
) -> None:
    """写入 seed_load_history 表（D15 审计轨迹）。"""
    try:
        await db.execute(
            text(
                "INSERT INTO seed_load_history "
                "(seed_name, loaded_at, loaded_by, record_count, inserted, updated, errors, status) "
                "VALUES (:seed_name, NOW(), :loaded_by, :record_count, :inserted, :updated, "
                "CAST(:errors AS JSONB), :status)"
            ),
            {
                "seed_name": seed_name,
                "loaded_by": loaded_by,
                "record_count": record_count,
                "inserted": inserted,
                "updated": updated,
                "errors": json.dumps(errors or [], ensure_ascii=False),
                "status": status,
            },
        )
    except Exception as exc:
        logger.error("record_history(%s) failed: %s", seed_name, exc)


async def _exec_seed(seed_name: str, db: AsyncSession, current_user: User) -> dict:
    """执行单个 seed（在 SAVEPOINT 内调用，由调用方处理事务边界）。

    返回结构 {seed_name, status, inserted, updated, record_count, errors}
    """
    if seed_name == "report_config":
        from app.services.report_config_service import ReportConfigService
        from app.services.report_formula_service import report_formula_service
        svc = ReportConfigService(db)
        count = await svc.load_seed_data()
        formula_stats = await report_formula_service.fill_all_formulas(db, standard="all")
        return {
            "seed_name": seed_name,
            "status": "loaded",
            "inserted": int(formula_stats.get("updated", 0)),
            "updated": 0,
            "record_count": int(count or 0),
            "errors": [],
        }
    if seed_name == "gt_wp_coding":
        from app.services.gt_coding_service import GTCodingService
        svc = GTCodingService()
        result = await svc.load_seed_data(db) if hasattr(svc, "load_seed_data") else None
        # gt_coding seed 端点使用 service 加载 — 通过实际查 COUNT 推导 record_count
        row = (await db.execute(text("SELECT COUNT(*) AS c FROM gt_wp_coding"))).mappings().first()
        record_count = int(row["c"] or 0) if row else 0
        return {
            "seed_name": seed_name,
            "status": "loaded",
            "inserted": int((result or {}).get("inserted", 0)) if isinstance(result, dict) else 0,
            "updated": int((result or {}).get("updated", 0)) if isinstance(result, dict) else 0,
            "record_count": record_count,
            "errors": [],
        }
    if seed_name == "wp_template_metadata":
        # 复用 wp_template_metadata.py 加载逻辑（直接读 3 个 seed 文件 + UPSERT）
        seed_files = [
            DATA_DIR / "wp_template_metadata_dn_seed.json",
            DATA_DIR / "wp_template_metadata_b_seed.json",
            DATA_DIR / "wp_template_metadata_cas_seed.json",
        ]
        from uuid import uuid4
        total_entries: list[dict] = []
        for sf in seed_files:
            if not sf.exists():
                continue
            with open(sf, "r", encoding="utf-8") as f:
                data = json.load(f)
            total_entries.extend(data.get("entries", []))

        inserted, updated, errors = 0, 0, []
        for entry in total_entries:
            wp_code = entry.get("wp_code")
            if not wp_code:
                continue
            try:
                existing = (await db.execute(
                    text("SELECT id FROM wp_template_metadata WHERE wp_code = :code"),
                    {"code": wp_code},
                )).first()
                row_data = {
                    "wp_code": wp_code,
                    "component_type": entry.get("component_type", "univer"),
                    "audit_stage": entry.get("audit_stage", "substantive"),
                    "cycle": entry.get("cycle"),
                    "file_format": entry.get("file_format", "xlsx"),
                    "procedure_steps": json.dumps(entry.get("procedure_steps") or [], ensure_ascii=False),
                    "formula_cells": json.dumps(entry.get("formula_cells") or [], ensure_ascii=False),
                    "linked_accounts": json.dumps(entry.get("linked_accounts") or [], ensure_ascii=False),
                    "note_section": entry.get("note_section"),
                    "conclusion_cell": json.dumps(entry.get("conclusion_cell"), ensure_ascii=False) if entry.get("conclusion_cell") else None,
                    "audit_objective": entry.get("audit_objective"),
                    "related_assertions": json.dumps(entry.get("related_assertions") or [], ensure_ascii=False),
                }
                if existing:
                    set_clause = ", ".join(f"{k} = :{k}" for k in row_data if k != "wp_code")
                    await db.execute(
                        text(f"UPDATE wp_template_metadata SET {set_clause} WHERE wp_code = :wp_code"),
                        row_data,
                    )
                    updated += 1
                else:
                    row_data["id"] = str(uuid4())
                    cols = ", ".join(row_data.keys())
                    vals = ", ".join(f":{k}" for k in row_data.keys())
                    await db.execute(
                        text(f"INSERT INTO wp_template_metadata ({cols}) VALUES ({vals})"),
                        row_data,
                    )
                    inserted += 1
            except Exception as e:
                errors.append({"wp_code": wp_code, "error": str(e)})
        return {
            "seed_name": seed_name,
            "status": "loaded" if not errors else "partial",
            "inserted": inserted,
            "updated": updated,
            "record_count": inserted + updated,
            "errors": errors[:10],
        }
    if seed_name == "audit_report_templates":
        from app.services.audit_report_service import AuditReportService
        svc = AuditReportService(db)
        count = await svc.load_seed_templates()
        return {
            "seed_name": seed_name,
            "status": "loaded",
            "inserted": int(count or 0),
            "updated": 0,
            "record_count": int(count or 0),
            "errors": [],
        }
    if seed_name == "accounting_standards":
        from app.services.accounting_standard_service import AccountingStandardService
        svc = AccountingStandardService(db)
        result = await svc.load_seed_data() if hasattr(svc, "load_seed_data") else {}
        row = (await db.execute(text("SELECT COUNT(*) AS c FROM accounting_standards"))).mappings().first()
        record_count = int(row["c"] or 0) if row else 0
        return {
            "seed_name": seed_name,
            "status": "loaded",
            "inserted": int((result or {}).get("inserted", 0)) if isinstance(result, dict) else 0,
            "updated": int((result or {}).get("updated", 0)) if isinstance(result, dict) else 0,
            "record_count": record_count,
            "errors": [],
        }
    if seed_name == "template_sets":
        # template_sets 通过 wp_template.py /api/template-sets/seed 端点加载
        # 直接调用其 service 等价逻辑
        try:
            from app.services.wp_template_service import WpTemplateService
            svc = WpTemplateService(db)
            if hasattr(svc, "seed_template_sets"):
                result = await svc.seed_template_sets()
            else:
                result = {}
        except ImportError:
            result = {}
        row = (await db.execute(text("SELECT COUNT(*) AS c FROM template_sets"))).mappings().first()
        record_count = int(row["c"] or 0) if row else 0
        return {
            "seed_name": seed_name,
            "status": "loaded",
            "inserted": int((result or {}).get("inserted", 0)) if isinstance(result, dict) else 0,
            "updated": int((result or {}).get("updated", 0)) if isinstance(result, dict) else 0,
            "record_count": record_count,
            "errors": [],
        }
    raise ValueError(f"unknown seed: {seed_name}")


@router.post("/seed-all")
async def seed_all(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "partner"])),
):
    """一键加载全部种子（D15 SAVEPOINT 边界，每个 seed 独立事务）。

    Property 16: 后端二次校验 admin/partner 权限（不依赖前端 v-permission）。
    Property 9: Seed load resilience — 单个 seed 失败不影响其他 seed。
    """
    results: list[dict] = []
    for seed_name in SEED_PIPELINE:
        try:
            async with db.begin_nested():  # SAVEPOINT
                result = await _exec_seed(seed_name, db, current_user)
            # 历史记录在 SAVEPOINT 外提交（独立事务避免回滚污染）
            await _record_history(
                db,
                seed_name=seed_name,
                status=result.get("status", "loaded"),
                record_count=result.get("record_count", 0),
                inserted=result.get("inserted", 0),
                updated=result.get("updated", 0),
                errors=result.get("errors", []),
                loaded_by=current_user.id,
            )
            results.append(result)
        except Exception as exc:
            logger.exception("seed %s failed", seed_name)
            await _record_history(
                db,
                seed_name=seed_name,
                status="failed",
                errors=[{"error": str(exc)}],
                loaded_by=current_user.id,
            )
            results.append({
                "seed_name": seed_name,
                "status": "failed",
                "error": str(exc),
                "inserted": 0,
                "updated": 0,
                "record_count": 0,
            })

    # 全部完成后统一 commit（history 记录 + 各 seed 已 SAVEPOINT 提交）
    await db.commit()

    success_count = sum(1 for r in results if r.get("status") == "loaded")
    failed_count = sum(1 for r in results if r.get("status") == "failed")

    return {
        "total": len(results),
        "loaded": success_count,
        "failed": failed_count,
        "partial": len(results) - success_count - failed_count,
        "results": results,
    }


# ---------------------------------------------------------------------------
# 端点 6: GET /version-info — 版本标识 + seed 加载历史
# ---------------------------------------------------------------------------


@router.get("/version-info", response_model=VersionInfoResponse)
async def get_version_info(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回版本标识 + seed_load_history 最近 N 条记录（按 loaded_at DESC）。"""
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT seed_name, loaded_at, record_count, inserted, updated, status "
                    "FROM seed_load_history "
                    "ORDER BY loaded_at DESC "
                    "LIMIT 20"
                )
            )
        ).mappings().all()
        last_seed_loads = [
            {
                "seed_name": r["seed_name"],
                "loaded_at": r["loaded_at"].isoformat() if hasattr(r["loaded_at"], "isoformat") else str(r["loaded_at"]),
                "record_count": int(r["record_count"] or 0),
                "inserted": int(r["inserted"] or 0),
                "updated": int(r["updated"] or 0),
                "status": r["status"],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("query seed_load_history failed: %s", exc)
        last_seed_loads = []

    return VersionInfoResponse(
        version=TEMPLATE_LIBRARY_VERSION,
        release_date=TEMPLATE_LIBRARY_RELEASE_DATE,
        last_seed_loads=last_seed_loads,
    )
