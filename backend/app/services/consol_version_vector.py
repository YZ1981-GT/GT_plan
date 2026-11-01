"""合并运行输入版本向量与确定性摘要。"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.consol_context import ConsolContext
from app.schemas.consol_operation import ConsolVersionVector
from app.services.consol_tree_service import TreeNode


def _json_default(value: Any) -> Any:
    if isinstance(value, (UUID, date, datetime, Decimal, Enum)):
        return value.value if isinstance(value, Enum) else str(value)
    raise TypeError(f"不能序列化合并版本值：{type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default,
    )


def digest_payload(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def digest(value: Any) -> str:
    """兼容旧调用名；新代码用 ``digest_payload``。"""
    return digest_payload(value)


def request_hash(operation_type: str, trigger: str, payload: dict[str, Any]) -> str:
    return digest({"operation_type": operation_type, "trigger": trigger, "payload": payload})


def _rows_digest(rows: Iterable[Any]) -> str:
    return digest(list(rows))


async def build_version_vector(
    db: AsyncSession,
    project_id: UUID | None = None,
    year: int | None = None,
    *,
    context: ConsolContext | None = None,
    tree: TreeNode,
    tree_fingerprint: str | None = None,
    template_type: str | None = None,
) -> ConsolVersionVector:
    """批量读取影响合并结果的输入，并返回可比较的规范版本向量。"""
    if context is None:
        if project_id is None or year is None:
            raise ValueError("构建合并版本向量必须给 project_id/year 或 context")
        context = ConsolContext(
            project_id=project_id,
            year=year,
            tree_fingerprint=tree_fingerprint,
            template_type=template_type,
        )
    from app.models.audit_platform_models import TrialBalance
    from app.models.consol_note_mapping_models import (
        ConsolNoteMappingBinding,
        ConsolNoteMappingRule,
        ConsolNoteTemplateBinding,
    )
    from app.models.consol_push_models import ConsolNoteFormula
    from app.models.consol_scope_confirmation_models import ConsolScopeConfirmation
    from app.models.consol_worksheet_data_models import ConsolWorksheetData
    from app.models.consolidation_models import EliminationEntry, ReviewStatusEnum
    from app.models.report_models import ReportConfig
    from app.services.consol_calc_basis import data_leaves, index_tree

    scope = (await db.execute(
        sa.select(
            ConsolScopeConfirmation.revision,
            ConsolScopeConfirmation.fingerprint,
        ).where(
            ConsolScopeConfirmation.project_id == context.project_id,
            ConsolScopeConfirmation.year == context.year,
            ConsolScopeConfirmation.status == "active",
        ).order_by(ConsolScopeConfirmation.revision.desc())
    )).first()

    worksheets = (await db.execute(
        sa.select(ConsolWorksheetData.sheet_key, ConsolWorksheetData.version).where(
            ConsolWorksheetData.project_id == context.project_id,
            ConsolWorksheetData.year == context.year,
        ).order_by(ConsolWorksheetData.sheet_key)
    )).all()

    leaf_ids = sorted(
        {node.project_id for node in data_leaves(tree) if node.project_id is not None}, key=str,
    )
    tb_rows = (await db.execute(
        sa.select(
            TrialBalance.project_id,
            TrialBalance.standard_account_code,
            TrialBalance.company_code,
            TrialBalance.audited_amount,
            TrialBalance.updated_at,
        ).where(
            TrialBalance.project_id.in_(leaf_ids) if leaf_ids else sa.false(),
            TrialBalance.year == context.year,
            TrialBalance.is_deleted == sa.false(),
        ).order_by(TrialBalance.project_id, TrialBalance.standard_account_code, TrialBalance.id)
    )).all()

    consol_ids = sorted(index_tree(tree).consol_by_project, key=str)
    entries = (await db.execute(
        sa.select(
            EliminationEntry.id,
            EliminationEntry.project_id,
            EliminationEntry.entry_group_id,
            EliminationEntry.entry_type,
            EliminationEntry.branch_entity_code,
            EliminationEntry.lines,
            EliminationEntry.debit_amount,
            EliminationEntry.credit_amount,
            EliminationEntry.updated_at,
        ).where(
            EliminationEntry.project_id.in_(consol_ids) if consol_ids else sa.false(),
            EliminationEntry.year == context.year,
            EliminationEntry.review_status == ReviewStatusEnum.approved,
            EliminationEntry.is_deleted == sa.false(),
        ).order_by(EliminationEntry.project_id, EliminationEntry.entry_no, EliminationEntry.id)
    )).all()

    standard = f"{context.template_type or 'soe'}_consolidated"
    report_formulas = (await db.execute(
        sa.select(
            ReportConfig.report_type,
            ReportConfig.row_code,
            ReportConfig.formula,
            ReportConfig.formula_version,
            ReportConfig.updated_at,
        ).where(
            ReportConfig.applicable_standard == standard,
            ReportConfig.is_deleted == sa.false(),
        ).order_by(ReportConfig.report_type, ReportConfig.row_code)
    )).all()
    note_formulas = (await db.execute(
        sa.select(
            ConsolNoteFormula.section_id,
            ConsolNoteFormula.row_index,
            ConsolNoteFormula.col_index,
            ConsolNoteFormula.formula,
            ConsolNoteFormula.version,
            ConsolNoteFormula.updated_at,
        ).where(
            ConsolNoteFormula.template_type == (context.template_type or "soe"),
            ConsolNoteFormula.is_deleted == sa.false(),
        ).order_by(
            ConsolNoteFormula.section_id,
            ConsolNoteFormula.row_index,
            ConsolNoteFormula.col_index,
        )
    )).all()

    template_bindings = (await db.execute(
        sa.select(
            ConsolNoteTemplateBinding.section_id,
            ConsolNoteTemplateBinding.template_version_id,
        ).where(ConsolNoteTemplateBinding.project_id == context.project_id)
        .order_by(ConsolNoteTemplateBinding.section_id)
    )).all()
    mapping_rules = (await db.execute(
        sa.select(
            ConsolNoteMappingRule.id,
            ConsolNoteMappingRule.section_id,
            ConsolNoteMappingRule.template_version_id,
            ConsolNoteMappingRule.source_structure_hash,
            ConsolNoteMappingRule.version_number,
            ConsolNoteMappingRule.mappings,
        ).where(
            ConsolNoteMappingRule.project_id == context.project_id,
            ConsolNoteMappingRule.is_active == sa.true(),
        ).order_by(ConsolNoteMappingRule.section_id, ConsolNoteMappingRule.id)
    )).all()
    mapping_bindings = (await db.execute(
        sa.select(
            ConsolNoteMappingBinding.section_id,
            ConsolNoteMappingBinding.entity_node_key,
            ConsolNoteMappingBinding.rule_id,
            ConsolNoteMappingBinding.bound_source_hash,
            ConsolNoteMappingBinding.status,
        ).where(ConsolNoteMappingBinding.project_id == context.project_id)
        .order_by(ConsolNoteMappingBinding.section_id, ConsolNoteMappingBinding.entity_node_key)
    )).all()

    actual_tree_fingerprint = context.tree_fingerprint or tree_fingerprint
    if not actual_tree_fingerprint:
        from app.services.consol_context_service import tree_fingerprint as compute_tree_fingerprint
        actual_tree_fingerprint = compute_tree_fingerprint(tree)
    if not actual_tree_fingerprint:
        raise ValueError("企业树指纹为空")
    vector: dict[str, Any] = {
        "schema_version": 1,
        "tree_revision": int(scope.revision) if scope else None,
        "tree_fingerprint": actual_tree_fingerprint,
        "recorded_tree_fingerprint": scope.fingerprint if scope else None,
        "worksheet_versions": {key: int(version or 0) for key, version in worksheets},
        "tb_digest": _rows_digest(tuple(row) for row in tb_rows),
        "elimination_digest": _rows_digest(tuple(row) for row in entries),
        "formula_digest": digest({
            "report": [tuple(row) for row in report_formulas],
            "note": [tuple(row) for row in note_formulas],
        }),
        "note_mapping_digest": digest({
            "templates": [tuple(row) for row in template_bindings],
            "rules": [tuple(row) for row in mapping_rules],
            "bindings": [tuple(row) for row in mapping_bindings],
        }),
        "template_digest": digest({
            "template_type": context.template_type,
            "report_scope": context.report_scope,
            "period_end": context.period_end,
            "report_standard": standard,
        }),
    }
    vector["digest"] = vector_digest(vector)
    return ConsolVersionVector.model_validate(vector)


def _as_dict(value: ConsolVersionVector | dict[str, Any]) -> dict[str, Any]:
    return value.model_dump(mode="json") if isinstance(value, ConsolVersionVector) else dict(value)


def vector_digest(value: ConsolVersionVector | dict[str, Any]) -> str:
    raw = _as_dict(value)
    return digest_payload({
        key: item for key, item in raw.items()
        if key not in {"digest", "tree_revision", "recorded_tree_fingerprint"}
    })


def vectors_equal(
    before: ConsolVersionVector | dict[str, Any],
    after: ConsolVersionVector | dict[str, Any],
) -> bool:
    return vector_digest(before) == vector_digest(after)


def changed_version_keys(
    before: ConsolVersionVector | dict[str, Any],
    after: ConsolVersionVector | dict[str, Any],
) -> list[str]:
    """返回除总摘要和只读记录版本外发生变化的向量键。"""
    left, right = _as_dict(before), _as_dict(after)
    ignored = {"digest", "tree_revision", "recorded_tree_fingerprint"}
    return sorted(
        key for key in (set(left) | set(right)) - ignored
        if left.get(key) != right.get(key)
    )
