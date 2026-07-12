<template>
  <div class="n5-current-tax-calc">
    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <p><strong>当期所得税计算链</strong>：会计利润总额(A利润表) → ±纳税调整(N5-5) → 应纳税所得额 → ×适用税率 → −减免税额(N5-6) → 当期应纳所得税。应纳税所得额为负时标记"亏损结转"，当期所得税为零。</p>
    </div>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>当期所得税费用计算表 N5-4</span>
        <el-tag type="danger" size="small">核心计算</el-tag>
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

    <!-- ═══ 亏损警告 ═══ -->
    <el-alert v-if="calc.isLoss.value" type="warning" :closable="false" show-icon class="loss-alert">
      <template #title>
        <span class="loss-title">⚠ 应纳税所得额为负（亏损）：{{ fmtAmount(calc.taxableIncome.value) }}，当期所得税为零</span>
      </template>
      <span>亏损可结转以后年度弥补（一般5年内，高新技术企业10年）</span>
    </el-alert>

    <!-- ═══ 计算链汇总卡片 ═══ -->
    <div class="calc-summary-cards">
      <div class="calc-card">
        <span class="card-label">会计利润</span>
        <span class="card-value" :class="{ negative: calc.accountingProfit.value < 0 }">{{ fmtAmount(calc.accountingProfit.value) }}</span>
        <span class="card-source">← <GtIndexChip value="A" /> 利润表</span>
      </div>
      <div class="calc-card">
        <span class="card-label">纳税调增</span>
        <span class="card-value">{{ fmtAmount(calc.addBackTotal.value) }}</span>
        <span class="card-source">← N5-5</span>
      </div>
      <div class="calc-card">
        <span class="card-label">纳税调减</span>
        <span class="card-value">{{ fmtAmount(calc.deductTotal.value) }}</span>
        <span class="card-source">← N5-5</span>
      </div>
      <div class="calc-card highlight">
        <span class="card-label">应纳税所得额</span>
        <span class="card-value" :class="{ negative: calc.taxableIncome.value < 0, loss: calc.isLoss.value }">{{ fmtAmount(calc.taxableIncome.value) }}</span>
        <span class="card-source">= 利润+调增−调减</span>
      </div>
      <div class="calc-card">
        <span class="card-label">当期所得税</span>
        <span class="card-value primary">{{ fmtAmount(calc.currentTax.value) }}</span>
        <span class="card-source">→ 回填N5-1</span>
      </div>
    </div>

    <!-- ═══ 主数据表格（核心9行+动态行） ═══ -->
    <el-table :data="calc.rows.value" border size="small" class="calc-table" row-key="index">
      <el-table-column prop="lineNo" label="行号" width="60" align="center" />
      <el-table-column prop="label" label="项目" min-width="260">
        <template #default="{ row }">
          <span :class="['item-label', { 'formula-row': row.isFormula, 'loss-row': row.label.includes('应纳税所得额') && calc.isLoss.value }]">
            {{ row.label }}
          </span>
          <el-tag v-if="row.source" type="info" size="small" class="source-tag">{{ row.source }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="金额" min-width="160" align="right">
        <template #header>
          <span class="formula-header" title="公式单元格为自动计算">金额</span>
        </template>
        <template #default="{ row }">
          <template v-if="row.isFormula">
            <el-tooltip :content="getFormulaTooltip(row)" placement="top">
              <span class="formula-cell" :class="{ 'loss-value': row.label.includes('应纳税所得额') && calc.isLoss.value }">
                {{ row.lineNo === '5' ? fmtPercent(row.amount) : fmtAmount(row.amount) }}
              </span>
            </el-tooltip>
          </template>
          <template v-else>
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" :precision="row.lineNo === '5' ? 4 : 2" size="small" class="cell-input" @change="() => handleRowAmountChange(row)" />
            <span v-else class="cell-value">
              {{ row.lineNo === '5' ? fmtPercent(row.amount) : fmtAmount(row.amount) }}
            </span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="来源/依据" min-width="140">
        <template #default="{ row }">
          <span class="source-text">{{ row.source || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 适用税率编辑 ═══ -->
    <div class="tax-rate-section">
      <span class="rate-label">适用税率：</span>
      <el-select v-if="!isReadonly" v-model="selectedTaxRate" size="small" style="width: 180px" @change="handleTaxRateChange">
        <el-option :value="0.25" label="25%（一般企业）" />
        <el-option :value="0.15" label="15%（高新技术企业）" />
        <el-option :value="0.20" label="20%（小型微利企业）" />
        <el-option :value="0.10" label="10%（非居民企业）" />
      </el-select>
      <span v-else class="rate-value">{{ fmtPercent(calc.taxRate.value) }}</span>
      <span class="rate-hint">高新认定状态请查阅N5-6-2</span>
    </div>

    <!-- ═══ 动态行管理 ═══ -->
    <div class="dynamic-row-bar" v-if="!isReadonly">
      <el-button size="small" type="primary" plain @click="handleAddDynamicRow">
        <el-icon><Plus /></el-icon>新增附加计算项
      </el-button>
    </div>

    <!-- ═══ 回填N5-1按钮 ═══ -->
    <div class="action-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" :loading="syncLoading" @click="handleSyncToAdjudication">
        回填当期所得税 → N5-1审定表
      </el-button>
      <span class="action-hint">将当期所得税费用{{ fmtAmount(calc.currentTax.value) }}回填审定表</span>
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
        <el-input v-model="auditNotes" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请说明当期所得税计算的审计关注事项..." :disabled="isReadonly" @change="saveNotes" />
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
        <li>计算链：会计利润(A利润表) + 纳税调增(N5-5) − 纳税调减(N5-5) = 应纳税所得额</li>
        <li>应纳所得税额 = 应纳税所得额 × 适用税率</li>
        <li>当期应纳所得税 = 应纳所得税额 − 减免税额(N5-6) − 抵免税额</li>
        <li>应纳税所得额为负时标记<strong>亏损结转</strong>，当期所得税为零</li>
        <li>高新技术企业适用15%优惠税率（需N5-6-2认定通过）</li>
        <li>加计扣除额(N5-6-1)通过N5-5纳税调减项体现</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N5TabCurrentTaxCalc — 当期所得税费用计算表N5-4（核心）
 *
 * 82行7列，计算链：会计利润→±调整→应纳税所得额→×税率→减免→当期所得税
 * A利润表联动 + N5-5/N5-6/N5-6-1取数 + 结果回填N5-1
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 4.6
 * Requirements: 3.1-3.7
 */
import { ref, computed, inject, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, Plus } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN5FormData } from '../../composables/useN5FormData'
import { useN5CurrentTaxCalc } from '../../composables/useN5CurrentTaxCalc'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId) as Ref<string>
const allResponsesRef = computed(() => props.allResponses)

const formData = useN5FormData({ wpId: wpIdRef, projectId: projectIdRef })

const calc = useN5CurrentTaxCalc({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  saveField: formData.setField,
  getField: formData.getField,
})

const selectedTaxRate = ref(0.25)
const syncLoading = ref(false)
const auditNotes = ref('')
const auditConclusion = ref('')

// ─── 初始化 ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  selectedTaxRate.value = calc.taxRate.value || 0.25
  auditNotes.value = formData.getField('4', 'audit-notes') ?? ''
  auditConclusion.value = formData.getField('4', 'audit-conclusion') ?? ''
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

async function handleTaxRateChange(rate: number) {
  await calc.setTaxRate(rate)
}

async function handleRowAmountChange(row: any) {
  if (row.lineNo === '5') {
    await calc.setTaxRate(row.amount)
    selectedTaxRate.value = row.amount
  } else if (row.lineNo === '8') {
    await calc.setTaxCredit(row.amount)
  }
}

async function handleSyncToAdjudication() {
  syncLoading.value = true
  try {
    await calc.syncCurrentTaxToAdjudication()
    ElMessage.success(`当期所得税${fmtAmount(calc.currentTax.value)}已回填N5-1审定表`)
  } catch { ElMessage.error('回填失败') }
  finally { syncLoading.value = false }
}

async function handleAddDynamicRow() {
  const { value: name } = await ElMessageBox.prompt('请输入附加计算项名称', '新增计算项', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '如：境外所得抵免',
  }).catch(() => ({ value: '' }))
  if (!name) return
  await formData.setField('4', 'dynamic-row-' + Date.now(), { label: name, amount: 0 })
  ElMessage.success(`已新增：${name}`)
}

function getFormulaTooltip(row: any): string {
  const tooltips: Record<string, string> = {
    '1': '来自A类利润表联动',
    '2': '来自N5-5纳税调整调增合计',
    '3': '来自N5-5纳税调整调减合计',
    '4': '= 会计利润(行1) + 调增(行2) − 调减(行3)',
    '6': '= 应纳税所得额(行4) × 税率(行5)',
    '7': '来自N5-6税收优惠合计',
    '9': '= 应纳所得税额(行6) − 减免(行7) − 抵免(行8)',
  }
  return tooltips[row.lineNo] || '公式自动计算'
}

async function saveNotes() { await formData.setField('4', 'audit-notes', auditNotes.value) }
async function saveConclusion() { await formData.setField('4', 'audit-conclusion', auditConclusion.value) }
function handleAiAssist() { ElMessage.info('AI辅助分析当期所得税计算...') }
function handleNotesAi() { ElMessage.info('AI辅助生成审计说明...') }
function handleReview() { openReviewDialog ? openReviewDialog('N5-4-当期所得税计算') : ElMessage.info('复核对话未配置') }

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPercent(val: number | null | undefined): string {
  if (val == null) return '—'
  return (Number(val) * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.n5-current-tax-calc { padding: 12px; font-size: var(--wp-font-size, 13px); }
.methodology-context { padding: 12px 16px; margin-bottom: 16px; background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #92400e; line-height: 1.7; }
.methodology-context p { margin: 0; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }

.loss-alert { margin-bottom: 16px; }
.loss-title { font-weight: 600; }

.calc-summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.calc-card { display: flex; flex-direction: column; align-items: center; padding: 12px 8px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 8px; gap: 4px; }
.calc-card.highlight { background: #ecf5ff; border-color: #b3d8ff; }
.card-label { font-size: 12px; color: #909399; font-weight: 500; }
.card-value { font-size: 16px; font-weight: 700; color: #303133; }
.card-value.negative { color: #f56c6c; }
.card-value.loss { color: #e6a23c; text-decoration: underline wavy #e6a23c; }
.card-value.primary { color: #409eff; }
.card-source { font-size: 11px; color: #c0c4cc; }

.calc-table { margin-bottom: 16px; }
:deep(.calc-table .el-table) { font-size: var(--wp-font-size, 13px); }
.item-label { font-weight: 500; color: #303133; }
.formula-row { color: #409eff; font-weight: 600; }
.loss-row { color: #e6a23c; font-weight: 700; }
.source-tag { margin-left: 8px; }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-weight: 500; color: #303133; padding-bottom: 1px; }
.loss-value { color: #e6a23c !important; font-weight: 700; }
.cell-input { width: 100%; }
:deep(.cell-input .el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }
.cell-value { font-size: var(--wp-font-size, 13px); color: #606266; }
.source-text { font-size: 12px; color: #909399; }

.tax-rate-section { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding: 10px 16px; background: #f5f7fa; border: 1px solid #ebeef5; border-radius: 6px; }
.rate-label { font-weight: 500; color: #303133; }
.rate-value { font-weight: 600; color: #409eff; }
.rate-hint { font-size: 12px; color: #909399; margin-left: auto; }

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
