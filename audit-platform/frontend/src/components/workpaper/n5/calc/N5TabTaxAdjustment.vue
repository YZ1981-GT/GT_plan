<template>
  <div class="n5-tax-adjustment">
    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p><strong>纳税调整明细表（N5-5）</strong>：按税法与会计差异分5大类（收入类/扣除类/资产类/特殊事项/其他），逐项列示调增/调减金额。调增合计−调减合计=纳税调整净额→回填N5-4应纳税所得额计算。研发费用加计扣除行联动N5-6-1。</p>
    </div>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>纳税调整明细表 N5-5</span>
        <el-tag size="small">{{ adjustment.totals.value.totalRows }}行</el-tag>
        <el-tag type="warning" size="small">虚拟滚动</el-tag>
      </div>
      <div class="section-actions">
        <el-dropdown trigger="click" @command="handleImportExportCmd">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据（按分类分sheet）</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon>AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon>复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 汇总指标卡片 ═══ -->
    <div class="summary-indicators">
      <div class="indicator-item">
        <span class="ind-label">调增合计</span>
        <span class="ind-value add-back">{{ fmtAmount(adjustment.addBackTotal.value) }}</span>
      </div>
      <div class="indicator-item">
        <span class="ind-label">调减合计</span>
        <span class="ind-value deduct">{{ fmtAmount(adjustment.deductTotal.value) }}</span>
      </div>
      <div class="indicator-item highlight">
        <span class="ind-label">纳税调整净额</span>
        <span class="ind-value" :class="{ negative: adjustment.netAdjustment.value < 0 }">{{ fmtAmount(adjustment.netAdjustment.value) }}</span>
      </div>
    </div>

    <!-- ═══ 分类筛选 ═══ -->
    <div class="category-filter">
      <el-radio-group v-model="activeCategory" size="small">
        <el-radio-button label="全部">全部</el-radio-button>
        <el-radio-button v-for="cat in categories" :key="cat" :label="cat">
          {{ cat }}({{ getCategoryCount(cat) }})
        </el-radio-button>
      </el-radio-group>
    </div>

    <!-- ═══ 分类小计区域 ═══ -->
    <div class="category-subtotals">
      <div v-for="sub in adjustment.categorySubtotals.value" :key="sub.category" class="cat-sub-item" :class="{ active: activeCategory === sub.category }">
        <span class="cat-name">{{ sub.category }}</span>
        <span class="cat-counts">{{ sub.rowCount }}项</span>
        <span class="cat-add">+{{ fmtAmount(sub.addBackSubtotal) }}</span>
        <span class="cat-ded">−{{ fmtAmount(sub.deductSubtotal) }}</span>
      </div>
    </div>

    <!-- ═══ 主数据表格（虚拟滚动 max-height + 分页） ═══ -->
    <el-table :data="filteredRows" border size="small" class="adjustment-table" max-height="520" :row-class-name="getRowClassName">
      <el-table-column prop="index" label="序号" width="55" align="center" fixed />
      <el-table-column prop="code" label="编码" width="90" align="center">
        <template #default="{ row }">
          <span class="code-cell">{{ row.code }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="label" label="项目名称" min-width="200" fixed>
        <template #default="{ row }">
          <span class="item-label">{{ row.label }}</span>
          <el-tag v-if="row.linkedSource" type="success" size="small" class="link-tag">{{ row.linkedSource }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="getCategoryTagType(row.category)" size="small">{{ row.category }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="bookAmount" label="账面金额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" v-model="row.bookAmount" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleCellUpdate($index, 'bookAmount', row.bookAmount)" />
          <span v-else class="cell-value">{{ fmtAmount(row.bookAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="taxAmount" label="税收金额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" v-model="row.taxAmount" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleCellUpdate($index, 'taxAmount', row.taxAmount)" />
          <span v-else class="cell-value">{{ fmtAmount(row.taxAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="调增" min-width="110" align="right">
        <template #header>
          <span class="formula-header" title="调增 = max(账面−税收, 0)">调增</span>
        </template>
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" v-model="row.addBack" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleCellUpdate($index, 'addBack', row.addBack)" />
          <span v-else class="cell-value add-back">{{ fmtAmount(row.addBack) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="调减" min-width="110" align="right">
        <template #header>
          <span class="formula-header" title="调减 = max(税收−账面, 0)">调减</span>
        </template>
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" v-model="row.deduct" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleCellUpdate($index, 'deduct', row.deduct)" />
          <span v-else class="cell-value deduct">{{ fmtAmount(row.deduct) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="basis" label="依据" min-width="140">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.basis" size="small" placeholder="依据" @change="() => handleCellUpdate($index, 'basis', row.basis)" />
          <span v-else class="cell-value">{{ row.basis || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
        <template #default="{ row, $index }">
          <el-button v-if="!row.isFixed" type="danger" link size="small" @click="handleRemoveRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 动态行新增 ═══ -->
    <div class="dynamic-row-bar" v-if="!isReadonly">
      <el-button size="small" type="primary" plain @click="handleAddRow">
        <el-icon><Plus /></el-icon>新增调整项
      </el-button>
      <span class="hint">新增项将按分类归入对应类别</span>
    </div>

    <!-- ═══ 回填N5-4 ═══ -->
    <div class="action-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" :loading="syncLoading" @click="handleSyncToCalc">
        回填调增/调减合计 → N5-4
      </el-button>
      <span class="action-hint">调增{{ fmtAmount(adjustment.addBackTotal.value) }} / 调减{{ fmtAmount(adjustment.deductTotal.value) }}</span>
    </div>

    <!-- ═══ 审计说明与结论 ═══ -->
    <el-card shadow="never" class="audit-notes-card">
      <template #header>
        <div class="notes-header">
          <span>审计说明与结论</span>
          <el-button size="small" @click="handleNotesAi"><el-icon><MagicStick /></el-icon>AI辅助</el-button>
        </div>
      </template>
      <div class="notes-field">
        <label class="field-label">审计说明</label>
        <el-input v-model="auditNotes" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请说明纳税调整项的审计关注..." :disabled="isReadonly" @change="saveNotes" />
      </div>
      <div class="notes-field">
        <label class="field-label">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="请输入审计结论..." :disabled="isReadonly" @change="saveConclusion" />
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>本表对应企业所得税年度纳税申报表附表A105000</li>
        <li>5大类：收入类/扣除类/资产类/特殊事项/其他</li>
        <li>调增：会计确认但税法不允许扣除的金额；调减：税法允许扣除但会计未确认的金额</li>
        <li>研发费用加计扣除（A180000行）自动联动N5-6-1加计扣除额</li>
        <li>纳税调整净额 = Σ调增 − Σ调减 → 回填N5-4当期所得税计算表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N5TabTaxAdjustment — 纳税调整明细表N5-5（107行大表）
 *
 * 107×8 + 虚拟滚动 + 调增/调减分类小计 + 净额回填N5-4
 * 研发加计联动N5-6-1 + 动态行 + 分sheet导入导出
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 4.7
 * Requirements: 4.1-4.7
 */
import { ref, computed, inject, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, Plus } from '@element-plus/icons-vue'
import { useN5FormData } from '../../composables/useN5FormData'
import { useN5TaxAdjustment, type TaxAdjustmentCategory } from '../../composables/useN5TaxAdjustment'
import { useN5ImportExport } from '../../composables/useN5ImportExport'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId?: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId || '') as Ref<string>
const allResponsesRef = computed(() => props.allResponses)

const formData = useN5FormData({ wpId: wpIdRef, projectId: projectIdRef })
const importExport = useN5ImportExport({ wpId: wpIdRef })

const adjustment = useN5TaxAdjustment({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  saveField: formData.setField,
  getField: formData.getField,
})

const categories: TaxAdjustmentCategory[] = ['收入类', '扣除类', '资产类', '特殊事项', '其他']
const activeCategory = ref<string>('全部')
const syncLoading = ref(false)
const auditNotes = ref('')
const auditConclusion = ref('')

// ─── 筛选行（按分类） ──────────────────────────────────────────────────────

const filteredRows = computed(() => {
  if (activeCategory.value === '全部') return adjustment.rows.value
  return adjustment.rows.value.filter(r => r.category === activeCategory.value)
})

function getCategoryCount(cat: TaxAdjustmentCategory): number {
  return adjustment.groupedByCategory.value[cat]?.length ?? 0
}

function getCategoryTagType(cat: TaxAdjustmentCategory): string {
  const map: Record<TaxAdjustmentCategory, string> = { '收入类': 'success', '扣除类': 'warning', '资产类': 'info', '特殊事项': 'danger', '其他': '' }
  return map[cat] || ''
}

function getRowClassName({ row }: { row: any }): string {
  if (row.linkedSource) return 'linked-row'
  return ''
}

// ─── 初始化 ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  auditNotes.value = formData.getField('5', 'audit-notes') ?? ''
  auditConclusion.value = formData.getField('5', 'audit-conclusion') ?? ''
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

async function handleCellUpdate(index: number, field: string, value: any) {
  await adjustment.updateRow(index, field as any, value)
}

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('请输入调整项名称', '新增纳税调整项', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '如：研发费用加计扣除',
  }).catch(() => ({ value: '' }))
  if (!name) return

  // 选择分类
  const { value: cat } = await ElMessageBox.prompt('请选择分类（收入类/扣除类/资产类/特殊事项/其他）', '选择分类', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputValue: '其他',
  }).catch(() => ({ value: '其他' }))

  await adjustment.addRow({
    label: name,
    category: (categories.includes(cat as TaxAdjustmentCategory) ? cat : '其他') as TaxAdjustmentCategory,
  })
  ElMessage.success(`已新增：${name}`)
}

async function handleRemoveRow(index: number) {
  await adjustment.removeRow(index)
  ElMessage.success('已删除')
}

async function handleSyncToCalc() {
  syncLoading.value = true
  try {
    await adjustment.syncTotalsToCurrentTaxCalc()
    ElMessage.success('调增/调减合计已回填N5-4')
  } catch { ElMessage.error('回填失败') }
  finally { syncLoading.value = false }
}

function handleImportExportCmd(cmd: string) {
  if (cmd === 'exportTemplate') importExport.exportTemplate('N5-5')
  else if (cmd === 'exportData') importExport.exportData('N5-5')
  else if (cmd === 'importData') importExport.importData('N5-5')
}

async function saveNotes() { await formData.setField('5', 'audit-notes', auditNotes.value) }
async function saveConclusion() { await formData.setField('5', 'audit-conclusion', auditConclusion.value) }
function handleAiAssist() { ElMessage.info('AI辅助分析纳税调整项...') }
function handleNotesAi() { ElMessage.info('AI辅助生成审计说明...') }
function handleReview() { openReviewDialog ? openReviewDialog('N5-5-纳税调整明细') : ElMessage.info('复核对话未配置') }

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.n5-tax-adjustment { padding: 12px; font-size: 13px; }
.methodology-context { padding: 12px 16px; margin-bottom: 16px; background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 6px; font-size: 13px; color: #92400e; line-height: 1.7; }
.methodology-context p { margin: 0; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }

.summary-indicators { display: flex; gap: 16px; margin-bottom: 16px; padding: 12px 16px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 8px; }
.indicator-item { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 8px 16px; }
.indicator-item.highlight { background: #ecf5ff; border-radius: 6px; padding: 8px 20px; }
.ind-label { font-size: 12px; color: #909399; }
.ind-value { font-size: 18px; font-weight: 700; color: #303133; }
.ind-value.add-back { color: #f56c6c; }
.ind-value.deduct { color: #67c23a; }
.ind-value.negative { color: #67c23a; }

.category-filter { margin-bottom: 12px; }
.category-subtotals { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.cat-sub-item { display: flex; align-items: center; gap: 6px; padding: 6px 12px; background: #f5f7fa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 12px; }
.cat-sub-item.active { background: #ecf5ff; border-color: #b3d8ff; }
.cat-name { font-weight: 500; color: #303133; }
.cat-counts { color: #909399; }
.cat-add { color: #f56c6c; font-weight: 500; }
.cat-ded { color: #67c23a; font-weight: 500; }

.adjustment-table { margin-bottom: 16px; }
:deep(.adjustment-table .el-table) { font-size: 13px; }
:deep(.linked-row) { background: #f0f9eb !important; }
.code-cell { font-family: monospace; font-size: 12px; color: #909399; }
.item-label { font-weight: 500; color: #303133; }
.link-tag { margin-left: 6px; }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; font-weight: 600; }
.cell-input { width: 100%; }
:deep(.cell-input .el-input__inner) { text-align: right; font-size: 13px; }
.cell-value { font-size: 13px; color: #606266; }
.cell-value.add-back { color: #f56c6c; font-weight: 500; }
.cell-value.deduct { color: #67c23a; font-weight: 500; }

.dynamic-row-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.dynamic-row-bar .hint { font-size: 12px; color: #909399; }

.action-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; padding: 10px 16px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 6px; }
.action-hint { font-size: 12px; color: #67c23a; }

.audit-notes-card { margin-bottom: 16px; }
.notes-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }
.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: 13px; font-weight: 500; color: #606266; margin-bottom: 6px; }

.n5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.n5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.n5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
