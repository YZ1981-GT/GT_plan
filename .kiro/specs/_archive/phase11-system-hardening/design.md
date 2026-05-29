# Phase 11 系统加固 — 技术设计文档

## 概述

本文档针对问题1审查报告中的12个问题，给出逐个的前后端详细修改方案。
按 P0（紧急）→ P1（重要）→ P2（优化）顺序组织。

---

## P0-1：空壳页面从导航移除/路由删除

### 修改范围

**前端路由删除（router/index.ts）：**
删除以下路由条目：
- `ai/AIChatView` 相关路由（如果存在）
- `ai/AIWorkpaperView` 相关路由（如果存在）

**前端路由标记 developing（router/index.ts + ThreeColumnLayout.vue）：**
以下页面路由保留但导航入口标记灰色不可点击：
- MobileProjectList / MobileReportView / MobileWorkpaperEditor（移动端3个）
- ConsolSnapshots（合并快照）
- CheckInsPage（打卡签到）
- AuxSummaryPanel（辅助汇总）

**ThreeColumnLayout.vue navItems 修改：**
```typescript
// 在 navItems computed 中，给空壳页面加 maturity: 'developing'
// 已有 maturity 机制（gt-nav-item--developing 样式 + 点击弹 info 提示不跳转）
```

**具体操作步骤：**
1. 在 router/index.ts 中找到 AIChatView 和 AIWorkpaperView 的路由，注释掉或删除
2. 在 ThreeColumnLayout.vue 的 navItems 中，给 6 个空壳页面设置 `maturity: 'developing'`
3. 确认 AIChatPanel.vue 不被其他组件引用（grep 验证），如果只被 AIChatView 引用则无需改动

**回归防护：** 7 个核心深度页面（LedgerPenetration/WorkpaperWorkbench/WorkpaperList/Adjustments/TrialBalance/DisclosureEditor/ReportView）的路由和功能不受影响。

---

## P0-2：LLM stub 入口隐藏或标注"即将上线"

### 2a. AI 插件管理页面（AIPluginManagement.vue）

**修改方案：**
在插件列表渲染时，检查插件是否为 stub（8 个预设插件 ID），如果是则：
- 卡片右上角显示"即将上线"标签（el-tag type="info"）
- "执行"按钮改为 disabled 状态
- tooltip 提示"该插件正在开发中"

```vue
<!-- AIPluginManagement.vue 中插件卡片 -->
<el-tag v-if="isStubPlugin(plugin.plugin_id)" type="info" size="small"
  style="position:absolute;top:8px;right:8px">即将上线</el-tag>
<el-button :disabled="isStubPlugin(plugin.plugin_id)" ...>执行</el-button>
```

```typescript
const STUB_PLUGIN_IDS = [
  'invoice_verify', 'business_info', 'bank_reconcile', 'seal_check',
  'voice_note', 'wp_review', 'continuous_audit', 'team_chat'
]
function isStubPlugin(id: string) { return STUB_PLUGIN_IDS.includes(id) }
```

### 2b. 附注校验按钮提示（DisclosureEditor.vue）

**修改方案：**
在"执行校验"按钮旁加 el-tooltip 提示：

```vue
<el-tooltip content="当前仅支持余额核对和子项校验，其他校验规则开发中" placement="top">
  <el-button @click="onValidate" :loading="validateLoading" type="warning">执行校验</el-button>
</el-tooltip>
```

### 2c. AI 变动分析静默降级改为提示卡片（WorkpaperWorkbench.vue）

**修改方案：**
将 catch 块从静默降级改为设置提示状态：

```typescript
// 原代码（约第570行）：
// catch { /* LLM 不可用时静默降级 */ }

// 改为：
catch {
  aiAnalysis.value = { unavailable: true, message: 'AI 分析服务未启动，请检查 vLLM 是否运行' }
}
```

模板中增加不可用提示卡片：
```vue
<div v-if="aiAnalysis?.unavailable" class="gt-wpb-ai-unavailable">
  <el-icon><WarningFilled /></el-icon>
  <span>{{ aiAnalysis.message }}</span>
</div>
```

---

## P0-3：底稿复核退回原因 + 逐条回复强制校验

### 3a. 数据库变更（WorkingPaper 模型新增 3 个字段）

**ALTER TABLE 语句：**
```sql
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS rejection_reason TEXT;
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS rejected_by UUID REFERENCES users(id);
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP;
```

**ORM 模型修改（workpaper_models.py WorkingPaper 类）：**
```python
rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
rejected_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
rejected_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

### 3b. 后端 ReviewStatusRequest schema 新增 reason 字段

**修改文件：backend/app/routers/working_paper.py**
```python
class ReviewStatusRequest(BaseModel):
    review_status: str
    reason: str | None = None  # 退回时必填
```

### 3c. working_paper_service.py update_review_status 强制退回原因

**修改文件：backend/app/services/working_paper_service.py**

在 update_review_status 方法中，当 new_review_status 包含 "rejected" 时：
```python
async def update_review_status(self, db, wp_id, new_review_status, project_id, reason=None, rejected_by_id=None):
    # ... 已有的状态流转校验 ...
    
    if "rejected" in new_review_status:
        if not reason or not reason.strip():
            raise ValueError("退回时必须填写退回原因")
        wp.rejection_reason = reason
        wp.rejected_by = rejected_by_id
        wp.rejected_at = datetime.now(timezone.utc)
        wp.status = WpFileStatus.revision_required
    
    # ... 其余逻辑不变 ...
```

**路由层传递 reason（working_paper.py update_review_status 端点）：**
```python
@router.put("/working-papers/{wp_id}/review-status")
async def update_review_status(..., data: ReviewStatusRequest, ...):
    result = await svc.update_review_status(
        db=db, wp_id=wp_id, new_review_status=data.review_status,
        project_id=project_id, reason=data.reason,
        rejected_by_id=current_user.id,
    )
```

### 3d. submit-review 新增第 5 项门禁：逐条回复检查

**修改文件：backend/app/routers/working_paper.py submit_review 函数**

在已有的 4 项门禁之后，新增：
```python
# 门禁 5：所有 open 状态的复核意见必须已被 replied
from app.models.workpaper_models import ReviewRecord, ReviewCommentStatus
open_unreplied = await db.execute(
    sa.select(sa.func.count()).select_from(ReviewRecord).where(
        ReviewRecord.working_paper_id == wp_id,
        ReviewRecord.status == ReviewCommentStatus.open,
        ReviewRecord.is_deleted == sa.false(),
    )
)
unreplied_count = open_unreplied.scalar() or 0
if unreplied_count > 0:
    blocking_reasons.append(f"{unreplied_count} 条复核意见未回复（状态仍为 open）")
```

### 3e. 前端 WorkpaperList.vue 退回弹窗强制填写原因

**修改方案：**
在复核人操作区的"退回修改"按钮点击后，弹出 el-dialog 要求填写退回原因：
```vue
<el-dialog v-model="showRejectDialog" title="退回底稿" width="450px" append-to-body>
  <el-input v-model="rejectReason" type="textarea" :rows="3"
    placeholder="请填写退回原因（必填）" />
  <template #footer>
    <el-button @click="showRejectDialog = false">取消</el-button>
    <el-button type="warning" @click="onConfirmReject" :disabled="!rejectReason.trim()">
      确认退回
    </el-button>
  </template>
</el-dialog>
```

调用 API 时传递 reason：
```typescript
async function onConfirmReject() {
  await http.put(`/api/projects/${projectId}/working-papers/${wpId}/review-status`, {
    review_status: 'level1_rejected',
    reason: rejectReason.value,
  })
}
```

---

## P0-4：el-dialog 批量加 append-to-body

### 修复方案：Python 脚本批量替换

**不用 PowerShell**（避免编码损坏），用 Python 脚本：

```python
# scripts/fix_dialog_append.py
import pathlib, re

vue_dir = pathlib.Path('audit-platform/frontend/src')
count = 0
for f in vue_dir.rglob('*.vue'):
    text = f.read_text(encoding='utf-8')
    # 匹配 <el-dialog 但后面没有 append-to-body 的情况
    new_text = re.sub(
        r'<el-dialog(?!\s[^>]*append-to-body)',
        '<el-dialog append-to-body',
        text
    )
    if new_text != text:
        f.write_text(new_text, encoding='utf-8')
        count += 1
        print(f'Fixed: {f}')
print(f'Total fixed: {count} files')
```

**幂等性保证：** 正则 `(?!\s[^>]*append-to-body)` 确保已有 append-to-body 的不会重复添加。

**回归防护：** 已有 append-to-body 的弹窗（如 Adjustments.vue 的驳回弹窗）不受影响。


---

## P1-1：附注编辑器上年数据 + 公式计算（问题七）

### 5a. 后端：disclosure_engine.py 增加上年数据查询

**新增方法 get_prior_year_data：**

```python
# backend/app/services/disclosure_engine.py

async def get_prior_year_data(
    self, db: AsyncSession, project_id: UUID, year: int, note_section: str
) -> dict | None:
    """查询上年（year-1）同一附注章节的 table_data，用于前端双列对比。"""
    prior_year = year - 1
    result = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == prior_year,
            DisclosureNote.note_section == note_section,
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    note = result.scalar_one_or_none()
    if not note:
        # 尝试从 trial_balance 取上年审定数作为兜底
        return await self._get_prior_from_trial_balance(db, project_id, prior_year, note_section)
    return {
        "year": prior_year,
        "table_data": note.table_data,
        "text_content": note.text_content,
    }

async def _get_prior_from_trial_balance(
    self, db: AsyncSession, project_id: UUID, year: int, note_section: str
) -> dict | None:
    """从上年试算表取审定数，构造简化的上年数据。"""
    from app.models.audit_platform_models import TrialBalance
    # 通过 note_section 找到关联的科目编码（从 note_templates_seed.json 映射）
    # 查询 trial_balance 中 year=prior_year 的审定数
    # 返回 {"year": year, "amounts": {account_code: audited_amount, ...}}
    return None  # 具体实现依赖附注模版的科目映射
```

**新增 API 端点（disclosure_notes.py）：**

```python
@router.get("/{project_id}/{year}/notes/{note_section}/prior-year")
async def get_prior_year_note(
    project_id: UUID, year: int, note_section: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    engine = DisclosureEngine(db)
    data = await engine.get_prior_year_data(db, project_id, year, note_section)
    return data or {"year": year - 1, "table_data": None, "text_content": None}
```

### 5b. 前端：DisclosureEditor.vue 增加上年数据列

**新增状态变量：**
```typescript
const priorYearNote = ref<any>(null)
const priorYearLoading = ref(false)
```

**在 fetchDetail 中并行加载上年数据：**
```typescript
async function fetchDetail(noteSection: string) {
  currentNote.value = await getDisclosureNoteDetail(projectId.value, year.value, noteSection)
  // 并行加载上年数据
  priorYearLoading.value = true
  try {
    priorYearNote.value = await api.get(
      `/api/disclosure-notes/${projectId.value}/${year.value}/notes/${noteSection}/prior-year`
    )
  } catch { priorYearNote.value = null }
  priorYearLoading.value = false
  // ... 已有的 TipTap 内容设置 ...
}
```

**表格列增加上年数据：**
```vue
<!-- 在 el-table 中，每个数值列后面增加上年对比列 -->
<el-table-column v-for="(h, hiRaw) in (currentNote.table_data.headers || [])" :key="hiRaw"
  :label="h" ...>
  <!-- 已有的当期数据渲染 -->
</el-table-column>
<!-- 上年数据列（仅在有上年数据时显示） -->
<el-table-column v-if="priorYearNote?.table_data" label="上年数" width="120" align="right">
  <template #default="{ row, $index }">
    <span class="gt-prior-year-val">
      {{ fmtAmt(getPriorYearValue(row, $index)) }}
    </span>
  </template>
</el-table-column>
```

```typescript
function getPriorYearValue(row: any, rowIndex: number): any {
  if (!priorYearNote.value?.table_data?.rows) return null
  const priorRow = priorYearNote.value.table_data.rows[rowIndex]
  if (!priorRow) return null
  // 取第一个数值列（期末余额）
  const values = priorRow.values || priorRow.cells || []
  return values[0] ?? null
}
```

**样式：上年数据用灰色斜体区分：**
```css
.gt-prior-year-val {
  color: var(--gt-color-text-tertiary);
  font-style: italic;
  font-size: 12px;
}
```

### 5c. 前端：表格内实时公式计算

**方案：在 el-input-number 的 @change 事件中实时计算合计行。**

```typescript
// 公式规则：对于变动表，期末 = 期初 + 本期增加 - 本期减少
// 对于明细表，合计 = 所有明细行之和

function onCellValueChange(rowIndex: number, colIndex: number, newValue: number) {
  if (!currentNote.value?.table_data?.rows) return
  const rows = currentNote.value.table_data.rows

  // 找到合计行
  const totalRowIndex = rows.findIndex((r: any) => r.is_total)
  if (totalRowIndex < 0) return

  // 重新计算合计：所有非合计行的同列求和
  let sum = 0
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].is_total) continue
    const vals = rows[i].values || []
    sum += parseFloat(vals[colIndex]) || 0
  }

  // 更新合计行
  if (!rows[totalRowIndex].values) rows[totalRowIndex].values = []
  rows[totalRowIndex].values[colIndex] = sum

  // 横向公式：如果有 opening + changes = closing 的结构
  recalcHorizontalFormula(rowIndex)
}

function recalcHorizontalFormula(rowIndex: number) {
  const row = currentNote.value?.table_data?.rows?.[rowIndex]
  if (!row || !row.formula_type) return
  // formula_type: 'opening_plus_changes' → values[last] = values[0] + sum(values[1:-1])
  if (row.formula_type === 'opening_plus_changes') {
    const vals = row.values || []
    if (vals.length >= 3) {
      const opening = parseFloat(vals[0]) || 0
      let changes = 0
      for (let i = 1; i < vals.length - 1; i++) {
        changes += parseFloat(vals[i]) || 0
      }
      vals[vals.length - 1] = opening + changes
    }
  }
}
```

**在 el-input-number 上绑定 @change：**
```vue
<el-input-number v-if="editMode && !row.is_total"
  v-model="row.values[Number(hiRaw) - 1]" :controls="false" :precision="2"
  size="small" style="width: 100%"
  @change="onCellValueChange($index, Number(hiRaw) - 1, $event)" />
```

**差异高亮：当计算值与实际值不一致时显示红色：**
```vue
<span v-if="row.is_total" :class="{ 'gt-formula-mismatch': isFormulaMismatch(row, Number(hiRaw) - 1) }">
  {{ fmtAmt(getCellValue(row, Number(hiRaw) - 1)) }}
</span>
```

```css
.gt-formula-mismatch {
  color: var(--gt-color-coral) !important;
  font-weight: 700;
  text-decoration: underline wavy var(--gt-color-coral);
}
```

---

## P1-2：合并报表模块标记 developing（问题二）

### 修改方案

**ThreeColumnLayout.vue navItems 修改：**

找到合并报表/合并项目相关的导航项，设置 `maturity: 'developing'`：

```typescript
// 在 navItems computed 中
{
  key: 'consolidation',
  label: '合并项目',
  icon: Connection,
  path: '/consolidation',
  maturity: 'developing',  // ← 新增
}
```

**已有的 developing 机制（gt-nav-item--developing 样式）：**
- 灰色半透明显示
- 点击弹 ElMessage.info 提示"该功能正在开发中"
- 不跳转路由

**回归防护：** 后端 10 个合并路由代码不删除不修改，仅前端导航入口灰色不可点击。后续改为异步 ORM 后可重新开放。

---

## P1-3：scope_cycles 落地到核心 4 个路由（问题九）

### 3a. 抽取公共函数 get_user_scope_cycles

**新增到 deps.py：**

```python
async def get_user_scope_cycles(
    current_user: User,
    project_id: UUID,
    db: AsyncSession,
) -> list[str] | None:
    """获取用户在指定项目中的循环范围限制。
    admin/partner 返回 None（不限制）。
    """
    if current_user.role.value in ("admin", "partner"):
        return None
    result = await db.execute(
        sa.select(ProjectUser.scope_cycles).where(
            ProjectUser.project_id == project_id,
            ProjectUser.user_id == current_user.id,
            ProjectUser.is_deleted == False,
        )
    )
    sc = result.scalar()
    if sc and isinstance(sc, str) and sc.strip():
        return [c.strip() for c in sc.split(",") if c.strip()]
    return None
```

### 3b. trial_balance.py 增加 scope_cycles 过滤

```python
@router.get("/api/projects/{project_id}/trial-balance")
async def get_trial_balance(...):
    scope_cycles = await get_user_scope_cycles(current_user, project_id, db)
    svc = TrialBalanceService(db)
    rows = await svc.get_trial_balance(project_id, year)
    if scope_cycles:
        # 通过 account_mapping 找到 scope_cycles 对应的科目编码
        from app.services.mapping_service import MappingService
        msvc = MappingService(db)
        allowed_codes = await msvc.get_codes_by_cycles(project_id, scope_cycles)
        rows = [r for r in rows if r['standard_account_code'] in allowed_codes]
    return rows
```

### 3c. adjustments.py 增加 scope_cycles 过滤

```python
@router.get("/api/projects/{project_id}/adjustments")
async def list_adjustments(...):
    scope_cycles = await get_user_scope_cycles(current_user, project_id, db)
    entries = await svc.list_entries(project_id, year, ...)
    if scope_cycles:
        allowed_codes = await msvc.get_codes_by_cycles(project_id, scope_cycles)
        entries = [e for e in entries if any(
            li['standard_account_code'] in allowed_codes
            for li in (e.get('line_items') or [])
        )]
    return entries
```

### 3d. ledger_penetration.py 增加 scope_cycles 过滤

```python
# 在 balance 查询端点中
scope_cycles = await get_user_scope_cycles(current_user, project_id, db)
if scope_cycles:
    allowed_codes = await msvc.get_codes_by_cycles(project_id, scope_cycles)
    query = query.where(TbBalance.account_code.in_(allowed_codes))
```

### 3e. disclosure_notes.py 增加 scope_cycles 过滤

```python
# 在 get_tree 端点中，按 scope_cycles 过滤附注章节
scope_cycles = await get_user_scope_cycles(current_user, project_id, db)
if scope_cycles:
    # 通过 note_wp_mapping 找到 scope_cycles 对应的附注章节
    allowed_sections = await get_sections_by_cycles(db, project_id, scope_cycles)
    notes = [n for n in notes if n.note_section in allowed_sections]
```

### 3f. MappingService 新增 get_codes_by_cycles 方法

```python
async def get_codes_by_cycles(self, project_id: UUID, cycles: list[str]) -> set[str]:
    """根据审计循环列表，返回对应的标准科目编码集合。
    通过 wp_account_mapping.json 的 cycle→account_codes 映射。
    """
    import json
    from pathlib import Path
    mapping_path = Path(__file__).parent.parent.parent / "data" / "wp_account_mapping.json"
    with open(mapping_path, encoding='utf-8-sig') as f:
        mappings = json.load(f)
    codes = set()
    for m in mappings:
        if m.get('cycle') in cycles:
            codes.update(m.get('account_codes', []))
    return codes
```

---

## P1-4：dashboard 5 个硬编码 0 指标接入真实数据（问题十一）

### 修改文件：backend/app/services/dashboard_service.py

**overdue_projects（逾期项目数）：**
```python
# 原："overdue_projects": 0,  # TODO
# 改为：
from app.models.core import Project, ProjectStatus
overdue_result = await db.execute(
    sa.select(sa.func.count()).select_from(Project).where(
        Project.status.in_([ProjectStatus.execution, ProjectStatus.planning]),
        Project.is_deleted == sa.false(),
        # 项目创建超过 180 天仍未归档视为逾期
        Project.created_at < datetime.now(timezone.utc) - timedelta(days=180),
    )
)
overdue_projects = overdue_result.scalar() or 0
```

**pending_review_workpapers（待复核底稿数）：**
```python
# 原："pending_review_workpapers": 0,  # TODO
from app.models.workpaper_models import WorkingPaper, WpReviewStatus
pending_result = await db.execute(
    sa.select(sa.func.count()).select_from(WorkingPaper).where(
        WorkingPaper.is_deleted == sa.false(),
        WorkingPaper.review_status.in_([
            WpReviewStatus.pending_level1,
            WpReviewStatus.pending_level2,
        ]),
    )
)
pending_review_workpapers = pending_result.scalar() or 0
```

**qc_pass_rate（QC 通过率）：**
```python
from app.models.workpaper_models import WpQcResult
total_qc = await db.execute(
    sa.select(sa.func.count()).select_from(WpQcResult)
)
passed_qc = await db.execute(
    sa.select(sa.func.count()).select_from(WpQcResult).where(WpQcResult.passed == True)
)
total = total_qc.scalar() or 0
passed = passed_qc.scalar() or 0
qc_pass_rate = round(passed / total * 100, 1) if total > 0 else 0
```

**review_completion_rate（复核完成率）：**
```python
total_wp = await db.execute(
    sa.select(sa.func.count()).select_from(WorkingPaper).where(
        WorkingPaper.is_deleted == sa.false(),
    )
)
reviewed_wp = await db.execute(
    sa.select(sa.func.count()).select_from(WorkingPaper).where(
        WorkingPaper.is_deleted == sa.false(),
        WorkingPaper.review_status.in_([
            WpReviewStatus.level1_passed, WpReviewStatus.level2_passed,
        ]),
    )
)
t = total_wp.scalar() or 0
r = reviewed_wp.scalar() or 0
review_completion_rate = round(r / t * 100, 1) if t > 0 else 0
```

**adjustment_count（活跃调整分录数）：**
```python
from app.models.audit_platform_models import Adjustment
adj_result = await db.execute(
    sa.select(sa.func.count()).select_from(Adjustment).where(
        Adjustment.is_deleted == sa.false(),
    )
)
adjustment_count = adj_result.scalar() or 0
```


---

## P2-1：前端 API 调用统一为 apiProxy（问题四）

### 改造策略

**核心原则：** 所有 Vue 页面统一使用 `api.get/api.post`（来自 apiProxy.ts），不再直接 `import http`。

**分 3 批改造：**

**第 1 批（向导组件 5 个，影响新建项目流程）：**
- BasicInfoStep.vue
- AccountImportStep.vue
- AccountMappingStep.vue
- MaterialityStep.vue
- ReportLineMappingStep.vue

改造模式（每个文件相同）：
```typescript
// 删除：
import http from '@/utils/http'

// 替换为：
import { api } from '@/services/apiProxy'

// 所有调用从：
const { data } = await http.get('/api/xxx')
// 改为：
const data = await api.get('/api/xxx')

// POST 从：
const { data } = await http.post('/api/xxx', body)
// 改为：
const data = await api.post('/api/xxx', body)
```

**第 2 批（布局组件 5 个，影响所有页面）：**
- ThreeColumnLayout.vue
- MiddleProjectList.vue
- DetailProjectPanel.vue
- FourColumnCatalog.vue
- FourColumnContent.vue

**第 3 批（扩展组件 13 个，优先级低）：**
- LanguageSwitcher / StandardSelector / PluginList / PluginConfig
- SignatureLevel1 / SignatureLevel2 / SignatureHistory
- WPIndexGenerator / CICPAReportForm / ArchivalStandardForm
- AuditTypeSelector / MetabaseDashboard / DrillDownNavigator

**其他 6 个：**
- NoteTrimPanel / DataImportPanel / SamplingPanel
- SEChecklistPanel / FilingError / CollaborationIndex（间接）

**保留不改的 2 个（有正当理由）：**
- LedgerPenetration.vue — 4 个复杂穿透调用（游标分页 + 流式响应）
- WorkpaperEditor.vue — 1 个 WOPI 锁刷新（需自定义 X-WOPI-Override headers）

### commonApi.ts 的处理

commonApi.ts 内部仍然使用 `http`（因为它本身就是封装层），但页面不应同时 import commonApi 和 http。页面应该：
- 优先用 commonApi 中已有的函数
- commonApi 没有的端点用 `api.get/api.post`
- 不直接 import http

---

## P2-2：E2E 集成测试（问题五）

### 测试环境搭建

**新增 docker-compose.test.yml：**
```yaml
version: '3.8'
services:
  test-db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: audit_test
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    ports: ["5433:5432"]
    tmpfs: /var/lib/postgresql/data  # 内存数据库，测试后自动清理

  test-redis:
    image: redis:7-alpine
    ports: ["6381:6379"]
```

**新增 backend/tests/e2e/ 目录：**

```
backend/tests/e2e/
  conftest.py          — PG + Redis 连接配置
  test_e2e_chain1.py   — 链路1：建项目→导数据→试算表→报表
  test_e2e_chain2.py   — 链路2：创建AJE→试算表更新→报表更新
  test_e2e_chain3.py   — 链路3：上传底稿→WORKPAPER_SAVED→审定数比对
```

**conftest.py 核心配置：**
```python
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.main import app
from app.core.database import get_db

TEST_DB_URL = "postgresql+asyncpg://test:test@localhost:5433/audit_test"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        from app.models.base import Base
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def client(engine):
    async def override_get_db():
        async with AsyncSession(engine) as session:
            yield session
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

**test_e2e_chain1.py 示例：**
```python
@pytest.mark.asyncio
async def test_import_triggers_trial_balance(client):
    """链路1：导入四表数据 → 验证试算表自动生成"""
    # 1. 创建项目
    r = await client.post("/api/projects/wizard", json={...})
    project_id = r.json()["data"]["id"]

    # 2. 导入余额表数据
    r = await client.post(f"/api/account-chart/{project_id}/import", ...)
    assert r.status_code == 200

    # 3. 等待事件处理（debounce 500ms + 处理时间）
    await asyncio.sleep(2)

    # 4. 验证试算表已自动生成
    r = await client.get(f"/api/projects/{project_id}/trial-balance?year=2025")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) > 0

    # 5. 验证报表已联动更新
    r = await client.get(f"/api/projects/{project_id}/reports?year=2025")
    assert r.status_code == 200
```

---

## P2-3：导入错误行号定位（问题八）

### 后端修改：smart_import_engine.py

**在 convert_balance_rows / convert_ledger_rows 中记录跳过的行：**

```python
def convert_balance_rows(raw_rows: list[dict], col_map: dict, diagnostics: list | None = None) -> list[dict]:
    """将原始行转换为标准余额表记录。diagnostics 用于记录跳过的行。"""
    results = []
    for i, row in enumerate(raw_rows):
        excel_row = i + 2  # +2 因为第1行是表头，索引从0开始
        try:
            code = row.get(col_map.get('account_code', ''))
            if not code:
                if diagnostics is not None:
                    diagnostics.append({
                        "row_number": excel_row,
                        "reason": "科目编码为空",
                        "raw_data": {k: str(v)[:50] for k, v in row.items() if v},
                    })
                continue
            # ... 已有的转换逻辑 ...
            results.append(record)
        except Exception as e:
            if diagnostics is not None:
                diagnostics.append({
                    "row_number": excel_row,
                    "reason": f"{type(e).__name__}: {str(e)[:100]}",
                    "raw_data": {k: str(v)[:50] for k, v in row.items() if v},
                })
            continue
    return results
```

**同样修改 convert_ledger_rows：**
```python
def convert_ledger_rows(raw_rows, col_map, diagnostics=None):
    # 同上模式，每个 try/except 中记录 excel_row + reason
```

**调用方传入 diagnostics 列表：**
```python
# smart_import_streaming 或 write_four_tables 中
diag_balance = []
balance_records = convert_balance_rows(raw_rows, col_map, diagnostics=diag_balance)
# 将 diag_balance 写入 ImportBatch.diagnostics 或返回给前端
```

### 前端修改：AccountImportStep.vue

**导入结果页展示跳过行信息：**
```vue
<div v-if="importResult?.skipped_rows?.length" class="gt-import-skipped">
  <el-alert type="warning" :closable="false">
    <template #title>
      跳过 {{ importResult.skipped_rows.length }} 行数据
      <el-button text size="small" @click="showSkippedDetail = !showSkippedDetail">
        {{ showSkippedDetail ? '收起' : '查看详情' }}
      </el-button>
    </template>
  </el-alert>
  <el-table v-if="showSkippedDetail" :data="importResult.skipped_rows" size="small" border
    max-height="300" style="margin-top: 8px">
    <el-table-column prop="row_number" label="Excel行号" width="100" />
    <el-table-column prop="reason" label="跳过原因" min-width="200" />
    <el-table-column prop="sheet_name" label="Sheet" width="120" />
  </el-table>
</div>
```

---

## P2-4：29 个文件 http→apiProxy 改造（问题十二）

### 改造方案

与 P2-1 合并执行。P2-1 定义了改造策略和分批计划，P2-4 是具体的文件清单。

**批量改造脚本（辅助工具，非自动替换）：**

```python
# scripts/audit_http_imports.py
"""扫描所有 Vue 文件，列出仍直接 import http 的文件及调用位置。"""
import pathlib, re

vue_dir = pathlib.Path('audit-platform/frontend/src')
EXCLUDE = {'LedgerPenetration.vue', 'WorkpaperEditor.vue'}

for f in sorted(vue_dir.rglob('*.vue')):
    if f.name in EXCLUDE:
        continue
    text = f.read_text(encoding='utf-8', errors='ignore')
    if "import http from '@/utils/http'" in text:
        # 统计 http.get/http.post/http.put/http.delete 调用次数
        calls = len(re.findall(r'http\.(get|post|put|delete|patch)\(', text))
        print(f'{f.relative_to(vue_dir)}  ({calls} calls)')
```

**每个文件的改造步骤：**
1. 将 `import http from '@/utils/http'` 改为 `import { api } from '@/services/apiProxy'`
2. 将 `const { data } = await http.get(url)` 改为 `const data = await api.get(url)`
3. 将 `const { data } = await http.post(url, body)` 改为 `const data = await api.post(url, body)`
4. 将 `await http.put(url, body)` 改为 `await api.put(url, body)`
5. 将 `await http.delete(url)` 改为 `await api.delete(url)`
6. 特殊情况：`responseType: 'blob'` 的下载调用改为 `api.download(url, filename)`
7. 验证页面数据展示正确

---

## 执行顺序总结

```
Week 1（P0，约 4 天）：
  Day 1: P0-1 空壳页面移除 + P0-4 el-dialog 批量修复（脚本化，半天搞定）
  Day 2: P0-2 stub 入口隐藏（3 个子任务）
  Day 3-4: P0-3 底稿复核硬化（数据库变更 + 后端 + 前端）

Week 2（P1，约 7 天）：
  Day 5-6: P1-1 附注编辑器上年数据 + 公式计算
  Day 7: P1-2 合并报表标记 developing（半天）+ P1-4 dashboard 指标接入（半天）
  Day 8-9: P1-3 scope_cycles 落地 4 个路由

Week 3-4（P2，约 9 天）：
  Day 10-12: P2-1 + P2-4 前端 API 调用统一（分 3 批）
  Day 13-15: P2-2 E2E 集成测试
  Day 16-17: P2-3 导入错误行号定位
```


---

## P1-2 扩展：合并报表深度开发（替代原"标记 developing"方案）

> 原 P1-2 方案是将合并模块标记为 developing 灰色不可点击。
> 用户要求直接开发落地，以下是完整的技术设计。
> 详细代码见 consolidation-deep-dev.md。

### 核心架构

**三码树形 + 差额表 + 节点汇总 + 穿透 + 自定义查询**

合并公式（用户确认）：
```
差额表 = 本级调整 + 本级抵消（不含个别数）
本级合并数 = Σ(下级审定数/合并数) + 本级差额净额
```

### 数据库变更

新增 2 张表：
- `consol_worksheet` — 差额表（node_company_code + account_code 唯一，含 adjustment_debit/credit + elimination_debit/credit + net_difference + children_amount_sum + consolidated_amount）
- `consol_query_template` — 自定义查询模板（行/列维度 + 值字段 + 筛选 + 转置 + 汇总模式）

### 后端新增 5 个服务 + 1 个路由

| 服务文件 | 职责 |
|----------|------|
| consol_tree_service.py | 三码树形构建（build_tree/find_node/get_descendants/to_dict） |
| consol_worksheet_engine.py | 差额表后序遍历计算引擎（recalc_full） |
| consol_aggregation_service.py | 三种汇总模式查询（self/children/descendants） |
| consol_drilldown_service.py | 三层穿透（合并→企业构成→抵消分录→试算表） |
| consol_pivot_service.py | 自定义透视查询 + 转置 + Excel 导出 + 模板 CRUD |
| consol_worksheet.py（路由） | 12 个 API 端点（树/重算/汇总/穿透/透视/导出/模板） |

### 后端同步→异步改造

10 个现有路由 + 13 个现有服务从 `Depends(sync_db)` + `db.query()` 改为 `Depends(get_db)` + `await db.execute(sa.select())`。

### 前端改造

- 重建 consolidationApi.ts（40+ 个 API 函数 + 类型定义）
- ConsolidationIndex.vue 改为 4 个 Tab（集团架构/差额表/穿透/自定义查询）
- 差额表列：下级汇总 | 调整借方 | 调整贷方 | 抵消借方 | 抵消贷方 | 差额净额 | 合并数
- 穿透面包屑：合并数 → 企业构成 → 抵消分录 → 试算表
- 透视表：行/列维度切换 + 转置开关 + 企业/科目筛选 + Excel 导出 + 模板保存

### 回归防护

- 现有 14 个子组件（平均 480 行）保留不删除，Tab 2-4 可复用
- Pinia store（consolidation.ts 180 行）保留，新增 worksheet/pivot 相关 action
- 已有的 12 张 ORM 表不修改，新增 2 张表
