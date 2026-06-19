"""底稿 sheet 归类服务

实现 9 类（A~I）→ componentType 白名单映射 + 项目级覆盖合并。
Requirements: 1.2（9 类全覆盖）+ 3.9（决策树禁止 Univer 兜底）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_wp_sheet_override import ProjectWorkpaperSheetOverride
from app.models.workpaper_models import WorkpaperSheetClassification

logger = logging.getLogger(__name__)


# ─── componentType 白名单（design §7.2） ─────────────────────────────────────
VALID_COMPONENT_TYPES: set[str] = {
    "a-program-console",
    "b-index",
    "c-note-table",
    "d-form-table",
    "d-form-paragraph",
    "d-form-qa",
    "d-form-confirmation",
    "d-form-review",
    "e-control-test",
    "h-static-doc",
    "custom",
    "audit-sheet",
    "bad-debt-sheet",
    "misstatement-summary",
    "review-checklist",
    "word-template",
    "independence-signing",
    "audit-legend",
    "univer",
    "skip",
    "checklist-table",
    "analytical-review",
    "misstatement-workpaper",
    "a14-3-workbook",
    "a17-summary",
    "kam-workpaper",
    "regulatory-letter",
    "a11-bundle",
    "a15-bundle",
    "redirect-materiality",
    "confirmation-hub",
    "a1-dashboard",
    "a2-adjustment-console",
    "a3-consolidation-console",
    "cf-verification",
}

# ─── 9 类 class_code 前缀 → componentType 映射 ──────────────────────────────
# D 类需要 sub-routing（基于 class_code 子类型）
_CLASS_TO_COMPONENT: dict[str, str] = {
    "A-": "a-program-console",
    "B-": "b-index",
    "C-": "c-note-table",
    "E-": "e-control-test",
    "F-": "univer",
    "G-": "univer",
    "H-": "h-static-doc",
    "I-": "skip",
}

# wp_code 级专用路由覆盖（优先于 class_code 派生）
# 特定底稿直接路由到专用 HTML 组件，不经过 class_code 映射
_WP_CODE_OVERRIDE: dict[str, str] = {
    "A1": "a1-dashboard",                 # 财务报告程序表 → 项目总控仪表盘
    "A2": "a2-adjustment-console",        # 调整分录程序表 → 卡片式中控台
    "A3": "a3-consolidation-console",    # 合并流程程序表 → 合并专用卡片中控台（仅合并项目）
    "A5": "cf-verification",          # 财务报表支持程序表 → 现金流量表核查视图
    "A13": "misstatement-workpaper",
    "A11": "a11-bundle",
    "A15": "a15-bundle",
    "A16": "word-template",
    "A21": "review-checklist",        # 现场负责人复核表 → 结构化复核面板
    "A21-1": "review-checklist",
    "A21-2": "review-checklist",
    "A22": "review-checklist",        # 项目经理复核 → 结构化复核面板
    "A22-1": "review-checklist",
    "A22-2": "review-checklist",
    "A23": "review-checklist",        # 合伙人复核 → 结构化复核面板
    "A23-1": "review-checklist",
    "A23-2": "review-checklist",
    "A24": "review-checklist",        # 质量复核 → 结构化复核面板
    "A24-1": "review-checklist",
    "A24-2": "review-checklist",
    "A25": "review-checklist",        # EQCR 复核 → 结构化复核面板
    "A25-1": "review-checklist",
    "A25-2": "review-checklist",
    "A31": "audit-legend",            # 审计标识一览表 → 标识符号对照面板
    "A17-7": "independence-signing",  # 独立性声明书 → 电子签署面板
    "A1-13": "analytical-review",     # 分析性复核（母公司） → 分析性复核专用组件
    "A1-14": "analytical-review",     # 分析性复核（合并） → 分析性复核专用组件
    "A1-11": "univer",                # 业务报告签发流转控制表（签字表,xlsx）
    "A1-12": "checklist-table",       # 重大事项决定程序核查表
    "A1-15": "checklist-table",       # 核对表（CAS列报及披露） → 核对表专用组件
    "A1-16": "checklist-table",       # 核对表（法规合规） → 核对表专用组件
    "A15-1": "checklist-table",
    "A14-1": "checklist-table",
    "A11-2": "checklist-table",
    "A11-3": "checklist-table",
    "A17-5-1": "checklist-table",
    "A17-5-2": "checklist-table",
    "A17-5-3": "checklist-table",
    "A17-5-4": "checklist-table",
    "A17-5-5": "checklist-table",
    "A17-1": "a17-summary",
    "A18-2": "regulatory-letter",
    "A14-3": "a14-3-workbook",
    "A13-2": "d-form-table",
    "A13-3": "d-form-table",
    "A13-4": "d-form-table",
    "A13-5": "d-form-table",
    "A10-2": "d-form-confirmation",
    "A14-2": "d-form-table",
    "A14-4": "d-form-table",
    "A14-5": "d-form-table",
    "A7-2": "c-note-table",
    "A14-6": "e-control-test",
    # ─── B 类 — 承接与计划 ────────────────────────────────────────────────────
    "B1A": "a-program-console",       # 业务承接程序表
    "B1B": "a-program-console",       # 业务保持程序表
    "B1-1": "d-form-table",           # 风险评估表（承接）
    "B1-2": "d-form-table",           # 风险评估表（保持）
    "B1-5": "checklist-table",        # KAA检查程序表
    "B2": "a-program-console",        # 与前任沟通程序表
    "B2-5": "d-form-table",           # 前任沟通评价表
    "B3": "checklist-table",          # 独立性确认程序表
    "B10": "a-program-console",       # 了解被审计单位及环境
    "B11": "a-program-console",       # 检查相关信息程序表
    "B12": "a-program-console",       # 与相关人员访谈程序
    "B13": "a-program-console",       # 初步分析程序表
    "B15": "redirect-materiality",       # 重要性计算表 → 重定向到 Materiality 模块
    "B18": "a-program-console",       # 了解内部审计程序表
    "B19": "a-program-console",       # 识别关联方程序表
    "B22A-1": "d-form-table",         # 企业层面控制-控制环境
    "B22A-2": "d-form-table",         # 企业层面控制-管理层凌驾
    "B22A-3": "d-form-table",         # 企业层面控制-风险评估
    "B22A-4": "d-form-table",         # 企业层面控制-信息与沟通
    "B22A-5": "d-form-table",         # 企业层面控制-监督
    "B22B": "d-form-table",           # 企业层面控制-控制矩阵
    "B22C": "d-form-table",           # 评价设计有效性-企业层面
    "B23-1": "d-form-table",          # 销售循环业务层面控制
    "B23-2": "d-form-table",          # 货币资金循环业务层面控制
    "B23-3": "d-form-table",          # 存货循环业务层面控制
    "B23-4": "d-form-table",          # 投资循环业务层面控制
    "B23-5": "d-form-table",          # 固定资产循环业务层面控制
    "B23-6": "d-form-table",          # 在建工程循环业务层面控制
    "B23-7": "d-form-table",          # 无形资产循环业务层面控制
    "B23-8": "d-form-table",          # 研发循环业务层面控制
    "B23-9": "d-form-table",          # 职工薪酬循环业务层面控制
    "B23-10": "d-form-table",         # 管理循环业务层面控制
    "B23-11": "d-form-table",         # 税金循环业务层面控制
    "B23-12": "d-form-table",         # 债务循环业务层面控制
    "B23-13": "d-form-table",         # 租赁循环业务层面控制
    "B23-14": "d-form-table",         # 关联方及交易业务层面控制
    "B23-15": "d-form-table",         # 了解信息处理控制
    "B23-XX-5": "d-form-table",       # 职责分离-通用模板
    "B30": "a-program-console",       # 集团审计程序表
    "B40": "a-program-console",       # 项目组讨论程序表
    "B50": "a-program-console",       # 汇总风险评估结果程序表
    "B50-1": "d-form-table",          # 汇总识别的风险因素
    "B50-2": "d-form-table",          # 财务报表层次风险
    "B50-3": "d-form-table",          # 认定层次重大错报风险
    "B50-4": "d-form-table",          # 汇总认定层次特别风险
    "B51": "d-form-table",            # 舞弊风险因素（三因素分析）
    "B52": "d-form-table",            # 舞弊-管理层凌驾
    "B60-1": "audit-sheet",           # 审计项目工时预算与控制表
    # ─── B 类子底稿 — 独立文件（非 B10 sheet）补全 ─────────────────────────
    "B13-2": "analytical-review",     # 未审报表初步分析
    "B19-1": "d-form-table",          # 识别未披露的关联方关系及异常关联交易
    "B51-3": "d-form-table",          # 识别对货币资金需保持警觉的情形程序
    "B51-5": "d-form-table",          # 识别收入确认方面可能存在舞弊风险的迹象程序
    "B30-1": "d-form-table",          # 了解组成部分
    "B30-8": "d-form-table",          # 了解组成部分注册会计师
    "B30-12": "d-form-table",         # 组成部分已识别错报汇总表
    "B30-15": "audit-sheet",          # 组成部分预算和实际收费信息（含公式）
    "B30-2A": "audit-sheet",          # 组成部分重要性及审计范围（含公式 xlsm）
    "B30-2B": "audit-sheet",          # 组成部分重要性水平（含公式 xlsm）
    "B22A-4-1": "d-form-table",       # IT概要
    "B22A-4-2": "d-form-table",       # 重大业务流程涉及的信息系统
    "B22A-4-3": "d-form-table",       # 了解IT环境 (xlsm)
    "B22A-4-4-1": "d-form-table",     # 了解IT一般控制
    "B22A-4-4-2": "d-form-table",     # IT一般控制职责分离分析
    "B22A-4-5": "d-form-table",       # 财务报告过程
    "B30-1-2-1": "d-form-table",      # 特别风险记录模板
    "B30-13-1": "d-form-table",       # 财务报告文件包
    # ─── C 类 — 控制测试 ─────────────────────────────────────────────────────
    "C1": "a-program-console",        # 企业层面控制测试程序表
    "C2": "d-form-table",             # 销售循环控制测试
    "C3": "d-form-table",             # 货币资金循环控制测试
    "C4": "d-form-table",             # 存货循环控制测试
    "C5": "d-form-table",             # 投资循环控制测试
    "C6": "d-form-table",             # 固定资产循环控制测试
    "C7": "d-form-table",             # 在建工程循环控制测试
    "C8": "d-form-table",             # 无形资产循环控制测试
    "C9": "d-form-table",             # 研发循环控制测试
    "C10": "d-form-table",            # 职工薪酬循环控制测试
    "C11": "d-form-table",            # 管理循环控制测试
    "C12": "d-form-table",            # 税金循环控制测试
    "C13": "d-form-table",            # 债务循环控制测试
    "C14": "d-form-table",            # 租赁循环控制测试
    "C15": "d-form-table",            # 关联方循环控制测试
    "C2-2": "d-form-table",           # 销售循环评价控制偏差
    "C3-2": "d-form-table",           # 货币资金循环评价控制偏差
    "C4-2": "d-form-table",           # 存货循环评价控制偏差
    "C5-2": "d-form-table",           # 投资循环评价控制偏差
    "C6-2": "d-form-table",           # 固定资产循环评价控制偏差
    "C7-2": "d-form-table",           # 在建工程循环评价控制偏差
    "C8-2": "d-form-table",           # 无形资产循环评价控制偏差
    "C9-2": "d-form-table",           # 研发循环评价控制偏差
    "C10-2": "d-form-table",          # 职工薪酬循环评价控制偏差
    "C11-2": "d-form-table",          # 管理循环评价控制偏差
    "C12-2": "d-form-table",          # 税金循环评价控制偏差
    "C13-2": "d-form-table",          # 债务循环评价控制偏差
    "C14-2": "d-form-table",          # 租赁循环评价控制偏差
    "C15-2": "d-form-table",          # 关联方循环评价控制偏差
    "C21": "d-form-table",            # IT专业人员资质
    "C21-1": "d-form-table",          # IT审计发现汇总
    "C22": "audit-sheet",             # IT一般控制测试（34 sheet，OnlyOffice）
    "C23": "d-form-table",            # 会计分录控制测试
    "C24": "d-form-table",            # 会计分录细节测试
    "C25": "d-form-table",            # 利用内审工作
    "C26": "d-form-table",            # 信息处理控制测试
    # ─── D 类 — 销售收入循环实质性程序 ────────────────────────────────────────
    # 函证
    "D0": "confirmation-hub",         # 收入循环函证 → ConfirmationHub 模块
    "D0-1": "d-form-table",           # 函证结果汇总
    "D0-2": "d-form-table",           # 核实被函证单位
    "D0-3": "d-form-table",           # 跟函控制
    "D0-4": "d-form-table",           # 差异调节
    "D0-5": "d-form-table",           # 替代程序
    # 应收票据
    "D1": "d-form-table",             # 应收票据审定表
    "D1-1": "d-form-table",           # 应收票据审定表（明细）
    "D1-2": "audit-sheet",            # 原值明细（按类）含公式
    "D1-3": "audit-sheet",            # 原值明细（按客户）含公式
    "D1-4": "d-form-table",           # 坏账准备（HTML优先）
    # 应收账款
    "D2": "d-form-table",             # 应收账款审定表
    "D2-1": "d-form-table",           # 应收账款审定表（明细）
    "D2-2": "audit-sheet",            # 明细表（大数据量）
    "D2-3": "d-form-table",           # 坏账准备明细（HTML优先）
    "D2-4": "d-form-table",           # 调整分录汇总
    "D2-5": "audit-sheet",            # 分析程序（含图表）
    "D2-6": "audit-sheet",            # 检查（多sheet）
    # 预收账款
    "D3": "d-form-table",             # 预收账款审定表
    "D3-1": "d-form-table",           # 预收账款审定表（明细）
    "D3-2": "d-form-table",           # 明细表（HTML优先）
    # 营业收入
    "D4": "d-form-table",             # 营业收入审定表
    "D4-1": "d-form-table",           # 营业收入审定表（明细）
    "D4-2": "audit-sheet",            # 收入明细按类别（大数据量）
    "D4-3": "audit-sheet",            # 收入明细按客户（大数据量）
    "D4-4": "audit-sheet",            # 收入明细按月份（大数据量）
    "D4-5": "d-form-table",           # 会计政策检查
    "D4-6": "audit-sheet",            # 分析程序（含图表）
    "D4-12": "d-form-table",          # 合同检查
    "D4-13": "audit-sheet",           # 检查（多sheet）
    "D4-21": "d-form-table",          # 关联方检查
    "D4-22": "audit-sheet",           # IPO舞弊应对（多sheet）
    "D4-33": "d-form-table",          # 其他业务收入
    # 应收款项融资
    "D5": "d-form-table",             # 应收款项融资审定表
    "D5-1": "d-form-table",           # 应收款项融资审定表（明细）
    "D5-2": "audit-sheet",            # 明细（含公式）
    # 合同资产
    "D6": "d-form-table",             # 合同资产审定表
    "D6-1": "d-form-table",           # 合同资产明细表
    "D6-2": "audit-sheet",            # 详细明细（含公式）
    "D6-3": "audit-sheet",            # 减值准备明细（含公式）
    "D6-4": "d-form-table",           # 调整分录汇总
    "D6-5": "d-form-table",           # 关联方检查
    "D6-6": "d-form-table",           # 检查表
    "D6-7": "d-form-paragraph",       # 会计政策检查（段落）
    "D6-8": "audit-sheet",            # 减值测算（DCF公式）
    "D6-9": "d-form-table",           # 转回核销检查
    # 合同负债
    "D7": "d-form-table",             # 合同负债审定表
    "D7-1": "d-form-table",           # 合同负债明细表
    "D7-2": "d-form-table",           # 详细明细（HTML优先）
    # ─── E 类 — 货币资金循环实质性程序 ────────────────────────────────────────
    # 函证
    "E0": "confirmation-hub",         # 货币资金函证 → ConfirmationHub 模块
    "E0-1": "d-form-table",           # 函证结果汇总
    "E0-2": "d-form-table",           # 核实被函证银行
    "E0-3": "d-form-table",           # 跟函控制
    "E0-4": "d-form-table",           # 差异调节
    "E0-5": "d-form-table",           # 替代程序
    # 货币资金 - 常规
    "E1": "d-form-table",             # 货币资金审定表
    "E1-1": "d-form-table",           # 货币资金审定表（明细）
    "E1-2": "d-form-table",           # 库存现金明细表
    "E1-3": "audit-sheet",            # 银行存款明细表（含公式）
    "E1-4": "audit-sheet",            # 其他货币资金明细表（含公式）
    "E1-5": "audit-sheet",            # 银行存款余额调节表（含公式）
    "E1-6": "d-form-table",           # 受限货币资金明细
    "E1-7": "audit-sheet",            # 大额现金收支检查
    "E1-8": "audit-sheet",            # 银行存款检查
    "E1-9": "audit-sheet",            # 利息测算（含公式）
    "E1-10": "d-form-table",          # 调整分录汇总
    "E1-11": "audit-sheet",           # 未达账项明细
    # 货币资金 - 分析
    "E1-14": "audit-sheet",           # 货币资金分析程序（一）
    "E1-15": "audit-sheet",           # 货币资金分析程序（二）
    # 货币资金 - 检查
    "E1-18": "audit-sheet",           # 货币资金检查（一）
    "E1-19": "audit-sheet",           # 货币资金检查（二）
    "E1-20": "audit-sheet",           # 货币资金检查（三）
    "E1-21": "audit-sheet",           # 货币资金检查（四）
    "E1-22": "audit-sheet",           # 货币资金检查（五）
    "E1-23": "audit-sheet",           # 货币资金检查（六）
    # 货币资金 - IPO
    "E1-26": "audit-sheet",           # IPO/舞弊应对（一）
    "E1-27": "audit-sheet",           # IPO/舞弊应对（二）
    "E1-28": "audit-sheet",           # IPO/舞弊应对（三）
    "E1-29": "audit-sheet",           # IPO/舞弊应对（四）
    "E1-30": "audit-sheet",           # IPO/舞弊应对（五）
    "E1-31": "audit-sheet",           # IPO/舞弊应对（六）
    "E1-32": "audit-sheet",           # IPO/舞弊应对（七）
    # ─── F 类 — 采购存货循环实质性程序 ────────────────────────────────────────
    # 函证
    "F0": "confirmation-hub",         # 存货循环函证 → ConfirmationHub 模块
    "F0-1": "d-form-table",           # 函证结果汇总
    "F0-2": "d-form-table",           # 核实被函证单位
    "F0-3": "d-form-table",           # 跟函控制
    "F0-4": "d-form-table",           # 差异调节
    "F0-5": "d-form-table",           # 替代程序
    # 预付账款
    "F1": "d-form-table",             # 预付账款审定表
    "F1-1": "d-form-table",           # 预付账款审定表（明细）
    "F1-2": "audit-sheet",            # 预付账款明细表（含公式）
    "F1-3": "audit-sheet",            # 预付账款账龄分析（含公式）
    "F1-4": "d-form-table",           # 预付账款坏账准备
    "F1-5": "audit-sheet",            # 预付账款调整分录汇总
    "F1-6": "audit-sheet",            # 预付账款检查
    # 存货 - 审定明细
    "F2": "d-form-table",             # 存货及跌价准备审定表
    "F2-1": "d-form-table",           # 存货审定表（明细）
    "F2-2": "audit-sheet",            # 存货分类明细（含公式）
    "F2-3": "audit-sheet",            # 存货增减变动（含公式）
    "F2-4": "audit-sheet",            # 原材料明细（含公式）
    "F2-5": "audit-sheet",            # 在产品明细（含公式）
    "F2-6": "audit-sheet",            # 库存商品明细（含公式）
    "F2-7": "audit-sheet",            # 在途物资明细（含公式）
    "F2-8": "audit-sheet",            # 委托加工物资明细（含公式）
    "F2-9": "audit-sheet",            # 工程施工明细（含公式）
    "F2-10": "audit-sheet",           # 开发产品明细（含公式）
    "F2-11": "d-form-table",          # 跌价准备明细
    "F2-12": "d-form-table",          # 跌价准备变动
    "F2-13": "d-form-table",          # 存货调整分录汇总
    "F2-14": "d-form-table",          # 存货担保质押
    # 存货 - 会计政策
    "F2-16": "d-form-table",          # 存货会计政策检查
    # 存货 - 分析
    "F2-18": "audit-sheet",           # 存货分析程序（一）
    "F2-19": "audit-sheet",           # 存货分析程序（二）
    "F2-20": "audit-sheet",           # 存货分析程序（三）
    # 存货 - 盘点
    "F2-21": "audit-sheet",           # 存货监盘计划
    "F2-22": "audit-sheet",           # 盘点观察记录
    "F2-23": "audit-sheet",           # 盘点抽盘测试
    "F2-24": "audit-sheet",           # 存货截止测试
    "F2-25": "audit-sheet",           # 盘点差异汇总
    "F2-26": "audit-sheet",           # 监盘结论
    # 存货 - 检查
    "F2-29": "audit-sheet",           # 存货检查（一）
    "F2-30": "audit-sheet",           # 存货检查（二）
    "F2-31": "audit-sheet",           # 存货检查（三）
    "F2-32": "audit-sheet",           # 存货检查（四）
    "F2-33": "audit-sheet",           # 存货检查（五）
    "F2-34": "audit-sheet",           # 存货检查（六）
    "F2-35": "audit-sheet",           # 存货检查（七）
    # 存货 - 计价
    "F2-38": "audit-sheet",           # 计价测试（一）
    "F2-39": "audit-sheet",           # 计价测试（二）
    "F2-40": "audit-sheet",           # 计价测试（三）
    "F2-41": "audit-sheet",           # 计价测试（四）
    "F2-42": "audit-sheet",           # 计价测试（五）
    "F2-43": "audit-sheet",           # 计价测试（六）
    "F2-44": "audit-sheet",           # 计价测试（七）
    # 存货 - 跌价
    "F2-47": "audit-sheet",           # 跌价准备测试（一）
    "F2-48": "audit-sheet",           # 跌价准备测试（二）
    "F2-49": "audit-sheet",           # 跌价准备测试（三）
    # 存货 - 关联交易
    "F2-52": "d-form-table",          # 存货关联交易检查
    # 存货 - 合同履约成本
    "F2-55": "audit-sheet",           # 合同履约成本（一）
    "F2-56": "audit-sheet",           # 合同履约成本（二）
    "F2-57": "audit-sheet",           # 合同履约成本（三）
    "F2-58": "audit-sheet",           # 合同履约成本（四）
    # 存货 - IPO
    "F2-61": "audit-sheet",           # 存货IPO舞弊应对（一）
    "F2-62": "audit-sheet",           # 存货IPO舞弊应对（二）
    "F2-63": "audit-sheet",           # 存货IPO舞弊应对（三）
    "F2-64": "audit-sheet",           # 存货IPO舞弊应对（四）
    "F2-65": "audit-sheet",           # 存货IPO舞弊应对（五）
    "F2-66": "audit-sheet",           # 存货IPO舞弊应对（六）
    "F2-67": "audit-sheet",           # 存货IPO舞弊应对（七）
    "F2-68": "audit-sheet",           # 存货IPO舞弊应对（八）
    "F2-69": "audit-sheet",           # 存货IPO舞弊应对（九）
    "F2-70": "audit-sheet",           # 存货IPO舞弊应对（十）
    "F2-71": "audit-sheet",           # 存货IPO舞弊应对（十一）
    "F2-72": "audit-sheet",           # 存货IPO舞弊应对（十二）
    # 应付票据
    "F3": "d-form-table",             # 应付票据审定表
    "F3-1": "d-form-table",           # 应付票据审定表（明细）
    "F3-2": "audit-sheet",            # 应付票据明细表（含公式）
    "F3-3": "audit-sheet",            # 应付票据检查
    "F3-4": "d-form-table",           # 应付票据调整分录汇总
    "F3-5": "audit-sheet",            # 应付票据分析程序
    "F3-6": "audit-sheet",            # 应付票据到期日分析
    # 应付账款
    "F4": "d-form-table",             # 应付账款审定表
    "F4-1": "d-form-table",           # 应付账款审定表（明细）
    "F4-2": "audit-sheet",            # 应付账款明细表（含公式）
    "F4-3": "audit-sheet",            # 应付账款账龄分析（含公式）
    "F4-4": "d-form-table",           # 应付账款调整分录汇总
    "F4-5": "audit-sheet",            # 应付账款检查
    "F4-6": "audit-sheet",            # 应付账款分析程序
    # 营业成本
    "F5": "d-form-table",             # 营业成本审定表
    "F5-1": "d-form-table",           # 营业成本审定表（明细）
    "F5-2": "audit-sheet",            # 营业成本明细表（含公式）
    "F5-3": "audit-sheet",            # 成本结转测试（含公式）
    "F5-4": "audit-sheet",            # 毛利率分析（含公式）
    "F5-5": "audit-sheet",            # 营业成本检查
    "F5-6": "audit-sheet",            # 营业成本分析程序
    # ─── G 类 — 投资循环实质性程序 ────────────────────────────────────────────
    # 函证
    "G0": "confirmation-hub",         # 投资循环函证 → ConfirmationHub 模块
    "G0-1": "d-form-table",           # 函证结果汇总
    "G0-2": "d-form-table",           # 核实被函证单位
    "G0-3": "d-form-table",           # 跟函控制
    "G0-4": "d-form-table",           # 差异调节
    "G0-5": "d-form-table",           # 替代程序
    # 交易性金融资产
    "G1": "d-form-table",             # 交易性金融资产审定表
    "G1-1": "d-form-table",           # 交易性金融资产审定表（明细）
    "G1-2": "audit-sheet",            # 交易性金融资产明细表（含公式）
    "G1-3": "audit-sheet",            # 公允价值测试（含公式）
    "G1-4": "audit-sheet",            # 分析程序
    "G1-5": "audit-sheet",            # 检查
    "G1-6": "d-form-table",           # 调整分录
    # 应收利息
    "G2": "d-form-table",             # 应收利息审定表
    "G2-1": "d-form-table",           # 应收利息审定表（明细）
    "G2-2": "audit-sheet",            # 应收利息明细表
    "G2-3": "audit-sheet",            # 利息测算（含公式）
    "G2-4": "d-form-table",           # 调整分录
    # 应收股利
    "G3": "d-form-table",             # 应收股利审定表
    "G3-1": "d-form-table",           # 应收股利审定表（明细）
    "G3-2": "d-form-table",           # 应收股利明细表
    "G3-3": "audit-sheet",            # 应收股利检查
    "G3-4": "d-form-table",           # 调整分录
    # 债权投资
    "G4": "d-form-table",             # 债权投资审定表
    "G4-1": "d-form-table",           # 债权投资审定表（明细）
    "G4-2": "audit-sheet",            # 债权投资明细表
    "G4-3": "audit-sheet",            # 摊余成本测算（含IRR公式）
    "G4-4": "audit-sheet",            # 实际利率法测算（含公式）
    "G4-5": "audit-sheet",            # ECL三阶段模型
    "G4-6": "audit-sheet",            # 分析程序
    "G4-7": "audit-sheet",            # 检查
    "G4-8": "d-form-table",           # 调整分录
    # 长期应收款
    "G5": "d-form-table",             # 长期应收款审定表
    "G5-1": "d-form-table",           # 长期应收款审定表（明细）
    "G5-2": "d-form-table",           # 长期应收款明细表
    "G5-3": "audit-sheet",            # 现值测算（含折现公式）
    "G5-4": "d-form-table",           # 调整分录
    # 其他债权投资
    "G6": "d-form-table",             # 其他债权投资审定表
    "G6-1": "d-form-table",           # 其他债权投资审定表（明细）
    "G6-2": "audit-sheet",            # 其他债权投资明细表
    "G6-3": "audit-sheet",            # 公允价值测试
    "G6-4": "audit-sheet",            # ECL测试
    "G6-5": "audit-sheet",            # 分析程序
    "G6-6": "d-form-table",           # 调整分录
    # 长期股权投资
    "G7": "d-form-table",             # 长期股权投资审定表
    "G7-1": "d-form-table",           # 长期股权投资审定表（明细）
    "G7-2": "audit-sheet",            # 长期股权投资明细表
    "G7-3": "audit-sheet",            # 权益法核算（含公式）
    "G7-4": "audit-sheet",            # 减值测试
    "G7-5": "audit-sheet",            # 投资收益测算
    "G7-6": "audit-sheet",            # 分析程序
    "G7-7": "audit-sheet",            # 检查
    "G7-8": "d-form-table",           # 调整分录
    # 其他权益工具投资
    "G8": "d-form-table",             # 其他权益工具投资审定表
    "G8-1": "d-form-table",           # 其他权益工具投资审定表（明细）
    "G8-2": "audit-sheet",            # 其他权益工具投资明细表
    "G8-3": "audit-sheet",            # 公允价值测试
    "G8-4": "audit-sheet",            # OCI变动
    "G8-5": "audit-sheet",            # 分析程序
    "G8-6": "d-form-table",           # 调整分录
    # 其他非流动金融资产
    "G9": "d-form-table",             # 其他非流动金融资产审定表
    "G9-1": "d-form-table",           # 其他非流动金融资产审定表（明细）
    "G9-2": "audit-sheet",            # 明细表
    "G9-3": "audit-sheet",            # 分析程序
    "G9-4": "d-form-table",           # 调整分录
    # 交易性金融负债
    "G10": "d-form-table",            # 交易性金融负债审定表
    "G10-1": "d-form-table",          # 交易性金融负债审定表（明细）
    "G10-2": "audit-sheet",           # 明细表
    "G10-3": "audit-sheet",           # 公允价值测试
    "G10-4": "d-form-table",          # 调整分录
    # 投资收益
    "G11": "d-form-table",            # 投资收益审定表
    "G11-1": "d-form-table",          # 投资收益审定表（明细）
    "G11-2": "audit-sheet",           # 投资收益明细表
    "G11-3": "audit-sheet",           # 分析程序
    "G11-4": "d-form-table",          # 调整分录
    # 净敞口套期收益
    "G12": "d-form-table",            # 净敞口套期收益审定表
    "G12-1": "d-form-table",          # 净敞口套期收益审定表（明细）
    "G12-2": "audit-sheet",           # 明细表
    "G12-3": "d-form-table",          # 调整分录
    # 公允价值变动收益
    "G13": "d-form-table",            # 公允价值变动收益审定表
    "G13-1": "d-form-table",          # 公允价值变动收益审定表（明细）
    "G13-2": "audit-sheet",           # 明细表
    "G13-3": "audit-sheet",           # 联动交易性金融资产
    "G13-4": "d-form-table",          # 调整分录
    # 信用减值损失
    "G14": "d-form-table",            # 信用减值损失审定表
    "G14-1": "d-form-table",          # 信用减值损失审定表（明细）
    "G14-2": "audit-sheet",           # ECL计算明细
    "G14-3": "audit-sheet",           # 分析程序
    "G14-4": "d-form-table",          # 调整分录
    # ─── H 类 — 固定资产循环实质性程序 ────────────────────────────────────────
    # 函证
    "H0": "confirmation-hub",         # 固定资产循环函证 → ConfirmationHub 模块
    "H0-1": "d-form-table",           # 函证结果汇总
    "H0-2": "d-form-table",           # 核实被函证单位
    "H0-3": "d-form-table",           # 跟函控制
    "H0-4": "d-form-table",           # 差异调节
    "H0-5": "d-form-table",           # 替代程序
    # 固定资产
    "H1": "d-form-table",             # 固定资产审定表
    "H1-1": "d-form-table",           # 固定资产审定表（明细）
    "H1-2": "audit-sheet",            # 固定资产明细表（含公式）
    "H1-3": "audit-sheet",            # 折旧测算（含公式）
    "H1-4": "audit-sheet",            # 增减变动（含公式）
    "H1-5": "audit-sheet",            # 减值测试（含公式）
    "H1-6": "audit-sheet",            # 分析程序
    "H1-7": "audit-sheet",            # 检查
    "H1-8": "d-form-table",           # 调整分录
    # 在建工程
    "H2": "d-form-table",             # 在建工程审定表
    "H2-1": "d-form-table",           # 在建工程审定表（明细）
    "H2-2": "audit-sheet",            # 在建工程明细表（含公式）
    "H2-3": "audit-sheet",            # 利息资本化测算（含公式）
    "H2-4": "audit-sheet",            # 转固测试（含公式）
    "H2-5": "audit-sheet",            # 分析程序
    "H2-6": "d-form-table",           # 调整分录
    # 投资性房地产
    "H3": "d-form-table",             # 投资性房地产审定表
    "H3-1": "d-form-table",           # 投资性房地产审定表（明细）
    "H3-2": "audit-sheet",            # 投资性房地产明细表（含公式）
    "H3-3": "audit-sheet",            # 公允价值测试（含公式）
    "H3-4": "audit-sheet",            # 折旧/摊销测算（含公式）
    "H3-5": "audit-sheet",            # 分析程序
    "H3-6": "d-form-table",           # 调整分录
    # 工程物资
    "H4": "d-form-table",             # 工程物资审定表
    "H4-1": "d-form-table",           # 工程物资审定表（明细）
    "H4-2": "audit-sheet",            # 工程物资明细表（含公式）
    "H4-3": "audit-sheet",            # 工程物资检查
    "H4-4": "d-form-table",           # 调整分录
    # 油气资产
    "H5": "d-form-table",             # 油气资产审定表
    "H5-1": "d-form-table",           # 油气资产审定表（明细）
    "H5-2": "audit-sheet",            # 油气资产明细表（含公式）
    "H5-3": "audit-sheet",            # 折耗测算（含公式）
    "H5-4": "d-form-table",           # 调整分录
    # 固定资产清理
    "H6": "d-form-table",             # 固定资产清理审定表
    "H6-1": "d-form-table",           # 固定资产清理审定表（明细）
    "H6-2": "audit-sheet",            # 固定资产清理明细表（含公式）
    "H6-3": "audit-sheet",            # 固定资产清理检查
    "H6-4": "d-form-table",           # 调整分录
    # 生产性生物资产
    "H7": "d-form-table",             # 生产性生物资产审定表
    "H7-1": "d-form-table",           # 生产性生物资产审定表（明细）
    "H7-2": "audit-sheet",            # 生产性生物资产明细表（含公式）
    "H7-3": "audit-sheet",            # 生产性生物资产折旧测算（含公式）
    "H7-4": "d-form-table",           # 调整分录
    # 使用权资产（CAS21 新租赁准则）
    "H8": "d-form-table",             # 使用权资产审定表
    "H8-1": "d-form-table",           # 使用权资产审定表（明细）
    "H8-2": "audit-sheet",            # 使用权资产明细表（含公式）
    "H8-3": "audit-sheet",            # 使用权资产折旧测算（含公式）
    "H8-4": "audit-sheet",            # 使用权资产租赁还原（CAS21含公式）
    "H8-5": "audit-sheet",            # 使用权资产减值测试
    "H8-6": "d-form-table",           # 调整分录
    # 租赁负债（CAS21 新租赁准则）
    "H9": "d-form-table",             # 租赁负债审定表
    "H9-1": "d-form-table",           # 租赁负债审定表（明细）
    "H9-2": "audit-sheet",            # 租赁负债明细表（含公式）
    "H9-3": "audit-sheet",            # 租赁负债现值测算（CAS21含公式）
    "H9-4": "audit-sheet",            # 租赁负债摊销表（CAS21含公式）
    "H9-5": "audit-sheet",            # 分析程序
    "H9-6": "d-form-table",           # 调整分录
    # 资产处置损益
    "H10": "d-form-table",            # 资产处置损益审定表
    "H10-1": "d-form-table",          # 资产处置损益审定表（明细）
    "H10-2": "audit-sheet",           # 资产处置损益明细表（含公式）
    "H10-3": "audit-sheet",           # 资产处置损益检查
    "H10-4": "d-form-table",          # 调整分录
    # ─── I 类 — 无形资产循环实质性程序 ────────────────────────────────────────
    # 无形资产（I1）
    "I1": "d-form-table",             # 无形资产审定表
    "I1-1": "d-form-table",           # 无形资产审定表（按类别分行+摊销/减值扣减）
    "I1-2": "audit-sheet",            # 无形资产明细表（含公式）
    "I1-3": "audit-sheet",            # 摊销测算（直线法/产量法含公式）
    "I1-4": "audit-sheet",            # 减值测试（含公式）
    "I1-5": "audit-sheet",            # 增减变动（含公式）
    "I1-6": "audit-sheet",            # 分析程序
    "I1-7": "audit-sheet",            # 检查
    "I1-8": "d-form-table",           # 调整分录
    # 开发支出（I2）
    "I2": "d-form-table",             # 开发支出审定表
    "I2-1": "d-form-table",           # 开发支出审定表（明细）
    "I2-2": "audit-sheet",            # 开发支出明细表（含公式）
    "I2-3": "d-form-table",           # 资本化条件检查（CAS6五条件→d-form-table）
    "I2-4": "audit-sheet",            # 转无形资产（含公式）
    "I2-5": "audit-sheet",            # 分析程序
    "I2-6": "d-form-table",           # 调整分录
    # 商誉（I3）
    "I3": "d-form-table",             # 商誉审定表
    "I3-1": "d-form-table",           # 商誉审定表（明细）
    "I3-2": "audit-sheet",            # 商誉明细表（含公式）
    "I3-3": "d-form-table",           # 减值测试概要
    "I3-4": "audit-sheet",            # DCF计算（WACC/CAPM/FCF/TV/NPV含复杂公式）
    "I3-5": "audit-sheet",            # 敏感性分析（折现率/增长率矩阵含公式）
    "I3-6": "d-form-table",           # 调整分录
    # 长期待摊费用（I4）
    "I4": "d-form-table",             # 长期待摊费用审定表
    "I4-1": "d-form-table",           # 长期待摊费用审定表（明细）
    "I4-2": "audit-sheet",            # 长期待摊费用明细表（含公式）
    "I4-3": "audit-sheet",            # 摊销检查
    "I4-4": "d-form-table",           # 调整分录
    # 其他非流动资产（I5）
    "I5": "d-form-table",             # 其他非流动资产审定表
    "I5-1": "d-form-table",           # 其他非流动资产审定表（明细）
    "I5-2": "audit-sheet",            # 其他非流动资产明细表（含公式）
    "I5-3": "audit-sheet",            # 检查
    "I5-4": "d-form-table",           # 调整分录
    # 研发费用（I6）
    "I6": "d-form-table",             # 研发费用审定表
    "I6-1": "d-form-table",           # 研发费用审定表（明细）
    "I6-2": "audit-sheet",            # 研发费用明细表（含公式，从tb_ledger取数）
    "I6-3": "d-form-table",           # 资本化/费用化分类（结构化判断→d-form-table）
    "I6-4": "audit-sheet",            # 研发项目台账
    "I6-5": "audit-sheet",            # 分析程序
    "I6-6": "audit-sheet",            # 检查
    "I6-7": "audit-sheet",            # 加计扣除测算（税法公式含公式）
    "I6-8": "d-form-table",           # 调整分录
    # ─── J 类 — 职工薪酬循环实质性程序 ────────────────────────────────────────
    # 程序表
    "J1A": "a-program-console",       # 应付职工薪酬程序表
    "J2A": "a-program-console",       # 设定受益计划程序表
    "J3A": "a-program-console",       # 股份支付程序表
    # 审定表
    "J1-1": "d-form-table",           # 应付职工薪酬审定表
    "J2-1": "d-form-table",           # 设定受益计划审定表
    "J3-1": "d-form-table",           # 股份支付审定表
    # J1 应付职工薪酬 - 明细/测算/分析/检查
    "J1-2": "audit-sheet",            # 应付职工薪酬明细表
    "J1-3": "audit-sheet",            # 工资测算（人数×平均工资×月份含公式）
    "J1-4": "audit-sheet",            # 社保测算（含公式）
    "J1-5": "audit-sheet",            # 分析程序
    "J1-6": "audit-sheet",            # 检查
    "J1-7": "audit-sheet",            # 个税验证
    "J1-8": "d-form-table",           # 调整分录
    # J2 设定受益计划
    "J2-2": "audit-sheet",            # 设定受益计划明细
    "J2-3": "d-form-table",           # 精算假设评估（折现率/工资增长率/离职率/死亡率）
    "J2-4": "d-form-table",           # 精算师工作利用
    "J2-5": "audit-sheet",            # 精算重新计算（DBO/计划资产/净负债含公式）
    "J2-6": "d-form-table",           # 调整分录
    # J3 股份支付
    "J3-2": "audit-sheet",            # 股份支付明细
    "J3-3": "d-form-table",           # 授予条件检查
    "J3-4": "audit-sheet",            # 期权定价（Black-Scholes参数+公式）
    "J3-5": "audit-sheet",            # 费用分摊（等待期费用含公式）
    "J3-6": "d-form-table",           # 调整分录
    # ─── K 类 — 管理循环实质性程序 ────────────────────────────────────────────
    # 程序表
    "K0A": "a-program-console",       # 管理循环函证程序表
    "K1A": "a-program-console",       # 其他应收款程序表
    "K2A": "a-program-console",       # 其他流动资产程序表
    "K3A": "a-program-console",       # 其他应付款程序表
    "K4A": "a-program-console",       # 其他流动负债程序表
    "K5A": "a-program-console",       # 预计负债程序表
    "K6A": "a-program-console",       # 持有待售程序表
    "K7A": "a-program-console",       # 递延收益程序表
    "K8A": "a-program-console",       # 销售费用程序表
    "K9A": "a-program-console",       # 管理费用程序表
    "K10A": "a-program-console",      # 其他收益程序表
    "K11A": "a-program-console",      # 资产减值损失程序表
    "K12A": "a-program-console",      # 营业外收入程序表
    "K13A": "a-program-console",      # 营业外支出程序表
    # K0 函证
    "K0": "confirmation-hub",         # 管理循环函证 → ConfirmationHub 模块
    "K0-1": "d-form-table",           # 函证结果汇总
    "K0-2": "d-form-table",           # 核实被函证单位
    "K0-3": "d-form-table",           # 跟函控制
    "K0-4": "d-form-table",           # 差异调节
    "K0-5": "d-form-table",           # 替代程序
    # K1 其他应收款
    "K1": "c-note-table",             # 其他应收款附注
    "K1-1": "d-form-table",           # 其他应收款审定表
    "K1-2": "audit-sheet",            # 其他应收款明细表
    "K1-3": "audit-sheet",            # 其他应收款账龄分析
    "K1-4": "d-form-table",           # 坏账准备（结构化判断）
    "K1-5": "audit-sheet",            # 其他应收款检查
    "K1-6": "d-form-table",           # 调整分录
    # K2 其他流动资产
    "K2": "c-note-table",             # 其他流动资产附注
    "K2-1": "d-form-table",           # 其他流动资产审定表
    "K2-2": "audit-sheet",            # 其他流动资产明细表
    "K2-3": "audit-sheet",            # 其他流动资产检查
    "K2-4": "d-form-table",           # 调整分录
    # K3 其他应付款
    "K3": "c-note-table",             # 其他应付款附注
    "K3-1": "d-form-table",           # 其他应付款审定表
    "K3-2": "audit-sheet",            # 其他应付款明细表
    "K3-3": "audit-sheet",            # 其他应付款账龄分析
    "K3-4": "audit-sheet",            # 其他应付款检查
    "K3-5": "audit-sheet",            # 其他应付款分析
    "K3-6": "d-form-table",           # 调整分录
    # K4 其他流动负债
    "K4": "c-note-table",             # 其他流动负债附注
    "K4-1": "d-form-table",           # 其他流动负债审定表
    "K4-2": "audit-sheet",            # 其他流动负债明细表
    "K4-3": "audit-sheet",            # 其他流动负债检查
    "K4-4": "d-form-table",           # 调整分录
    # K5 预计负债
    "K5": "c-note-table",             # 预计负债附注
    "K5-1": "d-form-table",           # 预计负债审定表
    "K5-2": "audit-sheet",            # 预计负债明细表
    "K5-3": "d-form-table",           # 或有事项评估（三级可能性→d-form-table）
    "K5-4": "audit-sheet",            # 最佳估计数计算（上下限+加权平均含公式）
    "K5-5": "d-form-table",           # 律师函回函分析（结构化→d-form-table）
    "K5-6": "d-form-table",           # 调整分录
    # K6 持有待售资产和负债
    "K6": "c-note-table",             # 持有待售附注
    "K6-1": "d-form-table",           # 持有待售审定表
    "K6-2": "audit-sheet",            # 持有待售明细表
    "K6-3": "d-form-table",           # 持有待售分类条件（CAS42 五条件→d-form-table）
    "K6-4": "d-form-table",           # 调整分录
    # K7 递延收益
    "K7": "c-note-table",             # 递延收益附注
    "K7-1": "d-form-table",           # 递延收益审定表
    "K7-2": "audit-sheet",            # 递延收益明细表
    "K7-3": "audit-sheet",            # 政府补助分摊
    "K7-4": "d-form-table",           # 调整分录
    # K8 销售费用
    "K8": "c-note-table",             # 销售费用附注
    "K8-1": "d-form-table",           # 销售费用审定表
    "K8-2": "audit-sheet",            # 销售费用明细表（从tb_ledger取数）
    "K8-3": "audit-sheet",            # 销售费用分析（同比/环比趋势）
    "K8-4": "audit-sheet",            # 销售费用检查
    "K8-5": "audit-sheet",            # 销售费用大额检查
    "K8-6": "d-form-table",           # 调整分录
    # K9 管理费用
    "K9": "c-note-table",             # 管理费用附注
    "K9-1": "d-form-table",           # 管理费用审定表
    "K9-2": "audit-sheet",            # 管理费用明细表（从tb_ledger取数）
    "K9-3": "audit-sheet",            # 管理费用分析（同比/环比趋势）
    "K9-4": "audit-sheet",            # 管理费用检查
    "K9-5": "audit-sheet",            # 管理费用大额检查
    "K9-6": "d-form-table",           # 调整分录
    # K10 其他收益
    "K10": "c-note-table",            # 其他收益附注
    "K10-1": "d-form-table",          # 其他收益审定表
    "K10-2": "audit-sheet",           # 其他收益明细表
    "K10-3": "audit-sheet",           # 政府补助验证
    "K10-4": "d-form-table",          # 调整分录
    # K11 资产减值损失
    "K11": "c-note-table",            # 资产减值损失附注
    "K11-1": "d-form-table",          # 资产减值损失审定表
    "K11-2": "audit-sheet",           # 资产减值损失明细表
    "K11-3": "audit-sheet",           # 减值测试汇总
    "K11-4": "d-form-table",          # 调整分录
    # K12 营业外收入
    "K12": "c-note-table",            # 营业外收入附注
    "K12-1": "d-form-table",          # 营业外收入审定表
    "K12-2": "audit-sheet",           # 营业外收入明细表
    "K12-3": "audit-sheet",           # 营业外收入检查
    "K12-4": "d-form-table",          # 调整分录
    # K13 营业外支出
    "K13": "c-note-table",            # 营业外支出附注
    "K13-1": "d-form-table",          # 营业外支出审定表
    "K13-2": "audit-sheet",           # 营业外支出明细表
    "K13-3": "audit-sheet",           # 营业外支出检查
    "K13-4": "d-form-table",          # 调整分录
    # ─── L 类 — 筹资循环实质性程序 ────────────────────────────────────────────
    # 程序表
    "L0A": "a-program-console",       # 筹资循环函证程序表
    "L1A": "a-program-console",       # 短期借款程序表
    "L2A": "a-program-console",       # 应付利息程序表
    "L3A": "a-program-console",       # 长期借款程序表
    "L4A": "a-program-console",       # 应付债券程序表
    "L5A": "a-program-console",       # 长期应付款程序表
    "L6A": "a-program-console",       # 专项应付款程序表
    "L7A": "a-program-console",       # 其他非流动负债程序表
    "L8A": "a-program-console",       # 财务费用程序表
    # L0 函证
    "L0": "confirmation-hub",         # 筹资循环函证 → ConfirmationHub 模块
    "L0-1": "d-form-table",           # 函证结果汇总
    "L0-2": "d-form-table",           # 核实被函证单位
    "L0-3": "d-form-table",           # 跟函控制
    "L0-4": "d-form-table",           # 差异调节
    "L0-5": "d-form-table",           # 替代程序
    # L1 短期借款
    "L1": "c-note-table",             # 短期借款附注
    "L1-1": "d-form-table",           # 短期借款审定表
    "L1-2": "audit-sheet",            # 短期借款明细表
    "L1-3": "audit-sheet",            # 短期借款利息测算（本金×利率×天数/360）
    "L1-4": "audit-sheet",            # 还款计划
    "L1-5": "audit-sheet",            # 短期借款检查
    "L1-6": "d-form-table",           # 调整分录
    # L2 应付利息
    "L2": "c-note-table",             # 应付利息附注
    "L2-1": "d-form-table",           # 应付利息审定表
    "L2-2": "audit-sheet",            # 应付利息明细表
    "L2-3": "audit-sheet",            # 利息计提测算
    "L2-4": "d-form-table",           # 调整分录
    # L3 长期借款
    "L3": "c-note-table",             # 长期借款附注
    "L3-1": "d-form-table",           # 长期借款审定表
    "L3-2": "audit-sheet",            # 长期借款明细表
    "L3-3": "audit-sheet",            # 长期借款利息测算（本金×利率×天数/360）
    "L3-4": "d-form-table",           # 一年内到期重分类（结构化→d-form-table）
    "L3-5": "audit-sheet",            # 长期借款检查
    "L3-6": "d-form-table",           # 调整分录
    # L4 应付债券（实际利率法）
    "L4": "c-note-table",             # 应付债券附注
    "L4-1": "d-form-table",           # 应付债券审定表
    "L4-2": "audit-sheet",            # 应付债券明细表
    "L4-3": "audit-sheet",            # 实际利率计算（IRR公式）
    "L4-4": "audit-sheet",            # 摊余成本摊销表（期初×实际利率-票面利息=摊销）
    "L4-5": "audit-sheet",            # 利息费用测算
    "L4-6": "audit-sheet",            # 折价/溢价分析
    "L4-7": "audit-sheet",            # 应付债券检查
    "L4-8": "d-form-table",           # 调整分录
    # L5 长期应付款
    "L5": "c-note-table",             # 长期应付款附注
    "L5-1": "d-form-table",           # 长期应付款审定表
    "L5-2": "audit-sheet",            # 长期应付款明细表
    "L5-3": "audit-sheet",            # 长期应付款现值测算
    "L5-4": "d-form-table",           # 调整分录
    # L6 专项应付款
    "L6": "c-note-table",             # 专项应付款附注
    "L6-1": "d-form-table",           # 专项应付款审定表
    "L6-2": "audit-sheet",            # 专项应付款明细表
    "L6-3": "audit-sheet",            # 使用情况检查
    "L6-4": "d-form-table",           # 调整分录
    # L7 其他非流动负债
    "L7": "c-note-table",             # 其他非流动负债附注
    "L7-1": "d-form-table",           # 其他非流动负债审定表
    "L7-2": "audit-sheet",            # 其他非流动负债明细表
    "L7-3": "audit-sheet",            # 其他非流动负债检查
    "L7-4": "d-form-table",           # 调整分录
    # L8 财务费用（损益类取发生额）
    "L8": "c-note-table",             # 财务费用附注
    "L8-1": "d-form-table",           # 财务费用审定表
    "L8-2": "audit-sheet",            # 财务费用明细表
    "L8-3": "audit-sheet",            # 利息费用测算（L1/L3/L4利息汇总）
    "L8-4": "audit-sheet",            # 财务费用分析
    "L8-5": "audit-sheet",            # 汇兑损益测算（汇率差×外币余额）
    "L8-6": "d-form-table",           # 调整分录
    # ─── M 类 — 股东权益循环实质性程序 ────────────────────────────────────────
    # 程序表
    "M1A": "a-program-console",       # 应付股利程序表
    "M2A": "a-program-console",       # 实收资本程序表
    "M3A": "a-program-console",       # 库存股程序表
    "M4A": "a-program-console",       # 资本公积程序表
    "M5A": "a-program-console",       # 盈余公积程序表
    "M6A": "a-program-console",       # 未分配利润程序表
    "M7A": "a-program-console",       # 专项储备程序表
    "M8A": "a-program-console",       # 一般风险准备程序表
    "M9A": "a-program-console",       # 其他综合收益程序表
    "M10A": "a-program-console",      # 其他权益工具程序表
    # M1 应付股利
    "M1": "c-note-table",             # 应付股利附注
    "M1-1": "d-form-table",           # 应付股利审定表
    "M1-2": "audit-sheet",            # 应付股利明细表
    "M1-3": "d-form-table",           # 分配决议核实
    "M1-4": "d-form-table",           # 应付股利调整分录
    # M2 实收资本（股本）
    "M2": "c-note-table",             # 实收资本附注
    "M2-1": "d-form-table",           # 实收资本审定表（按股东分行）
    "M2-2": "audit-sheet",            # 实收资本明细表
    "M2-3": "d-form-table",           # 验资报告核实
    "M2-4": "d-form-table",           # 工商变更核实
    "M2-5": "d-form-table",           # 股权结构表
    "M2-6": "d-form-table",           # 实收资本调整分录
    # M3 库存股
    "M3": "c-note-table",             # 库存股附注
    "M3-1": "d-form-table",           # 库存股审定表
    "M3-2": "audit-sheet",            # 库存股明细表
    "M3-3": "d-form-table",           # 回购注销检查
    "M3-4": "d-form-table",           # 库存股调整分录
    # M4 资本公积
    "M4": "c-note-table",             # 资本公积附注
    "M4-1": "d-form-table",           # 资本公积审定表
    "M4-2": "audit-sheet",            # 资本公积明细表
    "M4-3": "audit-sheet",            # 资本公积变动分析
    "M4-4": "d-form-table",           # 资本公积来源检查
    "M4-5": "d-form-table",           # 股份支付联动
    "M4-6": "d-form-table",           # 资本公积调整分录
    # M5 盈余公积
    "M5": "c-note-table",             # 盈余公积附注
    "M5-1": "d-form-table",           # 盈余公积审定表
    "M5-2": "audit-sheet",            # 盈余公积明细表
    "M5-3": "d-form-table",           # 法定/任意提取验证
    "M5-4": "d-form-table",           # 盈余公积调整分录
    # M6 未分配利润
    "M6": "c-note-table",             # 未分配利润附注
    "M6-1": "d-form-table",           # 未分配利润审定表（公式型）
    "M6-2": "audit-sheet",            # 未分配利润勾稽表（期初+净利润-提取-分配=期末）
    "M6-3": "d-form-table",           # 利润分配方案
    "M6-4": "d-form-table",           # 以前年度调整
    "M6-5": "audit-sheet",            # 损益联动验证（D~N 净利润核对）
    "M6-6": "d-form-table",           # 未分配利润调整分录
    # M7 专项储备
    "M7": "c-note-table",             # 专项储备附注
    "M7-1": "d-form-table",           # 专项储备审定表
    "M7-2": "audit-sheet",            # 专项储备明细表
    "M7-3": "d-form-table",           # 安全生产费用检查
    "M7-4": "d-form-table",           # 专项储备调整分录
    # M8 一般风险准备（金融企业）
    "M8": "c-note-table",             # 一般风险准备附注
    "M8-1": "d-form-table",           # 一般风险准备审定表
    "M8-2": "audit-sheet",            # 一般风险准备明细表
    "M8-3": "d-form-table",           # 提取比例验证
    "M8-4": "d-form-table",           # 一般风险准备调整分录
    # M9 其他综合收益
    "M9": "c-note-table",             # 其他综合收益附注
    "M9-1": "d-form-table",           # OCI审定表
    "M9-2": "audit-sheet",            # OCI明细表
    "M9-3": "d-form-table",           # OCI分类检查（不可重分类 vs 可重分类）
    "M9-4": "audit-sheet",            # OCI来源追溯
    "M9-5": "audit-sheet",            # 转损益检查
    "M9-6": "d-form-table",           # OCI调整分录
    # M10 其他权益工具
    "M10": "c-note-table",            # 其他权益工具附注
    "M10-1": "d-form-table",          # 其他权益工具审定表
    "M10-2": "audit-sheet",           # 其他权益工具明细表
    "M10-3": "d-form-table",          # 权益/负债分类检查（永续债条件）
    "M10-4": "d-form-table",          # 其他权益工具调整分录
    # ─── N 类 — 税费循环实质性程序 ────────────────────────────────────────────
    # 程序表
    "N1A": "a-program-console",       # 递延所得税资产程序表
    "N2A": "a-program-console",       # 应交税费程序表
    "N3A": "a-program-console",       # 递延所得税负债程序表
    "N4A": "a-program-console",       # 税金及附加程序表
    "N5A": "a-program-console",       # 所得税费用程序表
    # N1 递延所得税资产
    "N1": "c-note-table",             # 递延所得税资产附注
    "N1-1": "d-form-table",           # 递延所得税资产审定表
    "N1-2": "audit-sheet",            # 递延所得税资产明细表
    "N1-3": "audit-sheet",            # 暂时性差异计算表（可抵扣）
    "N1-4": "d-form-table",           # 可抵扣确认条件检查
    "N1-5": "audit-sheet",            # 递延所得税资产分析
    "N1-6": "d-form-table",           # 递延所得税资产调整分录
    # N2 应交税费
    "N2": "c-note-table",             # 应交税费附注
    "N2-1": "d-form-table",           # 应交税费审定表（按税种分行）
    "N2-2": "audit-sheet",            # 应交税费明细表
    "N2-3": "audit-sheet",            # 增值税核对表（销项-进项-转出=应缴）
    "N2-4": "d-form-table",           # 税费完整性检查
    "N2-5": "audit-sheet",            # 应交税费分析
    "N2-6": "d-form-table",           # 应交税费调整分录
    # N3 递延所得税负债
    "N3": "c-note-table",             # 递延所得税负债附注
    "N3-1": "d-form-table",           # 递延所得税负债审定表
    "N3-2": "audit-sheet",            # 递延所得税负债明细表
    "N3-3": "audit-sheet",            # 暂时性差异计算表（应纳税）
    "N3-4": "d-form-table",           # 应纳税差异来源检查
    "N3-5": "audit-sheet",            # 递延所得税负债分析
    "N3-6": "d-form-table",           # 递延所得税负债调整分录
    # N4 税金及附加（损益类取发生额）
    "N4": "c-note-table",             # 税金及附加附注
    "N4-1": "d-form-table",           # 税金及附加审定表
    "N4-2": "audit-sheet",            # 税金及附加明细表
    "N4-3": "audit-sheet",            # 税金及附加测算验证
    "N4-4": "d-form-table",           # 税金及附加调整分录
    # N5 所得税费用（核心计算）
    "N5": "c-note-table",             # 所得税费用附注
    "N5-1": "d-form-table",           # 所得税费用审定表（当期+递延=合计）
    "N5-2": "audit-sheet",            # 所得税费用明细表
    "N5-3": "audit-sheet",            # 所得税计算表（利润±调整=应纳税所得×税率）
    "N5-4": "audit-sheet",            # 纳税调增调减明细
    "N5-5": "audit-sheet",            # 有效税率分析（实际vs法定+差异解释）
    "N5-6": "d-form-table",           # 递延所得税联动（读取N1/N3变动）
    "N5-7": "audit-sheet",            # 研发加计扣除（联动I6-7）
    "N5-8": "d-form-table",           # 所得税费用调整分录
    # ─── S 类 — 专项循环（特殊审计考虑+IPO核查） ──────────────────────────────
    # S1~S17 特殊审计考虑事项（程序表式 7 个）
    "S1": "a-program-console",        # 违反法规行为的考虑
    "S2": "a-program-console",        # 首次接受委托期初余额
    "S3": "a-program-console",        # 会计政策变更/前期差错/估计变更
    # S4~S6 检查表式
    "S4": "d-form-table",             # 非货币性资产交换
    "S5": "d-form-table",             # 债务重组
    "S6": "d-form-table",             # 大股东资金占用/违规担保
    # S8~S11
    "S8": "a-program-console",        # 租赁
    "S9": "d-form-table",             # 电子商务考虑
    "S10": "a-program-console",       # 环境事项考虑
    "S11": "a-program-console",       # 利用服务机构
    # S12 利用专家
    "S12": "d-form-table",            # 利用专家工作
    "S12A": "word-template",          # 评估专家报告（docx）
    # S13~S17
    "S13": "a-program-console",       # 利用管理层专家
    "S14": "d-form-table",            # 会计估计和相关披露
    "S15": "audit-sheet",             # 每股收益和净资产收益率
    "S16": "d-form-table",            # 套期活动
    "S17": "audit-sheet",             # 非经常性损益
    # S20~S21 新准则
    "S20": "d-form-table",            # 营业收入扣除情况核查
    "S21": "d-form-table",            # 数据资产
    # S32 IPO 专项核查（13 条）
    "S32-1": "d-form-table",          # IPO核查-自我交易
    "S32-2": "d-form-table",          # IPO核查-串通
    "S32-3": "d-form-table",          # IPO核查-关联方代付
    "S32-4": "d-form-table",          # IPO核查-利益输送
    "S32-5": "d-form-table",          # IPO核查-体外资金
    "S32-6": "d-form-table",          # IPO核查-互联网造假
    "S32-7": "d-form-table",          # IPO核查-资本化
    "S32-8": "d-form-table",          # IPO核查-压缩薪金
    "S32-9": "d-form-table",          # IPO核查-延迟费用
    "S32-10": "d-form-table",         # IPO核查-资产减值
    "S32-11": "d-form-table",         # IPO核查-延迟转固
    "S32-12": "d-form-table",         # IPO核查-其他粉饰
    "S32-13": "d-form-table",         # IPO核查-期后下滑
    # S33 综合核查（10 条）
    "S33-1": "d-form-table",          # 综合核查-内控制度
    "S33-2": "d-form-table",          # 综合核查-财务非财务印证
    "S33-3": "d-form-table",          # 综合核查-盈利异常
    "S33-4": "d-form-table",          # 综合核查-关联方
    "S33-5": "d-form-table",          # 综合核查-收入毛利
    "S33-6": "d-form-table",          # 综合核查-客户供应商
    "S33-7": "d-form-table",          # 综合核查-存货资产
    "S33-8": "d-form-table",          # 综合核查-现金收付
    "S33-9": "d-form-table",          # 综合核查-财务异常
    "S33-REV": "word-template",       # 综合核查-程序修订说明（docx）
    # S34 证监会核查事项（43 条）
    "S34-0": "d-form-table",          # 证监会核查事项清单
    "S34-1": "d-form-table",          # 证监会-涉秘豁免
    "S34-1-1": "word-template",       # 信息披露豁免专项核查意见（docx）
    "S34-2": "d-form-table",          # 证监会-期权
    "S34-3": "d-form-table",          # 证监会-股份支付
    "S34-4": "d-form-table",          # 证监会-关联交易
    "S34-5": "d-form-table",          # 证监会-应收减值
    "S34-6": "d-form-table",          # 证监会-固定资产
    "S34-7": "d-form-table",          # 证监会-税收优惠
    "S34-8": "d-form-table",          # 证监会-合并无形
    "S34-9": "d-form-table",          # 证监会-共同投资
    "S34-10": "d-form-table",         # 证监会-财务性投资
    "S34-11": "d-form-table",         # 证监会-业务重组
    "S34-12": "d-form-table",         # 证监会-经营下滑
    "S34-13": "d-form-table",         # 证监会-持续经营
    "S34-14": "d-form-table",         # 证监会-财务内控
    "S34-15": "d-form-table",         # 证监会-现金交易
    "S34-16": "d-form-table",         # 证监会-第三方回款
    "S34-17": "d-form-table",         # 证监会-会计政策
    "S34-18": "d-form-table",         # 证监会-第三方数据
    "S34-19": "d-form-table",         # 证监会-经销商
    "S34-20": "d-form-table",         # 证监会-劳务外包
    "S34-21": "d-form-table",         # 证监会-委外加工
    "S34-22": "d-form-table",         # 证监会-股权集中
    "S34-23": "d-form-table",         # 证监会-互联网系统
    "S34-24": "d-form-table",         # 证监会-信息系统
    "S34-25": "d-form-table",         # 证监会-资金流水
    "S34-26": "d-form-table",         # 证监会-未盈利
    "S34-27": "d-form-table",         # 证监会-研发认定
    "S34-28": "d-form-table",         # 证监会-研发资本化
    "S34-29": "d-form-table",         # 证监会-政府补助
    "S34-30": "d-form-table",         # 证监会-对赌
    "S34-31": "d-form-table",         # 证监会-存货
    "S34-32": "d-form-table",         # 证监会-期间费用
    "S34-33": "d-form-table",         # 证监会-商誉减值
    "S34-34": "d-form-table",         # 证监会-涉农
    "S34-35": "d-form-table",         # 证监会-收入
    "S34-36": "d-form-table",         # 证监会-投资收益
    "S34-37": "d-form-table",         # 证监会-现金流异常
    "S34-38": "d-form-table",         # 证监会-估值调整
    "S34-39": "d-form-table",         # 证监会-应收票据融资
    "S34-40": "d-form-table",         # 证监会-在建工程
    "S34-41": "d-form-table",         # 证监会-客户供应商
    # S35 再融资核查（5 条）
    "S35-1": "d-form-table",          # 再融资核查-关联交易
    "S35-2": "d-form-table",          # 再融资核查-财务性投资
    "S35-3": "d-form-table",          # 再融资核查-现金分红
    "S35-4": "d-form-table",          # 再融资核查-商誉减值
    "S35-5": "d-form-table",          # 再融资核查-募集资金收购
}

# D 类子路由映射（基于 class_code 具体值）
_D_SUB_ROUTING: dict[str, str] = {
    "D-函证": "d-form-confirmation",
    "D-盘点": "d-form-confirmation",
    "D-访谈": "d-form-confirmation",
    "D-询证": "d-form-confirmation",
    "D-政策检查": "d-form-paragraph",
    "D-业务模式": "d-form-qa",
    "D-复核记录": "d-form-review",
    "D-复核": "d-form-review",
}

# D 类默认 componentType（表格型检查表）
_D_DEFAULT = "d-form-table"

# F 类子路由映射（精确匹配优先于 _CLASS_TO_COMPONENT["F-"] 前缀 fallback）
# F-审定表 / F-明细表 → audit-sheet（可编辑表格组件，列结构从模板动态解析）；
# 其余 F-（F-分析表/F-汇总表 等）仍 fallback 到 univer
_F_SUB_ROUTING: dict[str, str] = {
    "F-审定表": "audit-sheet",
    "F-明细表": "audit-sheet",
}

# ─── sheet 名级专用路由（优先于 class_code 派生） ────────────────────────────
# 坏账准备明细表（D2-3 等）的 class_code 是共享的 "F-明细表"，无法靠 class_code
# 区分。但坏账准备明细表是两层嵌套结构专用底稿（计提类别父行 → 明细子行 → 合计），
# 必须路由到专用组件 bad-debt-sheet（GtBadDebtSheet）。故按 sheet 名前缀匹配，
# 优先于 class_code 派生。
def _match_sheet_name_override(sheet_name: str | None) -> str | None:
    """按 sheet 名匹配专用 componentType（None 表示无专用路由，走 class_code 派生）。"""
    if not sheet_name:
        return None
    # 坏账准备明细表（各循环的坏账准备嵌套明细表，如 D2-3/D1-4/G2-3 等）
    if sheet_name.startswith("坏账准备明细表"):
        return "bad-debt-sheet"
    return None


@dataclass
class ClassificationResult:
    """归类结果"""

    wp_code: str
    sheet_name: str
    class_code: str | None
    class_: str | None
    scope: str
    is_real_workpaper: bool
    delegated_module: str | None
    render_schema_path: str | None
    template_version_id: UUID | None
    # 项目级覆盖来源标记
    has_override: bool = False


class WpClassificationService:
    """底稿 sheet 归类服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_classification(
        self,
        wp_code: str,
        project_id: UUID,
        template_version_id: UUID | None = None,
    ) -> list[ClassificationResult]:
        """获取底稿所有 sheet 的归类信息（含项目级覆盖合并）

        流程：
        1. 查 workpaper_sheet_classification 获取模板级归类
        2. 若精确 wp_code 无记录，按以下顺序回退：
           a. parent code（strip trailing -N，如 D1-1 → D1）
           b. base code（仅保留首字母+首数字，如 H1-12 → H1）
        3. 查 project_workpaper_sheet_override 获取项目级覆盖
        4. 合并：override 字段优先覆盖 base classification
        """
        # 候选 wp_code 列表（精确 → 父级 → 基础）
        candidates = self._build_wp_code_candidates(wp_code)

        # ─── Step 1: 按候选顺序查模板级归类 ──────────────────────────────
        base_rows = []
        matched_code = None
        for candidate in candidates:
            base_query = sa.select(WorkpaperSheetClassification).where(
                WorkpaperSheetClassification.wp_code == candidate,
            )
            if template_version_id is not None:
                base_query = base_query.where(
                    WorkpaperSheetClassification.template_version_id == template_version_id
                )
            rows = (await self.db.execute(base_query)).scalars().all()
            if rows:
                base_rows = rows
                matched_code = candidate
                if candidate != wp_code:
                    logger.info(
                        "[WP_CLASSIFICATION] wp_code=%s fallback → matched parent=%s",
                        wp_code, candidate,
                    )
                break

        if not base_rows:
            raise ClassificationNotFoundError(
                f"No classification found for wp_code='{wp_code}' "
                f"(template_version_id={template_version_id}). "
                "Every sheet must have a classification — Univer fallback is prohibited. "
                "Run: python backend/scripts/seed_workpaper_sheet_classification.py"
            )

        # ─── Step 2: 查项目级覆盖 ────────────────────────────────────────
        override_query = sa.select(ProjectWorkpaperSheetOverride).where(
            ProjectWorkpaperSheetOverride.project_id == project_id,
            ProjectWorkpaperSheetOverride.wp_code == wp_code,
        )
        override_rows = (await self.db.execute(override_query)).scalars().all()

        # 按 sheet_name 索引覆盖记录
        overrides_by_sheet: dict[str, ProjectWorkpaperSheetOverride] = {
            o.sheet_name: o for o in override_rows
        }

        # ─── Step 3: 合并 ────────────────────────────────────────────────
        results: list[ClassificationResult] = []
        for base in base_rows:
            override = overrides_by_sheet.get(base.sheet_name)
            has_override = override is not None

            # 覆盖字段：class_override 覆盖 class_code/class_
            effective_class_code = base.class_code
            effective_class = base.class_
            effective_scope = base.scope

            if override:
                if override.class_override:
                    effective_class_code = override.class_override
                    effective_class = override.class_override
                if override.scope_override:
                    effective_scope = override.scope_override

            results.append(
                ClassificationResult(
                    wp_code=base.wp_code,
                    sheet_name=base.sheet_name,
                    class_code=effective_class_code,
                    class_=effective_class,
                    scope=effective_scope,
                    is_real_workpaper=base.is_real_workpaper,
                    delegated_module=base.delegated_module,
                    render_schema_path=base.render_schema_path,
                    template_version_id=base.template_version_id,
                    has_override=has_override,
                )
            )

        return results

    @staticmethod
    def _build_wp_code_candidates(wp_code: str) -> list[str]:
        """构建 wp_code 查询候选列表（精确 → 父级 → 基础）

        示例：
        - "D2-3"   → ["D2-3"]            （精确匹配，模板里就有 D2-3 sheets）
        - "D2"     → ["D2", "D2-1"]      （umbrella code，回退到 D2-1 模板）
        - "D1-1"   → ["D1-1", "D1"]      （回退到 D1 父级）
        - "H1-12"  → ["H1-12", "H1"]     （回退到 H1 父级）
        - "B22A-4" → ["B22A-4", "B22A", "B22"]  （多级回退）
        """
        import re

        candidates = [wp_code]

        # umbrella code（无 dash 的纯字母+数字，如 D2/D4/F2/H1）
        # → 加上 -1 作为 fallback（致同模板里审定表通常是 -1 编号）
        if re.match(r"^[A-Z]\d+$", wp_code):
            candidates.append(f"{wp_code}-1")

        # 逐级 strip trailing "-N"
        cur = wp_code
        while "-" in cur:
            cur = cur.rsplit("-", 1)[0]
            if cur not in candidates:
                candidates.append(cur)

        return candidates

    async def get_sheet_classification(
        self,
        wp_code: str,
        sheet_name: str,
        project_id: UUID,
        template_version_id: UUID | None = None,
    ) -> ClassificationResult:
        """获取单个 sheet 的归类信息（含项目级覆盖合并）"""
        # 查模板级归类
        base_query = sa.select(WorkpaperSheetClassification).where(
            WorkpaperSheetClassification.wp_code == wp_code,
            WorkpaperSheetClassification.sheet_name == sheet_name,
        )
        if template_version_id is not None:
            base_query = base_query.where(
                WorkpaperSheetClassification.template_version_id == template_version_id
            )

        base = (await self.db.execute(base_query)).scalars().first()

        if not base:
            raise ClassificationNotFoundError(
                f"No classification found for wp_code='{wp_code}', "
                f"sheet_name='{sheet_name}'. "
                "Every sheet must have a classification — Univer fallback is prohibited."
            )

        # 查项目级覆盖
        override_query = sa.select(ProjectWorkpaperSheetOverride).where(
            ProjectWorkpaperSheetOverride.project_id == project_id,
            ProjectWorkpaperSheetOverride.wp_code == wp_code,
            ProjectWorkpaperSheetOverride.sheet_name == sheet_name,
        )
        override = (await self.db.execute(override_query)).scalars().first()

        has_override = override is not None
        effective_class_code = base.class_code
        effective_class = base.class_
        effective_scope = base.scope

        if override:
            if override.class_override:
                effective_class_code = override.class_override
                effective_class = override.class_override
            if override.scope_override:
                effective_scope = override.scope_override

        return ClassificationResult(
            wp_code=base.wp_code,
            sheet_name=base.sheet_name,
            class_code=effective_class_code,
            class_=effective_class,
            scope=effective_scope,
            is_real_workpaper=base.is_real_workpaper,
            delegated_module=base.delegated_module,
            render_schema_path=base.render_schema_path,
            template_version_id=base.template_version_id,
            has_override=has_override,
        )


def derive_component_type(classification: ClassificationResult) -> str:
    """将归类结果映射到 componentType 白名单值

    映射规则（design §7.2 + task 1.6）：
    - A- (程序表) → 'a-program-console'
    - B- (底稿目录) → 'b-index'
    - C- (附注披露) → 'c-note-table'
    - D- (检查表) → 需 sub-routing:
        - D-函证/D-盘点/D-访谈/D-询证 → 'd-form-confirmation'
        - D-政策检查 → 'd-form-paragraph'
        - D-业务模式 → 'd-form-qa'
        - D-复核记录/D-复核 → 'd-form-review'
        - 其他 D- → 'd-form-table' (默认)
    - E- (控制测试) → 'e-control-test'
    - F- (数据表) → 需 sub-routing:
        - F-审定表 → 'audit-sheet'（可编辑审定表组件）
        - 其他 F- → 'univer' (默认)
    - G- (测算表) → 'univer'
    - H- (辅助说明) → 'h-static-doc'
    - I- (占位) → 'skip'

    sheet 名级专用路由（优先于 class_code 派生）：
    - 坏账准备明细表* → 'bad-debt-sheet'（两层嵌套结构专用组件）

    CRITICAL: 禁止 Univer 兜底！无归类时抛异常而非返回 'univer'。
    """
    class_code = classification.class_code

    if class_code and class_code.upper().startswith("CUSTOM"):
        # GT_Custom sheets are auxiliary/internal — always skip
        if classification.sheet_name and "GT_Custom" in classification.sheet_name:
            return "skip"
        return "custom"

    # sheet 名级专用路由优先（坏账准备明细表嵌套结构 → bad-debt-sheet）
    sheet_override = _match_sheet_name_override(classification.sheet_name)
    if sheet_override:
        return sheet_override

    # wp_code 级专用路由覆盖（A5-1→cf-verification, A2-1→report-analysis）
    wp_code_override = _WP_CODE_OVERRIDE.get(classification.wp_code)
    if wp_code_override:
        return wp_code_override

    if not class_code:
        raise ClassificationNotFoundError(
            f"Sheet '{classification.sheet_name}' (wp_code='{classification.wp_code}') "
            "has no class_code. Cannot derive componentType — "
            "Univer fallback is prohibited (Requirement 3.9)."
        )

    # 检查 D 类 sub-routing（精确匹配优先）
    if class_code.startswith("D-"):
        component_type = _D_SUB_ROUTING.get(class_code, _D_DEFAULT)
        return component_type

    # 检查 F 类 sub-routing（精确匹配优先于前缀 fallback）
    # F- 是 _CLASS_TO_COMPONENT 的前缀键（→ univer），若直接走下方前缀循环
    # 会把所有 F- 一律映射到 univer，因此必须在前缀匹配前先查 _F_SUB_ROUTING。
    if class_code.startswith("F-"):
        component_type = _F_SUB_ROUTING.get(class_code)
        if component_type:
            return component_type
        # fallback: 其余 F-（F-明细表/F-分析表/F-汇总表 等）仍返回 univer
        return "univer"

    # 其他类按前缀匹配
    for prefix, component_type in _CLASS_TO_COMPONENT.items():
        if class_code.startswith(prefix):
            return component_type

    # 无法匹配 → 抛异常（禁止 Univer 兜底）
    raise ClassificationNotFoundError(
        f"Unknown class_code='{class_code}' for sheet '{classification.sheet_name}' "
        f"(wp_code='{classification.wp_code}'). "
        "Cannot derive componentType — Univer fallback is prohibited (Requirement 3.9). "
        "Please add classification rule for this sheet."
    )


class ClassificationNotFoundError(Exception):
    """归类未找到异常

    当 sheet 没有归类记录或 class_code 无法映射到 componentType 时抛出。
    前端应显示 'pending' 错误状态，禁止降级到 Univer。
    """

    pass
