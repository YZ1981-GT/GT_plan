"""底稿 sheet 归类服务

实现 9 类（A~I）→ componentType 白名单映射 + 项目级覆盖合并。
Requirements: 1.2（9 类全覆盖）+ 3.9（决策树禁止 Univer 兜底）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_wp_sheet_override import ProjectWorkpaperSheetOverride
from app.models.workpaper_models import WorkpaperSheetClassification
from app.services.wp_component_type_mapping import class_code_to_component

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
    "wp-popup-signing",
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
    "confirmation-summary",
    "confirmation-entity-verify",
    "confirmation-followup",
    "confirmation-diff-reconcile",
    "confirmation-diff-checklist",
    "confirmation-alternative-d05",
    "confirmation-alternative-d06",
    "confirmation-reliability",
    "confirmation-fraud-risk",
    "a1-11-signing-form",
    "a1-12-dual-checklist",
    "b50-risk-assessment",
    "b22a-control-matrix",
    "b22b-deficiency-evaluation",
    "b23-process-control",
    "b30-group-audit",
    "a17-bundle",
    "a16-bundle",
    "a10-bundle",
    "a12-bundle",
    "review-bundle",
    "b2-bundle",
    "b13-bundle",
    "b19-bundle",
    "b51-bundle",
    "c-control-test",
    "d1-notes-receivable",
    "d2-accounts-receivable",
    "a1-15-disclosure-checklist",
    "a1-17-corresponding-data",
    "a3-8-goodwill-impairment",
    "a17-6-closing-meeting",
    "a18-1-regulatory-submission",
    "a18-2-regulatory-communication",
    "a8-1-other-info-representation",
    "a11-1-subsequent-events-inquiry",
    "a17-3-consultation-record",
    "a17-4-disagreement-record",
    "a17-3-1-consultation-execution",
    "a17-7-independence-declaration",
    "a9-1-deficiency-letter",
    "a9-2-deficiency-letter-governance",
    "a27-1-it-audit-memo",
    "a12-1-legal-confirmation",
    "a10-1-governance-communication",
    "a17-1-audit-summary",
    "a17-2-1-kam",
    "a5-1-cashflow-audit",
    "f2-stocktake-bundle",
    "b1-4-due-diligence-report",
    "d4-operating-revenue",
    "d3-prepaid-accounts",
    "d5-receivables-financing",
    "d6-contract-assets",
    "d7-contract-liabilities",
    "e1-monetary-fund",
    "confirmation-alternative-f05",
    "confirmation-alternative-f06",
    "c1-entity-level-control",
    "c22-itgc-bundle",
    "c23-journal-entry-control",
    "c24-journal-entry-detail",
    "c25-internal-audit-reliance",
    "c26-info-processing-control",
    "l1-short-term-loans",
    "l2-interest-payable",
    "l3-long-term-loans",
    "l4-bonds-payable",
    "l5-long-term-payables",
    "l6-special-payables",
    "l7-other-noncurrent-liabilities",
    "l8-financial-expenses",
    "m1-dividends-payable",
    "m2-paid-in-capital",
    "m3-treasury-stock",
    "m4-capital-reserve",
    "m5-surplus-reserve",
    "m6-retained-earnings",
    "m7-special-reserve",
    "m8-general-risk-reserve",
    "m9-other-comprehensive-income",
    "m10-other-equity-instruments",
    "g7-long-term-equity-main",
    "g7-long-term-equity-method",
    "g7-long-term-equity-subsidiary",
    "h10-asset-disposal-income",
    "h1-fixed-assets",
    "h5-oil-gas-assets",
    "h7-biological-assets",
    "h2-construction-in-progress",
    "h3-investment-property",
    "h4-engineering-materials",
    "h6-asset-disposal-clearing",
    "h8-right-of-use-assets",
    "h9-lease-liabilities",
    # F/G 循环专用组件（wp_code_overrides 映射）
    "confirmation-alternative-g06",
    "confirmation-alternative-h05",
    "confirmation-alternative-k05",
    "confirmation-alternative-k06",
    "confirmation-diff-securities",
    "f1-prepayment",
    "f2-inventory-main",
    "f2-inventory-special",
    "f2-inventory-valuation-impairment",
    "f3-notes-payable",
    "f4-accounts-payable",
    "f5-cost-of-sales",
    "g1-trading-financial-assets",
    "g2-interest-receivable",
    "g3-dividend-receivable",
    "g4-bond-investment-main",
    "g4-bond-investment-sppi",
    "g4-bond-investment-ecl",
    "g5-long-term-receivable",
    "g6-other-bond-investment-main",
    "g6-other-bond-investment-sppi",
    "g6-other-bond-investment-ecl",
    "g8-other-equity-instruments",
    "g9-other-noncurrent-financial",
    "g10-trading-financial-liabilities",
    "g11-investment-income",
    "g12-net-hedge-gains",
    "g13-fair-value-changes",
    "g14-credit-impairment-loss",
    "n1-deferred-tax-assets",
    "n2-taxes-payable",
    "n3-deferred-tax-liabilities",
    "n4-taxes-and-surcharges",
    "n5-income-tax-expense",
    "s3-policy-change",
    "s4-nonmonetary-exchange",
    "s5-debt-restructuring",
    "s6-fund-occupation",
    "s12-cpa-expert",
    "s13-mgmt-expert",
    "s14-accounting-estimate",
    "s15-eps-roe",
    "s20-revenue-deduction",
    "s21-data-asset",
    "s32-fraud-bundle",
    "s33-ann14-bundle",
    "s34-ipo-bundle",
    "s35-refinance-bundle",
    # I 循环专用组件
    "i1-intangible-assets",
    "i2-development-expenditure",
    "i3-goodwill",
    "i4-long-term-prepaid",
    "i5-other-noncurrent-assets",
    "i6-research-development-expense",
    # J 循环专用组件（职工薪酬）
    "j1-employee-compensation",
    "j2-defined-benefit-plan",
    "j3-share-based-payment",
    # K 循环专用组件（其他应收款/其他流动资产/其他应付款/其他流动负债/预计负债）
    "k1-other-receivables",
    "k2-other-current-assets",
    "k3-other-payables",
    "k4-other-current-liabilities",
    "k5-provisions",
    "k6-held-for-sale",
    "k7-deferred-income",
    "k8-selling-expenses",
    "k9-admin-expenses",
    "k10-other-income",
    "k11-asset-impairment-loss",
    "k12-non-operating-income",
    "k13-non-operating-expense",
}

# wp_code 级专用路由覆盖（优先于 class_code 派生）
# 特定底稿直接路由到专用 HTML 组件，不经过 class_code 映射
# 数据外置于 backend/app/data/wp_code_overrides.json，启动时加载+验证+热重载
from app.services.wp_code_override_loader import load_wp_code_overrides

_WP_CODE_OVERRIDE: dict[str, str] = load_wp_code_overrides()

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
    # 示例/参考类底稿 → 静态文档（只读 HTML 展示，不走函证/程序表渲染）
    if "（示例）" in sheet_name or "（参考）" in sheet_name:
        return "h-static-doc"
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
    # 多文件聚合：该 sheet 内容来源模板文件路径（str）。空列表=走全局 template_path。
    # 由 wp_account_package_resolver 填充（spec workpaper-account-multifile-aggregation）。
    source_files: list[str] = field(default_factory=list)


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
            ).order_by(WorkpaperSheetClassification.created_at)
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


def derive_component_type(
    classification: ClassificationResult,
    ignore_wp_code_override: bool = False,
) -> str:
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

    Args:
        ignore_wp_code_override: True 时跳过 wp_code 级 override 检查，强制按 class_code 派生。
            用于多 sheet 底稿（如 D2 含目录/程序表/审定表/附注），避免 wp_code override
            把所有 sheet 压平成同一 componentType。

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
    # 多 sheet 底稿（ignore_wp_code_override=True）跳过此检查，按 class_code 各自派生
    if not ignore_wp_code_override:
        wp_code_override = _WP_CODE_OVERRIDE.get(classification.wp_code)
        if wp_code_override:
            return wp_code_override

    if not class_code:
        raise ClassificationNotFoundError(
            f"Sheet '{classification.sheet_name}' (wp_code='{classification.wp_code}') "
            "has no class_code. Cannot derive componentType — "
            "Univer fallback is prohibited (Requirement 3.9)."
        )

    # 通过共享纯函数映射 class_code → componentType（design §2）
    result = class_code_to_component(class_code)
    if result is not None:
        return result

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
