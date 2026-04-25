"""报表行次映射服务 — AI建议 + 确认 + 集团参照 + 跨年继承

Validates: Requirements 3.9, 3.10, 3.11, 3.12, 3.13, 3.14
"""

import logging
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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 标准科目编码 → 报表行次 规则映射（占位，后续接入LLM）
# ---------------------------------------------------------------------------

# 资产负债表行次
_BALANCE_SHEET_LINES: dict[str, tuple[str, str, int, str | None]] = {
    # code_prefix: (line_code, line_name, level, parent_line_code)
    "1001": ("BS001", "货币资金", 1, None),
    "1002": ("BS001", "货币资金", 1, None),
    "1012": ("BS001", "货币资金", 1, None),
    "1101": ("BS002", "交易性金融资产", 1, None),
    "1121": ("BS003", "应收票据", 1, None),
    "1122": ("BS004", "应收账款", 1, None),
    "1123": ("BS005", "预付款项", 1, None),
    "1131": ("BS006", "应收利息", 1, None),
    "1132": ("BS007", "应收股利", 1, None),
    "1221": ("BS008", "其他应收款", 1, None),
    "1401": ("BS009", "存货", 1, None),
    "1403": ("BS009", "存货", 1, None),
    "1405": ("BS009", "存货", 1, None),
    "1406": ("BS009", "存货", 1, None),
    "1408": ("BS009", "存货", 1, None),
    "1411": ("BS009", "存货", 1, None),
    "1501": ("BS010", "持有待售资产", 1, None),
    "1601": ("BS011", "长期股权投资", 1, None),
    "1701": ("BS012", "固定资产", 1, None),
    "1702": ("BS012", "固定资产", 1, None),
    "1801": ("BS013", "无形资产", 1, None),
    "1901": ("BS014", "长期待摊费用", 1, None),
    "2001": ("BS101", "短期借款", 1, None),
    "2201": ("BS102", "应付票据", 1, None),
    "2202": ("BS103", "应付账款", 1, None),
    "2203": ("BS104", "预收款项", 1, None),
    "2211": ("BS105", "应付职工薪酬", 1, None),
    "2221": ("BS106", "应交税费", 1, None),
    "2241": ("BS107", "其他应付款", 1, None),
    "2501": ("BS108", "长期借款", 1, None),
    "2502": ("BS109", "应付债券", 1, None),
    "2711": ("BS110", "长期应付款", 1, None),
    "3001": ("BS201", "实收资本", 1, None),
    "3002": ("BS202", "资本公积", 1, None),
    "3101": ("BS203", "盈余公积", 1, None),
    "3103": ("BS203", "盈余公积", 1, None),
    "3104": ("BS204", "未分配利润", 1, None),
}

# 利润表行次
_INCOME_STATEMENT_LINES: dict[str, tuple[str, str, int, str | None]] = {
    "5001": ("IS001", "营业收入", 1, None),
    "5051": ("IS001", "营业收入", 1, None),
    "5401": ("IS002", "营业成本", 1, None),
    "5402": ("IS002", "营业成本", 1, None),
    "5403": ("IS003", "税金及附加", 1, None),
    "5601": ("IS004", "销售费用", 1, None),
    "5602": ("IS005", "管理费用", 1, None),
    "5603": ("IS006", "研发费用", 1, None),
    "5711": ("IS007", "财务费用", 1, None),
    "5801": ("IS008", "资产减值损失", 1, None),
    "5802": ("IS009", "信用减值损失", 1, None),
    "6001": ("IS010", "资产处置收益", 1, None),
    "6051": ("IS011", "其他收益", 1, None),
    "6101": ("IS012", "投资收益", 1, None),
    "6111": ("IS013", "公允价值变动收益", 1, None),
    "6301": ("IS014", "营业外收入", 1, None),
    "6401": ("IS015", "营业外支出", 1, None),
    "6801": ("IS016", "所得税费用", 1, None),
}


def _determine_report_type_from_code(account_code: str) -> ReportType | None:
    """根据科目编码前缀判断报表类型。

    企业会计准则科目编码规则：
    - 1xxx: 资产类 → 资产负债表
    - 2xxx: 负债类 → 资产负债表
    - 3xxx: 共同类 → 资产负债表
    - 4xxx: 所有者权益类 → 资产负债表（权益侧）
    - 5xxx: 成本类 → 利润表
    - 6xxx: 损益类 → 利润表
    """
    prefix = account_code[:1] if account_code else ""
    if prefix in ("1", "2", "3", "4"):
        return ReportType.balance_sheet
    if prefix in ("5", "6"):
        return ReportType.income_statement
    return None


def _lookup_report_line(
    account_code: str, report_type: ReportType
) -> tuple[str, str, int, str | None, float] | None:
    """查找科目编码对应的报表行次。返回 (line_code, line_name, level, parent, confidence)。"""
    mapping_dict = (
        _BALANCE_SHEET_LINES
        if report_type == ReportType.balance_sheet
        else _INCOME_STATEMENT_LINES
    )

    # 精确匹配（4位编码）
    prefix4 = account_code[:4] if len(account_code) >= 4 else account_code
    if prefix4 in mapping_dict:
        lc, ln, lv, pc = mapping_dict[prefix4]
        return lc, ln, lv, pc, 1.0

    # 前缀匹配（逐步缩短）
    for length in (3, 2, 1):
        prefix = account_code[:length]
        for code, (lc, ln, lv, pc) in mapping_dict.items():
            if code.startswith(prefix):
                return lc, ln, lv, pc, 0.8

    return None


# ---------------------------------------------------------------------------
# ai_suggest_mappings (Task 7a.2)
# ---------------------------------------------------------------------------


async def ai_suggest_mappings(
    project_id: UUID,
    db: AsyncSession,
) -> list[dict]:
    """规则匹配占位（后续接入LLM）：根据标准科目编码前缀生成报表行次映射建议。

    Validates: Requirements 3.10
    """
    # 获取项目已映射的标准科目（通过 account_mapping）
    mapped_result = await db.execute(
        select(AccountMapping.standard_account_code).where(
            AccountMapping.project_id == project_id,
            AccountMapping.is_deleted == False,  # noqa: E712
        ).distinct()
    )
    mapped_std_codes = [row[0] for row in mapped_result.all()]

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

    suggestions: list[dict] = []
    seen_keys: set[str] = set()

    for std_code in mapped_std_codes:
        rt = _determine_report_type_from_code(std_code)
        if rt is None:
            continue

        result = _lookup_report_line(std_code, rt)
        if result is None:
            continue

        line_code, line_name, level, parent_code, confidence = result
        key = f"{std_code}:{rt.value}"
        if key in seen_keys:
            continue
        seen_keys.add(key)

        # 检查是否已存在映射
        existing = await db.execute(
            select(ReportLineMapping).where(
                ReportLineMapping.project_id == project_id,
                ReportLineMapping.standard_account_code == std_code,
                ReportLineMapping.report_type == rt,
                ReportLineMapping.is_deleted == False,  # noqa: E712
            )
        )
        if existing.scalar_one_or_none():
            continue

        # 创建映射建议
        mapping = ReportLineMapping(
            project_id=project_id,
            standard_account_code=std_code,
            report_type=rt,
            report_line_code=line_code,
            report_line_name=line_name,
            report_line_level=level,
            parent_line_code=parent_code,
            mapping_type=ReportLineMappingType.ai_suggested,
            is_confirmed=False,
        )
        db.add(mapping)
        suggestions.append({
            "standard_account_code": std_code,
            "report_type": rt.value,
            "report_line_code": line_code,
            "report_line_name": line_name,
            "report_line_level": level,
            "parent_line_code": parent_code,
            "confidence": confidence,
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
