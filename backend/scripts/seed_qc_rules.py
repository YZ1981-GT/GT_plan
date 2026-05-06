"""Seed QC 规则定义到 qc_rule_definitions 表

将 QC-01~14（qc_engine.py）+ QC-19~26（gate_rules_phase14.py）迁移为
expression_type='python' 的元数据记录。

幂等：按 rule_code 检查，已存在则跳过。
启动 lifespan 调用一次确保规则存在。

Refinement Round 3 — 需求 1, 10
"""

import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qc_rule_models import QcRuleDefinition

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 规则定义数据
# ---------------------------------------------------------------------------

SEED_RULES: list[dict] = [
    # ── QC-01 ~ QC-14: qc_engine.py ──────────────────────────────────────
    {
        "rule_code": "QC-01",
        "severity": "blocking",
        "scope": "workpaper",
        "category": "内容完整性",
        "title": "结论区已填写",
        "description": "检查底稿 parsed_data 中结论区是否为空",
        "standard_ref": [{"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.ConclusionNotEmptyRule",
    },
    {
        "rule_code": "QC-02",
        "severity": "blocking",
        "scope": "workpaper",
        "category": "AI 内容",
        "title": "AI 填充内容全部已确认",
        "description": "检查 parsed_data.ai_content 中是否存在 status=pending 的未确认项",
        "standard_ref": [{"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.AIFillConfirmedRule",
    },
    {
        "rule_code": "QC-03",
        "severity": "blocking",
        "scope": "workpaper",
        "category": "数据一致性",
        "title": "公式一致性（审定数=未审数+AJE+RJE）",
        "description": "检查审定数是否等于未审数加调整分录合计，误差阈值 0.01 元",
        "standard_ref": [{"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.FormulaConsistencyRule",
    },
    {
        "rule_code": "QC-04",
        "severity": "blocking",
        "scope": "workpaper",
        "category": "流程合规",
        "title": "复核人已分配",
        "description": "检查底稿是否已分配复核人",
        "standard_ref": [{"code": "1121", "name": "质量管理"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.ReviewerAssignedRule",
    },
    {
        "rule_code": "QC-05",
        "severity": "blocking",
        "scope": "workpaper",
        "category": "流程合规",
        "title": "无未解决的复核意见",
        "description": "检查底稿是否存在未解决的复核批注",
        "standard_ref": [{"code": "1121", "name": "质量管理"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.UnresolvedAnnotationsRule",
    },
    {
        "rule_code": "QC-06",
        "severity": "warning",
        "scope": "workpaper",
        "category": "内容完整性",
        "title": "人工填写区完整",
        "description": "检查 parsed_data 中审定数、未审数等关键字段是否已填写",
        "standard_ref": [{"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.ManualInputCompleteRule",
    },
    {
        "rule_code": "QC-07",
        "severity": "warning",
        "scope": "workpaper",
        "category": "数据一致性",
        "title": "小计准确性（宽松版）",
        "description": "审定数与计算值差异超过 1 元时警告（与 QC-03 互补）",
        "standard_ref": [{"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.SubtotalAccuracyRule",
    },
    {
        "rule_code": "QC-08",
        "severity": "warning",
        "scope": "workpaper",
        "category": "交叉引用",
        "title": "交叉索引一致性",
        "description": "检查 parsed_data.cross_refs 中引用的底稿编码是否在项目索引中存在",
        "standard_ref": [{"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.CrossRefConsistencyRule",
    },
    {
        "rule_code": "QC-09",
        "severity": "warning",
        "scope": "workpaper",
        "category": "索引登记",
        "title": "底稿已在索引表中登记",
        "description": "检查底稿对应的 wp_index 记录是否存在",
        "standard_ref": [{"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.IndexRegistrationRule",
    },
    {
        "rule_code": "QC-10",
        "severity": "warning",
        "scope": "workpaper",
        "category": "交叉引用",
        "title": "引用底稿存在且已完成",
        "description": "检查交叉引用的目标底稿是否存在",
        "standard_ref": [{"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.CrossRefExistsRule",
    },
    {
        "rule_code": "QC-11",
        "severity": "warning",
        "scope": "workpaper",
        "category": "审计程序",
        "title": "关联审计程序已执行完成",
        "description": "检查底稿关联的审计程序执行状态是否为 completed",
        "standard_ref": [{"code": "1211", "name": "审计程序"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.AuditProcedureStatusRule",
    },
    {
        "rule_code": "QC-12",
        "severity": "warning",
        "scope": "workpaper",
        "category": "抽样",
        "title": "抽样记录完整",
        "description": "有抽样配置则必须有对应的抽样记录",
        "standard_ref": [{"code": "1314", "name": "审计抽样"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.SamplingCompletenessRule",
    },
    {
        "rule_code": "QC-13",
        "severity": "warning",
        "scope": "workpaper",
        "category": "调整分录",
        "title": "调整事项已录入",
        "description": "检查底稿中发现的待录入调整事项是否已处理",
        "standard_ref": [{"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.AdjustmentRecordedRule",
    },
    {
        "rule_code": "QC-14",
        "severity": "info",
        "scope": "workpaper",
        "category": "编制日期",
        "title": "编制日期合理性",
        "description": "底稿创建超过 90 天仍为草稿状态时提示",
        "standard_ref": [{"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.PreparationDateRule",
    },
    # ── QC-19 ~ QC-26: gate_rules_phase14.py ─────────────────────────────
    {
        "rule_code": "QC-19",
        "severity": "blocking",
        "scope": "workpaper",
        "category": "审计程序",
        "title": "mandatory 程序裁剪阻断",
        "description": "不允许裁剪 mandatory 类别的审计程序",
        "standard_ref": [{"code": "1211", "name": "审计程序"}, {"code": "1101", "name": "注册会计师的总体目标和审计工作的基本要求"}],
        "expression_type": "python",
        "expression": "app.services.gate_rules_phase14.QC19MandatoryTrimRule",
    },
    {
        "rule_code": "QC-20",
        "severity": "blocking",
        "scope": "workpaper",
        "category": "审计程序",
        "title": "conditional 裁剪无证据阻断",
        "description": "conditional 类别程序裁剪时必须提供证据引用",
        "standard_ref": [{"code": "1211", "name": "审计程序"}, {"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.gate_rules_phase14.QC20ConditionalNoEvidenceRule",
    },
    {
        "rule_code": "QC-21",
        "severity": "blocking",
        "scope": "workpaper",
        "category": "证据充分性",
        "title": "关键结论缺少证据锚点",
        "description": "关键结论必须绑定 evidence_id 证据引用",
        "standard_ref": [{"code": "1301", "name": "审计工作底稿"}, {"code": "1131", "name": "审计证据"}],
        "expression_type": "python",
        "expression": "app.services.gate_rules_phase14.QC21ConclusionWithoutEvidenceRule",
    },
    {
        "rule_code": "QC-22",
        "severity": "blocking",
        "scope": "workpaper",
        "category": "证据充分性",
        "title": "低置信单点依赖",
        "description": "关键结论仅依赖单一低置信度（OCR<0.7）证据时阻断",
        "standard_ref": [{"code": "1131", "name": "审计证据"}, {"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.gate_rules_phase14.QC22LowConfidenceSingleSourceRule",
    },
    {
        "rule_code": "QC-23",
        "severity": "blocking",
        "scope": "workpaper",
        "category": "AI 内容",
        "title": "LLM 关键内容未确认",
        "description": "存在未确认的 LLM 生成关键内容时阻断提交",
        "standard_ref": [{"code": "1301", "name": "审计工作底稿"}, {"code": "1121", "name": "质量管理"}],
        "expression_type": "python",
        "expression": "app.services.gate_rules_phase14.QC23LLMPendingConfirmationRule",
    },
    {
        "rule_code": "QC-24",
        "severity": "blocking",
        "scope": "workpaper",
        "category": "AI 内容",
        "title": "LLM 采纳与裁剪冲突",
        "description": "已确认的 AI 内容与被裁剪的程序存在冲突时阻断",
        "standard_ref": [{"code": "1211", "name": "审计程序"}, {"code": "1121", "name": "质量管理"}],
        "expression_type": "python",
        "expression": "app.services.gate_rules_phase14.QC24LLMTrimConflictRule",
    },
    {
        "rule_code": "QC-25",
        "severity": "blocking",
        "scope": "project",
        "category": "报告一致性",
        "title": "正文引用附注版本过期",
        "description": "审计报告正文引用的附注版本已过期时阻断签字",
        "standard_ref": [{"code": "1501", "name": "对财务报表形成审计意见和出具审计报告"}, {"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.gate_rules_phase14.QC25ReportNoteVersionStaleRule",
    },
    {
        "rule_code": "QC-26",
        "severity": "blocking",
        "scope": "project",
        "category": "报告一致性",
        "title": "附注关键披露缺来源映射",
        "description": "附注关键披露缺少 source_cells 来源映射时阻断",
        "standard_ref": [{"code": "1501", "name": "对财务报表形成审计意见和出具审计报告"}, {"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.gate_rules_phase14.QC26NoteSourceMappingMissingRule",
    },
    # ── AL-01 ~ AL-05: 审计日志审查规则（需求 12）────────────────────────
    {
        "rule_code": "AL-01",
        "severity": "warning",
        "scope": "audit_log",
        "category": "日志合规",
        "title": "非工作时间批量修改底稿",
        "description": "检测 22:00-06:00 时段内批量修改底稿超过 10 次/小时的异常行为",
        "standard_ref": [{"code": "1121", "name": "质量管理"}, {"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "jsonpath",
        "expression": "$.action_type",
        "parameters_schema": {
            "expect_match": False,
            "message": "非工作时间（22:00-06:00）批量修改底稿超过阈值",
            "threshold_per_hour": 10,
            "off_hours": [22, 23, 0, 1, 2, 3, 4, 5],
            "target_action_type": "workpaper_modified",
        },
        "enabled": True,
    },
    {
        "rule_code": "AL-02",
        "severity": "blocking",
        "scope": "audit_log",
        "category": "日志合规",
        "title": "同 IP 多账号登录",
        "description": "同一 IP 24 小时内以 admin + auditor 多种角色登录，疑似越权",
        "standard_ref": [{"code": "1121", "name": "质量管理"}],
        "expression_type": "python",
        "expression": "app.services.audit_log_rules.MultiAccountSameIPRule",
        "parameters_schema": {
            "message": "同一 IP 多账号登录（admin+auditor），潜在越权",
            "time_window_hours": 24,
        },
        "enabled": False,  # Python 类型 deferred to R6+
    },
    {
        "rule_code": "AL-03",
        "severity": "info",
        "scope": "audit_log",
        "category": "日志合规",
        "title": "保留期/轮换覆盖操作",
        "description": "检测 retention_override 或 rotation_override 动作触发",
        "standard_ref": [{"code": "1121", "name": "质量管理"}, {"code": "1151", "name": "独立性"}],
        "expression_type": "jsonpath",
        "expression": "$.action_type",
        "parameters_schema": {
            "expect_match": False,
            "message": "检测到保留期/轮换覆盖操作",
            "target_action_types": ["retention_override", "rotation_override"],
        },
        "enabled": True,
    },
    {
        "rule_code": "AL-04",
        "severity": "warning",
        "scope": "audit_log",
        "category": "日志合规",
        "title": "gate_override 频率过高",
        "description": "同一角色近 30 天 gate_override 次数超过 5 次",
        "standard_ref": [{"code": "1121", "name": "质量管理"}],
        "expression_type": "python",
        "expression": "app.services.audit_log_rules.GateOverrideFrequencyRule",
        "parameters_schema": {
            "message": "gate_override 次数/月超过阈值",
            "threshold_per_month": 5,
        },
        "enabled": False,  # Python 类型 deferred to R6+
    },
    {
        "rule_code": "AL-05",
        "severity": "blocking",
        "scope": "audit_log",
        "category": "日志合规",
        "title": "哈希链断裂",
        "description": "审计日志哈希链断裂，可能存在篡改",
        "standard_ref": [{"code": "1121", "name": "质量管理"}, {"code": "1301", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.audit_log_rules.HashChainBreakRule",
        "parameters_schema": {
            "message": "审计日志哈希链断裂，必须 48 小时内人工答复",
            "notify_roles": ["chief_partner", "chief_risk_partner"],
        },
        "enabled": False,  # Python 类型 deferred to R6+
    },
]


# ---------------------------------------------------------------------------
# 幂等 seed 函数
# ---------------------------------------------------------------------------


async def seed_qc_rules(db: AsyncSession) -> int:
    """将预定义的 QC 规则写入 qc_rule_definitions 表。

    幂等：按 rule_code 检查，已存在则跳过。
    返回新插入的规则数量。
    """
    inserted = 0

    for rule_data in SEED_RULES:
        rule_code = rule_data["rule_code"]

        # 检查是否已存在
        existing = await db.execute(
            select(QcRuleDefinition).where(
                QcRuleDefinition.rule_code == rule_code,
                QcRuleDefinition.is_deleted == False,  # noqa: E712
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        # 插入新规则
        rule = QcRuleDefinition(
            id=uuid4(),
            rule_code=rule_code,
            severity=rule_data["severity"],
            scope=rule_data["scope"],
            category=rule_data.get("category"),
            title=rule_data["title"],
            description=rule_data["description"],
            standard_ref=rule_data.get("standard_ref"),
            expression_type=rule_data["expression_type"],
            expression=rule_data["expression"],
            parameters_schema=rule_data.get("parameters_schema"),
            enabled=rule_data.get("enabled", True),
            version=1,
            created_by=None,  # system seed
        )
        db.add(rule)
        inserted += 1

    if inserted > 0:
        await db.flush()

    logger.info(
        "[seed_qc_rules] Seeded %d new rules (total defined: %d)",
        inserted,
        len(SEED_RULES),
    )
    return inserted
