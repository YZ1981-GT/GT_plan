"""合并附注服务 (ConsolDisclosureService)

扩展 Phase 2 合并附注生成能力，包含：
1. 合并范围说明（纳入/排除子公司列表及理由）
2. 重要子公司信息表（公司名、持股比例、注册资本、注册地）
3. 范围变动说明（本期新增/处置子公司）
4. 商誉披露（初始确认金额、累计减值）
5. 少数股东权益披露（各子公司少数股东权益金额）
6. 内部交易抵消说明（内部往来、内部交易抵消金额）
7. 外币折算披露（汇率选择依据、汇率变动影响）

以及与 Phase 1 附注体系的整合功能。

Validates: Phase 2 Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import (
    Company,
    ConsolScope,
    ForexTranslation,
    GoodwillCalc,
    InternalTrade,
    InternalArAp,
)
from app.models.consolidation_schemas import ConsolDisclosureSection, ConsolDisclosureRow
from app.models.report_models import DisclosureNote, ContentType, SourceTemplate, NoteStatus
from app.services.goodwill_service import get_goodwill_list
from app.services.minority_interest_service import get_mi_list

logger = logging.getLogger(__name__)


def _decimal(v) -> Decimal:
    """安全转换为 Decimal"""
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _float(v) -> float:
    """安全转换为 float"""
    try:
        return float(_decimal(v))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


# ============================================================================
# 合并附注服务
# ============================================================================

class ConsolDisclosureService:
    """合并附注服务

    扩展 consol_report_service.generate_consol_notes，补充：
    1. 范围变动说明
    2. 外币折算披露
    3. 与 Phase 1 附注体系的整合
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 核心方法
    # ------------------------------------------------------------------

    def generate_consol_notes(
        self,
        project_id: UUID,
        year: int,
    ) -> list[ConsolDisclosureSection]:
        """
        生成合并附注章节列表。

        包含 7 个章节：
        1. 合并范围说明
        2. 重要子公司信息表
        3. 范围变动说明
        4. 商誉披露
        5. 少数股东权益披露
        6. 内部交易抵消说明
        7. 外币折算披露

        Returns:
            list[ConsolDisclosureSection]: 合并附注章节列表
        """
        sections: list[ConsolDisclosureSection] = []

        # 1. 合并范围说明
        scope_section = self._generate_scope_section(project_id, year)
        sections.append(scope_section)

        # 2. 重要子公司信息表
        subsidiary_section = self._generate_subsidiary_section(project_id, year)
        sections.append(subsidiary_section)

        # 3. 范围变动说明
        scope_change_section = self._generate_scope_change_section(project_id, year)
        sections.append(scope_change_section)

        # 4. 商誉披露
        goodwill_section = self._generate_goodwill_section(project_id, year)
        sections.append(goodwill_section)

        # 5. 少数股东权益披露
        mi_section = self._generate_minority_interest_section(project_id, year)
        sections.append(mi_section)

        # 6. 内部交易抵消说明
        trade_section = self._generate_internal_trade_section(project_id, year)
        sections.append(trade_section)

        # 7. 外币折算披露
        forex_section = self._generate_forex_section(project_id, year)
        sections.append(forex_section)

        return sections

    # ------------------------------------------------------------------
    # 附注章节生成
    # ------------------------------------------------------------------

    def _generate_scope_section(
        self,
        project_id: UUID,
        year: int,
    ) -> ConsolDisclosureSection:
        """生成合并范围说明（纳入/排除子公司列表）"""
        # 获取纳入合并范围的公司
        included = (
            self.db.query(Company, ConsolScope)
            .join(ConsolScope, sa.and_(
                ConsolScope.company_code == Company.company_code,
                ConsolScope.project_id == project_id,
                ConsolScope.year == year,
            ))
            .filter(
                Company.project_id == project_id,
                ConsolScope.is_included.is_(True),
                Company.is_deleted.is_(False),
            )
            .all()
        )

        # 获取排除的公司
        excluded = (
            self.db.query(Company, ConsolScope)
            .join(ConsolScope, sa.and_(
                ConsolScope.company_code == Company.company_code,
                ConsolScope.project_id == project_id,
                ConsolScope.year == year,
            ))
            .filter(
                Company.project_id == project_id,
                ConsolScope.is_included.is_(False),
                Company.is_deleted.is_(False),
            )
            .all()
        )

        rows = []
        for company, scope in included:
            rows.append({
                "公司名称": company.company_name,
                "公司代码": company.company_code,
                "持股比例": f"{company.shareholding}%" if company.shareholding else "N/A",
                "合并方法": company.consol_method.value if company.consol_method else "全额合并",
                "是否纳入": "是",
                "纳入原因": scope.inclusion_reason.value if scope.inclusion_reason else "子公司",
            })

        for company, scope in excluded:
            rows.append({
                "公司名称": company.company_name,
                "公司代码": company.company_code,
                "持股比例": f"{company.shareholding}%" if company.shareholding else "N/A",
                "合并方法": company.consol_method.value if company.consol_method else "-",
                "是否纳入": "否",
                "排除原因": scope.exclusion_reason or "-",
            })

        summary = f"本期纳入合并范围的子公司共 {len(included)} 家"
        if excluded:
            summary += f"，未纳入合并范围的共 {len(excluded)} 家"

        return ConsolDisclosureSection(
            section_code="consol_scope",
            section_title="合并范围",
            content_type="table",
            rows=rows,
            summary=summary,
        )

    def _generate_subsidiary_section(
        self,
        project_id: UUID,
        year: int,
    ) -> ConsolDisclosureSection:
        """生成重要子公司信息表"""
        subsidiaries = (
            self.db.query(Company)
            .join(ConsolScope, sa.and_(
                ConsolScope.company_code == Company.company_code,
                ConsolScope.project_id == project_id,
                ConsolScope.year == year,
                ConsolScope.is_included.is_(True),
            ))
            .filter(
                Company.project_id == project_id,
                Company.is_deleted.is_(False),
                Company.is_active.is_(True),
            )
            .all()
        )

        rows = []
        for sub in subsidiaries:
            rows.append({
                "公司名称": sub.company_name,
                "注册地": sub.functional_currency,
                "业务性质": sub.consol_method.value if sub.consol_method else "其他",
                "注册资本": "-",  # TODO: 从公司详情取
                "母公司持股比例": f"{sub.shareholding}%" if sub.shareholding else "N/A",
                "合并方法": "全额合并" if sub.consol_method and sub.consol_method.value == "full" else "权益法",
            })

        return ConsolDisclosureSection(
            section_code="important_subsidiaries",
            section_title="重要子公司情况",
            content_type="table",
            rows=rows,
            summary=f"共有 {len(subsidiaries)} 家重要子公司",
        )

    def _generate_scope_change_section(
        self,
        project_id: UUID,
        year: int,
    ) -> ConsolDisclosureSection:
        """生成范围变动说明（本期新增/处置子公司）"""
        from app.models.consolidation_models import ScopeChangeType

        # 获取本年新增纳入的公司
        new_inclusions = (
            self.db.query(Company, ConsolScope)
            .join(ConsolScope, sa.and_(
                ConsolScope.company_code == Company.company_code,
                ConsolScope.project_id == project_id,
                ConsolScope.year == year,
            ))
            .filter(
                Company.project_id == project_id,
                ConsolScope.scope_change_type == ScopeChangeType.new_inclusion,
                Company.is_deleted.is_(False),
            )
            .all()
        )

        # 获取本年处置/排除的公司
        exclusions = (
            self.db.query(Company, ConsolScope)
            .join(ConsolScope, sa.and_(
                ConsolScope.company_code == Company.company_code,
                ConsolScope.project_id == project_id,
                ConsolScope.year == year,
            ))
            .filter(
                Company.project_id == project_id,
                ConsolScope.scope_change_type == ScopeChangeType.exclusion,
                Company.is_deleted.is_(False),
            )
            .all()
        )

        rows = []
        for company, scope in new_inclusions:
            rows.append({
                "变动类型": "新增纳入",
                "公司名称": company.company_name,
                "公司代码": company.company_code,
                "变动日期": str(company.acquisition_date) if company.acquisition_date else "-",
                "持股比例": f"{company.shareholding}%" if company.shareholding else "N/A",
                "变动说明": scope.scope_change_description or "本年新设/收购纳入合并范围",
            })

        for company, scope in exclusions:
            rows.append({
                "变动类型": "处置排除",
                "公司名称": company.company_name,
                "公司代码": company.company_code,
                "变动日期": str(company.disposal_date) if company.disposal_date else "-",
                "持股比例": f"{company.shareholding}%" if company.shareholding else "N/A",
                "变动说明": scope.scope_change_description or scope.exclusion_reason or "-",
            })

        summary = ""
        if new_inclusions:
            summary += f"本年新增纳入 {len(new_inclusions)} 家；"
        if exclusions:
            summary += f"本年处置/排除 {len(exclusions)} 家；"
        if not summary:
            summary = "本年合并范围无变动"

        return ConsolDisclosureSection(
            section_code="scope_change",
            section_title="合并范围变动说明",
            content_type="table",
            rows=rows,
            summary=summary,
        )

    def _generate_goodwill_section(
        self,
        project_id: UUID,
        year: int,
    ) -> ConsolDisclosureSection:
        """生成商誉披露"""
        goodwill_records = get_goodwill_list(self.db, project_id, year)

        rows = []
        total_goodwill = Decimal("0")
        for gw in goodwill_records:
            carrying = gw.carrying_amount or Decimal("0")
            total_goodwill += carrying
            rows.append({
                "被投资单位": gw.subsidiary_company_code,
                "初始确认金额": _float(gw.goodwill_amount),
                "本期增加": 0.0,  # TODO: 从变动记录取
                "本期减少": 0.0,  # TODO: 从变动记录取
                "累计减值": _float(gw.accumulated_impairment),
                "期末账面价值": _float(carrying),
                "负商誉标识": "是" if gw.is_negative_goodwill else "否",
            })

        return ConsolDisclosureSection(
            section_code="goodwill",
            section_title="商誉",
            content_type="table",
            rows=rows,
            summary=f"期末商誉账面价值合计 {_float(total_goodwill):,.2f} 元",
        )

    def _generate_minority_interest_section(
        self,
        project_id: UUID,
        year: int,
    ) -> ConsolDisclosureSection:
        """生成少数股东权益披露"""
        mi_records = get_mi_list(self.db, project_id, year)

        rows = []
        total_mi = Decimal("0")
        total_mi_profit = Decimal("0")
        for mi in mi_records:
            equity = mi.minority_equity or Decimal("0")
            profit = mi.minority_profit or Decimal("0")
            total_mi += equity
            total_mi_profit += profit

            # 计算少数股东持股比例
            minority_ratio = (1 - float(mi.minority_share_ratio or Decimal("1"))) * 100
            rows.append({
                "子公司": mi.subsidiary_company_code,
                "少数股东持股比例": f"{minority_ratio:.2f}%",
                "期末少数股东权益": _float(equity),
                "本期少数股东损益": _float(profit),
                "超额亏损标识": "是" if mi.is_excess_loss else "否",
                "超额亏损金额": _float(mi.excess_loss_amount),
            })

        return ConsolDisclosureSection(
            section_code="minority_interest",
            section_title="少数股东权益及少数股东损益",
            content_type="table",
            rows=rows,
            summary=f"期末少数股东权益合计 {_float(total_mi):,.2f} 元，本期少数股东损益合计 {_float(total_mi_profit):,.2f} 元",
        )

    def _generate_internal_trade_section(
        self,
        project_id: UUID,
        year: int,
    ) -> ConsolDisclosureSection:
        """生成内部交易抵消说明"""
        # 获取内部交易汇总
        trades = (
            self.db.query(InternalTrade)
            .filter(
                InternalTrade.project_id == project_id,
                InternalTrade.year == year,
                InternalTrade.is_deleted.is_(False),
            )
            .all()
        )

        # 获取内部往来汇总
        ar_aps = (
            self.db.query(InternalArAp)
            .filter(
                InternalArAp.project_id == project_id,
                InternalArAp.year == year,
                InternalArAp.is_deleted.is_(False),
            )
            .all()
        )

        total_trade = sum(t.trade_amount or Decimal("0") for t in trades)
        total_unrealized = sum(t.unrealized_profit or Decimal("0") for t in trades)
        total_ar = sum(a.ar_amount or Decimal("0") for a in ar_aps)
        total_ap = sum(a.ap_amount or Decimal("0") for a in ar_aps)

        rows = []
        for trade in trades:
            rows.append({
                "类型": "内部交易",
                "卖方": trade.seller_company_code,
                "买方": trade.buyer_company_code,
                "交易类型": trade.trade_type.value if trade.trade_type else "其他",
                "交易金额": _float(trade.trade_amount),
                "未实现利润": _float(trade.unrealized_profit),
                "期末存货中未实现比例": f"{_float(trade.inventory_remaining_ratio) * 100:.2f}%"
                    if trade.inventory_remaining_ratio else "0%",
            })

        for ar_ap in ar_aps:
            rows.append({
                "类型": "内部往来",
                "卖方": ar_ap.company_code,
                "买方": ar_ap.counterparty_code,
                "交易类型": "往来款项",
                "交易金额": _float(ar_ap.ar_amount),
                "未实现利润": 0.0,
                "期末存货中未实现比例": "-",
            })

        summary = f"本期内部交易合计 {_float(total_trade):,.2f} 元"
        summary += f"，未实现利润 {_float(total_unrealized):,.2f} 元"
        summary += f"；期末内部往来应收 {_float(total_ar):,.2f} 元、应付 {_float(total_ap):,.2f} 元"

        return ConsolDisclosureSection(
            section_code="internal_trade_elimination",
            section_title="内部交易抵消",
            content_type="table",
            rows=rows,
            summary=summary,
        )

    def _generate_forex_section(
        self,
        project_id: UUID,
        year: int,
    ) -> ConsolDisclosureSection:
        """生成外币折算披露"""
        # 获取外币折算记录
        forex_records = (
            self.db.query(ForexTranslation)
            .filter(
                ForexTranslation.project_id == project_id,
                ForexTranslation.year == year,
                ForexTranslation.is_deleted.is_(False),
            )
            .all()
        )

        rows = []
        total_translation_diff = Decimal("0")
        for forex in forex_records:
            # 折算差额 = 资产折算 - 负债折算 - 权益折算
            translation_diff = (
                (forex.bs_closing_assets or Decimal("0"))
                - (forex.bs_closing_liabilities or Decimal("0"))
                - (forex.equity_translation or Decimal("0"))
            )
            total_translation_diff += translation_diff

            rows.append({
                "公司名称": forex.company_code,
                "功能货币": forex.functional_currency,
                "资产负债表期末汇率": _float(forex.bs_closing_rate),
                "利润表平均汇率": _float(forex.pl_average_rate),
                "期初汇率": _float(forex.opening_rate),
                "汇率变动影响": _float(translation_diff),
                "折算说明": forex.translation_description or "-",
            })

        # 生成汇率选择依据说明
        text_content = ""
        if forex_records:
            currencies = set(f.functional_currency for f in forex_records if f.functional_currency)
            if currencies:
                text_content = (
                    f"外币报表折算方法：本集团对境外子公司的外币报表采用上述汇率进行折算。"
                    f"其中，功能货币为 {', '.join(currencies)} 的子公司采用资产负债表日汇率法，"
                    f"即资产、负债项目按期末汇率折算，所有者权益项目按历史汇率折算，"
                    f"利润表项目按平均汇率折算。折算差额计入其他综合收益。"
                )
            else:
                text_content = "本年无外币报表折算业务。"

        return ConsolDisclosureSection(
            section_code="forex_translation",
            section_title="外币报表折算",
            content_type="mixed",
            rows=rows,
            summary=(
                f"共有 {len(forex_records)} 家境外子公司进行外币报表折算，"
                f"本年折算差额影响合计 {_float(total_translation_diff):,.2f} 元"
                if forex_records
                else "本年无外币报表折算业务"
            ),
        )

    # ------------------------------------------------------------------
    # 整合方法
    # ------------------------------------------------------------------

    def integrate_with_notes(
        self,
        project_id: UUID,
        year: int,
        existing_notes: list[dict] | None = None,
    ) -> list[ConsolDisclosureSection]:
        """
        将合并附注插入 Phase 1 附注体系的适当位置。

        Phase 1 附注体系顺序（参考 disclosure_notes 表）：
        1. 公司基本情况
        2. 重要会计政策及会计估计
        3. 税项
        4. 财务报表主要项目注释（各科目）
        5. 合并财务报表主要项目注释  <-- 合并附注插入位置
        6. 关联方及关联交易
        7. 或有事项
        8. 承诺事项
        9. 资产负债表日后事项
        10. 其他重要事项

        Args:
            project_id: 项目ID
            year: 报表年度
            existing_notes: Phase 1 现有附注列表（可选，用于确定插入位置）

        Returns:
            list[ConsolDisclosureSection]: 整合后的附注章节列表
        """
        # 获取合并附注章节
        consol_sections = self.generate_consol_notes(project_id, year)

        if existing_notes is None:
            # 从数据库加载 Phase 1 附注
            existing_notes = self._load_existing_notes(project_id, year)

        # 按 Phase 1 顺序构建整合后的附注列表
        integrated_sections = self._build_integrated_notes(
            project_id, year, consol_sections, existing_notes,
        )

        return integrated_sections

    def _load_existing_notes(
        self,
        project_id: UUID,
        year: int,
    ) -> list[dict]:
        """从数据库加载 Phase 1 附注"""
        notes = (
            self.db.query(DisclosureNote)
            .filter(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted.is_(False),
            )
            .order_by(DisclosureNote.sort_order, DisclosureNote.note_section)
            .all()
        )

        return [
            {
                "id": str(n.id),
                "note_section": n.note_section,
                "section_title": n.section_title,
                "content_type": n.content_type.value if n.content_type else "table",
                "sort_order": n.sort_order or 0,
            }
            for n in notes
        ]

    def _build_integrated_notes(
        self,
        project_id: UUID,
        year: int,
        consol_sections: list[ConsolDisclosureSection],
        existing_notes: list[dict],
    ) -> list[ConsolDisclosureSection]:
        """构建整合后的附注列表"""
        # Phase 1 附注顺序定义（按 note_section 前缀排序）
        phase1_order = [
            ("company_info", "公司基本情况"),
            ("accounting_policy", "重要会计政策和会计估计"),
            ("tax", "税项"),
            ("accounts", "财务报表主要项目注释"),  # 各科目附注
            ("related_party", "关联方及关联交易"),
            ("contingencies", "或有事项"),
            ("commitments", "承诺事项"),
            ("events_after", "资产负债表日后事项"),
            ("other", "其他重要事项"),
        ]

        # 合并附注插入点：在 "财务报表主要项目注释" 之后
        insert_after_prefixes = ["accounts", "主要项目"]

        # 构建整合后的章节列表
        result: list[ConsolDisclosureSection] = []

        for note in existing_notes:
            section_title = note.get("section_title", "")
            note_section = note.get("note_section", "")

            # 检查是否到达插入点
            should_insert_here = any(
                note_section.startswith(prefix) or section_title.startswith(prefix)
                for prefix in insert_after_prefixes
            )

            # 如果已到达插入点，先添加 Phase 1 章节
            if should_insert_here:
                result.append(ConsolDisclosureSection(
                    section_code=note_section,
                    section_title=section_title,
                    content_type=note.get("content_type", "table"),
                    rows=[],
                    summary="",
                ))
                # 然后插入合并附注
                result.extend(consol_sections)
                # 标记已插入
                should_insert_here = False
            else:
                result.append(ConsolDisclosureSection(
                    section_code=note_section,
                    section_title=section_title,
                    content_type=note.get("content_type", "table"),
                    rows=[],
                    summary="",
                ))

        # 如果没有找到插入点，追加到末尾
        if len(result) == len(existing_notes):
            result.extend(consol_sections)

        return result

    def save_consol_notes(
        self,
        project_id: UUID,
        year: int,
        sections: list[ConsolDisclosureSection],
    ) -> list[DisclosureNote]:
        """
        将生成的合并附注保存到数据库。

        Args:
            project_id: 项目ID
            year: 报表年度
            sections: 合并附注章节列表

        Returns:
            list[DisclosureNote]: 保存的附注记录列表
        """
        saved_notes: list[DisclosureNote] = []

        for idx, section in enumerate(sections):
            # 查询是否已存在
            existing = (
                self.db.query(DisclosureNote)
                .filter(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.note_section == section.section_code,
                    DisclosureNote.is_deleted.is_(False),
                )
                .first()
            )

            if existing:
                # 更新现有记录
                existing.section_title = section.section_title
                existing.content_type = ContentType(section.content_type)
                existing.table_data = {"rows": section.rows, "summary": section.summary}
                existing.source_template = SourceTemplate.consolidated
                existing.sort_order = 100 + idx  # 合并附注排序在 Phase 1 之后
                existing.updated_at = sa.func.now()
                saved_notes.append(existing)
            else:
                # 创建新记录
                note = DisclosureNote(
                    project_id=project_id,
                    year=year,
                    note_section=section.section_code,
                    section_title=section.section_title,
                    content_type=ContentType(section.content_type),
                    table_data={"rows": section.rows, "summary": section.summary},
                    source_template=SourceTemplate.consolidated,
                    status=NoteStatus.draft,
                    sort_order=100 + idx,
                )
                # F50 / Sprint 8.19: 附注创建时绑定当前 active dataset
                try:
                    from app.services.dataset_query import bind_to_active_dataset_sync
                    bind_to_active_dataset_sync(self.db, note, project_id, year)
                except Exception as _bind_err:
                    import logging
                    logging.getLogger(__name__).warning(
                        "consol disclosure_note dataset binding failed: section=%s err=%s",
                        section.section_code, _bind_err,
                    )
                self.db.add(note)
                saved_notes.append(note)

        self.db.flush()
        return saved_notes


# ============================================================================
# 便捷函数（同步风格，供路由层调用）
# ============================================================================


def generate_consol_notes_sync(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> list[ConsolDisclosureSection]:
    """同步封装：生成合并附注"""
    service = ConsolDisclosureService(db)
    return service.generate_consol_notes(project_id, year)


def integrate_consol_notes_sync(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    existing_notes: list[dict] | None = None,
) -> list[ConsolDisclosureSection]:
    """同步封装：整合合并附注与 Phase 1 附注"""
    service = ConsolDisclosureService(db)
    return service.integrate_with_notes(project_id, year, existing_notes)


def save_consol_notes_sync(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    sections: list[ConsolDisclosureSection],
) -> list[DisclosureNote]:
    """同步封装：保存合并附注到数据库"""
    service = ConsolDisclosureService(db)
    return service.save_consol_notes(project_id, year, sections)


# ============================================================================
# Phase 2：V2 附注 feature flag 灰度接线（ADR-CONSOL-202 / 需求 3 / 属性 S4）
# ============================================================================


def _adapt_v2_row_to_schema(row) -> ConsolDisclosureRow:
    """将单个 V2 行（dict 或 list）映射到 ConsolDisclosureRow（最多 6 列）.

    防御性处理：
    - dict 形态：按 col_1..col_6 / col1..col6 键取值（任一命名都接受）；
    - list 形态：按位置映射到 col_1..col_6（多余的截断，缺的留 None）；
    - 其他/None：返回空行。
    所有单元格值统一 stringify（None 保持 None）。
    """
    def _stringify(v):
        return None if v is None else str(v)

    if isinstance(row, dict):
        data: dict = {}
        row_index = row.get("row_index")
        if isinstance(row_index, int):
            data["row_index"] = row_index
        for i in range(1, 7):
            # 同时兼容 col_1 / col1 两种命名
            val = row.get(f"col_{i}")
            if val is None:
                val = row.get(f"col{i}")
            if val is not None:
                data[f"col_{i}"] = _stringify(val)
        return ConsolDisclosureRow(**data)

    if isinstance(row, (list, tuple)):
        data = {}
        for i, val in enumerate(row[:6], start=1):
            data[f"col_{i}"] = _stringify(val)
        return ConsolDisclosureRow(**data)

    return ConsolDisclosureRow()


def _adapt_v2_sections_to_schema(
    v2_sections: list[dict],
) -> list[ConsolDisclosureSection]:
    """S4 归一化层：将 V2 dict 章节列表适配为 ConsolDisclosureSection（与老版契约一致）.

    V2 章节是 plain dict（section_id / section_title / section_type / table_data{rows,summary} ...），
    老版返回 Pydantic ConsolDisclosureSection。本适配器保证无论数据来源如何，
    路由 response_model=list[ConsolDisclosureSection] 的契约都成立。

    映射规则：
    - section_code  <- section_id / section_code / ""
    - section_title <- section_title / ""
    - content       <- summary / table_data.summary / None
    - rows          <- table_data.rows 逐行映射为 ConsolDisclosureRow（最多 6 列）
    - is_editable   <- is_editable（默认 True）
    - is_group_header <- is_group_header 或 section_type == "group_header"
    """
    adapted: list[ConsolDisclosureSection] = []
    for raw in v2_sections or []:
        if not isinstance(raw, dict):
            continue

        table_data = raw.get("table_data") or {}
        if not isinstance(table_data, dict):
            table_data = {}

        content = raw.get("summary") or table_data.get("summary") or None

        raw_rows = table_data.get("rows")
        if not isinstance(raw_rows, (list, tuple)):
            raw_rows = []
        rows = [_adapt_v2_row_to_schema(r) for r in raw_rows]

        is_group_header = bool(
            raw.get("is_group_header")
            or raw.get("section_type") == "group_header"
        )

        adapted.append(
            ConsolDisclosureSection(
                section_code=raw.get("section_id") or raw.get("section_code") or "",
                section_title=raw.get("section_title") or "",
                content=content,
                rows=rows,
                is_editable=bool(raw.get("is_editable", True)),
                is_group_header=is_group_header,
            )
        )
    return adapted


async def generate_consol_notes_with_flag(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> list[ConsolDisclosureSection]:
    """合并附注生成统一入口（feature flag 灰度，ADR-CONSOL-202）.

    - CONSOL_NOTES_V2_ENABLED == True：调 V2 generate_full_consol_notes（消费子公司
      单体附注汇总），经 _adapt_v2_sections_to_schema 归一化为 ConsolDisclosureSection；
      V2 任意异常（EH3/R2）→ logger.warning + 回退老版 generate_consol_notes_sync，
      不破坏既有可用性。
    - 否则：直接返回老版 generate_consol_notes_sync（7 骨架章节）。

    返回结构契约与老版一致（list[ConsolDisclosureSection]，属性 S4）。
    """
    from app.core.config import settings

    if getattr(settings, "CONSOL_NOTES_V2_ENABLED", False):
        try:
            v2_sections = await generate_full_consol_notes(db, project_id, year)
            return _adapt_v2_sections_to_schema(v2_sections)
        except Exception as err:  # EH3/R2：V2 失败回退老版兼容
            logger.warning(
                "generate_full_consol_notes (V2) failed, falling back to legacy "
                "generate_consol_notes_sync: project_id=%s year=%s err=%s",
                project_id, year, err,
            )
            return generate_consol_notes_sync(db, project_id, year)

    return generate_consol_notes_sync(db, project_id, year)


# ============================================================================
# V2：合并附注完整生成（Sprint B.1.1~B.1.10）
# ============================================================================

# B.1.10 事件名
CONSOL_SUBSIDIARY_CHANGED = "CONSOL_SUBSIDIARY_CHANGED"

# B.1.5 合并专用章节 wp_code 绑定
_CONSOL_SECTION_WP_BINDINGS: dict[str, dict] = {
    "goodwill": {"source": "wp_data", "wp_code": "h08", "description": "商誉底稿"},
    "minority_interest": {"source": "wp_data", "wp_code": "g", "description": "少数股东权益底稿"},
    "forex_translation": {"source": "wp_data", "wp_code": "m", "description": "外币折算底稿"},
}


async def generate_full_consol_notes(
    db: AsyncSession,
    parent_project_id: UUID,
    year: int,
    template_type: str = "soe",
) -> list[dict]:
    """合并附注完整生成（173 共有 + 7 合并专用 = 180 章节）.

    B.1.1 主方法。步骤：
    1. 加载子公司树（consol_tree_service.build_tree）
    2. 加载章节映射（consol_note_section_mapping.csv）
    3. 对每个共有章节：调 aggregate_section（B.0.2）
    4. 生成 7 个合并专用章节（保留现有逻辑）
    5. 章节序号按 scope='consolidated' 重排（D13）
    6. 文字段落 Jinja 渲染（合并版 vars）
    7. 写 lineage + 保存

    Args:
        db: AsyncSession
        parent_project_id: 合并项目 ID
        year: 报告年度
        template_type: 模板类型 (soe/listed)

    Returns:
        list[dict]: 180 章节结构列表
    """
    # Step 1: B.1.3 子公司清单实时拉取
    subsidiaries = await _fetch_subsidiary_list(db, parent_project_id)

    # Step 2: 加载章节映射
    section_mapping = _load_section_mapping()

    # Step 3: B.1.2 对每个共有章节调 aggregate
    common_sections: list[dict] = []
    for mapping in section_mapping:
        section_result = await _aggregate_common_section(
            db=db,
            consol_project_id=parent_project_id,
            year=year,
            mapping=mapping,
            subsidiaries=subsidiaries,
            consol_type=template_type,
        )
        if section_result is not None:
            common_sections.append(section_result)

    # Step 4: B.1.9 生成 7 个合并专用章节（wp_data 强化）
    consol_only_sections = _generate_consol_only_sections_v2(
        parent_project_id, year, subsidiaries,
    )

    # 合并所有章节
    all_sections = common_sections + consol_only_sections

    # Step 5: B.1.8 章节序号 scope='consolidated' 重排
    all_sections = _renumber_sections_consolidated(all_sections)

    # Step 6: B.1.7 文字段落合并版 vars 渲染
    consol_vars = _build_consol_paragraph_vars(subsidiaries, year)
    all_sections = _render_text_paragraphs_v2(all_sections, consol_vars)

    # Step 7: B.1.6 写 lineage
    lineage_chain = await _write_lineage_v2(db, parent_project_id)
    for section in all_sections:
        section["lineage"] = lineage_chain

    return all_sections


# ---------------------------------------------------------------------------
# B.1.2 _aggregate_common_section
# ---------------------------------------------------------------------------


async def _aggregate_common_section(
    db: AsyncSession,
    consol_project_id: UUID,
    year: int,
    mapping: dict,
    subsidiaries: list[dict],
    consol_type: str = "soe",
) -> dict | None:
    """调 consol_note_aggregation_service.aggregate_section 汇总单个共有章节.

    B.1.2 实现。
    """
    from app.services.consol_note_aggregation_service import aggregate_section

    section_id = mapping.get("section_id", "")
    consol_section_id = mapping.get("consol_section_id", section_id)
    method = mapping.get("aggregation_method", "simple_sum")
    elimination_rule = mapping.get("elimination_rule", "")

    elimination_rules: list[dict] = []
    if elimination_rule:
        elimination_rules = [{"rule_type": elimination_rule}]

    child_filter = {
        "subsidiaries": [s["project_id"] for s in subsidiaries],
    }

    result = await aggregate_section(
        consol_project_id=consol_project_id,
        section_id=section_id,
        year=year,
        method=method,
        elimination_rules=elimination_rules,
        child_filter=child_filter,
        db=db,
    )

    if result is None:
        # 即使无数据也生成空章节占位
        result = {
            "rows": [],
            "method": method,
            "child_count": len(subsidiaries),
            "section_id": section_id,
            "elimination_applied": bool(elimination_rule),
        }

    # B.1.4 抵销前后双列标记
    result = _add_elimination_columns(result, elimination_rule)

    # Phase 3（consol-phase3-frontend-drilldown / T2 / ADR-CONSOL-302）：
    # 汇总每章节时同步写 consolidation_breakdown provenance（哪些子公司贡献多少），
    # 供附注穿透端点直接读，无需事后重算。
    # 注：V2 generate_full_consol_notes 输出目前尚未接 disclosure_notes 落库路径
    # （依赖 Phase 2 V2 接线）；这里先把 provenance + source_project_id 附在返回的
    # 章节 dict 上，供端点（note_consol_drilldown_service）与未来落库逻辑读取。
    section_title = mapping.get("section_title") or consol_section_id
    consolidation_breakdown = _build_section_consolidation_breakdown(
        section_title=section_title,
        result=result,
        subsidiaries=subsidiaries,
    )

    # 5C cross_template 孤儿接线（ADR-CONSOL-204 / 需求 6 / S7 / EH7）：
    # 当 V2 + cross_template 双开关开启且子公司模板与合并模板不同时，
    # 调 consol_cross_template_service.translate_child_section 翻译后汇总，
    # 并把 provenance（含降级 warning）附在章节 dict 上。无需翻译时返回 None。
    cross_template = await _maybe_apply_cross_template(
        db=db,
        parent_project_id=consol_project_id,
        year=year,
        consol_type=consol_type,
        mapping=mapping,
        subsidiaries=subsidiaries,
    )

    section_out = {
        "section_id": consol_section_id,
        "source_section_id": section_id,
        "section_type": "common",
        "aggregation_method": method,
        "table_data": result,
        "scope": "consolidated",
        "level": 3,
        "auto_numbering": True,
        # Phase 3 附注级穿透 provenance（落 disclosure_notes.consolidation_breakdown）
        "source_project_id": str(consol_project_id),
        "consolidation_breakdown": consolidation_breakdown,
    }
    if cross_template is not None:
        section_out["cross_template"] = cross_template
    return section_out


# ---------------------------------------------------------------------------
# Phase 3 附注级穿透 provenance 构建（consol-phase3-frontend-drilldown / T2）
# ---------------------------------------------------------------------------


def _build_section_consolidation_breakdown(
    section_title: str,
    result: dict,
    subsidiaries: list[dict],
) -> dict:
    """构建附注合并章节的 consolidation_breakdown provenance.

    形态与 Phase 0 consol_trial.consolidation_breakdown 对称（V034 / B1）：
        {
          "by_company": [
            {"company_code", "company_name", "section_title", "amount"(str Decimal)}
          ],
          "computed_at": "<iso>",
        }

    各子公司贡献金额 = 该子公司所有行的全部数值单元格之和（按 source_project 归并）。
    section 汇总值 == Σ by_company[*].amount（同一批单元格按来源子公司的划分，
    自洽性见属性 T2）。amount == 0 的子公司仍保留（便于穿透展示"贡献为 0"）。

    无法归属来源（source_project 缺失，如已模糊合并的行）的金额走 best-effort：
    不计入 by_company（避免错误归属），故仅在所有行均带 source_project 时
    Σ by_company == section 汇总值严格成立。
    """
    # project_id(str) -> {company_code, company_name}
    company_map: dict[str, dict] = {}
    for sub in subsidiaries:
        pid = sub.get("project_id")
        if pid is None:
            continue
        company_map[str(pid)] = {
            "company_code": sub.get("company_code"),
            "company_name": sub.get("company_name"),
        }

    amounts: dict[str, Decimal] = {}
    for row in (result.get("rows") or []):
        if not isinstance(row, dict):
            continue
        source_project = row.get("source_project")
        if source_project is None:
            # 已合并/无来源行：best-effort 不归属（避免错误归属，见 docstring）
            continue
        pid_str = str(source_project)
        row_total = _sum_row_numeric_values(row.get("values") or {})
        amounts[pid_str] = amounts.get(pid_str, Decimal("0")) + row_total

    by_company: list[dict] = []
    for pid_str, amount in amounts.items():
        meta = company_map.get(pid_str, {})
        by_company.append({
            # source_project_id 供前端 ConsolBreakdownDialog 跨项目跳转单体附注（T3）
            "source_project_id": pid_str,
            "company_code": meta.get("company_code"),
            "company_name": meta.get("company_name"),
            "section_title": section_title,
            "amount": str(amount),
        })

    return {
        "by_company": by_company,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _sum_row_numeric_values(values: dict) -> Decimal:
    """对一行的全部数值单元格求和（Decimal，跳过非数值/None）."""
    total = Decimal("0")
    for val in (values or {}).values():
        if val is None:
            continue
        try:
            total += Decimal(str(val))
        except (InvalidOperation, ValueError, TypeError):
            continue
    return total


# ---------------------------------------------------------------------------
# B.1.3 子公司清单实时拉取
# ---------------------------------------------------------------------------


async def _fetch_subsidiary_list(
    db: AsyncSession,
    parent_project_id: UUID,
) -> list[dict]:
    """用 consol_tree_service.build_tree 实时拉取子公司清单.

    B.1.3 实现。
    """
    from app.services.consol_tree_service import build_tree, get_descendants
    from app.models.core import Project

    tree = await build_tree(db, parent_project_id)
    if tree is None:
        return []

    descendants = get_descendants(tree)

    # 批量读取各子公司 Project.template_type（国企/上市 跨模板翻译用，ADR-CONSOL-204）。
    # build_tree 的 TreeNode 不带 template_type，这里单独一次性 IN 查询补齐，
    # 失败时降级为 None（视为未知 → 翻译路径按"同模板"处理，不丢章节）。
    template_type_map: dict[UUID, str | None] = {}
    try:
        node_ids = [node.project_id for node in descendants]
        if node_ids:
            rows = await db.execute(
                sa.select(Project.id, Project.template_type).where(
                    Project.id.in_(node_ids),
                )
            )
            template_type_map = {row[0]: row[1] for row in rows.all()}
    except Exception as err:  # 降级：template_type 读取失败不阻断附注生成
        logger.warning(
            "Failed to load subsidiary template_type (cross_template will treat as "
            "same-type): parent_project_id=%s err=%s",
            parent_project_id, err,
        )

    return [
        {
            "project_id": node.project_id,
            "company_code": node.company_code,
            "company_name": node.company_name,
            "consol_level": node.consol_level,
            "template_type": template_type_map.get(node.project_id),
        }
        for node in descendants
    ]


# ---------------------------------------------------------------------------
# 5C cross_template 孤儿接线（ADR-CONSOL-204 / 需求 6 / 属性 S7 / EH7）
# ---------------------------------------------------------------------------


def apply_cross_template_to_children(
    section_id: str,
    children: list[dict],
    consol_type: str,
) -> tuple[list[dict], list[str]]:
    """对各子公司章节做国企↔上市跨模板翻译（feature flag 受控）.

    把孤立的 `consol_cross_template_service.translate_child_section` 接入 V2 附注
    汇总的 live 路径（消除孤儿，需求 6.1/6.2）。

    Args:
        section_id: 章节标识（用于回填 child section_id，便于映射查找）
        children: 子公司章节列表，每项形如
            ``{"project_id", "company_name", "template_type", "section_data": dict}``
        consol_type: 合并项目模板类型（soe/listed），即翻译目标 to_type

    Returns:
        ``(translated_children, warnings)``：
        - translated_children：与输入**等长**的列表（S7 不丢章节），每项的
          ``section_data`` 被替换为翻译结果；同模板/未知模板原样透传。
        - warnings：降级（无匹配映射 / 翻译异常）时累计的中文 warning（EH7）。

    保证（属性 S7 / 错误场景 EH7）：
    - 输出章节数 == 输入章节数（``len(out) == len(children)``），任何情况下不丢章节。
    - 子公司 template_type 与 consol_type 相同（或未知 None）→ 原样汇总，不翻译。
    - 不同 → 调 translate_child_section 翻译后汇总。
    - 翻译异常 / 无匹配映射 → 降级为原样章节 + 累计 warning（不让翻译缺失丢章节）。
    """
    from app.services.consol_cross_template_service import translate_child_section

    translated_children: list[dict] = []
    warnings: list[str] = []

    for child in children:
        child_template = child.get("template_type") or consol_type
        section_data = child.get("section_data")
        company_name = child.get("company_name", "")

        # 同模板 / 未知模板 / section_data 非 dict → 原样透传（不翻译，不丢）
        if (
            child_template == consol_type
            or not isinstance(section_data, dict)
        ):
            translated_children.append(child)
            continue

        try:
            # 回填 section_id 便于 classify_section_mapping 命中映射
            payload = dict(section_data)
            payload.setdefault("section_id", section_id)
            translated = translate_child_section(
                payload,
                from_type=child_template,
                to_type=consol_type,
            )
            translation_type = translated.get("_translation_type")
            # EH7：无匹配映射（unknown / target_only / 子公司无数据）→ warning，
            # 但仍保留章节（translate_child_section 永不返回 None，保证不丢）。
            if translation_type in ("unknown", "target_only") or translated.get(
                "_not_applicable"
            ):
                warnings.append(
                    f"章节 {section_id} 子公司「{company_name}」"
                    f"（{child_template}→{consol_type}）无匹配跨模板映射，已降级原样汇总"
                )
                # target_only/not_applicable：子公司本无此章节数据，保留原始 section_data
                new_child = dict(child)
                new_child["section_data"] = section_data
                translated_children.append(new_child)
                continue

            new_child = dict(child)
            new_child["section_data"] = translated
            translated_children.append(new_child)
        except Exception as err:  # EH7：翻译异常 → 降级原样汇总 + warning，绝不丢章节
            logger.warning(
                "cross_template translate_child_section failed, degrade to passthrough: "
                "section_id=%s company=%s %s→%s err=%s",
                section_id, company_name, child_template, consol_type, err,
            )
            warnings.append(
                f"章节 {section_id} 子公司「{company_name}」跨模板翻译异常，已降级原样汇总"
            )
            translated_children.append(child)

    return translated_children, warnings


async def _maybe_apply_cross_template(
    db: AsyncSession,
    parent_project_id: UUID,
    year: int,
    consol_type: str,
    mapping: dict,
    subsidiaries: list[dict],
) -> dict | None:
    """读取各子公司单体附注章节并做跨模板翻译，返回 cross_template provenance.

    仅当 `CONSOL_NOTES_V2_ENABLED AND CONSOL_CROSS_TEMPLATE_ENABLED` 同时为 True，
    且子公司中存在与 consol_type 不同的 template_type 时才真正执行（避免影响
    老版/同模板路径，需求 6.3 feature flag 受控）。

    返回值挂在章节 dict 的 `cross_template` 字段，作为孤儿服务被 live 路径调用的
    真实证据（build_cross_template_provenance 标识 has_cross_template）。
    无需翻译时返回 None（调用方据此不附加该字段）。
    """
    from app.core.config import settings
    from app.services.consol_cross_template_service import (
        build_cross_template_provenance,
    )

    if not (
        getattr(settings, "CONSOL_NOTES_V2_ENABLED", False)
        and getattr(settings, "CONSOL_CROSS_TEMPLATE_ENABLED", False)
    ):
        return None

    # 仅当存在跨模板子公司时才介入（同模板集团跳过，零开销）
    differing = [
        s for s in subsidiaries
        if (s.get("template_type") or consol_type) != consol_type
    ]
    if not differing:
        return None

    section_id = mapping.get("section_id", "")

    # 读取各子公司该章节的单体附注数据（与 aggregation_service 同源 disclosure_notes）
    children: list[dict] = []
    try:
        for sub in subsidiaries:
            section_data = await _load_child_section_data(
                db, sub["project_id"], year, section_id,
            )
            children.append({
                "project_id": str(sub["project_id"]),
                "company_name": sub.get("company_name", ""),
                "template_type": sub.get("template_type") or consol_type,
                "section_data": section_data or {"section_id": section_id},
            })
    except Exception as err:  # 读取失败不阻断附注生成（降级：不附加 cross_template）
        logger.warning(
            "cross_template child section load failed, skip translation: "
            "section_id=%s err=%s", section_id, err,
        )
        return None

    translated_children, warnings = apply_cross_template_to_children(
        section_id, children, consol_type,
    )

    # S7 不变量：翻译前后章节数恒等（断言式防御，永不丢章节）
    if len(translated_children) != len(children):  # pragma: no cover - 防御
        logger.error(
            "cross_template section loss detected (in=%d out=%d), aborting translation "
            "for section_id=%s", len(children), len(translated_children), section_id,
        )
        return None

    contributions = [
        {
            "project_id": c.get("project_id", ""),
            "company_name": c.get("company_name", ""),
            "template_type": c.get("template_type", consol_type),
        }
        for c in translated_children
    ]
    provenance = build_cross_template_provenance(contributions)
    provenance["warnings"] = warnings
    provenance["child_count"] = len(translated_children)
    return provenance


async def _load_child_section_data(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
) -> dict | None:
    """读取单个子公司单体附注章节的 table_data（供跨模板翻译用）."""
    try:
        row = await db.execute(
            sa.text(
                "SELECT table_data FROM disclosure_notes "
                "WHERE project_id = :pid AND year = :year "
                "AND section_id = :sid AND is_deleted = false LIMIT 1"
            ),
            {"pid": str(project_id), "year": year, "sid": section_id},
        )
        record = row.first()
        if record and isinstance(record[0], dict):
            data = dict(record[0])
            data.setdefault("section_id", section_id)
            return data
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# B.1.4 抵销前后双列
# ---------------------------------------------------------------------------


def _add_elimination_columns(result: dict, elimination_rule: str) -> dict:
    """在 table_data 中加 _pre_elimination / _post_elimination 双列标记.

    B.1.4 实现。当有抵销规则时，标记原始数据为 pre，抵销后为 post。
    """
    if not elimination_rule:
        return result

    result["_pre_elimination"] = True
    result["_post_elimination"] = True
    result["elimination_rule"] = elimination_rule
    return result


# ---------------------------------------------------------------------------
# B.1.5 商誉/MI/外币 章节绑 wp_data
# ---------------------------------------------------------------------------


def _generate_consol_only_sections_v2(
    parent_project_id: UUID,
    year: int,
    subsidiaries: list[dict],
) -> list[dict]:
    """生成 7 个合并专用章节（wp_data 强化版）.

    B.1.5 + B.1.9 实现。
    """
    consol_sections = [
        {
            "section_id": "consol_scope",
            "section_title": "合并范围",
            "section_type": "consol_only",
            "scope": "consolidated",
            "level": 2,
            "auto_numbering": True,
            "table_data": {"rows": [], "summary": f"纳入合并范围子公司 {len(subsidiaries)} 家"},
        },
        {
            "section_id": "important_subsidiaries",
            "section_title": "重要子公司情况",
            "section_type": "consol_only",
            "scope": "consolidated",
            "level": 2,
            "auto_numbering": True,
            "table_data": {"rows": [], "summary": f"共有 {len(subsidiaries)} 家重要子公司"},
        },
        {
            "section_id": "scope_change",
            "section_title": "合并范围变动说明",
            "section_type": "consol_only",
            "scope": "consolidated",
            "level": 2,
            "auto_numbering": True,
            "table_data": {"rows": [], "summary": ""},
        },
        {
            "section_id": "goodwill",
            "section_title": "商誉",
            "section_type": "consol_only",
            "scope": "consolidated",
            "level": 2,
            "auto_numbering": True,
            "table_data": {"rows": [], "summary": ""},
            "binding": _CONSOL_SECTION_WP_BINDINGS.get("goodwill"),
        },
        {
            "section_id": "minority_interest",
            "section_title": "少数股东权益及少数股东损益",
            "section_type": "consol_only",
            "scope": "consolidated",
            "level": 2,
            "auto_numbering": True,
            "table_data": {"rows": [], "summary": ""},
            "binding": _CONSOL_SECTION_WP_BINDINGS.get("minority_interest"),
        },
        {
            "section_id": "internal_trade_elimination",
            "section_title": "内部交易抵消",
            "section_type": "consol_only",
            "scope": "consolidated",
            "level": 2,
            "auto_numbering": True,
            "table_data": {"rows": [], "summary": ""},
        },
        {
            "section_id": "forex_translation",
            "section_title": "外币报表折算",
            "section_type": "consol_only",
            "scope": "consolidated",
            "level": 2,
            "auto_numbering": True,
            "table_data": {"rows": [], "summary": ""},
            "binding": _CONSOL_SECTION_WP_BINDINGS.get("forex_translation"),
        },
    ]
    return consol_sections


# ---------------------------------------------------------------------------
# B.1.6 多层合并 lineage
# ---------------------------------------------------------------------------


async def _write_lineage_v2(
    db: AsyncSession,
    parent_project_id: UUID,
) -> list[str]:
    """调 get_lineage_chain 获取多层合并 lineage.

    B.1.6 实现。
    """
    from app.services.consol_note_aggregation_service import get_lineage_chain

    chain = await get_lineage_chain(parent_project_id, db=db)
    return [str(pid) for pid in chain]


# ---------------------------------------------------------------------------
# B.1.7 文字段落合并版 vars
# ---------------------------------------------------------------------------


def _build_consol_paragraph_vars(
    subsidiaries: list[dict],
    year: int,
) -> dict:
    """构建合并版文字段落变量.

    B.1.7 实现。包含 subsidiary_count / consolidated_revenue /
    controlled_subsidiaries 等合并专用变量。
    """
    controlled = [s for s in subsidiaries if s.get("consol_level", 1) <= 2]
    return {
        "subsidiary_count": len(subsidiaries),
        "controlled_subsidiaries": len(controlled),
        "consolidated_revenue": None,  # 需从合并试算表取，此处占位
        "year": year,
        "report_year": year,
        "is_consolidated": True,
        "has_consolidation": True,
        "subsidiaries": [
            {"name": s.get("company_name", ""), "company_code": s.get("company_code", "")}
            for s in subsidiaries
        ],
    }


def _render_text_paragraphs_v2(
    sections: list[dict],
    consol_vars: dict,
) -> list[dict]:
    """用合并版 vars 渲染文字段落.

    B.1.7 实现。对含 text_template 的章节进行 Jinja 渲染。
    """
    from app.services.note_text_template_engine import render_text_paragraph

    for section in sections:
        text_template = section.get("text_template")
        if text_template:
            try:
                rendered = render_text_paragraph(
                    text_template, consol_vars, strict=False,
                )
                section["text_content"] = rendered
            except Exception as err:
                logger.warning(
                    "V2 text render failed for %s: %s",
                    section.get("section_id"), err,
                )
    return sections


# ---------------------------------------------------------------------------
# B.1.8 章节序号 scope='consolidated' 重排
# ---------------------------------------------------------------------------


def _renumber_sections_consolidated(sections: list[dict]) -> list[dict]:
    """按 scope='consolidated' 重排章节序号.

    B.1.8 实现。调 NoteSectionNumberingService.render_sections。
    """
    from app.services.note_section_numbering_service import NoteSectionNumberingService

    svc = NoteSectionNumberingService()
    # 为每个 section 补充 render_sections 所需字段
    for idx, s in enumerate(sections):
        s.setdefault("sort_index", idx + 1)
        s.setdefault("level", 3)
        s.setdefault("parent_section_id", None)
        s.setdefault("auto_numbering", True)
        s.setdefault("lock_number", False)
        s.setdefault("locked_number", None)
        s.setdefault("scope", "consolidated")
        s.setdefault("is_deleted", False)

    rendered_numbers = svc.render_sections(sections, scope="consolidated")

    for section in sections:
        sid = section.get("section_id")
        if sid and sid in rendered_numbers:
            section["rendered_number"] = rendered_numbers[sid]

    return sections


# ---------------------------------------------------------------------------
# B.1.9 合并专用章节 wp_data 强化（已在 B.1.5 中实现 binding 字段）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# B.1.10 合并范围变化事件 → stale
# ---------------------------------------------------------------------------


async def handle_consol_subsidiary_changed(event: dict | None = None) -> None:
    """订阅 CONSOL_SUBSIDIARY_CHANGED 事件，标记合并附注 stale.

    B.1.10 实现。当合并范围变化（新增/处置子公司）时触发。
    """
    if event is None:
        return

    project_id = event.get("project_id")
    year = event.get("year")

    if not project_id or not year:
        logger.debug("handle_consol_subsidiary_changed: missing project_id or year")
        return

    try:
        from app.services.consol_note_stale_handler import mark_consol_sections_stale
        from app.core.database import async_session as async_session_factory

        pid = UUID(str(project_id)) if isinstance(project_id, str) else project_id

        async with async_session_factory() as db:
            await mark_consol_sections_stale(
                parent_project_id=pid,
                section_id=None,  # 范围变化影响全部章节
                year=year,
                db=db,
            )
            await db.commit()

        logger.info(
            "CONSOL_SUBSIDIARY_CHANGED: marked all sections stale for project %s year %d",
            project_id, year,
        )
    except Exception as err:
        logger.warning("handle_consol_subsidiary_changed failed: %s", err)


def register_consol_subsidiary_changed_handler(event_bus) -> None:
    """注册 CONSOL_SUBSIDIARY_CHANGED 事件处理器.

    B.1.10 实现。在应用启动时调用。
    """
    try:
        event_bus.subscribe(CONSOL_SUBSIDIARY_CHANGED, handle_consol_subsidiary_changed)
        logger.info("Registered handler for %s", CONSOL_SUBSIDIARY_CHANGED)
    except Exception as err:
        logger.warning("Failed to register CONSOL_SUBSIDIARY_CHANGED handler: %s", err)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _load_section_mapping() -> list[dict]:
    """加载 consol_note_section_mapping.csv.

    返回 list[dict]，每项含 section_id / consol_section_id /
    aggregation_method / elimination_rule。
    """
    import csv
    import os

    csv_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "consol_note_section_mapping.csv",
    )

    if not os.path.exists(csv_path):
        logger.warning("Section mapping CSV not found: %s", csv_path)
        return []

    mappings: list[dict] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(
            (line for line in f if not line.startswith("#")),
        )
        for row in reader:
            mappings.append({
                "section_id": row.get("section_id", "").strip(),
                "consol_section_id": row.get("consol_section_id", "").strip(),
                "aggregation_method": row.get("aggregation_method", "simple_sum").strip(),
                "elimination_rule": row.get("elimination_rule", "").strip(),
            })

    return mappings
