"""自定义底稿公式绑定 API（custom-workpaper-formula-binding 组①任务 2）。

- GET    /api/workpapers/{wp_id}/formulas
- PUT    /api/workpapers/{wp_id}/formulas
- DELETE /api/workpapers/{wp_id}/formulas/{formula_id}
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex
from app.services.d_cycle_extraction.anchor_registry import is_known_anchor
from app.services.d_cycle_extraction.presets import (
    SOURCE_DISABLED,
    resolve_effective as resolve_effective_extraction,
    tier_a_semantic,
    tier_b_provenance,
)
from app.services.wp_formula_eval_service import (
    evaluate_wp_formula_expression,
    find_unsupported_formula_functions,
)
from app.routers.wp_surfaced_formulas import CYCLE_SHEET_FORMULAS as _CYCLE_SHEET_FORMULAS
from app.services.wp_formula_service import wp_formula_service
from app.services.wp_parsed_data_service import (
    format_cell_display_value,
    write_cell_to_parsed_data,
)

logger = logging.getLogger(__name__)


# ─── E1 货币资金 各 sheet 取数/计算/逻辑审核公式目录（只读 surfacing）──────────────
# 与 useE1FormulaEngine（共享纯函数公式引擎）+ 各 sheet composable 同源，不臆造。
# 让公式管理中心底稿节点对 E1-1 之外的每张 sheet 也能体现其取数逻辑（对齐 E1-1 标准）。
# 格式：sheet_code -> [(项目名称, 公式, 分类, 说明, 来源), ...]
# 分类：取数 / 计算 / logic_check(逻辑审核) / 只读溯源
_E1_SHEET_FORMULAS: dict[str, list[tuple[str, str, str, str, str]]] = {
    # E1-2 现金明细表（按币种）
    "E1-2": [
        ("期末余额（原币）", "期初余额 + 本期增加 - 本期减少", "计算",
         "各币种期末原币余额链式计算（calcCashBalance）", "E1-2 现金明细表"),
        ("期末折算人民币", "期末余额（原币） × 期末汇率", "计算",
         "外币现金按期末汇率折算人民币（calcFxConvert）", "E1-2 现金明细表"),
        ("期末审定数（人民币）", "期末折算人民币 + 审计调整（原币） × 期末汇率", "计算",
         "期末审定数 = 期末折算人民币 + 审计调整折算", "E1-2 现金明细表"),
        ("现金合计（期末未审·人民币）", "Σ 各币种期末折算人民币", "计算",
         "现金明细合计写入 E1-cash-detail-total-unaudited，供 E1-1 审定表取数", "E1-2 现金明细表"),
    ],
    # E1-3 银行存款明细表（本金/应计利息 × 银行机构/财务公司/其他货币资金）
    "E1-3": [
        ("期末余额", "期初余额 + 本期增加 - 本期减少", "计算",
         "银行存款期末余额链式计算（本币口径）", "E1-3 银行存款明细表"),
        ("审定数", "期末余额 + 审计调整", "计算",
         "审定数 = 期末余额 + 审计调整（单列合并）", "E1-3 银行存款明细表"),
        ("外币各列（人民币）", "外币原币各列 × 期末汇率", "计算",
         "多币种版：期初/增加/减少/期末原币按汇率折算人民币（calcFxConvert）", "E1-3 银行存款明细表"),
        ("账户-对账单差异", "审定数 − 对账单余额", "logic_check",
         "账面审定数与银行对账单余额核对，差异≠0 须查明", "E1-3 银行存款明细表"),
        ("函证差异", "审定数 − 函证回函金额", "logic_check",
         "账面审定数与银行函证回函金额核对（函证回函自动回写）", "E1-3 银行存款明细表 / D0 函证"),
        ("存款本金合计（期末未审）", "Σ（银行机构 + 财务公司）期末余额", "计算",
         "写入 E1-bank-detail-principal-total-unaudited，供 E1-1 银行存款取数", "E1-3 银行存款明细表"),
        ("其他货币资金合计（期末未审）", "Σ 其他货币资金组期末余额", "计算",
         "写入 E1-bank-detail-other-total-unaudited，供 E1-1 其他货币资金取数", "E1-3 银行存款明细表"),
    ],
    # E1-4 数字货币明细表
    "E1-4": [
        ("期末余额（数量）", "期初数量 + 本期增加 - 本期减少", "计算",
         "数字货币期末数量链式计算（calcCashBalance）", "E1-4 数字货币明细表"),
        ("本位币折算", "数字货币数量 × 单位价格（汇率）", "计算",
         "数字货币按期末单价折算本位币（calcFxConvert）", "E1-4 数字货币明细表"),
        ("数字货币合计（期末未审）", "Σ 各数字货币本位币折算", "计算",
         "写入 E1-digital-total-unaudited，供 E1-1 其他货币资金/审定表取数", "E1-4 数字货币明细表"),
    ],
    # E1-5 调整分录汇总表
    "E1-5": [
        ("借贷平衡校验", "Σ 借方金额 = Σ 贷方金额", "logic_check",
         "调整分录汇总底部借贷平衡校验（isBalanced，容差 0.001）", "E1-5 调整分录"),
        ("按项目归集账项调整", "按项目汇总各调整分录借贷净额", "取数",
         "调整分录按货币资金项目归集，回写 E1-1 审定表各项账项调整列", "E1-5 调整分录"),
    ],
    # E1-6 银行存款余额调节表
    "E1-6": [
        ("调节后企业余额", "账面余额 + 银行已收企业未收 − 银行已付企业未付", "计算",
         "企业账面侧调节（calcReconciled）", "E1-6 余额调节表"),
        ("调节后银行余额", "对账单余额 + 企业已收银行未收 − 企业已付银行未付", "计算",
         "银行对账单侧调节（calcReconciled）", "E1-6 余额调节表"),
        ("调节差异", "调节后企业余额 − 调节后银行余额", "logic_check",
         "两侧调节后余额应相等，差异≠0（容差 0.005）须查明", "E1-6 余额调节表"),
        ("对账单余额核对", "E1-6 对账单余额 ↔ E1-3 同账号对账单余额", "logic_check",
         "余额调节表对账单余额与 E1-3 银行明细同账号交叉校验", "E1-3 银行存款明细表"),
    ],
    # E1-7 库存现金（人民币）盘点表
    "E1-7": [
        ("盘点差异", "实盘数 − 账面余额", "计算",
         "库存现金盘点差异（calcCountDiff），差异≠0 盘盈/盘亏须说明原因", "E1-7 库存现金盘点表"),
    ],
    # E1-8 库存现金（外币）盘点表
    "E1-8": [
        ("盘点差异（原币）", "实盘数（原币） − 账面余额（原币）", "计算",
         "外币现金盘点差异（calcCountDiff）", "E1-8 外币现金盘点表"),
        ("折人民币", "盘点金额（原币） × 汇率", "计算",
         "外币盘点金额折算人民币（calcFxConvert）", "E1-8 外币现金盘点表"),
    ],
    # E1-9 银行存单盘点表
    "E1-9": [
        ("存单金额合计", "Σ 各存单金额", "计算",
         "银行存单盘点金额合计", "E1-9 银行存单盘点表"),
    ],
    # E1-10 银行账户核对表（清单完整性）
    "E1-10": [
        ("账户清单完整性核对", "E1-10 账户清单 ↔ E1-3 银行明细账号双向核对", "logic_check",
         "账户清单与银行明细双向差集核对，识别遗漏/多余账户", "E1-3 银行存款明细表"),
        ("疑似账外账户", "清单标记「账面无记录」的账户", "logic_check",
         "清单有而账面无（hasBookRecord=否）→ 完整性认定风险提示", "E1-10 银行账户核对表"),
    ],
    # E1-14 货币资金分析表
    "E1-14": [
        ("期末审定数（取数）", "取自 E1-1 各项审定合计（E1-adj-total-1001/1002/1012）", "取数",
         "分析表期末数跨 sheet 取自 E1-1 审定表科目合计", "E1-1 审定表"),
        ("变动额", "期末审定数 − 期初审定数", "计算",
         "本期货币资金较期初变动额（calcChange）", "E1-14 分析表"),
        ("变动率", "变动额 ÷ 期初审定数", "计算",
         "变动率（calcChangeRate 模板口径）；|变动率|>30% 须填写波动原因", "E1-14 分析表"),
        ("银行存款÷资产总额", "银行存款 ÷ 资产总额", "计算",
         "资产结构比率", "E1-14 分析表"),
        ("定期存款÷银行存款", "定期存款 ÷ 银行存款", "计算",
         "存款期限结构比率", "E1-14 分析表"),
        ("（定期存款+大额存单）÷银行存款", "（定期存款 + 大额存单）÷ 银行存款", "计算",
         "定期+大额存单占比", "E1-14 分析表"),
        ("受限货币资金÷货币资金", "受限货币资金 ÷ 货币资金", "计算",
         "受限资金占比", "E1-14 分析表"),
        ("存放财务公司款项÷货币资金", "存放财务公司款项 ÷ 货币资金", "计算",
         "关联财务公司资金占比", "E1-14 分析表"),
        ("货币资金÷贷款总额", "货币资金 ÷ 贷款总额", "计算",
         "「存贷双高」识别比率", "E1-14 分析表"),
        ("银行存款÷货币资金（集中度）", "银行存款 ÷ 货币资金", "计算",
         "银行存款集中度比率", "E1-14 分析表"),
    ],
    # E1-15 利息收入月度分析表
    "E1-15": [
        ("计算利息（按月）", "月均余额 × 年利率 ÷ 12", "计算",
         "各账户逐月测算利息", "E1-15 利息收入月度分析"),
        ("利息差异", "计算利息合计 − 账面利息合计", "logic_check",
         "测算利息与账面已记利息核对，差异须查明", "E1-15 利息收入月度分析"),
        ("利息结构变动额", "本期利息 − 上期利息", "计算",
         "按存款类型的利息结构同比变动", "E1-15 利息收入月度分析"),
    ],
    # E1-20 应计利息测算表
    "E1-20": [
        ("计息天数", "截止日 − 起息日", "计算",
         "应计利息计息天数（日期差）", "E1-20 应计利息测算"),
        ("应计利息（原币）", "原币金额 × 计息天数 × 日利率", "计算",
         "应计利息原币测算（calcAccruedInterest）", "E1-20 应计利息测算"),
        ("应计利息（人民币）", "应计利息（原币） × 汇率", "计算",
         "应计利息折算人民币（calcFxConvert）", "E1-20 应计利息测算"),
        ("应计利息分项汇总", "按财务公司/银行/其他/数字货币四类汇总应计利息", "取数",
         "分项汇总供 E1-1 审定表应计利息取数", "E1-20 应计利息测算"),
    ],
    # E1-21 银行存款截止测试
    "E1-21": [
        ("跨期判定", "凭证日期 > 资产负债表日 → 跨期", "logic_check",
         "银行存款收支截止测试跨期判定（determineCutoff），跨期行高亮", "E1-21 银行存款截止测试"),
    ],
    # E1-22 其他货币资金截止测试
    "E1-22": [
        ("跨期判定", "凭证日期 > 资产负债表日 → 跨期", "logic_check",
         "其他货币资金收支截止测试跨期判定（determineCutoff），跨期行高亮", "E1-22 其他货币资金截止测试"),
    ],
    # E1-23 收支检查情况表
    "E1-23": [
        ("借方检查比例", "借方检查金额合计 ÷ 账面借方发生额", "计算",
         "收入方向抽查覆盖率", "E1-23 收支检查表"),
        ("贷方检查比例", "贷方检查金额合计 ÷ 账面贷方发生额", "计算",
         "支出方向抽查覆盖率", "E1-23 收支检查表"),
        ("账证金额核对", "账面金额 ↔ 收/付款单据金额", "logic_check",
         "账面金额与外部单据金额不符时标记异常（suggestAbnormal）", "E1-23 收支检查表"),
    ],
}


router = APIRouter(
    prefix="/api/workpapers/{wp_id}",
    tags=["wp-formula"],
)


class FormulaSaveRequest(BaseModel):
    sheet_name: str = Field(..., description="Sheet 名称")
    target_cell: str = Field(..., description="写入目标单元格，如 B5")
    expression: str = Field(..., description="公式表达式")
    year: int = Field(..., description="校验悬空引用所需年度")
    template_type: str = Field("soe", description="模板类型")
    category: str | None = None
    description: str | None = None
    # ── formula-management-library 三类型（Req 14.5）──
    formula_type: str = Field(
        "auto_calc",
        description="公式类型 auto_calc / logic_check / reasonability",
    )
    refs: list | None = Field(
        None, description="规范化引用列表（addr_id / formula_ref）"
    )
    issue_description: str | None = Field(
        None, description="logic_check 不通过时的问题描述"
    )
    hint_text: str | None = Field(
        None, description="reasonability 触发时的提示文案"
    )


class FormulaItemResponse(BaseModel):
    id: str
    project_id: str
    wp_id: str
    sheet_name: str
    target_cell: str
    expression: str
    category: str | None = None
    description: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def _formula_to_dict(f: WpFormula) -> dict:
    return {
        "id": str(f.id),
        "project_id": str(f.project_id),
        "wp_id": str(f.wp_id),
        "sheet_name": f.sheet_name,
        "target_cell": f.target_cell,
        "expression": f.expression,
        "category": f.category,
        "description": f.description,
        "formula_type": f.formula_type,
        "refs": f.refs,
        "issue_description": f.issue_description,
        "hint_text": f.hint_text,
        "last_computed_at": (
            f.last_computed_at.isoformat() if f.last_computed_at else None
        ),
        "created_by": str(f.created_by) if f.created_by else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


async def _load_wp(db: AsyncSession, wp_id: UUID) -> WorkingPaper:
    wp = (
        await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    return wp


# D-cycle 底稿编码识别（D1–D7）；捕获基础码用于预设/锚点/溯源查询。
# wp_code 可能是整册码 "D6" 或 sheet 级 "D6-1" → 统一归到基础码 "D6"。
_D_CYCLE_RE = re.compile(r"^(D[1-7])(?:-|$)")


async def _resolve_wp_code(db: AsyncSession, wp: WorkingPaper) -> str | None:
    """经 wp.wp_index_id 解析底稿编码（与 save 路径同款）。"""
    if not wp.wp_index_id:
        return None
    return (
        await db.execute(
            sa.select(WpIndex.wp_code).where(WpIndex.id == wp.wp_index_id)
        )
    ).scalar_one_or_none()


async def _resolve_project_year(
    db: AsyncSession, project_id: UUID
) -> int | None:
    """解析项目审计年度（`projects.audit_year` 物化列，与 render 策略同源，不臆造）。

    d-cycle-tier-a-writeback-detail-seed Task 3.1：GET Tier A 求值需 year，而
    `_build_extraction_block(db, wp)` 无 year 参。从 `projects.audit_year`（render 策略
    `_d6_contract_assets` 等唯一年度来源）解析；拿不到（列空/查询失败）→ None → 该底稿
    全部 Tier A value=None（fail-open，不阻断 GET / R2.3）。
    """
    try:
        year = (
            await db.execute(
                sa.select(Project.audit_year).where(Project.id == project_id)
            )
        ).scalar_one_or_none()
    except Exception as e:  # noqa: BLE001 — 年度拿不到即 fail-open，不阻断 GET
        logger.warning(
            "resolve project audit_year failed project_id=%s: %s", project_id, e
        )
        return None
    return int(year) if year is not None else None


async def _evaluate_tier_a_value(
    db: AsyncSession,
    project_id: UUID,
    year: int | None,
    binding: dict,
) -> object | None:
    """求值单条 Tier A binding 的 `value`（fail-open，单条失败返回 None）.

    d-cycle-tier-a-writeback-detail-seed Task 3.1（Requirements 2.1/2.3 / Property 4/5）：
      - year 缺失 / disabled 绑定（用户禁用，表达式空）/ 表达式空 → None（不求值，避免误导 0）。
      - 求值经 `evaluate_wp_formula_expression`（内部走 `get_active_filter`，与 Tier B 预填/
        保存同数据集版本口径 / Property 4）。
      - 求值抛异常 或 有 eval_errors（如悬空引用）→ None（不静默落错误/0，对齐 R1.4 语义）；
        单条 fail-open 不阻断其它条目或整个 GET（R2.3）。
    """
    if year is None:
        return None
    if binding.get("source") == SOURCE_DISABLED:
        return None
    expression = (binding.get("expression") or "").strip()
    if not expression:
        return None
    try:
        result, errs = await evaluate_wp_formula_expression(
            db,
            project_id=project_id,
            year=year,
            expression=expression,
        )
    except Exception as e:  # noqa: BLE001 — 单条 fail-open，不阻断其它条目/整个 GET
        logger.warning(
            "Tier A GET 求值失败 anchor=%s: %s", binding.get("anchor"), e
        )
        return None
    if errs:
        # 有 eval_errors（悬空引用等）→ 该条 value=None（不返回错误/0，R2.3 对齐 R1.4）。
        return None
    return format_cell_display_value(result)


async def _build_extraction_block(
    db: AsyncSession, wp: WorkingPaper
) -> dict | None:
    """构建 D-cycle 四表库提取分层块（Tier A 可编 + Tier B 只读溯源）.

    spec: d-cycle-four-table-extraction-formulas Task 3.3
      (Requirements 5.2, 5.3, 3.1, 3.2 / Property 5, 8, 11)

    - 灰度开关关闭（默认）→ 返回 None（GET 表现同当前，无 extraction 字段 / R7.1）。
    - 非 D 循环底稿（wp_code 非 D1–D7）→ 返回 None（GET 表现同当前）。
    - D 循环 + 开关开 → 返回 `{wp_code, enabled, note, tierA, tierB}`：
        * tierA = `resolve_effective`（预设 ∪ 用户 wp_formula，读时收敛 source=
          preset/custom/disabled，未知锚点丢弃 / Property 5, 8）；每条**求值填 `value`**
          （d-cycle-tier-a-writeback-detail-seed Task 3.1 / R2）。
        * tierB = `tier_b_provenance`（只读溯源，描述四表库 prefill 填什么，只登记确实
          接入 Tier B 的循环，当前仅 D6 / R7.4）；`value` 仍为 None（不重求值，seed 由
          render 的 adjudication_prefill 提供，行为不变 / R2.5）。
    - **Tier A 逐条求值填 value**（d-cycle-tier-a-writeback-detail-seed Task 3.1 / R2）：
      经 `evaluate_wp_formula_expression`（get_active_filter 同 Tier B/保存口径）；条目有界
      （≤2/循环）逐条求值，单条失败/有 eval_errors → 该条 value=None（fail-open，不阻断其它
      条目或整个 GET / R2.3）；year 从 `projects.audit_year` 解析，拿不到 → 全部 value=None。
    """
    if not settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED:
        return None
    wp_code = await _resolve_wp_code(db, wp)
    if not wp_code:
        return None
    m = _D_CYCLE_RE.match(wp_code)
    if not m:
        return None
    base = m.group(1)

    tier_a = await resolve_effective_extraction(db, wp.id, base, wp.project_id)
    # d-cycle-tier-a-writeback-detail-seed Task 3.1（R2 / Property 4/5）：GET 对每条 Tier A
    # binding 求值填 value（get_active_filter 同口径，单条 fail-open）。year 从 projects.audit_year
    # 解析（拿不到 → 全部 value=None）。P1-4：附取数语义标注（Tier A = trial_balance 审定核对
    # 标量，与 Tier B tb_balance 未审 seed 口径消歧）。
    year = await _resolve_project_year(db, wp.project_id)
    for b in tier_a:
        b["semantic"] = tier_a_semantic(b.get("expression"))
        b["value"] = await _evaluate_tier_a_value(db, wp.project_id, year, b)
    tier_b = tier_b_provenance(base)

    return {
        "wp_code": base,
        "enabled": True,
        "note": (
            "Tier A 可编辑公式（预设∪用户，读时收敛，取 trial_balance 审定核对标量，"
            "已逐条求值填当前值）+ Tier B 四表库未审/明细预填只读溯源"
            "（tb_balance/tb_aux_balance/序时账，value 由 render adjudication_prefill 提供）。"
        ),
        "tierA": tier_a,
        "tierB": tier_b,
    }


async def _build_surfaced_formulas(db: AsyncSession, wp: WorkingPaper) -> list[dict]:
    """专属组件（数据存 checklist_responses、无 wp_formula 网格记录）的取数公式 surfacing。

    这些底稿的取数公式内嵌在 render 策略 / 底稿内四表面板，不落 wp_formula → 公式管理中心
    对底稿节点为空。此处按 wp_code 组装**只读**取数公式条目，让公式管理中心体现该底稿取数逻辑。

    E1 试点（货币资金）：
    - 审定合计 ↔ 试算平衡表核对公式（科目来自报表规则映射 report_config BS-002，项目级可覆盖）；
    - 各源科目期末余额取数 `TB('code','期末余额')`（四表库，供明细/审定表取数）。

    返回 [] 表示该底稿无 surfacing（GET 表现同当前，零回归）。
    """
    wp_code = await _resolve_wp_code(db, wp)
    if not wp_code:
        return []
    base = re.sub(r"-\d+[A-Z]?$", "", wp_code)  # E1-1 / E1A → E1
    out: list[dict] = []
    if base == "E1":
        # 1) TB 核对合计（科目集来自报表规则映射 BS-002，项目级可覆盖）→ 归属审定表 E1-1
        try:
            from app.services.report_account_mapping import (
                resolve_report_line_account_codes,
            )
            codes = await resolve_report_line_account_codes(
                db, wp.project_id, "BS-002", fallback=["1001", "1002", "1012"]
            )
        except Exception:  # noqa: BLE001
            codes = ["1001", "1002", "1012"]
        check = " + ".join(f"TB('{c}','期末余额')" for c in codes)
        out.append({
            "id": "E1-surfaced-tb-check", "readonly": True,
            "sheet_codes": ["E1-1"],
            "row_code": "E1-1", "row_name": "货币资金 审定合计 ↔ 试算平衡表核对",
            "formula": check, "formula_category": "logic_check",
            "formula_description": "审定合计与试算平衡表（货币资金）核对；科目集来自报表规则映射 BS-002（项目级可覆盖）",
            "formula_source": "报表规则映射(report_config BS-002)",
        })
        # 1b) E1-1 审定表跨 sheet 取数 + 表间计算公式（只读，文档化审定表编制逻辑，归属 E1-1）
        #     与 useE1Adjudication 跨sheet取数/calcAudited/calcChange/calcChangeRate 同源。
        _E1_1_FORMULAS = [
            # 项目名称, 公式, 分类, 说明, 来源
            ("库存现金 · 期末未审数", "WP('E1-2','现金明细·期末未审合计')", "取数",
             "库存现金期末未审数跨 sheet 取自 E1-2 现金明细表合计", "E1-2 现金明细表"),
            ("银行存款（本金）· 期末未审数", "WP('E1-3','银行存款本金·期末未审合计')", "取数",
             "银行存款本金期末未审数跨 sheet 取自 E1-3 银行存款明细表", "E1-3 银行存款明细表"),
            ("其他货币资金（本金）· 期末未审数", "WP('E1-3','其他货币资金·期末未审合计')", "取数",
             "其他货币资金期末未审数跨 sheet 取自 E1-3 银行存款明细表其他组", "E1-3 银行存款明细表"),
            ("数字货币（本金）· 期末未审数", "WP('E1-4','数字货币·期末未审合计')", "取数",
             "数字货币期末未审数跨 sheet 取自 E1-4 数字货币明细表", "E1-4 数字货币明细表"),
            ("应计利息 · 期末未审数", "WP('E1-20','应计利息分项汇总(财务公司/银行/其他/数字货币)')", "取数",
             "应计利息按四类分项跨 sheet 取自 E1-20 应计利息测算", "E1-20 应计利息测算"),
            ("各项 · 期初/期末账项调整", "WP('E1-5','调整分录按项目归集')", "取数",
             "期初/期末账项调整跨 sheet 取自 E1-5 调整分录，按项目归集", "E1-5 调整分录"),
            ("期初审定数", "期初未审数 + 期初账项调整", "计算",
             "审定数 = 未审数 + 账项调整（自动计算，灰底列不可手工录入）", "表间计算"),
            ("期末审定数", "期末未审数 + 期末账项调整", "计算",
             "审定数 = 未审数 + 账项调整（自动计算，灰底列不可手工录入）", "表间计算"),
            ("变动额", "期末审定数 − 期初审定数", "计算",
             "本期审定数较期初变动额", "表间计算"),
            ("变动率", "变动额 ÷ 期初审定数", "计算",
             "变动率 = 变动额 / 期初审定数；超过 30% 须在原因分析列说明", "表间计算"),
            ("合计", "Σ（库存现金 + 银行存款本金 + 其他货币资金 + 数字货币 + 应计利息）", "计算",
             "货币资金审定合计（各项目审定数纵向汇总）", "表间计算"),
            ("差异数", "合计审定数 − 试算平衡表数", "logic_check",
             "审定合计与试算平衡表核对差异；差异≠0 须查明原因", "试算平衡表核对"),
        ]
        for i, (name, formula, cat, desc, src) in enumerate(_E1_1_FORMULAS):
            out.append({
                "id": f"E1-surfaced-adj-{i}", "readonly": True,
                "sheet_codes": ["E1-1"],
                "row_code": "E1-1", "row_name": name,
                "formula": formula, "formula_category": cat,
                "formula_description": desc, "formula_source": src,
            })
        # 1c) E1-1 之外各 sheet 的取数/计算/逻辑审核公式（对齐 E1-1 标准，逐 sheet 归属 sheet_codes）
        for sheet_code, entries in _E1_SHEET_FORMULAS.items():
            for i, (name, formula, cat, desc, src) in enumerate(entries):
                out.append({
                    "id": f"E1-surfaced-{sheet_code}-{i}", "readonly": True,
                    "sheet_codes": [sheet_code],
                    "row_code": sheet_code, "row_name": name,
                    "formula": formula, "formula_category": cat,
                    "formula_description": desc, "formula_source": src,
                })
        # 2) 按项目实际情况动态带入四表库**叶子**取数公式（1001/1002/1012 各叶子科目，
        #    与 E1 明细/审定表 render 同源 _build_four_table_prefill，过滤全零空账户）。
        #    **按 sheet 归属**（与底稿四表来源面板 ftSources 同口径）：
        #      cash(1001) → E1-2 现金明细；bank(1002) → E1-3 明细 + E1-10 账户核对；
        #      other(1012) → E1-3 明细 → 前端按选中 sheet 过滤，避免每个 sheet 显示同一份全量。
        _GROUP_SHEETS = {
            "cash": ["E1-2"],
            "bank": ["E1-3", "E1-10"],
            "other": ["E1-3"],
        }
        try:
            import types as _types
            from app.routers.wp_render_strategies._e1_monetary_fund import (
                _build_four_table_prefill,
            )
            year = await _resolve_project_year(db, wp.project_id)
            if year:
                _ctx = _types.SimpleNamespace(db=db, project_id=wp.project_id)
                prefill = await _build_four_table_prefill(_ctx, int(year))
                for gkey, glabel in (("cash", "库存现金"), ("bank", "银行存款"), ("other", "其他货币资金")):
                    for r in prefill.get(gkey, []) or []:
                        code = r.get("code") or ""
                        out.append({
                            "id": f"E1-surfaced-leaf-{code}", "readonly": True,
                            "sheet_codes": _GROUP_SHEETS.get(gkey, []),
                            "row_code": code, "row_name": f"{glabel} · {r.get('name', '')}".strip(" ·"),
                            "formula": r.get("formula") or f"TB('{code}','期末余额')",
                            "formula_category": "取数",
                            "formula_description": f"四表库叶子取数（{r.get('source', code)}），供货币资金明细/审定表取数",
                            "formula_source": "四表库(tb_balance 叶子)",
                        })
        except Exception as e:  # noqa: BLE001 — 叶子提取失败仍返回 TB 核对（不阻断）
            logger.warning("E1 surfaced 叶子提取失败 wp=%s: %s", wp.id, e)
    else:
        # 其他循环（D/F/G/H…）：静态公式目录，与各循环 FormulaEngine/Adjudication/CrossSheet 同源（不臆造）。
        # F2 灰度开时：F2-1 显式取数条目由 surface.py 动态产出（预设 ∪ 用户覆盖），
        # 替换 CYCLE_SHEET_FORMULAS 中 F2-1 的静态条目（其余 F2 sheet 仍用静态）。
        if base == "F2" and settings.F2_FOUR_TABLE_EXTRACTION_ENABLED:
            from app.services.f2_extraction.surface import build_f2_surfaced_formulas
            f2_dynamic = await build_f2_surfaced_formulas(db, wp)
            out.extend(f2_dynamic)
            # 静态目录中排除 F2-1（已由动态条目替代），其余 sheet 保持原静态
            catalog = _CYCLE_SHEET_FORMULAS.get(base)
            if catalog:
                catalog = {sc: entries for sc, entries in catalog.items() if sc != "F2-1"}
        else:
            catalog = _CYCLE_SHEET_FORMULAS.get(base)
        if catalog:
            for sheet_code, entries in catalog.items():
                # 非编码 sheet_code（如「附注上市」/「附注国企」，ACNR catalog 无独立可点节点，
                # note sheet 在 ACNR 里是编码节点如 D2-6~D2-13）→ 归到审定表 X-1（真实节点）。
                # 语义合理：附注披露金额取自审定表审定数，放审定表节点作下游取数溯源，
                # 避免挂不存在的节点导致前端按 sheet_codes 过滤后永不显示。
                is_coded = bool(re.match(r"^[A-Za-z]+\d+(-\d+)?$", sheet_code))
                target_sheet = sheet_code if is_coded else f"{base}-1"
                for i, (name, formula, cat, desc, src) in enumerate(entries):
                    out.append({
                        "id": f"{base}-surfaced-{sheet_code}-{i}", "readonly": True,
                        "sheet_codes": [target_sheet],
                        "row_code": target_sheet, "row_name": name,
                        "formula": formula, "formula_category": cat,
                        "formula_description": desc, "formula_source": src,
                    })
    return out


@router.get("/formulas")
async def list_formulas(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """列出该底稿的全部自定义公式（含 D-cycle 四表库提取分层，灰度开关 + 仅 D1–D7）。

    d-cycle-four-table-extraction-formulas Task 3.3：
    - 原始 `items`（用户已落库 wp_formula 行）保持向后兼容，不改形状。
    - 额外 `extraction`（仅 D 循环 + 灰度开关开启时出现）= `{tierA, tierB}`，供公式管理
      面板（Task 4.x）分层展示；OFF / 非 D 循环时无此字段，GET 表现同当前（零回归）。
    """
    wp = await _load_wp(db, wp_id)
    # 传 project_id 使 ownership 校验通过并真正列出该底稿公式（此前缺 project_id 恒空）。
    formulas = await wp_formula_service.list_by_wp(db, wp_id, project_id=wp.project_id)
    resp: dict = {
        "wp_id": str(wp_id),
        "count": len(formulas),
        "items": [_formula_to_dict(f) for f in formulas],
    }
    extraction = await _build_extraction_block(db, wp)
    if extraction is not None:
        resp["extraction"] = extraction
    # 专属组件取数公式 surfacing（E1 试点）：让公式管理中心底稿节点能体现取数逻辑（只读）。
    surfaced = await _build_surfaced_formulas(db, wp)
    if surfaced:
        resp["surfaced"] = surfaced
    return resp


@router.put("/formulas")
async def save_formula(
    wp_id: UUID,
    body: FormulaSaveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """保存（upsert）一条底稿公式；悬空引用返回 422。

    d-cycle-four-table-extraction-formulas 决策3（方案 a）：Tier A 可编辑公式
    只支持 TB/SUM_TB/WP（+ 字面量/四则运算/跨 sheet 引用）。含 AUX/PREV/序时账
    （LEDGER/COUNT_LEDGER）等未实现函数时返 422（FORMULA_UNSUPPORTED_FUNCTION），
    不静默落库、不静默求值为 0——这些复杂归集由 Tier B prefill 承担。
    """
    wp = await _load_wp(db, wp_id)

    # 不受支持函数硬阻断（写库前，仅作用于本编辑公式保存路径 = Tier A 入口）。
    unsupported = find_unsupported_formula_functions(body.expression)
    if unsupported:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "FORMULA_UNSUPPORTED_FUNCTION",
                "unsupported_functions": unsupported,
                "message": (
                    "公式含不受支持的函数 "
                    + "/".join(unsupported)
                    + "；可编辑公式仅支持 TB/SUM_TB/WP。AUX/PREV/序时账 等复杂"
                    "归集由四表库自动预填（Tier B）承担。"
                ),
            },
        )

    saved, issues = await wp_formula_service.save(
        db,
        project_id=wp.project_id,
        wp_id=wp_id,
        sheet_name=body.sheet_name,
        target_cell=body.target_cell,
        expression=body.expression,
        year=body.year,
        template_type=body.template_type,
        category=body.category,
        description=body.description,
        created_by=user.id,
        formula_type=body.formula_type,
        refs=body.refs,
        issue_description=body.issue_description,
        hint_text=body.hint_text,
    )
    if issues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "FORMULA_REF_NOT_FOUND", "issues": issues},
        )

    wp_code: str | None = None
    if wp.wp_index_id:
        idx = (
            await db.execute(
                sa.select(WpIndex.wp_code).where(WpIndex.id == wp.wp_index_id)
            )
        ).scalar_one_or_none()
        wp_code = idx

    # d-cycle-tier-a-writeback-detail-seed 决策1 / Task 2.1（Property 1/2/13）：
    # 按 is_known_anchor 路由 auto_calc 保存的目标单元——
    #   * D-cycle 锚点（base_wp_code 为 D1–D7 + target_cell ∈ known_anchors）+ 主灰度开关开
    #     → **跳过 write_cell_to_parsed_data**（专属组件读 checklist_responses 网格而非 parsed_data
    #       网格，写网格无意义且误导后续读 parsed_data 者）；仍求值以返回 evaluated_value 供前端
    #       即时本地显示；**不新增任何 checklist_responses/DB 写回**（render transient seed 才是
    #       "编辑即生效"的权威，见 Requirement 3）。
    #   * 普通网格 cell / 非 D-cycle / 主开关关 → 沿用现有 write_cell_to_parsed_data（逐字节零回归）。
    # base_wp_code：剥离 sheet 后缀（D6-1 → D6），与 anchor_registry / is_known_anchor 口径一致。
    base_wp_code: str | None = None
    if wp_code:
        _base_m = _D_CYCLE_RE.match(wp_code)
        if _base_m:
            base_wp_code = _base_m.group(1)
    is_dcycle_anchor = False
    if (
        settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED
        and base_wp_code
        and is_known_anchor(base_wp_code, body.target_cell)
    ):
        is_dcycle_anchor = True

    # --- F2 Tier A 取数公式分支（f2-four-table-extraction-refresh） ---
    is_f2_anchor = False
    if (
        settings.F2_FOUR_TABLE_EXTRACTION_ENABLED
        and base_wp_code == "F2"
    ):
        from app.services.f2_extraction.anchor_registry import is_known_anchor as f2_is_known_anchor
        if f2_is_known_anchor(body.target_cell):
            is_f2_anchor = True

            # F2 列名校验：表达式列名必须 ∈ F2_COLUMN_MAP
            from app.services.f2_extraction.validation import validate_f2_formula
            error = validate_f2_formula(body.expression)
            if error:
                raise HTTPException(
                    status_code=422,
                    detail=error,
                )

    # 仅 auto_calc 求值回填目标单元（Req 14.3）；logic_check / reasonability
    # 绝不改值（Req 6.3 / 7.3），不写回单元。跨 sheet 引用经 CrossSheetResolver
    # 追溯（Req 14.2），传 parsed_data + parent_wp_code 启用。
    evaluated_value: object | None = None
    eval_errors: list[str] = []
    if saved.formula_type == "auto_calc":
        if is_f2_anchor:
            # F2 Tier A 取数公式不走 generic evaluator（走 f2_extraction 取数路径）
            # 保存时不即时求值，值由 render/刷新提供
            evaluated_value = None
            eval_errors = []
        else:
            evaluated_value, eval_errors = await evaluate_wp_formula_expression(
                db,
                project_id=wp.project_id,
                year=body.year,
                expression=body.expression,
                parsed_data=wp.parsed_data,
                parent_wp_code=wp_code,
            )
        if not is_dcycle_anchor and not is_f2_anchor:
            # 普通网格 cell（∉ known_anchors）/ 非 D-cycle / 主开关关 → parsed_data 网格写回（零回归）
            write_cell_to_parsed_data(
                wp,
                sheet_name=body.sheet_name,
                cell_ref=body.target_cell,
                value=format_cell_display_value(evaluated_value),
            )

    linkage: dict | None = None
    # D-cycle 锚点未写 parsed_data 网格 → 无网格 cell 变更可传播，跳过 linkage（避免误导）。
    if wp_code and saved.formula_type == "auto_calc" and not is_dcycle_anchor and not is_f2_anchor:
        try:
            from app.services.wp_formula_linkage_service import (
                propagate_custom_wp_cell_change,
            )

            linkage = await propagate_custom_wp_cell_change(
                db,
                project_id=wp.project_id,
                year=body.year,
                wp_code=wp_code,
                sheet_name=body.sheet_name,
                cell_ref=body.target_cell,
            )
        except Exception as linkage_err:
            logger.warning(
                "propagate_custom_wp_cell_change after wp_formula save: %s",
                linkage_err,
            )

    await db.commit()
    # NOTE: touch_wp_registry 已由 ACNR events.on_workpaper_saved 统一处理（R23.1/R23.2）

    payload: dict = {"saved": _formula_to_dict(saved)}
    if saved.formula_type == "auto_calc":
        if is_dcycle_anchor and eval_errors:
            # R1.4 / Property 3：D-cycle 锚点求值失败或有 eval_errors → 只返回 eval_warnings，
            # 不返回错误/0 的 evaluated_value（不静默落空）。
            payload["eval_warnings"] = eval_errors
        else:
            # 非锚点（网格 cell）逐字节零回归：仍返回 evaluated_value（+ eval_warnings 若有）；
            # D-cycle 锚点求值成功：返回 evaluated_value 供前端即时本地显示（不落库）。
            payload["evaluated_value"] = str(evaluated_value)
            if eval_errors:
                payload["eval_warnings"] = eval_errors
    if linkage is not None:
        payload["linkage"] = linkage
    return payload


@router.delete("/formulas/{formula_id}")
async def delete_formula(
    wp_id: UUID,
    formula_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """删除单条底稿公式。"""
    wp = await _load_wp(db, wp_id)
    existing = (
        await db.execute(
            sa.select(WpFormula).where(
                WpFormula.id == formula_id,
                WpFormula.wp_id == wp_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="公式不存在")
    await wp_formula_service.delete(db, formula_id)
    await db.commit()
    # NOTE: touch_wp_registry 已由 ACNR events.on_workpaper_saved 统一处理（R23.1/R23.2）
    return {"deleted": str(formula_id)}
