"""致同底稿编码体系 ORM 模型 + 种子数据

对应 Alembic 迁移脚本 009_gt_wp_coding.py
"""

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GTWpType(str, enum.Enum):
    """底稿类型"""
    preliminary = "preliminary"
    risk_assessment = "risk_assessment"
    control_test = "control_test"
    substantive = "substantive"
    completion = "completion"
    specific = "specific"
    general = "general"
    permanent = "permanent"


class GTWpCoding(Base):
    """致同底稿编码"""

    __tablename__ = "gt_wp_coding"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code_prefix: Mapped[str] = mapped_column(String, nullable=False)
    code_range: Mapped[str] = mapped_column(String, nullable=False)
    cycle_name: Mapped[str] = mapped_column(String, nullable=False)
    wp_type: Mapped[GTWpType] = mapped_column(
        sa.Enum(GTWpType, name="gt_wp_type", create_type=False),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_cycle: Mapped[str | None] = mapped_column(String, nullable=True)
    sort_order: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        server_default=text("true"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_gt_wp_coding_prefix", "code_prefix"),
        Index("idx_gt_wp_coding_type", "wp_type"),
        Index("idx_gt_wp_coding_active", "is_active"),
    )


# ---------------------------------------------------------------------------
# 种子数据：致同底稿编码体系（基于附录G.1）
# ---------------------------------------------------------------------------

GT_CODING_SEED_DATA: list[dict] = [
    # ── B类：初步业务活动 ──
    {"code_prefix": "B", "code_range": "B1-B5", "cycle_name": "初步业务活动",
     "wp_type": "preliminary", "description": "业务承接/前任沟通/独立性/约定书", "sort_order": 10},
    # ── B类：风险评估 ──
    {"code_prefix": "B", "code_range": "B10-B60", "cycle_name": "风险评估",
     "wp_type": "risk_assessment", "description": "了解被审计单位/内控/集团审计/项目组讨论/风险评估结果/总体审计策略", "sort_order": 20},
    # ── B类：穿行测试（各循环） ──
    {"code_prefix": "B", "code_range": "B23-1", "cycle_name": "销售循环穿行测试",
     "wp_type": "risk_assessment", "description": "销售循环业务层面控制评估", "parent_cycle": "D", "sort_order": 31},
    {"code_prefix": "B", "code_range": "B23-2", "cycle_name": "货币资金穿行测试",
     "wp_type": "risk_assessment", "description": "货币资金业务层面控制评估", "parent_cycle": "E", "sort_order": 32},
    {"code_prefix": "B", "code_range": "B23-3", "cycle_name": "存货循环穿行测试",
     "wp_type": "risk_assessment", "description": "存货业务层面控制评估", "parent_cycle": "F", "sort_order": 33},
    {"code_prefix": "B", "code_range": "B23-4", "cycle_name": "投资循环穿行测试",
     "wp_type": "risk_assessment", "description": "投资业务层面控制评估", "parent_cycle": "G", "sort_order": 34},
    {"code_prefix": "B", "code_range": "B23-5", "cycle_name": "固定资产穿行测试",
     "wp_type": "risk_assessment", "description": "固定资产业务层面控制评估", "parent_cycle": "H", "sort_order": 35},
    {"code_prefix": "B", "code_range": "B23-6", "cycle_name": "在建工程穿行测试",
     "wp_type": "risk_assessment", "description": "在建工程业务层面控制评估", "parent_cycle": "H", "sort_order": 36},
    {"code_prefix": "B", "code_range": "B23-7", "cycle_name": "无形资产穿行测试",
     "wp_type": "risk_assessment", "description": "无形资产业务层面控制评估", "parent_cycle": "I", "sort_order": 37},
    {"code_prefix": "B", "code_range": "B23-8", "cycle_name": "研发穿行测试",
     "wp_type": "risk_assessment", "description": "研发业务层面控制评估", "parent_cycle": "I", "sort_order": 38},
    {"code_prefix": "B", "code_range": "B23-9", "cycle_name": "职工薪酬穿行测试",
     "wp_type": "risk_assessment", "description": "职工薪酬业务层面控制评估", "parent_cycle": "J", "sort_order": 39},
    {"code_prefix": "B", "code_range": "B23-10", "cycle_name": "管理循环穿行测试",
     "wp_type": "risk_assessment", "description": "管理费用业务层面控制评估", "parent_cycle": "K", "sort_order": 40},
    {"code_prefix": "B", "code_range": "B23-11", "cycle_name": "税金循环穿行测试",
     "wp_type": "risk_assessment", "description": "税金业务层面控制评估", "parent_cycle": "N", "sort_order": 41},
    {"code_prefix": "B", "code_range": "B23-12", "cycle_name": "债务循环穿行测试",
     "wp_type": "risk_assessment", "description": "债务业务层面控制评估", "parent_cycle": "L", "sort_order": 42},
    {"code_prefix": "B", "code_range": "B23-13", "cycle_name": "租赁循环穿行测试",
     "wp_type": "risk_assessment", "description": "租赁业务层面控制评估", "parent_cycle": "H", "sort_order": 43},
    {"code_prefix": "B", "code_range": "B23-14", "cycle_name": "关联方穿行测试",
     "wp_type": "risk_assessment", "description": "关联方业务层面控制评估", "parent_cycle": "Q", "sort_order": 44},
    # ── C类：控制测试 ──
    {"code_prefix": "C", "code_range": "C1", "cycle_name": "企业层面控制测试",
     "wp_type": "control_test", "description": "企业层面控制测试", "sort_order": 50},
    {"code_prefix": "C", "code_range": "C2", "cycle_name": "销售循环控制测试",
     "wp_type": "control_test", "description": "销售循环控制测试", "parent_cycle": "D", "sort_order": 51},
    {"code_prefix": "C", "code_range": "C3", "cycle_name": "货币资金控制测试",
     "wp_type": "control_test", "description": "货币资金控制测试", "parent_cycle": "E", "sort_order": 52},
    {"code_prefix": "C", "code_range": "C4", "cycle_name": "存货循环控制测试",
     "wp_type": "control_test", "description": "存货循环控制测试", "parent_cycle": "F", "sort_order": 53},
    {"code_prefix": "C", "code_range": "C5", "cycle_name": "投资循环控制测试",
     "wp_type": "control_test", "description": "投资循环控制测试", "parent_cycle": "G", "sort_order": 54},
    {"code_prefix": "C", "code_range": "C6", "cycle_name": "固定资产控制测试",
     "wp_type": "control_test", "description": "固定资产控制测试", "parent_cycle": "H", "sort_order": 55},
    {"code_prefix": "C", "code_range": "C7", "cycle_name": "在建工程控制测试",
     "wp_type": "control_test", "description": "在建工程控制测试", "parent_cycle": "H", "sort_order": 56},
    {"code_prefix": "C", "code_range": "C8", "cycle_name": "无形资产控制测试",
     "wp_type": "control_test", "description": "无形资产控制测试", "parent_cycle": "I", "sort_order": 57},
    {"code_prefix": "C", "code_range": "C9", "cycle_name": "研发控制测试",
     "wp_type": "control_test", "description": "研发控制测试", "parent_cycle": "I", "sort_order": 58},
    {"code_prefix": "C", "code_range": "C10", "cycle_name": "职工薪酬控制测试",
     "wp_type": "control_test", "description": "职工薪酬控制测试", "parent_cycle": "J", "sort_order": 59},
    {"code_prefix": "C", "code_range": "C11", "cycle_name": "管理循环控制测试",
     "wp_type": "control_test", "description": "管理费用控制测试", "parent_cycle": "K", "sort_order": 60},
    {"code_prefix": "C", "code_range": "C12", "cycle_name": "税金循环控制测试",
     "wp_type": "control_test", "description": "税金控制测试", "parent_cycle": "N", "sort_order": 61},
    {"code_prefix": "C", "code_range": "C13", "cycle_name": "债务循环控制测试",
     "wp_type": "control_test", "description": "债务控制测试", "parent_cycle": "L", "sort_order": 62},
    {"code_prefix": "C", "code_range": "C14", "cycle_name": "租赁循环控制测试",
     "wp_type": "control_test", "description": "租赁控制测试", "parent_cycle": "H", "sort_order": 63},
    {"code_prefix": "C", "code_range": "C15", "cycle_name": "关联方控制测试",
     "wp_type": "control_test", "description": "关联方控制测试", "parent_cycle": "Q", "sort_order": 64},
    {"code_prefix": "C", "code_range": "C21-C26", "cycle_name": "一般性控制程序",
     "wp_type": "control_test", "description": "IT审计/会计分录/内审利用/信息处理控制", "sort_order": 65},
    # ── D-N类：实质性程序 ──
    {"code_prefix": "D", "code_range": "D0-D12", "cycle_name": "销售循环",
     "wp_type": "substantive", "description": "收入/应收票据/应收账款/预收/合同资产/合同负债/税费/所得税", "sort_order": 100},
    {"code_prefix": "E", "code_range": "E0-E1", "cycle_name": "货币资金循环",
     "wp_type": "substantive", "description": "库存现金/银行存款/其他货币资金", "sort_order": 110},
    {"code_prefix": "F", "code_range": "F", "cycle_name": "存货循环",
     "wp_type": "substantive", "description": "原材料/在产品/库存商品/生物资产/成本", "sort_order": 120},
    {"code_prefix": "G", "code_range": "G", "cycle_name": "投资循环",
     "wp_type": "substantive", "description": "长期股权投资/金融资产/投资性房地产", "sort_order": 130},
    {"code_prefix": "H", "code_range": "H", "cycle_name": "固定资产循环",
     "wp_type": "substantive", "description": "固定资产/在建工程/使用权资产/租赁负债", "sort_order": 140},
    {"code_prefix": "I", "code_range": "I", "cycle_name": "无形资产循环",
     "wp_type": "substantive", "description": "无形资产/研发支出/商誉/长期待摊费用", "sort_order": 150},
    {"code_prefix": "J", "code_range": "J", "cycle_name": "职工薪酬循环",
     "wp_type": "substantive", "description": "应付职工薪酬/设定受益计划", "sort_order": 160},
    {"code_prefix": "K", "code_range": "K", "cycle_name": "管理循环",
     "wp_type": "substantive", "description": "管理费用/销售费用/财务费用/研发费用", "sort_order": 170},
    {"code_prefix": "L", "code_range": "L", "cycle_name": "债务循环",
     "wp_type": "substantive", "description": "短期借款/长期借款/应付债券/租赁负债", "sort_order": 180},
    {"code_prefix": "M", "code_range": "M", "cycle_name": "权益循环",
     "wp_type": "substantive", "description": "实收资本/资本公积/盈余公积/未分配利润/其他综合收益", "sort_order": 190},
    {"code_prefix": "N", "code_range": "N", "cycle_name": "税金循环",
     "wp_type": "substantive", "description": "应交税费/税金及附加/所得税费用/递延所得税", "sort_order": 200},
    {"code_prefix": "Q", "code_range": "Q", "cycle_name": "关联方循环",
     "wp_type": "substantive", "description": "关联方关系/关联方交易", "sort_order": 210},
    # ── A类：完成阶段 ──
    {"code_prefix": "A", "code_range": "A1-A30", "cycle_name": "完成阶段",
     "wp_type": "completion", "description": "报告与沟通/总结程序/质量控制", "sort_order": 300},
    # ── S类：特定项目程序 ──
    {"code_prefix": "S", "code_range": "S", "cycle_name": "特定项目程序",
     "wp_type": "specific", "description": "违法行为/期初余额/会计政策变更/非货币交换/债务重组/IPO/再融资/数据资产", "sort_order": 400},
    # ── T类：通用底稿 ──
    {"code_prefix": "T", "code_range": "T", "cycle_name": "通用底稿",
     "wp_type": "general", "description": "IPE测试模板等通用底稿", "sort_order": 500},
    # ── Z类：永久性档案 ──
    {"code_prefix": "Z", "code_range": "Z", "cycle_name": "永久性档案",
     "wp_type": "permanent", "description": "永久性档案黄页", "sort_order": 600},
]


# ---------------------------------------------------------------------------
# 三测联动关系映射（B穿行→C控制→D-N实质性）
# ---------------------------------------------------------------------------

THREE_TEST_LINKAGE: list[dict] = [
    {"cycle": "销售循环", "substantive_prefix": "D", "b_code": "B23-1", "c_code": "C2"},
    {"cycle": "货币资金", "substantive_prefix": "E", "b_code": "B23-2", "c_code": "C3"},
    {"cycle": "存货循环", "substantive_prefix": "F", "b_code": "B23-3", "c_code": "C4"},
    {"cycle": "投资循环", "substantive_prefix": "G", "b_code": "B23-4", "c_code": "C5"},
    {"cycle": "固定资产", "substantive_prefix": "H", "b_code": "B23-5", "c_code": "C6"},
    {"cycle": "无形资产", "substantive_prefix": "I", "b_code": "B23-7", "c_code": "C8"},
    {"cycle": "职工薪酬", "substantive_prefix": "J", "b_code": "B23-9", "c_code": "C10"},
    {"cycle": "管理循环", "substantive_prefix": "K", "b_code": "B23-10", "c_code": "C11"},
    {"cycle": "税金循环", "substantive_prefix": "N", "b_code": "B23-11", "c_code": "C12"},
    {"cycle": "债务循环", "substantive_prefix": "L", "b_code": "B23-12", "c_code": "C13"},
    {"cycle": "关联方", "substantive_prefix": "Q", "b_code": "B23-14", "c_code": "C15"},
]
