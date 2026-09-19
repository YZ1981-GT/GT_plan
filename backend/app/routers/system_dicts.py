"""系统字典 API — 枚举字典集中管理 [R4.1]

GET /api/system/dicts — 返回所有枚举字典
  响应格式: { [dictKey]: Array<{ value: str, label: str, color: str }> }
  color 对应 Element Plus el-tag type（success/warning/danger/info/空字符串）

GET /api/system/dicts/{dict_key}/usage-count — 返回各枚举值的引用计数
  [template-library-coordination Sprint 6 Task 6.2 / 需求 21.4]

POST/PUT /api/system/dicts/{dict_key}/items — 拒绝写操作（D13 ADR：枚举字典硬编码在代码中）
  [template-library-coordination Sprint 6 Task 6.3 / 需求 21.3, 21.5]

前端启动时加载一次，sessionStorage 缓存，配合 useDictStore 使用。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system-dicts"])


# ── 字典定义（与前端 `constants/statusEnum.ts`（dictStore 加载失败时的 fallback）保持一致；API `/api/system/dicts` 为运行时主源） ──

_DICTS: dict[str, list[dict[str, str]]] = {
    # 底稿状态
    "wp_status": [
        {"value": "not_started",          "label": "未开始",       "color": "info"},
        {"value": "in_progress",          "label": "编制中",       "color": "warning"},
        {"value": "draft",                "label": "草稿",         "color": "warning"},
        {"value": "draft_complete",       "label": "初稿完成",     "color": ""},
        {"value": "edit_complete",        "label": "编制完成",     "color": ""},
        {"value": "under_review",         "label": "复核中",       "color": ""},
        {"value": "revision_required",    "label": "退回修改",     "color": "danger"},
        {"value": "review_passed",        "label": "复核通过",     "color": "success"},
        {"value": "review_level1_passed", "label": "一级复核通过", "color": "success"},
        {"value": "review_level2_passed", "label": "二级复核通过", "color": "success"},
        {"value": "archived",             "label": "已归档",       "color": "info"},
    ],
    # 底稿复核状态
    "wp_review_status": [
        {"value": "not_submitted",      "label": "未提交",     "color": "info"},
        {"value": "pending_level1",     "label": "待一级复核", "color": "warning"},
        {"value": "level1_in_progress", "label": "一级复核中", "color": "warning"},
        {"value": "level1_passed",      "label": "一级通过",   "color": "success"},
        {"value": "level1_rejected",    "label": "一级退回",   "color": "danger"},
        {"value": "pending_level2",     "label": "待二级复核", "color": "warning"},
        {"value": "level2_in_progress", "label": "二级复核中", "color": "warning"},
        {"value": "level2_passed",      "label": "二级通过",   "color": "success"},
        {"value": "level2_rejected",    "label": "二级退回",   "color": "danger"},
    ],
    # 调整分录状态
    "adjustment_status": [
        {"value": "draft",          "label": "草稿",   "color": "info"},
        {"value": "pending_review", "label": "待复核", "color": "warning"},
        {"value": "approved",       "label": "已批准", "color": "success"},
        {"value": "rejected",       "label": "已驳回", "color": "danger"},
    ],
    # 报告状态
    "report_status": [
        {"value": "draft",          "label": "草稿",       "color": "info"},
        {"value": "review",         "label": "复核中",     "color": "warning"},
        {"value": "eqcr_approved",  "label": "EQCR已锁",  "color": ""},
        {"value": "final",          "label": "已定稿",     "color": "success"},
    ],
    # 模板状态
    "template_status": [
        {"value": "draft",      "label": "草稿",   "color": "info"},
        {"value": "published",  "label": "已发布", "color": "success"},
        {"value": "deprecated", "label": "已废弃", "color": "danger"},
    ],
    # 项目状态
    "project_status": [
        {"value": "created",    "label": "已创建", "color": "info"},
        {"value": "planning",   "label": "计划中", "color": "warning"},
        {"value": "execution",  "label": "执行中", "color": ""},
        {"value": "completion", "label": "已完成", "color": "success"},
        {"value": "reporting",  "label": "报告",   "color": ""},
        {"value": "archived",   "label": "已归档", "color": "info"},
    ],
    # 问题工单状态
    "issue_status": [
        {"value": "open",            "label": "待处理", "color": "info"},
        {"value": "in_fix",          "label": "修复中", "color": "warning"},
        {"value": "pending_recheck", "label": "待复验", "color": "warning"},
        {"value": "closed",          "label": "已关闭", "color": "success"},
        {"value": "rejected",        "label": "已驳回", "color": "danger"},
    ],
    # PDF 导出任务状态
    "pdf_task_status": [
        {"value": "queued",     "label": "排队中", "color": "info"},
        {"value": "processing", "label": "处理中", "color": "warning"},
        {"value": "completed",  "label": "已完成", "color": "success"},
        {"value": "failed",     "label": "失败",   "color": "danger"},
    ],
    # 工时状态 [R7-S2-06]
    "workhour_status": [
        {"value": "draft",     "label": "草稿",   "color": "info"},
        {"value": "tracking",  "label": "计时中", "color": "warning"},
        {"value": "confirmed", "label": "已确认", "color": ""},
        {"value": "approved",  "label": "已审批", "color": "success"},
        {"value": "rejected",  "label": "已退回", "color": "danger"},
    ],
    # ── 以下为 P2-6 扩展的核心业务枚举（value 硬编码锁死，仅 label/color 可治理） ──
    # 抵销分录类型（EliminationEntryType，合并模块）
    "elimination_entry_type": [
        {"value": "equity",            "label": "权益抵销",       "color": ""},
        {"value": "internal_trade",    "label": "内部交易抵销",   "color": "warning"},
        {"value": "internal_ar_ap",    "label": "内部往来抵销",   "color": "warning"},
        {"value": "unrealized_profit", "label": "未实现利润抵销", "color": "danger"},
        {"value": "other",             "label": "其他抵销",       "color": "info"},
    ],
    # 审计循环代号 A~N + S
    "audit_cycle": [
        {"value": "A", "label": "报表/调整",   "color": ""},
        {"value": "B", "label": "控制了解",     "color": ""},
        {"value": "C", "label": "控制测试",     "color": ""},
        {"value": "D", "label": "销售收入",     "color": "success"},
        {"value": "E", "label": "货币资金",     "color": "success"},
        {"value": "F", "label": "采购存货",     "color": "success"},
        {"value": "G", "label": "投资",         "color": "warning"},
        {"value": "H", "label": "固定资产",     "color": "warning"},
        {"value": "I", "label": "无形资产",     "color": "warning"},
        {"value": "J", "label": "职工薪酬",     "color": "info"},
        {"value": "K", "label": "管理",         "color": "info"},
        {"value": "L", "label": "筹资",         "color": "info"},
        {"value": "M", "label": "股东权益",     "color": ""},
        {"value": "N", "label": "税费",         "color": ""},
        {"value": "S", "label": "专项",         "color": "danger"},
    ],
    # 风险等级（RiskLevel）
    "risk_level": [
        {"value": "high",   "label": "高风险", "color": "danger"},
        {"value": "medium", "label": "中风险", "color": "warning"},
        {"value": "low",    "label": "低风险", "color": "success"},
    ],
    # ── P1-3.1: AI 内容确认状态 ──
    "ai_content_status": [
        {"value": "pending",   "label": "待确认", "color": "warning"},
        {"value": "confirmed", "label": "已确认", "color": "success"},
        {"value": "rejected",  "label": "已拒绝", "color": "danger"},
        {"value": "expired",   "label": "已过期", "color": "info"},
    ],
    # ── P1-3.1: 归档状态 ──
    "archive_status": [
        {"value": "not_archived",    "label": "未归档",   "color": "info"},
        {"value": "archiving",       "label": "归档中",   "color": "warning"},
        {"value": "archived",        "label": "已归档",   "color": "success"},
        {"value": "archive_failed",  "label": "归档失败", "color": "danger"},
    ],
    # ── 函证模块枚举（D0 系列底稿共用） ──
    "confirmation_account_type": [
        {"value": "accounts_receivable",    "label": "应收账款",     "color": ""},
        {"value": "contract_liability",     "label": "合同负债",     "color": ""},
        {"value": "other_receivable",       "label": "其他应收款",   "color": ""},
        {"value": "prepayment",             "label": "预付账款",     "color": ""},
        {"value": "accounts_payable",       "label": "应付账款",     "color": ""},
        {"value": "other_payable",          "label": "其他应付款",   "color": ""},
        {"value": "short_term_loan",        "label": "短期借款",     "color": ""},
        {"value": "long_term_loan",         "label": "长期借款",     "color": ""},
        {"value": "bank_deposit",           "label": "银行存款",     "color": ""},
        {"value": "time_deposit",           "label": "定期存款",     "color": ""},
        {"value": "financial_product",      "label": "理财产品",     "color": ""},
        {"value": "other_monetary",         "label": "其他货币资金", "color": ""},
        # ── H 循环（固定资产循环函证 H0）品种 ──
        # 🔴 标签逐字取 wp_system_map.json 的 business_cycles[固定资产循环].accounts，
        #    不得自拟简称（H0-1 下区矩阵按本列 SUMIF 分品种，品种名不在此枚举内则永远聚合不到行）。
        #    「资产处置损益」(H10) 是损益类不函证，故不在此列。
        #    spec: h0-confirmation-source-fidelity-and-linkage R1.1/R1.2/R1.6
        {"value": "fixed_assets",                "label": "固定资产",       "color": ""},
        {"value": "construction_in_progress",    "label": "在建工程",       "color": ""},
        {"value": "investment_property",         "label": "投资性房地产",   "color": ""},
        {"value": "engineering_materials",       "label": "工程物资",       "color": ""},
        {"value": "oil_gas_assets",              "label": "油气资产",       "color": ""},
        {"value": "fixed_assets_clearing",       "label": "固定资产清理",   "color": ""},
        {"value": "productive_biological_assets", "label": "生产性生物资产", "color": ""},
        {"value": "right_of_use_assets",         "label": "使用权资产",     "color": ""},
        {"value": "lease_liabilities",           "label": "租赁负债",       "color": ""},
        {"value": "other",                  "label": "其他",         "color": "info"},
    ],
    "confirmation_method": [
        # 🔴 这是准则 1312 的**程序层面**概念（X0A 程序 1「以积极方式…进行函证」），
        #    与源模板 X0-2!C7 的「函证方式」（发函渠道）是两个不同维度 —— 后者见
        #    confirmation_send_channel。两者都保留，不得互相替代。
        {"value": "positive",  "label": "积极式", "color": ""},
        {"value": "negative",  "label": "消极式", "color": "info"},
    ],
    # ── 发函渠道（源模板 X0-2!C7 数据验证，D0/F0/G0/H0/K0/L0 六枢纽取值完全同构） ──
    # X0-1 的「函证方式」列由 VLOOKUP 自 X0-2!C 列带入 → 两处必须绑定同一枚举。
    "confirmation_send_channel": [
        {"value": "mail",       "label": "邮寄",     "color": ""},
        {"value": "followup",   "label": "跟函",     "color": "success"},
        {"value": "electronic", "label": "电子函证", "color": "info"},
        {"value": "other",      "label": "其他",     "color": "info"},
    ],
    # ── 选取样本目的（源模板 X0-1!C8 数据验证，六枢纽同构） ──
    # 🔴 标签逐字保留源模板的空格与标点不一致（"A. 大额" 有空格 / "B.异常" 无空格）。
    "confirmation_sample_purpose": [
        {"value": "large_amount",         "label": "A. 大额",   "color": "warning"},
        {"value": "abnormal",             "label": "B.异常",    "color": "danger"},
        {"value": "zero_balance",         "label": "C.余额为0", "color": "info"},
        {"value": "long_aging",           "label": "D.账龄长",  "color": "warning"},
        {"value": "random",               "label": "E.随机",    "color": ""},
    ],
    # ── 地址不一致的核实方式（源模板 X0-2!L7 数据验证，六枢纽同构） ──
    "confirmation_addr_verify": [
        {"value": "invoice_contract",     "label": "发票/合同地址核实", "color": ""},
        {"value": "phone",                "label": "电话核实",          "color": ""},
        {"value": "website_announcement", "label": "官网/公告查询",     "color": ""},
        {"value": "map",                  "label": "地图查询",          "color": ""},
        {"value": "email",                "label": "邮件确认",          "color": ""},
        {"value": "other",                "label": "其他方式",          "color": "info"},
    ],
    "confirmation_reply_method": [
        {"value": "original_mail", "label": "原件寄回", "color": ""},
        {"value": "fax",           "label": "传真",     "color": "info"},
        {"value": "email",         "label": "电子邮件", "color": "info"},
        {"value": "in_person",     "label": "当面确认", "color": ""},
        # ── 源模板取值（X0-2!P7「回函方式」，六枢纽同构） ──
        # spec: h0-confirmation-source-fidelity-and-linkage R7.6
        {"value": "paper_original",     "label": "纸质原件", "color": ""},
        {"value": "electronic_platform", "label": "电子函证", "color": "info"},
        {"value": "other_medium",       "label": "其他介质", "color": "info"},
    ],
    "yes_no": [
        {"value": "yes", "label": "是", "color": "success"},
        {"value": "no",  "label": "否", "color": "danger"},
    ],
    "confirmation_match": [
        {"value": "matched",   "label": "相符",   "color": "success"},
        {"value": "unmatched", "label": "不符",   "color": "danger"},
        {"value": "no_reply",  "label": "未回函", "color": "warning"},
    ],
    "sampling_method": [
        {"value": "statistical",     "label": "统计抽样",   "color": ""},
        {"value": "non_statistical", "label": "非统计抽样", "color": ""},
        {"value": "all",             "label": "全部发函",   "color": ""},
        {"value": "other",           "label": "其他",       "color": "info"},
    ],
    # ── D0-2 核实被函证单位信息 额外枚举 ──
    "confirmation_send_result": [
        {"value": "delivered",  "label": "送抵", "color": "success"},
        {"value": "returned",   "label": "退回", "color": "danger"},
    ],
    "consistency_status": [
        {"value": "consistent",   "label": "一致",   "color": "success"},
        {"value": "inconsistent", "label": "不一致", "color": "danger"},
        {"value": "pending",      "label": "待核实", "color": "warning"},
    ],
    # ── D0-3 跟函函证过程控制 额外枚举 ──
    "confirmation_followup_scenario": [
        {"value": "immediate",    "label": "现场即时确认",       "color": "success"},
        {"value": "later_follow", "label": "无法即时确认留函",   "color": "warning"},
    ],
    "yes_no_na": [
        {"value": "yes", "label": "是",     "color": "success"},
        {"value": "no",  "label": "否",     "color": "danger"},
        {"value": "na",  "label": "不适用", "color": "info"},
    ],
    # ── D0-4 函证差异调节表 额外枚举 ──
    "confirmation_subject": [
        {"value": "应收账款",     "label": "应收账款",     "color": ""},
        {"value": "合同负债",     "label": "合同负债",     "color": ""},
        {"value": "销售收入",     "label": "销售收入",     "color": ""},
        {"value": "应收票据",     "label": "应收票据",     "color": ""},
        {"value": "合同资产",     "label": "合同资产",     "color": ""},
        {"value": "预付账款",     "label": "预付账款",     "color": ""},
        {"value": "应付账款",     "label": "应付账款",     "color": ""},
        {"value": "预收账款",     "label": "预收账款",     "color": ""},
        {"value": "其他应收款",   "label": "其他应收款",   "color": ""},
        {"value": "其他应付款",   "label": "其他应付款",   "color": ""},
        {"value": "银行存款",     "label": "银行存款",     "color": ""},
        {"value": "短期借款",     "label": "短期借款",     "color": ""},
        {"value": "长期借款",     "label": "长期借款",     "color": ""},
        # ── H 循环（固定资产循环函证 H0-4 差异核对表）品种 ──
        # 与 confirmation_account_type 的 H 类 9 项标签逐字一致（同一份品种，两个字典）。
        # spec: h0-confirmation-source-fidelity-and-linkage R1.4
        {"value": "固定资产",       "label": "固定资产",       "color": ""},
        {"value": "在建工程",       "label": "在建工程",       "color": ""},
        {"value": "投资性房地产",   "label": "投资性房地产",   "color": ""},
        {"value": "工程物资",       "label": "工程物资",       "color": ""},
        {"value": "油气资产",       "label": "油气资产",       "color": ""},
        {"value": "固定资产清理",   "label": "固定资产清理",   "color": ""},
        {"value": "生产性生物资产", "label": "生产性生物资产", "color": ""},
        {"value": "使用权资产",     "label": "使用权资产",     "color": ""},
        {"value": "租赁负债",       "label": "租赁负债",       "color": ""},
    ],
    "confirmation_diff_type": [
        {"value": "time",       "label": "时间性差异", "color": "info"},
        {"value": "accounting", "label": "记账差异",   "color": "warning"},
        {"value": "unrecorded", "label": "未达账项",   "color": "danger"},
        {"value": "other",      "label": "其他差异",   "color": ""},
    ],
    # ── D0-5 合同负债及销售替代程序 额外枚举 ──
    "sampling_selection_method": [
        {"value": "random",        "label": "随机选样",                    "color": ""},
        {"value": "systematic",    "label": "系统选样",                    "color": ""},
        {"value": "mus",           "label": "货币单元抽样",                "color": ""},
        {"value": "judgmental",    "label": "随意选样（非统计抽样适用）",   "color": "info"},
    ],
    # ── D0-7 回函可靠性验证 额外枚举 ──
    "reply_reliability_conclusion": [
        {"value": "可靠",             "label": "可靠",             "color": "success"},
        {"value": "部分可靠需补充",   "label": "部分可靠需补充",   "color": "warning"},
        {"value": "不可靠",           "label": "不可靠",           "color": "danger"},
    ],
    "reliability_identity_method": [
        {"value": "电话确认", "label": "电话确认", "color": ""},
        {"value": "邮件确认", "label": "邮件确认", "color": ""},
        {"value": "见面确认", "label": "见面确认", "color": ""},
        {"value": "系统确认", "label": "系统确认", "color": ""},
    ],
}


@router.get("/dicts")
async def get_system_dicts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回所有枚举字典，前端启动时加载一次并缓存到 sessionStorage

    DT-3 方案 B：合并 _DICTS 代码默认值 + enum_dict_overrides DB 覆盖
    """
    from app.models.enum_dict_override_models import EnumDictOverride

    # 加载所有 overrides
    overrides_map: dict[tuple[str, str], dict[str, str | None]] = {}
    try:
        rows = await db.execute(sa.select(EnumDictOverride))
        for ov in rows.scalars().all():
            overrides_map[(ov.dict_key, ov.value)] = {
                "label": ov.label_override,
                "color": ov.color_override,
            }
    except Exception as e:
        # 表不存在或查询失败时降级为只返回代码默认值
        logger.warning("enum_dict_overrides query failed (degraded to defaults): %s", e)

    # 合并：override.label/color 非 NULL 时覆盖
    result: dict[str, list[dict[str, str]]] = {}
    for dict_key, items in _DICTS.items():
        merged = []
        for item in items:
            ov = overrides_map.get((dict_key, item["value"]))
            merged.append({
                "value": item["value"],
                "label": ov["label"] if ov and ov["label"] is not None else item["label"],
                "color": ov["color"] if ov and ov["color"] is not None else item["color"],
            })
        result[dict_key] = merged
    return result


# ──────────────────────────────────────────────────────────────────────────
# Sprint 6 Task 6.2 — 枚举引用计数端点
# ──────────────────────────────────────────────────────────────────────────

# 字典键 → 数据源映射（表名 + 列名 + 可选过滤条件）
# 每个 dict_key 对应一条 SQL：SELECT col, COUNT(*) FROM table [WHERE ...] GROUP BY col
# 表/列必须与实际 DB schema 对齐（已 grep 核验：models/workpaper_models / audit_platform_models /
# report_models / phase15_models / core / staff_models）
_USAGE_COUNT_QUERIES: dict[str, dict[str, str]] = {
    "wp_status": {
        "table": "working_paper",
        "column": "status",
        "where": "is_deleted = false",
    },
    "wp_review_status": {
        "table": "working_paper",
        "column": "review_status",
        "where": "is_deleted = false",
    },
    "adjustment_status": {
        "table": "adjustments",
        "column": "status",
        "where": "is_deleted = false",
    },
    "report_status": {
        "table": "audit_report",
        "column": "status",
        "where": "is_deleted = false",
    },
    "project_status": {
        "table": "projects",
        "column": "status",
        "where": "is_deleted = false",
    },
    "issue_status": {
        "table": "issue_tickets",
        "column": "status",
        "where": "",
    },
    "workhour_status": {
        "table": "work_hours",
        "column": "status",
        "where": "",
    },
    # 以下字典暂无对应业务表（template_status 由代码维护，pdf_task_status 是临时任务态），
    # 返回全部 0，保持响应结构一致。
    "template_status": {
        "table": "",
        "column": "",
        "where": "",
    },
    "pdf_task_status": {
        "table": "",
        "column": "",
        "where": "",
    },
    # P2-6 扩展业务枚举
    "elimination_entry_type": {
        "table": "elimination_entries",
        "column": "entry_type",
        "where": "",
    },
    "audit_cycle": {
        "table": "",
        "column": "",
        "where": "",
    },
    "risk_level": {
        "table": "",
        "column": "",
        "where": "",
    },
    # P1-3.1 扩展
    "ai_content_status": {
        "table": "",
        "column": "",
        "where": "",
    },
    "archive_status": {
        "table": "",
        "column": "",
        "where": "",
    },
}


@router.get("/dicts/{dict_key}/usage-count")
async def get_dict_usage_count(
    dict_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回某字典各枚举值的引用计数。

    Response: `[{"value": "draft", "count": 12}, {"value": "approved", "count": 0}, ...]`

    - 字典中所有枚举值都会出现在响应中（即使 count=0），方便前端 UI 直接 join
    - 不存在对应业务表的字典返回全部 0
    - 单条查询失败（表不存在/列不存在）时记录 warning 并返回该字典全部 0
    """
    if dict_key not in _DICTS:
        raise HTTPException(status_code=404, detail={"error_code": "DICT_NOT_FOUND", "dict_key": dict_key})

    entries = _DICTS[dict_key]
    # 默认全部 0（保证响应结构稳定）
    counts: dict[str, int] = {e["value"]: 0 for e in entries}

    cfg = _USAGE_COUNT_QUERIES.get(dict_key)
    if cfg and cfg["table"]:
        sql = f"SELECT {cfg['column']} AS v, COUNT(*) AS c FROM {cfg['table']}"
        if cfg["where"]:
            sql += f" WHERE {cfg['where']}"
        sql += f" GROUP BY {cfg['column']}"
        try:
            result = await db.execute(text(sql))
            for row in result.fetchall():
                value = str(row[0]) if row[0] is not None else ""
                if value in counts:
                    counts[value] = int(row[1] or 0)
        except Exception as exc:
            # 失败时回滚事务避免后续查询全部失败（asyncpg session 污染）
            try:
                await db.rollback()
            except Exception:
                pass
            logger.warning(
                "usage_count query failed for dict_key=%s table=%s column=%s: %s",
                dict_key, cfg["table"], cfg["column"], exc,
            )

    return [{"value": v, "count": c} for v, c in counts.items()]


# ──────────────────────────────────────────────────────────────────────────
# Sprint 6 Task 6.3 — 枚举项 CRUD 端点（DT-3 方案 B：value 锁定 + label/color 可改）
# ──────────────────────────────────────────────────────────────────────────


@router.put("/dicts/{dict_key}/items/{item_value}")
async def update_dict_item(
    dict_key: str,
    item_value: str,
    payload: "EnumDictItemUpdate",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """DT-3 方案 B：仅修改 label/color（value 锁定，admin 可改）

    业务约束：
    - 仅 admin 角色可调用（其他角色 403）
    - dict_key 必须在 _DICTS 中
    - value 必须存在于 _DICTS[dict_key]（不允许新增）
    - label/color 至少一项非 None
    - color 必须 ∈ {success, warning, danger, info, ""}
    """
    from app.models.enum_dict_override_models import EnumDictOverride

    role = getattr(current_user, "role", "")
    role_value = role.value if hasattr(role, "value") else str(role)
    if role_value != "admin":
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "ENUM_DICT_FORBIDDEN",
                "message": "仅 admin 可修改枚举字典展示属性",
            },
        )

    # P2-6: value 硬编码锁死 — 尝试修改 value 返 405
    if payload.value is not None:
        raise HTTPException(
            status_code=405,
            detail={
                "error_code": "ENUM_DICT_VALUE_LOCKED",
                "message": "枚举字典 value 由代码硬编码锁死，不允许修改",
                "hint": _DICT_HARDCODED_HINT,
            },
        )

    if dict_key not in _DICTS:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "DICT_NOT_FOUND",
                "message": f"字典 '{dict_key}' 不存在",
                "available_keys": sorted(_DICTS.keys()),
            },
        )
    valid_values = {item["value"] for item in _DICTS[dict_key]}
    if item_value not in valid_values:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "DICT_VALUE_NOT_FOUND",
                "message": f"枚举值 '{item_value}' 不在 '{dict_key}' 中（不允许新增）",
                "available_values": sorted(valid_values),
            },
        )

    if payload.label is None and payload.color is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "EMPTY_UPDATE",
                "message": "label / color 至少需一项非 None",
            },
        )
    if payload.color is not None and payload.color not in ("success", "warning", "danger", "info", ""):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_COLOR",
                "message": "color 必须 ∈ {success, warning, danger, info, ''}",
            },
        )

    # upsert：先查再更新或插入
    existing = (
        await db.execute(
            sa.select(EnumDictOverride).where(
                EnumDictOverride.dict_key == dict_key,
                EnumDictOverride.value == item_value,
            )
        )
    ).scalar_one_or_none()

    if existing:
        if payload.label is not None:
            existing.label_override = payload.label
        if payload.color is not None:
            existing.color_override = payload.color
        existing.updated_by = getattr(current_user, "id", None)
    else:
        ov = EnumDictOverride(
            dict_key=dict_key,
            value=item_value,
            label_override=payload.label,
            color_override=payload.color,
            updated_by=getattr(current_user, "id", None),
        )
        db.add(ov)
    await db.flush()
    await db.commit()
    return {
        "dict_key": dict_key,
        "value": item_value,
        "label": payload.label,
        "color": payload.color,
        "message": "已更新（value 锁定，仅修改展示属性）",
    }


@router.delete("/dicts/{dict_key}/items/{item_value}/override")
async def reset_dict_item_override(
    dict_key: str,
    item_value: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """DT-3 方案 B：清除 label/color 覆盖，恢复代码默认值（不删除枚举值本身）"""
    from app.models.enum_dict_override_models import EnumDictOverride

    role = getattr(current_user, "role", "")
    role_value = role.value if hasattr(role, "value") else str(role)
    if role_value != "admin":
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "ENUM_DICT_FORBIDDEN",
                "message": "仅 admin 可重置枚举字典覆盖",
            },
        )

    result = await db.execute(
        sa.delete(EnumDictOverride).where(
            EnumDictOverride.dict_key == dict_key,
            EnumDictOverride.value == item_value,
        )
    )
    await db.commit()
    return {
        "dict_key": dict_key,
        "value": item_value,
        "deleted": result.rowcount,
        "message": "已恢复代码默认值",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Schema for label/color update
# ─────────────────────────────────────────────────────────────────────────────


class EnumDictItemUpdate(BaseModel):
    """枚举项展示属性更新（DT-3 方案 B）"""

    label: str | None = Field(None, max_length=255, description="展示文本（None 表示不改）")
    color: str | None = Field(
        None,
        description="el-tag type，必须 ∈ {success, warning, danger, info, ''}（None 表示不改）",
    )
    value: str | None = Field(None, description="value 字段锁死，传入即拒绝")

    model_config = {"extra": "ignore"}


# ─────────────────────────────────────────────────────────────────────────────
# 仍保留：拒绝新增枚举值（POST 405） + 拒绝物理删除枚举值（DELETE on /items 405）
# ─────────────────────────────────────────────────────────────────────────────

_DICT_HARDCODED_HINT = (
    "枚举字典 value 由代码定义（backend/app/routers/system_dicts.py 中的 _DICTS），"
    "不允许新增/删除/修改 value（避免代码引用悬空）。"
    "如需修改 label/color 展示属性请用 PUT /dicts/{dict_key}/items/{value}（仅 admin）。"
)


@router.post("/dicts/{dict_key}/items", status_code=405)
async def reject_dict_item_create(dict_key: str):
    """拒绝新增枚举项 — value 由代码硬编码（DT-3 / D13 ADR）。"""
    raise HTTPException(
        status_code=405,
        detail={
            "error_code": "ENUM_DICT_HARDCODED",
            "dict_key": dict_key,
            "hint": _DICT_HARDCODED_HINT,
        },
    )


@router.delete("/dicts/{dict_key}/items/{item_value}", status_code=405)
async def reject_dict_item_delete_value(dict_key: str, item_value: str):
    """拒绝物理删除枚举值 — 已被代码引用不可删（DT-3 / D13 ADR）。

    如需重置 label/color 覆盖请用 DELETE /dicts/{dict_key}/items/{value}/override
    """
    raise HTTPException(
        status_code=405,
        detail={
            "error_code": "ENUM_DICT_HARDCODED",
            "dict_key": dict_key,
            "item_value": item_value,
            "hint": _DICT_HARDCODED_HINT + " 重置覆盖请用 .../override 子路径。",
        },
    )
