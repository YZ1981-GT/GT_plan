"""报表行次映射服务 — AI建议 + 确认 + 集团参照 + 跨年继承

Validates: Requirements 3.9, 3.10, 3.11, 3.12, 3.13, 3.14

数据驱动: 标准科目 → 报表行次的映射来自 backend/data/account_to_report_line_seed.json
按项目维度 (template_type × report_scope) 加载 4 套独立 seed:
  - soe_standalone (国企单体)
  - soe_consolidated (国企合并)
  - listed_standalone (上市单体)
  - listed_consolidated (上市合并)
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountChart,
    AccountMapping,
    AccountSource,
    ReportLineMapping,
    ReportLineMappingType,
    ReportType,
)
from app.models.audit_platform_schemas import (
    ReferenceCopyResult,
    ReportLine,
    ReportLineMappingResponse,
    ReportLineMappingUpdate,
)
from app.models.core import Project

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据驱动: 加载 account_to_report_line_seed.json (按 4 套维度)
# ---------------------------------------------------------------------------

_SEED_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "account_to_report_line_seed.json"


@lru_cache(maxsize=1)
def _load_seed() -> dict[str, dict[str, dict]]:
    """加载 seed 文件,返回 {applicable_standard: {std_account_code: {row_code, row_name, report_type}}}.

    LRU 缓存,首次加载后常驻内存。如果 seed 改了需重启服务或调 _load_seed.cache_clear().
    """
    if not _SEED_PATH.exists():
        logger.error(f"account_to_report_line_seed.json 不存在: {_SEED_PATH}")
        return {}
    try:
        raw = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
        out: dict[str, dict[str, dict]] = {}
        for std_key, mappings in raw.get("mappings", {}).items():
            out[std_key] = {}
            for m in mappings:
                code = m["standard_account_code"]
                out[std_key][code] = {
                    "report_line_code": m["report_line_code"],
                    "report_line_name": m["report_line_name"],
                    "report_type": m["report_type"],
                }
        logger.info(
            f"account_to_report_line_seed loaded: "
            + ", ".join(f"{k}={len(v)}" for k, v in out.items())
        )
        return out
    except Exception as e:
        logger.error(f"加载 account_to_report_line_seed 失败: {e}")
        return {}


def _derive_applicable_standard(
    template_type: str | None, report_scope: str | None
) -> str:
    """根据项目的 template_type + report_scope 派生 seed 维度 key.

    - template_type: soe / listed (国企版/上市版,默认 soe)
    - report_scope: standalone / consolidated (单体/合并,默认 standalone)

    返回: soe_standalone / soe_consolidated / listed_standalone / listed_consolidated
    """
    tt = (template_type or "soe").lower().strip()
    if tt not in ("soe", "listed"):
        tt = "soe"
    rs = (report_scope or "standalone").lower().strip()
    if rs not in ("standalone", "consolidated"):
        rs = "standalone"
    return f"{tt}_{rs}"


async def _get_project_applicable_standard(
    project_id: UUID, db: AsyncSession
) -> str:
    """从 project 表读 template_type + report_scope 派生 applicable_standard."""
    result = await db.execute(
        select(Project.template_type, Project.report_scope).where(
            Project.id == project_id
        )
    )
    row = result.first()
    if not row:
        return "soe_standalone"  # 项目不存在,默认国企单体
    return _derive_applicable_standard(row[0], row[1])


def _normalize_account_code(code: str) -> str:
    """规范化客户科目编码,用于 seed 查表 (与 mapping_service._normalize_account_code 同源)."""
    if not code:
        return ""
    out = code.strip()
    for sep in (".", "-", "/", "_", "\\", " "):
        out = out.replace(sep, "")
    return out


def _lookup_report_line_from_seed(
    standard_account_code: str,
    applicable_standard: str,
) -> tuple[str, str, str] | None:
    """从 seed 查 (line_code, line_name, report_type). 找不到返回 None.

    匹配优先级:
    1. 完整编码精确匹配(如 1231-01 / 100201)
    2. 4 位前缀匹配(如 100201 → 1001)
    3. 客户科目带分隔符(如 6401.01 / 6401-01) 也走规范化后的 4 位前缀
    """
    seed = _load_seed()
    std_map = seed.get(applicable_standard) or seed.get("soe_standalone") or {}
    if not std_map:
        return None

    code = standard_account_code.strip()

    # 策略 1: 带连字符的二级科目(坏账分项 1231-01) 直接精确匹配
    if "-" in code and code in std_map:
        m = std_map[code]
        return m["report_line_code"], m["report_line_name"], m["report_type"]

    # 策略 2: 完整编码精确匹配
    if code in std_map:
        m = std_map[code]
        return m["report_line_code"], m["report_line_name"], m["report_type"]

    # 策略 3: 规范化后取 4 位前缀
    normalized = _normalize_account_code(code)
    prefix4 = normalized[:4] if len(normalized) >= 4 else normalized
    if prefix4 in std_map:
        m = std_map[prefix4]
        return m["report_line_code"], m["report_line_name"], m["report_type"]

    return None


def _determine_report_type_from_code(account_code: str) -> ReportType | None:
    """根据科目编码前缀判断报表类型(兜底,seed 优先).

    企业会计准则:
    - 1xxx/2xxx/3xxx: 资产/负债/权益 → 资产负债表
    - 4xxx/5xxx/6xxx: 成本/损益 → 4xxx 在新版准则归成本类(进利润表), 但 30/40 系列偶有权益用法
    """
    prefix = account_code[:1] if account_code else ""
    if prefix in ("1", "2", "3"):
        return ReportType.balance_sheet
    if prefix in ("4", "5", "6"):
        return ReportType.income_statement
    return None


# ---------------------------------------------------------------------------
# ai_suggest_mappings (Task 7a.2) — 数据驱动版,按项目维度从 seed 加载
# ---------------------------------------------------------------------------


async def ai_suggest_mappings(
    project_id: UUID,
    db: AsyncSession,
    force_refresh: bool = False,
) -> list[dict]:
    """根据项目维度 (template_type × report_scope) 从 seed 加载映射规则,生成报表行次映射建议.

    Validates: Requirements 3.10

    数据流:
    1. 读项目的 template_type / report_scope → 派生 applicable_standard
    2. 从 account_to_report_line_seed.json 加载对应维度的 seed
    3. 遍历项目已映射的标准科目, 按 seed 查 (line_code, line_name, report_type)
    4. 创建 ReportLineMapping 记录(is_confirmed=False, mapping_type=ai_suggested)

    Args:
        force_refresh: True 时强制刷新所有 ai_suggested 记录(不管 is_confirmed),
                       覆盖老 BSXXX 格式. manual / reference_copied 永远不动.
                       False(默认)时仅刷新 ai_suggested + is_confirmed=False 的记录.
    """
    # 1. 派生 applicable_standard
    applicable_standard = await _get_project_applicable_standard(project_id, db)
    logger.info(f"ai_suggest_mappings: project={project_id} standard={applicable_standard}")

    # 2. 获取项目已映射的标准科目
    mapped_result = await db.execute(
        select(AccountMapping.standard_account_code).where(
            AccountMapping.project_id == project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
        ).distinct()
    )
    mapped_std_codes = [row[0] for row in mapped_result.all()]

    # 构建科目编码→名称映射（从 AccountChart 获取）
    code_name_map: dict[str, str] = {}
    if mapped_std_codes:
        name_result = await db.execute(
            select(AccountChart.account_code, AccountChart.account_name).where(
                AccountChart.project_id == project_id,
                AccountChart.account_code.in_(mapped_std_codes),
                AccountChart.is_deleted == False,  # noqa: E712
            )
        )
        for row in name_result.all():
            code_name_map[row[0]] = row[1] or ""

    if not mapped_std_codes:
        # 回退：直接使用标准科目表
        std_result = await db.execute(
            select(AccountChart.account_code, AccountChart.account_name).where(
                AccountChart.project_id == project_id,
                AccountChart.source == AccountSource.standard,
                AccountChart.is_deleted == False,  # noqa: E712
            )
        )
        std_accounts = std_result.all()
        mapped_std_codes = [row[0] for row in std_accounts]
        for row in std_accounts:
            code_name_map[row[0]] = row[1] or ""

    # 如果 AccountChart 没有名称，尝试从 TrialBalance 获取
    if not code_name_map:
        from app.models.audit_platform_models import TrialBalance
        tb_result = await db.execute(
            select(TrialBalance.standard_account_code, TrialBalance.account_name).where(
                TrialBalance.project_id == project_id,
                TrialBalance.is_deleted == False,  # noqa: E712
            ).distinct()
        )
        for row in tb_result.all():
            if row[0] and row[1]:
                code_name_map[row[0]] = row[1]

    suggestions: list[dict] = []
    seen_keys: set[str] = set()

    for std_code in mapped_std_codes:
        # seed 优先: 直接从 seed 查 (line_code, line_name, report_type)
        seed_hit = _lookup_report_line_from_seed(std_code, applicable_standard)
        if seed_hit is None:
            # 编码前缀都不在 seed → 跳过(不再走旧的关键词兜底,避免乱匹配 BS001 vs BS-001)
            continue

        line_code, line_name, report_type_str = seed_hit
        try:
            rt = ReportType(report_type_str)
        except ValueError:
            logger.warning(f"seed 中 report_type 值非法: {report_type_str} for {std_code}")
            continue

        key = f"{std_code}:{rt.value}"
        if key in seen_keys:
            continue
        seen_keys.add(key)

        # 检查是否已存在映射
        existing_result = await db.execute(
            select(ReportLineMapping).where(
                ReportLineMapping.project_id == project_id,
                ReportLineMapping.standard_account_code == std_code,
                ReportLineMapping.report_type == rt,
                ReportLineMapping.is_deleted == False,  # noqa: E712
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            # 已存在: 仅当原是 ai_suggested 时考虑刷新
            # manual / reference_copied 永远不动,保护用户手工设置
            if existing.mapping_type != ReportLineMappingType.ai_suggested:
                continue
            # ai_suggested 记录:
            # - force_refresh=True: 不管 is_confirmed 都刷新 (修复底层格式 BSXXX→BS-XXX)
            # - force_refresh=False: 仅刷新未确认的
            if not force_refresh and existing.is_confirmed:
                continue
            old_code = existing.report_line_code
            if old_code != line_code or existing.report_line_name != line_name:
                existing.report_line_code = line_code
                existing.report_line_name = line_name
                existing.report_line_level = 1
                existing.parent_line_code = None
                suggestions.append({
                    "standard_account_code": std_code,
                    "report_type": rt.value,
                    "report_line_code": line_code,
                    "report_line_name": line_name,
                    "report_line_level": 1,
                    "parent_line_code": None,
                    "confidence": 1.0,
                    "applicable_standard": applicable_standard,
                    "action": "refreshed",
                    "old_report_line_code": old_code,
                })
            continue

        # 创建映射建议
        mapping = ReportLineMapping(
            project_id=project_id,
            standard_account_code=std_code,
            report_type=rt,
            report_line_code=line_code,
            report_line_name=line_name,
            report_line_level=1,
            parent_line_code=None,
            mapping_type=ReportLineMappingType.ai_suggested,
            is_confirmed=False,
        )
        db.add(mapping)
        suggestions.append({
            "standard_account_code": std_code,
            "report_type": rt.value,
            "report_line_code": line_code,
            "report_line_name": line_name,
            "report_line_level": 1,
            "parent_line_code": None,
            "confidence": 1.0,
            "applicable_standard": applicable_standard,
            "action": "created",
        })

    await db.flush()
    await db.commit()

    return suggestions


# ---------------------------------------------------------------------------
# get_mappings (列表查询)
# ---------------------------------------------------------------------------


async def get_mappings(
    project_id: UUID,
    db: AsyncSession,
    report_type: str | None = None,
) -> list[ReportLineMappingResponse]:
    """获取报表行次映射列表，可按 report_type 筛选。"""
    stmt = select(ReportLineMapping).where(
        ReportLineMapping.project_id == project_id,
        ReportLineMapping.is_deleted == False,  # noqa: E712
    )
    if report_type:
        stmt = stmt.where(ReportLineMapping.report_type == report_type)
    stmt = stmt.order_by(
        ReportLineMapping.report_type,
        ReportLineMapping.standard_account_code,
    )

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [ReportLineMappingResponse.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# confirm_mapping (Task 7a.3 — 单条确认)
# ---------------------------------------------------------------------------


async def confirm_mapping(
    project_id: UUID,
    mapping_id: UUID,
    db: AsyncSession,
) -> ReportLineMappingResponse:
    """确认单条报表行次映射。

    Validates: Requirements 3.11
    """
    result = await db.execute(
        select(ReportLineMapping).where(
            ReportLineMapping.id == mapping_id,
            ReportLineMapping.project_id == project_id,
            ReportLineMapping.is_deleted == False,  # noqa: E712
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="映射记录不存在")

    record.is_confirmed = True
    await db.flush()
    await db.commit()
    await db.refresh(record)
    return ReportLineMappingResponse.model_validate(record)


# ---------------------------------------------------------------------------
# batch_confirm (Task 7a.3 — 批量确认)
# ---------------------------------------------------------------------------


async def batch_confirm(
    project_id: UUID,
    mapping_ids: list[UUID],
    db: AsyncSession,
) -> int:
    """批量确认报表行次映射，返回确认数量。

    Validates: Requirements 3.11
    """
    if not mapping_ids:
        return 0

    await db.execute(
        update(ReportLineMapping)
        .where(
            ReportLineMapping.id.in_(mapping_ids),
            ReportLineMapping.project_id == project_id,
            ReportLineMapping.is_deleted == False,  # noqa: E712
        )
        .values(is_confirmed=True)
    )
    await db.commit()
    return len(mapping_ids)


# ---------------------------------------------------------------------------
# reference_copy (Task 7a.4 — 集团参照复制)
# ---------------------------------------------------------------------------


async def reference_copy(
    source_company_code: str,
    target_project_id: UUID,
    db: AsyncSession,
) -> ReferenceCopyResult:
    """从同集团源企业复制已确认的报表行次映射。

    Validates: Requirements 3.12, 3.13
    """
    from app.models.core import Project

    # 查找源企业的项目（通过 company_code 匹配，取最新的）
    source_project_result = await db.execute(
        select(Project).where(
            Project.is_deleted == False,  # noqa: E712
        ).order_by(Project.created_at.desc())
    )
    source_projects = source_project_result.scalars().all()

    # 查找有已确认映射的源项目
    source_project_id: UUID | None = None
    for proj in source_projects:
        if proj.id == target_project_id:
            continue
        # 检查 wizard_state 中的 company_code 或 client_name
        ws = proj.wizard_state or {}
        basic = ws.get("basic_info", {}).get("data", {})
        if basic.get("client_name", "") == source_company_code:
            source_project_id = proj.id
            break

    if source_project_id is None:
        # 回退：尝试用任何有已确认映射的其他项目
        for proj in source_projects:
            if proj.id == target_project_id:
                continue
            check = await db.execute(
                select(ReportLineMapping).where(
                    ReportLineMapping.project_id == proj.id,
                    ReportLineMapping.is_confirmed == True,  # noqa: E712
                    ReportLineMapping.is_deleted == False,  # noqa: E712
                ).limit(1)
            )
            if check.scalar_one_or_none():
                source_project_id = proj.id
                break

    if source_project_id is None:
        return ReferenceCopyResult(copied_count=0, unmatched_accounts=[])

    # 获取源项目已确认映射
    source_result = await db.execute(
        select(ReportLineMapping).where(
            ReportLineMapping.project_id == source_project_id,
            ReportLineMapping.is_confirmed == True,  # noqa: E712
            ReportLineMapping.is_deleted == False,  # noqa: E712
        )
    )
    source_mappings = source_result.scalars().all()

    if not source_mappings:
        return ReferenceCopyResult(copied_count=0, unmatched_accounts=[])

    # 获取目标项目的标准科目编码集合
    target_std_result = await db.execute(
        select(AccountChart.account_code).where(
            AccountChart.project_id == target_project_id,
            AccountChart.source == AccountSource.standard,
            AccountChart.is_deleted == False,  # noqa: E712
        )
    )
    target_std_codes = {row[0] for row in target_std_result.all()}

    # 也包含已映射的标准科目
    target_mapped_result = await db.execute(
        select(AccountMapping.standard_account_code).where(
            AccountMapping.project_id == target_project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
        ).distinct()
    )
    target_std_codes.update(row[0] for row in target_mapped_result.all())

    copied_count = 0
    unmatched: list[str] = []

    for src in source_mappings:
        if src.standard_account_code not in target_std_codes:
            unmatched.append(src.standard_account_code)
            continue

        # 检查目标项目是否已有该映射
        existing = await db.execute(
            select(ReportLineMapping).where(
                ReportLineMapping.project_id == target_project_id,
                ReportLineMapping.standard_account_code == src.standard_account_code,
                ReportLineMapping.report_type == src.report_type,
                ReportLineMapping.is_deleted == False,  # noqa: E712
            )
        )
        if existing.scalar_one_or_none():
            continue

        new_mapping = ReportLineMapping(
            project_id=target_project_id,
            standard_account_code=src.standard_account_code,
            report_type=src.report_type,
            report_line_code=src.report_line_code,
            report_line_name=src.report_line_name,
            report_line_level=src.report_line_level,
            parent_line_code=src.parent_line_code,
            mapping_type=ReportLineMappingType.reference_copied,
            is_confirmed=False,
        )
        db.add(new_mapping)
        copied_count += 1

    await db.flush()
    await db.commit()

    return ReferenceCopyResult(
        copied_count=copied_count,
        unmatched_accounts=list(set(unmatched)),
    )


# ---------------------------------------------------------------------------
# inherit_from_prior_year (Task 7a.5)
# ---------------------------------------------------------------------------


async def inherit_from_prior_year(
    prior_project_id: UUID,
    current_project_id: UUID,
    db: AsyncSession,
) -> ReferenceCopyResult:
    """从上年项目复制已确认的报表行次映射到本年项目。

    Validates: Requirements 3.14
    """
    # 获取上年已确认映射
    prior_result = await db.execute(
        select(ReportLineMapping).where(
            ReportLineMapping.project_id == prior_project_id,
            ReportLineMapping.is_confirmed == True,  # noqa: E712
            ReportLineMapping.is_deleted == False,  # noqa: E712
        )
    )
    prior_mappings = prior_result.scalars().all()

    if not prior_mappings:
        return ReferenceCopyResult(copied_count=0, unmatched_accounts=[])

    # 获取当前项目的标准科目
    current_std_result = await db.execute(
        select(AccountChart.account_code).where(
            AccountChart.project_id == current_project_id,
            AccountChart.source == AccountSource.standard,
            AccountChart.is_deleted == False,  # noqa: E712
        )
    )
    current_std_codes = {row[0] for row in current_std_result.all()}

    current_mapped_result = await db.execute(
        select(AccountMapping.standard_account_code).where(
            AccountMapping.project_id == current_project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
        ).distinct()
    )
    current_std_codes.update(row[0] for row in current_mapped_result.all())

    copied_count = 0
    unmatched: list[str] = []

    for pm in prior_mappings:
        if pm.standard_account_code not in current_std_codes:
            unmatched.append(pm.standard_account_code)
            continue

        # 检查是否已存在
        existing = await db.execute(
            select(ReportLineMapping).where(
                ReportLineMapping.project_id == current_project_id,
                ReportLineMapping.standard_account_code == pm.standard_account_code,
                ReportLineMapping.report_type == pm.report_type,
                ReportLineMapping.is_deleted == False,  # noqa: E712
            )
        )
        if existing.scalar_one_or_none():
            continue

        new_mapping = ReportLineMapping(
            project_id=current_project_id,
            standard_account_code=pm.standard_account_code,
            report_type=pm.report_type,
            report_line_code=pm.report_line_code,
            report_line_name=pm.report_line_name,
            report_line_level=pm.report_line_level,
            parent_line_code=pm.parent_line_code,
            mapping_type=ReportLineMappingType.reference_copied,
            is_confirmed=False,
        )
        db.add(new_mapping)
        copied_count += 1

    await db.flush()
    await db.commit()

    return ReferenceCopyResult(
        copied_count=copied_count,
        unmatched_accounts=list(set(unmatched)),
    )


# ---------------------------------------------------------------------------
# update_mapping
# ---------------------------------------------------------------------------


async def update_mapping(
    project_id: UUID,
    mapping_id: UUID,
    data: ReportLineMappingUpdate,
    db: AsyncSession,
) -> ReportLineMappingResponse:
    result = await db.execute(
        select(ReportLineMapping).where(
            ReportLineMapping.id == mapping_id,
            ReportLineMapping.project_id == project_id,
            ReportLineMapping.is_deleted == False,  # noqa: E712
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="映射记录不存在")

    report_line_code = data.report_line_code.strip()
    report_line_name = data.report_line_name.strip()
    parent_line_code = (
        data.parent_line_code.strip()
        if data.parent_line_code and data.parent_line_code.strip()
        else None
    )
    if not report_line_code or not report_line_name:
        raise HTTPException(status_code=400, detail="报表行次编码和名称不能为空")

    duplicate = await db.execute(
        select(ReportLineMapping.id).where(
            ReportLineMapping.project_id == project_id,
            ReportLineMapping.standard_account_code == record.standard_account_code,
            ReportLineMapping.report_type == data.report_type,
            ReportLineMapping.id != mapping_id,
            ReportLineMapping.is_deleted == False,  # noqa: E712
        ).limit(1)
    )
    if duplicate.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="该标准科目在当前报表类型下已存在其他映射")

    record.report_type = data.report_type
    record.report_line_code = report_line_code
    record.report_line_name = report_line_name
    record.report_line_level = data.report_line_level
    record.parent_line_code = parent_line_code
    record.mapping_type = ReportLineMappingType.manual
    record.is_confirmed = data.is_confirmed

    await db.flush()
    await db.commit()
    await db.refresh(record)
    return ReportLineMappingResponse.model_validate(record)


# ---------------------------------------------------------------------------
# delete_mapping
# ---------------------------------------------------------------------------


async def delete_mapping(
    project_id: UUID,
    mapping_id: UUID,
    db: AsyncSession,
) -> None:
    result = await db.execute(
        select(ReportLineMapping).where(
            ReportLineMapping.id == mapping_id,
            ReportLineMapping.project_id == project_id,
            ReportLineMapping.is_deleted == False,  # noqa: E712
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="映射记录不存在")

    record.is_deleted = True
    await db.flush()
    await db.commit()


# ---------------------------------------------------------------------------
# get_report_lines (供调整分录下拉)
# ---------------------------------------------------------------------------


async def get_report_lines(
    project_id: UUID,
    db: AsyncSession,
    report_type: str | None = None,
) -> list[ReportLine]:
    """获取已确认的报表行次列表（供调整分录下拉选择）。"""
    stmt = select(ReportLineMapping).where(
        ReportLineMapping.project_id == project_id,
        ReportLineMapping.is_confirmed == True,  # noqa: E712
        ReportLineMapping.is_deleted == False,  # noqa: E712
    )
    if report_type:
        stmt = stmt.where(ReportLineMapping.report_type == report_type)
    stmt = stmt.order_by(ReportLineMapping.report_line_code)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    # 去重（同一 report_line_code 可能对应多个标准科目）
    seen: set[str] = set()
    lines: list[ReportLine] = []
    for r in rows:
        if r.report_line_code in seen:
            continue
        seen.add(r.report_line_code)
        lines.append(ReportLine(
            report_line_code=r.report_line_code,
            report_line_name=r.report_line_name,
            report_line_level=r.report_line_level,
            report_type=r.report_type.value,
        ))

    return lines
