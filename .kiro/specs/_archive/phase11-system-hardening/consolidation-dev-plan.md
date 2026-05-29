# 合并报表模块深度开发计划

## 一、现状盘点

### 后端（已有基础，同步 ORM 需改异步）

| 文件 | 行数 | 状态 | 说明 |
|------|------|------|------|
| consolidation_models.py | 400+ | ✅ 完整 | 12 张表 ORM + 15 个枚举，数据模型齐全 |
| consolidation_schemas.py | 300+ | ✅ 完整 | Pydantic Schema 齐全 |
| elimination_service.py | 208 | ✅ 可用 | 抵消分录 CRUD + 复核状态机 |
| consol_report_service.py | 1117 | ✅ 最深 | 合并报表生成/保存/同比分析 |
| consol_disclosure_service.py | 763 | ✅ 较深 | 合并附注 6 类披露生成 |
| internal_trade_service.py | 162 | ⚠️ 基础 | 内部交易 CRUD + 自动生成抵消分录 |
| consol_scope_service.py | 122 | ⚠️ 基础 | 合并范围 CRUD |
| consol_trial_service.py | 142 | ⚠️ 基础 | 合并试算表汇总 |
| component_auditor_service.py | 238 | ⚠️ 基础 | 组成部分审计师管理 |
| goodwill_service.py | 117 | ⚠️ 基础 | 商誉计算 CRUD |
| minority_interest_service.py | 124 | ⚠️ 基础 | 少数股东权益 CRUD |
| forex_service.py | 109 | ⚠️ 基础 | 外币折算 CRUD |
| consol_enhanced_service.py | 95 | ❌ stub | 外部报表导入为 stub |

**核心问题：10 个路由全部用 `Depends(sync_db)` 同步 ORM，会阻塞 asyncio 事件循环。**

### 前端（框架完整，子组件较深）

| 页面/组件 | 行数 | 状态 |
|-----------|------|------|
| ConsolidationIndex.vue（主入口） | ~200 | ⚠️ 7 个 Tab 框架 |
| ConsolNotesView.vue | 733 | ✅ 较深 |
| ConsolReportView.vue | 651 | ✅ 较深 |
| ComponentAuditorView.vue | 305 | ✅ 可用 |
| EliminationView.vue | 191 | ⚠️ Tab 壳 |
| GroupStructureView.vue | 134 | ⚠️ 基础 |
| ConsolTrialView.vue | 127 | ⚠️ 基础 |
| ConsolCalculationView.vue | 105 | ⚠️ 基础 |
| **子组件（14 个）** | **平均 480** | **✅ 较深** |
| EliminationList.vue | 624 | ✅ 完整 CRUD |
| EliminationEntryForm.vue | 519 | ✅ 完整表单 |
| InternalTradePanel.vue | 719 | ✅ 最深 |
| MinorityInterestPanel.vue | 645 | ✅ 较深 |
| ForexTranslationPanel.vue | 577 | ✅ 较深 |
| ConsolTrialBalance.vue | 520 | ✅ 较深 |
| ComponentAuditorPanel.vue | 521 | ✅ 较深 |
| InternalArApPanel.vue | 527 | ✅ 较深 |
| GoodwillPanel.vue | 468 | ✅ 较深 |
| ComponentResultForm.vue | 472 | ✅ 较深 |
| InstructionForm.vue | 423 | ✅ 较深 |
| ConsolScopeTable.vue | 377 | ✅ 较深 |
| CompanyForm.vue | 336 | ✅ 较深 |
| GroupStructureTree.vue | 285 | ✅ 较深 |

**Pinia Store：** consolidation.ts 完整（180 行，20+ 个 action）

**API 服务层：** consolidationApi.ts 导出被删除（指向不存在的 consolidationApiCompat），需要重建。

### 结论

合并模块不是"空壳"——后端 12 张表 + 13 个服务 + 10 个路由，前端 14 个子组件平均 480 行。
**真正的问题是：**
1. 后端 10 个路由全部同步 ORM → 需改异步
2. 前端 API 服务层断裂（consolidationApiCompat 被删除）→ 需重建
3. 前端页面层较薄（Tab 壳），子组件较深但未被正确连接

---

## 二、开发步骤（共 8 步）

### 步骤 1：重建前端 API 服务层（consolidationApi.ts）

**问题：** consolidationApi.ts 只有一行 `export * from './consolidationApiCompat'`，而 consolidationApiCompat 已被删除。Pinia store 和所有子组件都依赖这个文件的导出。

**操作：**

创建完整的 `audit-platform/frontend/src/services/consolidationApi.ts`：

```typescript
/**
 * 合并报表 API 服务层
 * 覆盖：合并范围/合并试算/抵消分录/内部交易/商誉/外币/少数股东/组成部分审计师/合并附注/合并报表
 */
import { api } from '@/services/apiProxy'

// ═══ 类型定义 ═══

export interface ConsolScopeItem {
  id: string
  company_code: string
  company_name: string
  company_type: string
  ownership_ratio: number
  is_included: boolean
  inclusion_reason: string
  scope_change_type: string
}

export interface ConsolTrialRow {
  standard_account_code: string
  account_name: string
  account_category: string
  individual_sum: number
  consol_adjustment: number
  consol_elimination: number
  consol_amount: number
}

export interface ConsolTrialBalanceEntry extends ConsolTrialRow {
  elimination_details?: Array<{
    entry_id: string
    entry_no: string
    entry_type: string
    debit: number
    credit: number
  }>
}

export interface EliminationEntry {
  id: string
  entry_no: string
  entry_type: string
  description: string
  account_code: string
  account_name: string
  debit_amount: number
  credit_amount: number
  lines: any[]
  review_status: string
  entry_group_id: string
}

export interface InternalTrade {
  id: string
  seller_company_code: string
  buyer_company_code: string
  trade_type: string
  trade_amount: number
  cost_amount: number
  unrealized_profit: number
}

export interface GoodwillRow {
  id: string
  subsidiary_company_code: string
  goodwill_amount: number
  accumulated_impairment: number
  carrying_value: number
}

export interface ForexRow {
  id: string
  entity_name: string
  functional_currency: string
  exchange_rate: number
  translation_difference: number
}

export interface MinorityInterestRow {
  id: string
  subsidiary_name: string
  minority_ratio: number
  minority_equity: number
  minority_profit: number
}

export interface ComponentAuditor {
  id: string
  component_name: string
  auditor_firm: string
  auditor_name: string
  status: string
  competence_rating: string
}

export interface Instruction {
  id: string
  component_auditor_id: string
  instruction_type: string
  content: string
  status: string
}

export interface InstructionResult {
  id: string
  instruction_id: string
  result_summary: string
  findings: any[]
}

export interface ConsistencyCheckResult {
  consistent: boolean
  issues: Array<{ account_code: string; message: string }>
}

export interface ConsolReportData {
  report_type: string
  period: string
  rows: Array<{
    row_code: string
    row_name: string
    current_amount: number
    prior_amount: number
    indent_level: number
  }>
}

export interface YoYAnalysis {
  row_code: string
  row_name: string
  current: number
  prior: number
  change: number
  change_rate: number
}

// 合并附注类型
export interface ConsolScopeNote { company_name: string; ownership: string; method: string }
export interface SubsidiaryNote { name: string; registered_capital: string; business_nature: string }
export interface GoodwillNote { subsidiary: string; initial_amount: number; impairment: number }
export interface MinorityInterestNote { subsidiary: string; ratio: number; equity: number }
export interface InternalTradeNote { seller: string; buyer: string; amount: number }
export interface InternalArApNote { debtor: string; creditor: string; amount: number }
export interface ForexTranslationNote { entity: string; currency: string; rate: number }

// ═══ 合并范围 ═══

export async function getConsolScope(projectId: string, year?: number): Promise<ConsolScopeItem[]> {
  return api.get(`/api/consolidation/scope`, { params: { project_id: projectId, year } })
}

export async function createConsolScope(projectId: string, data: Partial<ConsolScopeItem>): Promise<ConsolScopeItem> {
  return api.post(`/api/consolidation/scope`, { ...data, project_id: projectId })
}

export async function updateConsolScope(id: string, projectId: string, data: Partial<ConsolScopeItem>): Promise<ConsolScopeItem> {
  return api.put(`/api/consolidation/scope/${id}?project_id=${projectId}`, data)
}

export async function deleteConsolScope(id: string, projectId: string): Promise<void> {
  return api.delete(`/api/consolidation/scope/${id}?project_id=${projectId}`)
}

// ═══ 合并试算表 ═══

export async function getConsolTrialBalance(projectId: string, year: number): Promise<ConsolTrialRow[]> {
  return api.get(`/api/consolidation/trial`, { params: { project_id: projectId, year } })
}

export async function recalcConsolTrial(projectId: string, year: number): Promise<ConsolTrialRow[]> {
  return api.post(`/api/consolidation/trial/recalc`, null, { params: { project_id: projectId, year } })
}

export async function checkConsolTrialConsistency(projectId: string, year: number): Promise<ConsistencyCheckResult> {
  return api.get(`/api/consolidation/trial/consistency`, { params: { project_id: projectId, year } })
}

// ═══ 抵消分录 ═══

export async function getEliminations(projectId: string, year?: number): Promise<EliminationEntry[]> {
  return api.get(`/api/consolidation/eliminations`, { params: { project_id: projectId, year } })
}

export async function createElimination(projectId: string, data: any): Promise<EliminationEntry> {
  return api.post(`/api/consolidation/eliminations?project_id=${projectId}`, data)
}

export async function updateElimination(id: string, projectId: string, data: any): Promise<EliminationEntry> {
  return api.put(`/api/consolidation/eliminations/${id}?project_id=${projectId}`, data)
}

export async function deleteElimination(id: string, projectId: string): Promise<void> {
  return api.delete(`/api/consolidation/eliminations/${id}?project_id=${projectId}`)
}

export async function reviewElimination(id: string, projectId: string, action: any): Promise<EliminationEntry> {
  return api.post(`/api/consolidation/eliminations/${id}/review?project_id=${projectId}`, action)
}

export async function getEliminationSummary(projectId: string, year: number): Promise<any[]> {
  return api.get(`/api/consolidation/eliminations/summary/year`, { params: { project_id: projectId, year } })
}

// ═══ 内部交易 ═══

export async function getInternalTrades(projectId: string, year: number): Promise<InternalTrade[]> {
  return api.get(`/api/consolidation/internal-trade`, { params: { project_id: projectId, year } })
}

export async function createInternalTrade(projectId: string, data: any): Promise<InternalTrade> {
  return api.post(`/api/consolidation/internal-trade?project_id=${projectId}`, data)
}

export async function deleteInternalTrade(id: string, projectId: string): Promise<void> {
  return api.delete(`/api/consolidation/internal-trade/${id}?project_id=${projectId}`)
}

export async function generateTradeEliminations(projectId: string, year: number): Promise<string[]> {
  return api.post(`/api/consolidation/internal-trade/generate-eliminations`, null, {
    params: { project_id: projectId, year }
  })
}

// ═══ 内部往来 ═══

export async function getInternalArAp(projectId: string, year: number): Promise<any[]> {
  return api.get(`/api/consolidation/internal-trade/ar-ap`, { params: { project_id: projectId, year } })
}

export async function reconcileArAp(projectId: string, year: number): Promise<any> {
  return api.post(`/api/consolidation/internal-trade/ar-ap/reconcile`, null, {
    params: { project_id: projectId, year }
  })
}

// ═══ 商誉 ═══

export async function getGoodwillRows(projectId: string, year: number): Promise<GoodwillRow[]> {
  return api.get(`/api/consolidation/goodwill`, { params: { project_id: projectId, year } })
}

export async function createGoodwill(projectId: string, data: any): Promise<GoodwillRow> {
  return api.post(`/api/consolidation/goodwill?project_id=${projectId}`, data)
}

export async function updateGoodwill(id: string, projectId: string, data: any): Promise<GoodwillRow> {
  return api.put(`/api/consolidation/goodwill/${id}?project_id=${projectId}`, data)
}

// ═══ 外币折算 ═══

export async function getForexRows(projectId: string, year: number): Promise<ForexRow[]> {
  return api.get(`/api/consolidation/forex`, { params: { project_id: projectId, year } })
}

export async function createForex(projectId: string, data: any): Promise<ForexRow> {
  return api.post(`/api/consolidation/forex?project_id=${projectId}`, data)
}

// ═══ 少数股东权益 ═══

export async function getMinorityInterestRows(projectId: string, year: number): Promise<MinorityInterestRow[]> {
  return api.get(`/api/consolidation/minority-interest`, { params: { project_id: projectId, year } })
}

export async function createMinorityInterest(projectId: string, data: any): Promise<MinorityInterestRow> {
  return api.post(`/api/consolidation/minority-interest?project_id=${projectId}`, data)
}

// ═══ 组成部分审计师 ═══

export async function getComponentAuditors(projectId: string): Promise<ComponentAuditor[]> {
  return api.get(`/api/consolidation/component-auditors`, { params: { project_id: projectId } })
}

export async function createComponentAuditor(projectId: string, data: any): Promise<ComponentAuditor> {
  return api.post(`/api/consolidation/component-auditors?project_id=${projectId}`, data)
}

export async function updateComponentAuditor(id: string, projectId: string, data: any): Promise<ComponentAuditor> {
  return api.put(`/api/consolidation/component-auditors/${id}?project_id=${projectId}`, data)
}

export async function getInstructions(projectId: string): Promise<Instruction[]> {
  return api.get(`/api/consolidation/component-auditors/instructions`, { params: { project_id: projectId } })
}

export async function createInstruction(projectId: string, data: any): Promise<Instruction> {
  return api.post(`/api/consolidation/component-auditors/instructions?project_id=${projectId}`, data)
}

export async function getResults(projectId: string): Promise<InstructionResult[]> {
  return api.get(`/api/consolidation/component-auditors/results`, { params: { project_id: projectId } })
}

export async function getComponentDashboard(projectId: string): Promise<any> {
  return api.get(`/api/consolidation/component-auditors/dashboard`, { params: { project_id: projectId } })
}

// ═══ 合并报表 ═══

export async function getConsolReport(projectId: string, reportType: string, period: string): Promise<ConsolReportData> {
  return api.get(`/api/consolidation/report`, { params: { project_id: projectId, report_type: reportType, period } })
}

export async function saveConsolReport(projectId: string, reportType: string, period: string, data: ConsolReportData): Promise<ConsolReportData> {
  return api.post(`/api/consolidation/report/save`, data, {
    params: { project_id: projectId, report_type: reportType, period }
  })
}

export async function getYoYAnalysis(projectId: string, reportType: string, period: string): Promise<YoYAnalysis[]> {
  return api.get(`/api/consolidation/report/yoy`, { params: { project_id: projectId, report_type: reportType, period } })
}

// ═══ 合并附注 ═══

export async function getConsolScopeNotes(projectId: string, period: string): Promise<ConsolScopeNote[]> {
  return api.get(`/api/consolidation/notes/scope`, { params: { project_id: projectId, period } })
}

export async function getSubsidiaryNotes(projectId: string, period: string): Promise<SubsidiaryNote[]> {
  return api.get(`/api/consolidation/notes/subsidiaries`, { params: { project_id: projectId, period } })
}

export async function getGoodwillNotes(projectId: string, period: string): Promise<GoodwillNote[]> {
  return api.get(`/api/consolidation/notes/goodwill`, { params: { project_id: projectId, period } })
}

export async function getMinorityInterestNotes(projectId: string, period: string): Promise<MinorityInterestNote[]> {
  return api.get(`/api/consolidation/notes/minority-interest`, { params: { project_id: projectId, period } })
}

export async function getInternalTradeNotes(projectId: string, period: string): Promise<{ trades: InternalTradeNote[]; arap: InternalArApNote[] }> {
  return api.get(`/api/consolidation/notes/internal-trade`, { params: { project_id: projectId, period } })
}

export async function getForexTranslationNotes(projectId: string, period: string): Promise<ForexTranslationNote[]> {
  return api.get(`/api/consolidation/notes/forex`, { params: { project_id: projectId, period } })
}

export async function saveConsolNotes(projectId: string, period: string, data: any): Promise<void> {
  return api.post(`/api/consolidation/notes/save`, data, { params: { project_id: projectId, period } })
}
```

**验证：** Pinia store 的所有 `api.xxx` 调用都能找到对应的导出函数。


---

### 步骤 2：后端 10 个路由从同步改异步

**核心改造模式（每个路由文件相同）：**

```python
# ── 改造前（同步） ──
from app.deps import sync_db
from sqlalchemy.orm import Session

@router.get("/xxx")
def list_xxx(
    project_id: UUID,
    db: Session = Depends(sync_db),
    user=Depends(get_current_user),
):
    return get_xxx(db, project_id)

# ── 改造后（异步） ──
from app.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

@router.get("/xxx")
async def list_xxx(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    return await get_xxx(db, project_id)
```

**10 个路由文件改造清单：**

| 文件 | 端点数 | 改造要点 |
|------|--------|----------|
| consolidation.py | 7 | 抵消分录 CRUD + 复核 + 汇总 |
| consol_scope.py | 4 | 合并范围 CRUD |
| consol_trial.py | 3 | 合并试算表查询 + 重算 + 一致性 |
| internal_trade.py | 6 | 内部交易 CRUD + 自动生成抵消 + 往来对账 |
| component_auditor.py | 8 | 审计师 CRUD + 指令 + 结果 + 看板 |
| goodwill.py | 3 | 商誉 CRUD |
| forex.py | 2 | 外币折算 CRUD |
| minority_interest.py | 3 | 少数股东 CRUD |
| consol_notes.py | 4 | 合并附注查询 + 保存 |
| consol_report.py | 5 | 合并报表生成 + 保存 + 同比 |

**对应的 13 个服务文件也需要改异步：**

每个服务文件的改造模式：
```python
# ── 改造前 ──
from sqlalchemy.orm import Session

def get_entries(db: Session, project_id: UUID, ...):
    result = db.query(EliminationEntry).filter(...)
    return result.all()

# ── 改造后 ──
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

async def get_entries(db: AsyncSession, project_id: UUID, ...):
    result = await db.execute(
        sa.select(EliminationEntry).where(...)
    )
    return result.scalars().all()
```

**关键差异点：**
- `db.query(Model).filter(...)` → `await db.execute(sa.select(Model).where(...))`
- `db.add(obj)` → `db.add(obj)` （不变）
- `db.commit()` → `await db.commit()`
- `db.refresh(obj)` → `await db.refresh(obj)`
- `db.delete(obj)` → `await db.delete(obj)`
- `.first()` → `.scalar_one_or_none()`
- `.all()` → `.scalars().all()`

**具体每个服务文件的改造：**

**elimination_service.py（208 行，7 个函数）：**
```python
# get_entries / get_entry / create_entry / update_entry / delete_entry / change_review_status / get_summary
# 全部从 def → async def，db.query → await db.execute(sa.select)
```

**consol_scope_service.py（122 行，4 个函数）：**
```python
# get_scope / create_scope / update_scope / delete_scope
```

**consol_trial_service.py（142 行，3 个函数）：**
```python
# get_trial_balance / recalc_trial / check_consistency
# recalc_trial 需要从各子公司 trial_balance 汇总 + 抵消分录扣减
```

**internal_trade_service.py（162 行，5 个函数）：**
```python
# get_trades / create_trade / delete_trade / generate_eliminations / get_ar_ap
# generate_eliminations 是核心：根据内部交易自动生成抵消分录
```

**component_auditor_service.py（238 行，8 个函数）：**
```python
# CRUD auditors + CRUD instructions + get_results + get_dashboard
```

**goodwill_service.py（117 行，3 个函数）：**
```python
# get_list / create / update
# 商誉 = 合并成本 - 可辨认净资产公允价值 × 持股比例
```

**forex_service.py（109 行，2 个函数）：**
```python
# get_list / create
# 外币折算差额 = 资产负债表日汇率折算的净资产 - 历史汇率折算的净资产
```

**minority_interest_service.py（124 行，3 个函数）：**
```python
# get_list / create / update
# 少数股东权益 = 子公司净资产 × (1 - 母公司持股比例)
```

**consol_disclosure_service.py（763 行，6 个函数）：**
```python
# get_scope_notes / get_subsidiary_notes / get_goodwill_notes
# get_minority_notes / get_trade_notes / get_forex_notes
# 这个文件最大，需要逐函数改造
```

**consol_report_service.py（1117 行，5 个函数）：**
```python
# generate_report / save_report / get_report / get_yoy_analysis / export_report
# 这个文件最复杂，generate_report 需要汇总所有子公司报表 + 抵消
```

---

### 步骤 3：合并试算表核心逻辑完善

**当前 consol_trial_service.py 的 recalc_trial 逻辑：**

```python
async def recalc_trial(db: AsyncSession, project_id: UUID, year: int) -> list[dict]:
    """重新计算合并试算表
    
    计算公式：合并数 = 个别汇总 + 合并调整 - 合并抵消
    
    步骤：
    1. 从 projects 表找到所有子公司项目（parent_project_id = project_id）
    2. 汇总每个子公司的 trial_balance 审定数 → individual_sum
    3. 从 elimination_entries 汇总抵消金额 → consol_elimination
    4. consol_amount = individual_sum - consol_elimination
    5. 写入 consol_trial 表
    """
    from app.models.core import Project
    from app.models.audit_platform_models import TrialBalance
    
    # 1. 找到所有子公司项目
    child_result = await db.execute(
        sa.select(Project.id).where(
            Project.parent_project_id == project_id,
            Project.is_deleted == sa.false(),
        )
    )
    child_ids = [r[0] for r in child_result.all()]
    # 加上母公司自身
    all_project_ids = [project_id] + child_ids
    
    # 2. 按科目汇总所有项目的审定数
    tb_result = await db.execute(
        sa.select(
            TrialBalance.standard_account_code,
            sa.func.max(TrialBalance.account_name).label('account_name'),
            sa.func.sum(TrialBalance.audited_amount).label('individual_sum'),
        ).where(
            TrialBalance.project_id.in_(all_project_ids),
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
        ).group_by(TrialBalance.standard_account_code)
    )
    
    # 3. 汇总抵消分录
    elim_result = await db.execute(
        sa.select(
            EliminationEntry.account_code,
            sa.func.sum(EliminationEntry.debit_amount - EliminationEntry.credit_amount).label('net_elimination'),
        ).where(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.is_deleted == sa.false(),
            EliminationEntry.review_status != ReviewStatusEnum.rejected,
        ).group_by(EliminationEntry.account_code)
    )
    elim_map = {r.account_code: r.net_elimination for r in elim_result.all()}
    
    # 4. 计算合并数并写入
    rows = []
    for r in tb_result.all():
        elimination = elim_map.get(r.standard_account_code, Decimal(0))
        consol_amount = r.individual_sum - elimination
        
        # upsert consol_trial
        existing = await db.execute(
            sa.select(ConsolTrial).where(
                ConsolTrial.project_id == project_id,
                ConsolTrial.year == year,
                ConsolTrial.standard_account_code == r.standard_account_code,
            )
        )
        ct = existing.scalar_one_or_none()
        if ct:
            ct.individual_sum = r.individual_sum
            ct.consol_elimination = elimination
            ct.consol_amount = consol_amount
        else:
            ct = ConsolTrial(
                id=uuid4(), project_id=project_id, year=year,
                standard_account_code=r.standard_account_code,
                account_name=r.account_name,
                individual_sum=r.individual_sum,
                consol_elimination=elimination,
                consol_amount=consol_amount,
            )
            db.add(ct)
        rows.append({...})
    
    await db.flush()
    return rows
```

---

### 步骤 4：内部交易自动生成抵消分录

**internal_trade_service.py 的 generate_eliminations 核心逻辑：**

```python
async def generate_eliminations(db: AsyncSession, project_id: UUID, year: int) -> list[str]:
    """根据内部交易记录自动生成抵消分录
    
    规则：
    1. 商品销售：借 营业收入（卖方金额），贷 营业成本（买方成本），贷 存货（未实现利润×剩余比例）
    2. 内部往来：借 应付账款（债务方），贷 应收账款（债权方）
    3. 固定资产内部交易：借 营业外收入/固定资产原值，贷 固定资产/累计折旧
    """
    trades = await get_trades(db, project_id, year)
    entry_ids = []
    
    for trade in trades:
        if trade.trade_type == TradeType.goods:
            # 收入成本抵消
            entries = _generate_goods_elimination(trade, project_id, year)
        elif trade.trade_type == TradeType.services:
            entries = _generate_service_elimination(trade, project_id, year)
        elif trade.trade_type == TradeType.assets:
            entries = _generate_asset_elimination(trade, project_id, year)
        else:
            continue
        
        for entry_data in entries:
            entry = await create_entry(db, project_id, entry_data)
            entry_ids.append(str(entry.id))
    
    await db.flush()
    return entry_ids


def _generate_goods_elimination(trade: InternalTrade, project_id: UUID, year: int) -> list[dict]:
    """商品销售抵消分录"""
    entries = []
    group_id = uuid4()
    
    # 借：营业收入（卖方销售额）
    entries.append({
        'entry_type': 'internal_trade',
        'description': f'抵消内部商品销售 {trade.seller_company_code}→{trade.buyer_company_code}',
        'account_code': '6001',  # 营业收入
        'debit_amount': trade.trade_amount,
        'credit_amount': Decimal(0),
        'entry_group_id': group_id,
        'year': year,
    })
    
    # 贷：营业成本（买方成本）
    entries.append({
        'entry_type': 'internal_trade',
        'description': f'抵消内部商品销售 {trade.seller_company_code}→{trade.buyer_company_code}',
        'account_code': '6401',  # 营业成本
        'debit_amount': Decimal(0),
        'credit_amount': trade.cost_amount or trade.trade_amount,
        'entry_group_id': group_id,
        'year': year,
    })
    
    # 如果有未实现利润且存货尚未全部对外销售
    if trade.unrealized_profit and trade.inventory_remaining_ratio:
        unrealized = trade.unrealized_profit * trade.inventory_remaining_ratio
        entries.append({
            'entry_type': 'unrealized_profit',
            'description': f'抵消未实现内部利润（存货剩余 {trade.inventory_remaining_ratio*100:.0f}%）',
            'account_code': '1405',  # 存货
            'debit_amount': Decimal(0),
            'credit_amount': unrealized,
            'entry_group_id': group_id,
            'year': year,
        })
    
    return entries
```

---

### 步骤 5：合并报表生成逻辑完善

**consol_report_service.py 的 generate_report 核心逻辑：**

```python
async def generate_report(
    db: AsyncSession, project_id: UUID, report_type: str, year: int
) -> ConsolReportData:
    """生成合并报表
    
    步骤：
    1. 从 consol_trial 取合并试算表数据
    2. 按报表配置（report_config_seed.json）的行次公式计算每行金额
    3. 同时取上年数据用于对比
    """
    # 1. 取合并试算表
    trial_rows = await get_consol_trial(db, project_id, year)
    trial_map = {r['standard_account_code']: r['consol_amount'] for r in trial_rows}
    
    # 2. 加载报表行次配置
    config = load_report_config(report_type)  # 从 report_config_seed.json
    
    # 3. 计算每行
    report_rows = []
    for row_config in config['rows']:
        amount = evaluate_formula(row_config['formula'], trial_map)
        prior_amount = await get_prior_year_amount(db, project_id, year - 1, row_config['row_code'])
        report_rows.append({
            'row_code': row_config['row_code'],
            'row_name': row_config['row_name'],
            'current_amount': float(amount),
            'prior_amount': float(prior_amount),
            'indent_level': row_config.get('indent_level', 0),
        })
    
    return ConsolReportData(report_type=report_type, period=str(year), rows=report_rows)
```

---

### 步骤 6：前端页面层完善（ConsolidationIndex.vue 7 个 Tab）

**当前 ConsolidationIndex.vue 是 7 个 Tab 的框架，每个 Tab 内容需要连接到子组件。**

**改造方案：每个 Tab 引入对应的子视图组件。**

```vue
<template>
  <div class="gt-consol gt-fade-in">
    <div class="gt-consol-banner">
      <div class="gt-consol-banner-text">
        <h2>合并报表</h2>
        <p>{{ childCount }} 个子公司 · {{ year }}年度</p>
      </div>
      <div class="gt-consol-banner-actions">
        <el-button size="small" @click="onRecalcTrial" :loading="recalcLoading" round>重算合并试算</el-button>
        <el-button size="small" @click="onCheckConsistency" round>一致性校验</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="集团架构" name="structure">
        <GroupStructureView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="合并范围" name="scope">
        <ConsolScopeTable :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="合并试算" name="trial">
        <ConsolTrialView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="抵消分录" name="elimination">
        <EliminationView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="内部交易" name="trade">
        <InternalTradeView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="合并附注" name="notes">
        <ConsolNotesView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="合并报表" name="report">
        <ConsolReportView :project-id="projectId" :year="year" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
```

**每个子视图组件已经存在且有一定深度（见现状盘点），主要工作是确保数据加载正确。**

---

### 步骤 7：合并附注 6 类披露完善

**consol_disclosure_service.py 已有 763 行，6 类披露：**

1. **合并范围变更说明** — 从 consol_scope 表读取 scope_change_type != 'none' 的记录
2. **重要子公司信息** — 从 companies 表读取子公司基本信息
3. **商誉变动表** — 从 goodwill_calc 表读取商誉初始确认 + 减值
4. **少数股东权益明细** — 从 minority_interest 计算
5. **内部交易披露** — 从 internal_trade + internal_ar_ap 汇总
6. **外币折算差额** — 从 forex 表读取

**需要完善的部分：**
- 每类披露的 Word 导出格式（python-docx 表格）
- 与单体附注的联动（合并附注引用单体附注数据）

---

### 步骤 8：导航开放 + 集成验证

**完成步骤 1-7 后：**

1. 在 ThreeColumnLayout.vue 中，将合并报表导航项的 `maturity: 'developing'` 改回正常
2. 验证完整流程：
   - 创建合并项目 → 添加子公司 → 导入各子公司数据
   - 合并试算表重算 → 验证个别汇总正确
   - 创建内部交易 → 自动生成抵消分录 → 验证合并数正确
   - 查看合并报表 → 验证四张报表数据
   - 查看合并附注 → 验证 6 类披露内容

---

## 三、执行顺序与工期估算

```
Day 1-2:  步骤 1 — 重建 consolidationApi.ts（前端 API 服务层）
Day 3-5:  步骤 2 — 后端 10 个路由 + 13 个服务从同步改异步
Day 6-7:  步骤 3 — 合并试算表核心逻辑（汇总 + 抵消扣减）
Day 8-9:  步骤 4 — 内部交易自动生成抵消分录
Day 10-11: 步骤 5 — 合并报表生成逻辑
Day 12:   步骤 6 — 前端页面层完善（Tab 连接子组件）
Day 13:   步骤 7 — 合并附注 6 类披露完善
Day 14:   步骤 8 — 导航开放 + 集成验证
```

**总工期：约 14 个工作日（3 周）**

---

## 四、风险与注意事项

1. **同步→异步改造风险：** 13 个服务文件 + 10 个路由文件，约 3000 行代码需要改造。每个 `db.query` 都要改成 `await db.execute(sa.select)`，容易遗漏。建议逐文件改造，每改一个跑一次测试。

2. **consolidation_models.py 的 server_default 问题：** memory.md 记录过 `server_default="'xxx'"` 双层引号导致 PG 枚举值错误，已修复为 `server_default="xxx"`。改造时注意不要回退。

3. **前端 API 路径匹配：** 后端路由 prefix 是 `/api/consolidation/xxx`，前端 API 调用路径必须完全匹配。建议用 grep 验证每个端点的路径一致性。

4. **合并试算表的数据依赖：** recalc_trial 依赖各子公司的 trial_balance 已经计算完成。如果子公司还没导入数据，合并试算表会是空的。前端需要提示"请先完成子公司数据导入"。

5. **抵消分录的借贷平衡：** generate_eliminations 自动生成的分录必须借贷平衡。需要在 create_entry 中加入借贷平衡校验（与 AdjustmentService 相同的逻辑）。
