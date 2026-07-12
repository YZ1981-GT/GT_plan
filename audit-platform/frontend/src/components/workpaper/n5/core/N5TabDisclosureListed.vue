<template>
  <div class="n5-disclosure-listed">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>附注披露信息（上市公司）</span>
        <el-tag size="small">29×12</el-tag>
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

    <!-- ═══ 所得税费用构成 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header><span class="card-title">（一）所得税费用</span></template>
      <el-table :data="expenseRows" border size="small" class="disclosure-table">
        <el-table-column prop="item" label="项目" min-width="200" />
        <el-table-column label="本期金额" min-width="130" align="right">
          <template #header><span class="formula-header" title="从N5-1审定表取数">本期金额</span></template>
          <template #default="{ row }">
            <el-tooltip :content="row.source" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.currentAmount) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上期金额" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.priorAmount" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleSave()" />
            <span v-else>{{ fmtAmount(row.priorAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 所得税费用与会计利润调节表 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header><span class="card-title">（二）所得税费用与会计利润的调节过程</span></template>
      <el-table :data="reconciliationRows" border size="small" class="disclosure-table">
        <el-table-column prop="item" label="项目" min-width="260" />
        <el-table-column label="金额" min-width="130" align="right">
          <template #header><span class="formula-header" title="调节过程">金额</span></template>
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isFormula" v-model="row.amount" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleSave()" />
            <el-tooltip v-else :content="row.formula || ''" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.amount) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 有效税率分析 ═══ -->
    <div class="etr-analysis">
      <span class="etr-title">有效税率分析：</span>
      <span class="etr-value">{{ etr.rate != null ? fmtPercent(etr.rate) : '—' }}</span>
      <span class="etr-desc">（所得税费用 / 会计利润总额，法定税率25%）</span>
      <el-tag v-if="etr.rate != null && Math.abs(etr.rate - 0.25) > 0.05" type="warning" size="small">
        偏离法定税率 {{ fmtPercent(Math.abs((etr.rate ?? 0) - 0.25)) }}
      </el-tag>
    </div>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="audit-notes-card">
      <template #header><span class="notes-title">审计说明与结论</span></template>
      <div class="notes-field">
        <label class="field-label">附注审核说明</label>
        <el-input v-model="auditNotes" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请输入..." :disabled="isReadonly" @change="saveNotes" />
      </div>
      <div class="notes-field">
        <label class="field-label">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="请输入..." :disabled="isReadonly" @change="saveConclusion" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * N5TabDisclosureListed — 附注披露信息（上市公司，29×12）
 * 所得税费用与会计利润调节表+有效税率分析+subscribe刷新
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 4.5
 * Requirements: 10.1-10.3
 */
import { ref, computed, inject, onMounted, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { useN5FormData } from '../../composables/useN5FormData'
import { useN5CrossSheet } from '../../composables/useN5CrossSheet'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<((s: string) => void) | undefined>('openReviewDialog', undefined)
const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId) as Ref<string>
const allResponsesRef = computed(() => props.allResponses)

const formData = useN5FormData({ wpId: wpIdRef, projectId: projectIdRef })
const { adjudicationVsCalc, effectiveTaxRate, profitFromIncomeStatement } = useN5CrossSheet(allResponsesRef, { wpId: wpIdRef, projectId: projectIdRef })

const etr = effectiveTaxRate
const auditNotes = ref('')
const auditConclusion = ref('')

// ─── subscribe 'substantive:adjudicated' 自动刷新 ────────────────────────────

function onSubstantiveAdjudicated(_payload: any) {
  // 重新加载数据刷新附注
  formData.loadData()
}

eventBus.on('substantive:adjudicated' as any, onSubstantiveAdjudicated)
onScopeDispose(() => { eventBus.off('substantive:adjudicated' as any, onSubstantiveAdjudicated) })

// ─── 所得税费用构成表（从N5-1取数） ─────────────────────────────────────────

interface ExpenseRow { item: string; currentAmount: number; priorAmount: number; source: string }

const expenseRows = computed<ExpenseRow[]>(() => [
  { item: '当期所得税费用', currentAmount: adjudicationVsCalc.value.current, priorAmount: formData.getField('disclosure-listed', 'prior-current') ?? 0, source: '取自N5-1审定表当期所得税行' },
  { item: '递延所得税费用', currentAmount: adjudicationVsCalc.value.deferred, priorAmount: formData.getField('disclosure-listed', 'prior-deferred') ?? 0, source: '取自N5-1审定表递延所得税行' },
  { item: '所得税费用合计', currentAmount: adjudicationVsCalc.value.total, priorAmount: (formData.getField('disclosure-listed', 'prior-current') ?? 0) + (formData.getField('disclosure-listed', 'prior-deferred') ?? 0), source: '= 当期 + 递延' },
])

// ─── 调节表（所得税费用与会计利润调节） ──────────────────────────────────────

interface ReconRow { item: string; amount: number; isFormula: boolean; formula?: string }

const reconciliationRows = computed<ReconRow[]>(() => {
  const profit = profitFromIncomeStatement.value.accountingProfit
  const taxAtRate = profit * 0.25
  const total = adjudicationVsCalc.value.total
  const diff = total - taxAtRate

  return [
    { item: '利润总额', amount: profit, isFormula: true, formula: '取自A类利润表' },
    { item: '按法定税率计算的所得税费用（25%）', amount: taxAtRate, isFormula: true, formula: '= 利润总额 × 25%' },
    { item: '加：纳税调整增加额的税收影响', amount: formData.getField('disclosure-listed', 'adj-add') ?? 0, isFormula: false },
    { item: '减：纳税调整减少额的税收影响', amount: formData.getField('disclosure-listed', 'adj-ded') ?? 0, isFormula: false },
    { item: '加：递延所得税费用', amount: adjudicationVsCalc.value.deferred, isFormula: true, formula: '取自N5-8递延所得税费用' },
    { item: '减：税收优惠的影响', amount: formData.getField('disclosure-listed', 'benefit') ?? 0, isFormula: false },
    { item: '加：以前年度所得税影响', amount: formData.getField('disclosure-listed', 'prior-year') ?? 0, isFormula: false },
    { item: '所得税费用', amount: total, isFormula: true, formula: '取自N5-1审定合计' },
    { item: '有效税率与法定税率差异', amount: diff, isFormula: true, formula: '= 实际所得税 − 按法定税率计算' },
  ]
})

// ─── 数据加载 ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  auditNotes.value = formData.getField('disclosure-listed', 'audit-notes') ?? ''
  auditConclusion.value = formData.getField('disclosure-listed', 'audit-conclusion') ?? ''
})

// ─── 保存 ────────────────────────────────────────────────────────────────────

async function handleSave() {
  // 保存上期数等可编辑字段
  const row0 = expenseRows.value[0]
  const row1 = expenseRows.value[1]
  await formData.saveBatch([
    { itemId: 'N5-disclosure-listed-prior-current', data: { conclusion: String(row0.priorAmount) } },
    { itemId: 'N5-disclosure-listed-prior-deferred', data: { conclusion: String(row1.priorAmount) } },
  ])
}

async function saveNotes() { await formData.setField('disclosure-listed', 'audit-notes', auditNotes.value) }
async function saveConclusion() { await formData.setField('disclosure-listed', 'audit-conclusion', auditConclusion.value) }
function handleAiAssist() { ElMessage.info('AI辅助生成附注披露...') }
function handleReview() { openReviewDialog ? openReviewDialog('N5-附注上市') : ElMessage.info('复核对话未配置') }

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPercent(val: number | null | undefined): string {
  if (val == null) return '—'
  return (val * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.n5-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }
.disclosure-card { margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.disclosure-table { margin-bottom: 0; }
:deep(.disclosure-table .el-table) { font-size: var(--wp-font-size, 13px); }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-weight: 500; color: #303133; padding-bottom: 1px; }
.cell-input { width: 100%; }
:deep(.cell-input .el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }

.etr-analysis { display: flex; align-items: center; gap: 8px; padding: 10px 16px; margin-bottom: 16px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.etr-title { font-weight: 500; color: #303133; }
.etr-value { font-size: 16px; font-weight: 700; color: #303133; }
.etr-desc { color: #909399; font-size: 12px; }

.audit-notes-card { margin-bottom: 16px; }
.notes-title { font-size: 14px; font-weight: 500; }
.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #606266; margin-bottom: 6px; }
</style>
