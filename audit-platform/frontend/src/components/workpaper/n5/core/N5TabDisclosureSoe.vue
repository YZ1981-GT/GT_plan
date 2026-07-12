<template>
  <div class="n5-disclosure-soe">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>附注披露信息（国有企业）</span>
        <el-tag size="small" type="warning">32×255</el-tag>
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

    <!-- ═══ 所得税费用构成（国企格式） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header><span class="card-title">（一）所得税费用明细</span></template>
      <el-table :data="expenseRows" border size="small" class="disclosure-table">
        <el-table-column prop="item" label="项目" min-width="220" />
        <el-table-column label="本年累计数" min-width="130" align="right">
          <template #header><span class="formula-header" title="从N5-1审定表取数">本年累计数</span></template>
          <template #default="{ row }">
            <el-tooltip :content="row.source" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.currentAmount) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上年同期数" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.priorAmount" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleSave()" />
            <span v-else>{{ fmtAmount(row.priorAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 所得税费用与会计利润调节表（国企扩展版） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header><span class="card-title">（二）所得税费用与会计利润调节表</span></template>
      <el-table :data="reconciliationRows" border size="small" class="disclosure-table">
        <el-table-column prop="item" label="项目" min-width="280" />
        <el-table-column label="金额（元）" min-width="130" align="right">
          <template #header><span class="formula-header" title="调节过程">金额（元）</span></template>
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
      <span class="etr-desc">（所得税费用 / 会计利润总额）</span>
    </div>

    <!-- ═══ 国企附注补充说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header-with-ai">
          <span class="card-title">（三）补充说明（国企特殊）</span>
          <el-button size="small" @click="handleSupplementAi"><el-icon><MagicStick /></el-icon>AI辅助</el-button>
        </div>
      </template>
      <div class="supplement-field">
        <label class="field-label">递延所得税资产未确认金额说明</label>
        <el-input v-model="unrecognizedNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="说明未确认递延所得税资产的原因及金额..." :disabled="isReadonly" @change="handleSupplementSave" />
      </div>
      <div class="supplement-field">
        <label class="field-label">税收优惠政策说明</label>
        <el-input v-model="taxBenefitNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="说明企业适用的税收优惠政策..." :disabled="isReadonly" @change="handleSupplementSave" />
      </div>
      <div class="supplement-field">
        <label class="field-label">跨年度亏损弥补情况</label>
        <el-input v-model="lossCarryNote" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="说明可弥补亏损情况..." :disabled="isReadonly" @change="handleSupplementSave" />
      </div>
    </el-card>

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
 * N5TabDisclosureSoe — 附注披露信息（国有企业，32×255）
 * 所得税费用与会计利润调节表+有效税率分析+subscribe刷新+国企补充说明
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
const unrecognizedNote = ref('')
const taxBenefitNote = ref('')
const lossCarryNote = ref('')

// ─── subscribe 'substantive:adjudicated' ────────────────────────────────────

function onSubstantiveAdjudicated(_payload: any) { formData.loadData() }
eventBus.on('substantive:adjudicated' as any, onSubstantiveAdjudicated)
onScopeDispose(() => { eventBus.off('substantive:adjudicated' as any, onSubstantiveAdjudicated) })

// ─── 所得税费用构成表 ────────────────────────────────────────────────────────

interface ExpenseRow { item: string; currentAmount: number; priorAmount: number; source: string }

const expenseRows = computed<ExpenseRow[]>(() => [
  { item: '当期所得税费用', currentAmount: adjudicationVsCalc.value.current, priorAmount: formData.getField('disclosure-soe', 'prior-current') ?? 0, source: '取自N5-1审定表当期所得税行' },
  { item: '递延所得税费用', currentAmount: adjudicationVsCalc.value.deferred, priorAmount: formData.getField('disclosure-soe', 'prior-deferred') ?? 0, source: '取自N5-1审定表递延所得税行' },
  { item: '所得税费用合计', currentAmount: adjudicationVsCalc.value.total, priorAmount: (formData.getField('disclosure-soe', 'prior-current') ?? 0) + (formData.getField('disclosure-soe', 'prior-deferred') ?? 0), source: '= 当期 + 递延' },
])

// ─── 调节表（国企扩展版） ────────────────────────────────────────────────────

interface ReconRow { item: string; amount: number; isFormula: boolean; formula?: string }

const reconciliationRows = computed<ReconRow[]>(() => {
  const profit = profitFromIncomeStatement.value.accountingProfit
  const taxAtRate = profit * 0.25
  const total = adjudicationVsCalc.value.total

  return [
    { item: '利润总额', amount: profit, isFormula: true, formula: '取自A类利润表' },
    { item: '按法定/适用税率计算的所得税费用', amount: taxAtRate, isFormula: true, formula: '= 利润总额 × 适用税率' },
    { item: '子公司适用不同税率的影响', amount: formData.getField('disclosure-soe', 'sub-rate') ?? 0, isFormula: false },
    { item: '加：纳税调整增加额的影响', amount: formData.getField('disclosure-soe', 'adj-add') ?? 0, isFormula: false },
    { item: '减：纳税调整减少额的影响', amount: formData.getField('disclosure-soe', 'adj-ded') ?? 0, isFormula: false },
    { item: '加：递延所得税费用（收益以"-"号填列）', amount: adjudicationVsCalc.value.deferred, isFormula: true, formula: '取自N5-8递延所得税费用' },
    { item: '减：高新技术企业税收优惠', amount: formData.getField('disclosure-soe', 'hightech') ?? 0, isFormula: false },
    { item: '减：研发费用加计扣除', amount: formData.getField('disclosure-soe', 'rd-super') ?? 0, isFormula: false },
    { item: '减：其他税收优惠', amount: formData.getField('disclosure-soe', 'other-benefit') ?? 0, isFormula: false },
    { item: '加：以前年度所得税调整', amount: formData.getField('disclosure-soe', 'prior-adj') ?? 0, isFormula: false },
    { item: '加：可弥补亏损未确认的递延税资产', amount: formData.getField('disclosure-soe', 'unrecog-loss') ?? 0, isFormula: false },
    { item: '所得税费用', amount: total, isFormula: true, formula: '取自N5-1审定合计' },
  ]
})

// ─── 数据加载 ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  auditNotes.value = formData.getField('disclosure-soe', 'audit-notes') ?? ''
  auditConclusion.value = formData.getField('disclosure-soe', 'audit-conclusion') ?? ''
  unrecognizedNote.value = formData.getField('disclosure-soe', 'unrecognized-note') ?? ''
  taxBenefitNote.value = formData.getField('disclosure-soe', 'tax-benefit-note') ?? ''
  lossCarryNote.value = formData.getField('disclosure-soe', 'loss-carry-note') ?? ''
})

// ─── 保存 ────────────────────────────────────────────────────────────────────

async function handleSave() {
  const row0 = expenseRows.value[0]
  const row1 = expenseRows.value[1]
  await formData.saveBatch([
    { itemId: 'N5-disclosure-soe-prior-current', data: { conclusion: String(row0.priorAmount) } },
    { itemId: 'N5-disclosure-soe-prior-deferred', data: { conclusion: String(row1.priorAmount) } },
  ])
}

async function handleSupplementSave() {
  await formData.saveBatch([
    { itemId: 'N5-disclosure-soe-unrecognized-note', data: { conclusion: unrecognizedNote.value } },
    { itemId: 'N5-disclosure-soe-tax-benefit-note', data: { conclusion: taxBenefitNote.value } },
    { itemId: 'N5-disclosure-soe-loss-carry-note', data: { conclusion: lossCarryNote.value } },
  ])
}

async function saveNotes() { await formData.setField('disclosure-soe', 'audit-notes', auditNotes.value) }
async function saveConclusion() { await formData.setField('disclosure-soe', 'audit-conclusion', auditConclusion.value) }
function handleAiAssist() { ElMessage.info('AI辅助生成国企附注披露...') }
function handleSupplementAi() { ElMessage.info('AI辅助生成补充说明...') }
function handleReview() { openReviewDialog ? openReviewDialog('N5-附注国企') : ElMessage.info('复核对话未配置') }

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
.n5-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }
.disclosure-card { margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.card-header-with-ai { display: flex; align-items: center; justify-content: space-between; }
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

.supplement-field { margin-bottom: 12px; }
.supplement-field:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #606266; margin-bottom: 6px; }

.audit-notes-card { margin-bottom: 16px; }
.notes-title { font-size: 14px; font-weight: 500; }
.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }
</style>
