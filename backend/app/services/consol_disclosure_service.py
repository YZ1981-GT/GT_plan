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
from app.models.consolidation_schemas import ConsolDisclosureSection
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
