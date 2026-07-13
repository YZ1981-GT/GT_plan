<template>
  <div class="n5-property-loss">
    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p><strong>财产损失明细表（N5-7）</strong>：列示企业发生的各项财产损失，区分已核准扣除/待核准/未核准部分。纳税调整额 = 账面损失 − 税前扣除额。未核准的财产损失不得税前扣除，形成纳税调增回填N5-5。损失须有充分证据链（如评估报告/法院判决/债务人破产清算文书）。</p>
    </div>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>财产损失明细表 N5-7</span>
        <el-tag size="small">15×7</el-tag>
        <el-tag v-if="pendingApprovalCount > 0" type="warning" size="small">{{ pendingApprovalCount }}项待核准</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon>AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon>复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 汇总卡片 ═══ -->
    <div class="loss-summary-cards">
      <div class="ls-card">
        <span class="ls-label">账面损失合计</span>
        <span class="ls-value">{{ fmtAmount(totalBookLoss) }}</span>
      </div>
      <div class="ls-card">
        <span class="ls-label">税前扣除额合计</span>
        <span class="ls-value">{{ fmtAmount(totalDeductible) }}</span>
      </div>
      <div class="ls-card highlight">
        <span class="ls-label">纳税调整额合计</span>
        <span class="ls-value" :class="{ 'add-back': totalAdjustment > 0 }">{{ fmtAmount(totalAdjustment) }}</span>
        <span class="ls-sub">→ N5-5调增</span>
      </div>
    </div>

    <!-- ═══ 未核准警告 ═══ -->
    <el-alert v-if="unapprovedRows.length > 0" type="warning" :closable="false" show-icon class="unapproved-alert">
      <template #title>
        <span>{{ unapprovedRows.length }}项财产损失未核准扣除，形成纳税调增</span>
      </template>
      <span>未核准财产损失须提供充分证据（评估报告/法院判决/清算文书等），否则不得税前扣除</span>
    </el-alert>

    <!-- ═══ 主数据表格 ═══ -->
    <el-table :data="lossRows" border size="small" show-summary :summary-method="getSummaries" class="loss-table" :row-class-name="getLossRowClass">
      <el-table-column prop="index" label="序号" width="55" align="center" />
      <el-table-column prop="itemName" label="损失项目" min-width="180">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.itemName" size="small" @change="() => handleFieldUpdate($index, 'itemName', row.itemName)" />
          <span v-else class="item-name">{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="bookLoss" label="账面损失" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" v-model="row.bookLoss" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleAmountUpdate($index)" />
          <span v-else class="cell-value">{{ fmtAmount(row.bookLoss) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="approvedDeduction" label="已核准扣除" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" v-model="row.approvedDeduction" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleAmountUpdate($index)" />
          <span v-else class="cell-value">{{ fmtAmount(row.approvedDeduction) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="pendingApproval" label="待核准" min-width="110" align="right">
        <template #default="{ row }">
          <span class="cell-value" :class="{ 'pending-value': row.pendingApproval > 0 }">{{ fmtAmount(row.pendingApproval) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="税前扣除额" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="税前扣除额 = 已核准扣除">税前扣除额</span>
        </template>
        <template #default="{ row }">
          <el-tooltip content="税前扣除额 = 已核准扣除额" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.deductibleLoss) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="纳税调整额" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="纳税调整额 = 账面损失 − 税前扣除额">纳税调整额</span>
        </template>
        <template #default="{ row }">
          <el-tooltip content="纳税调整额 = 账面损失 − 税前扣除额" placement="top">
            <span class="formula-cell" :class="{ 'adjustment-positive': row.adjustment > 0 }">{{ fmtAmount(row.adjustment) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="basis" label="依据" min-width="140">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.basis" size="small" placeholder="证据文书" @change="() => handleFieldUpdate($index, 'basis', row.basis)" />
          <span v-else class="cell-value">{{ row.basis || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" @click="handleRemoveRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 新增行 ═══ -->
    <div class="dynamic-row-bar" v-if="!isReadonly">
      <el-button size="small" type="primary" plain @click="handleAddRow">
        <el-icon><Plus /></el-icon>新增财产损失项
      </el-button>
    </div>

    <!-- ═══ 回填N5-5 ═══ -->
    <div class="action-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" :loading="syncLoading" @click="handleSyncToTaxAdjustment">
        回填纳税调整额 → N5-5调增
      </el-button>
      <span class="action-hint">纳税调整额合计 {{ fmtAmount(totalAdjustment) }}（调增）</span>
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
        <el-input v-model="auditNotes" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请说明财产损失核查情况及证据链完整性..." :disabled="isReadonly" @change="saveNotes" />
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
        <li>纳税调整额 = 账面损失 − 税前扣除额（calcPropertyLossAdjustment）</li>
        <li>税前扣除额 = 已核准税前扣除金额（须经税务机关审批或备案）</li>
        <li>待核准 = 账面损失 − 已核准扣除，表示尚未取得扣除依据的部分</li>
        <li>未核准扣除的财产损失形成纳税调增→回填N5-5资产类调增项</li>
        <li>财产损失证据链：内部审批+外部证据（评估报告/法院判决/清算文书/保险赔付凭证）</li>
        <li>关注大额损失、关联方损失、异常时点损失</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N5TabPropertyLoss — 财产损失明细表N5-7
 *
 * 15×7 + 12公式 + 账面损失/核准扣除/待核准
 * 纳税调整额=账面−税前扣除 + 未核准警告 + 回填N5-5
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 4.12
 * Requirements: 7.1-7.4
 */
import { ref, reactive, computed, inject, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, Plus } from '@element-plus/icons-vue'
import { useN5FormData } from '../../composables/useN5FormData'
import { calcPropertyLossAdjustment } from '../../composables/useN5TaxAdjustmentEngine'
import { calcSubtotal } from '../../composables/useN5FormulaEngine'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId?: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId || '') as Ref<string>

const formData = useN5FormData({ wpId: wpIdRef, projectId: projectIdRef })

// ─── 数据结构 ────────────────────────────────────────────────────────────────

interface LossRow {
  index: number
  itemName: string
  bookLoss: number
  approvedDeduction: number
  pendingApproval: number
  deductibleLoss: number
  adjustment: number
  basis: string
}

const lossRows = reactive<LossRow[]>([
  { index: 1, itemName: '坏账损失', bookLoss: 0, approvedDeduction: 0, pendingApproval: 0, deductibleLoss: 0, adjustment: 0, basis: '' },
  { index: 2, itemName: '存货报废损失', bookLoss: 0, approvedDeduction: 0, pendingApproval: 0, deductibleLoss: 0, adjustment: 0, basis: '' },
  { index: 3, itemName: '固定资产报废损失', bookLoss: 0, approvedDeduction: 0, pendingApproval: 0, deductibleLoss: 0, adjustment: 0, basis: '' },
  { index: 4, itemName: '投资损失', bookLoss: 0, approvedDeduction: 0, pendingApproval: 0, deductibleLoss: 0, adjustment: 0, basis: '' },
  { index: 5, itemName: '其他财产损失', bookLoss: 0, approvedDeduction: 0, pendingApproval: 0, deductibleLoss: 0, adjustment: 0, basis: '' },
])

const syncLoading = ref(false)
const auditNotes = ref('')
const auditConclusion = ref('')

// ─── 计算 ────────────────────────────────────────────────────────────────────

function recalcRow(row: LossRow) {
  row.deductibleLoss = row.approvedDeduction
  row.pendingApproval = Math.max(0, row.bookLoss - row.approvedDeduction)
  row.adjustment = calcPropertyLossAdjustment(row.bookLoss, row.deductibleLoss)
}

const totalBookLoss = computed(() => calcSubtotal(lossRows.map(r => r.bookLoss)))
const totalDeductible = computed(() => calcSubtotal(lossRows.map(r => r.deductibleLoss)))
const totalAdjustment = computed(() => calcSubtotal(lossRows.map(r => r.adjustment)))
const pendingApprovalCount = computed(() => lossRows.filter(r => r.pendingApproval > 0).length)
const unapprovedRows = computed(() => lossRows.filter(r => r.pendingApproval > 0))

function getLossRowClass({ row }: { row: LossRow }): string {
  if (row.pendingApproval > 0) return 'unapproved-row'
  return ''
}

function getSummaries({ columns }: { columns: any[] }) {
  return columns.map((_c: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 1) return ''
    if (idx === 2) return fmtAmount(totalBookLoss.value)
    if (idx === 3) return fmtAmount(totalDeductible.value)
    if (idx === 4) return fmtAmount(calcSubtotal(lossRows.map(r => r.pendingApproval)))
    if (idx === 5) return fmtAmount(totalDeductible.value)
    if (idx === 6) return fmtAmount(totalAdjustment.value)
    return ''
  })
}

// ─── 初始化 ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  const saved = formData.getField('7', 'loss-rows')
  if (saved && Array.isArray(saved)) {
    lossRows.splice(0, lossRows.length)
    saved.forEach((r: any, i: number) => {
      const row: LossRow = {
        index: i + 1,
        itemName: r.itemName || `损失项${i + 1}`,
        bookLoss: r.bookLoss || 0,
        approvedDeduction: r.approvedDeduction || 0,
        pendingApproval: 0,
        deductibleLoss: 0,
        adjustment: 0,
        basis: r.basis || '',
      }
      recalcRow(row)
      lossRows.push(row)
    })
  }
  auditNotes.value = formData.getField('7', 'audit-notes') ?? ''
  auditConclusion.value = formData.getField('7', 'audit-conclusion') ?? ''
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

async function handleAmountUpdate(index: number) {
  recalcRow(lossRows[index])
  await saveRows()
}

async function handleFieldUpdate(index: number, field: string, value: any) {
  ;(lossRows[index] as any)[field] = value
  await saveRows()
}

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('请输入损失项目名称', '新增财产损失项', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '如：存货报废损失',
  }).catch(() => ({ value: '' }))
  if (!name) return
  const row: LossRow = {
    index: lossRows.length + 1,
    itemName: name,
    bookLoss: 0,
    approvedDeduction: 0,
    pendingApproval: 0,
    deductibleLoss: 0,
    adjustment: 0,
    basis: '',
  }
  lossRows.push(row)
  await saveRows()
  ElMessage.success(`已新增：${name}`)
}

async function handleRemoveRow(index: number) {
  lossRows.splice(index, 1)
  // 重新编号
  lossRows.forEach((r, i) => { r.index = i + 1 })
  await saveRows()
  ElMessage.success('已删除')
}

async function handleSyncToTaxAdjustment() {
  syncLoading.value = true
  try {
    await formData.setField('7', 'property-loss-adjustment', totalAdjustment.value)
    ElMessage.success(`纳税调整额${fmtAmount(totalAdjustment.value)}已回填N5-5`)
  } catch { ElMessage.error('回填失败') }
  finally { syncLoading.value = false }
}

async function saveRows() {
  await formData.setField('7', 'loss-rows', lossRows.map(r => ({
    itemName: r.itemName,
    bookLoss: r.bookLoss,
    approvedDeduction: r.approvedDeduction,
    basis: r.basis,
  })))
}

async function saveNotes() { await formData.setField('7', 'audit-notes', auditNotes.value) }
async function saveConclusion() { await formData.setField('7', 'audit-conclusion', auditConclusion.value) }
function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n5-property-loss',
      prompt: '请基于所得税费用底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleNotesAi() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n5-property-loss',
      prompt: '请基于所得税费用底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog ? openReviewDialog('N5-7-财产损失') : ElMessage.info('复核对话未配置') }

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.n5-property-loss { padding: 12px; font-size: var(--wp-font-size, 13px); }
.methodology-context { padding: 12px 16px; margin-bottom: 16px; background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #92400e; line-height: 1.7; }
.methodology-context p { margin: 0; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }

.loss-summary-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.ls-card { display: flex; flex-direction: column; align-items: center; padding: 12px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 8px; gap: 4px; }
.ls-card.highlight { background: #fff3e0; border-color: #ffcc80; }
.ls-label { font-size: 12px; color: #909399; }
.ls-value { font-size: 16px; font-weight: 700; color: #303133; }
.ls-value.add-back { color: #f56c6c; }
.ls-sub { font-size: 11px; color: #c0c4cc; }

.unapproved-alert { margin-bottom: 16px; }

.loss-table { margin-bottom: 16px; }
:deep(.loss-table .el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.unapproved-row) { background: #fffbe6 !important; }
.item-name { font-weight: 500; color: #303133; }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-weight: 500; color: #303133; padding-bottom: 1px; }
.adjustment-positive { color: #f56c6c !important; font-weight: 700; }
.pending-value { color: #e6a23c; font-weight: 600; }
.cell-input { width: 100%; }
:deep(.cell-input .el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }
.cell-value { font-size: var(--wp-font-size, 13px); color: #606266; }

.dynamic-row-bar { margin-bottom: 16px; }

.action-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; padding: 10px 16px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 6px; }
.action-hint { font-size: 12px; color: #67c23a; }

.audit-notes-card { margin-bottom: 16px; }
.notes-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }
.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #606266; margin-bottom: 6px; }

.n5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.n5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
