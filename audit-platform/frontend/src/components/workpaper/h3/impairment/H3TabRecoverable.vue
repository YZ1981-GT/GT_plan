<template>
  <div class="h3-tab-recoverable">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表用于测算投资性房地产（成本模式）可收回金额，取公允价值减处置费用与预计未来现金流量现值（DCF）孰高。</p>
        <p>2. DCF 现值 = Σ 各年净现金流 × 折现系数；关键假设含折现率、预测期、永续增长率、年租金与运营成本。</p>
        <p>3. 敏感性矩阵展示折现率与增长率变动对现值的影响，用于评估估值稳健性。</p>
        <p>4. 可收回金额结果回填 H3-10 减值测算表，与账面价值比较确定减值。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：复核投资性房地产可收回金额（DCF 模型）关键假设的合理性与测算的准确性，为 H3-10 减值判断提供支持。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-11" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ cashFlowRows.length }} 期</el-tag>
    </div>

    <!-- DCF模型 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>可收回金额 — DCF模型（H3-11）</span>
          <el-button size="small" @click="generateAI('H3-11-dcf')">AI</el-button>
        </div>
      </template>

      <!-- 假设区 -->
      <div class="assumptions-grid">
        <div class="assumption-item">
          <label>折现率(%)</label>
          <el-input v-model.number="assumptions.discountRate" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>预测期(年)</label>
          <el-input v-model.number="assumptions.forecastYears" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>永续增长率(%)</label>
          <el-input v-model.number="assumptions.terminalGrowth" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>年租金收入</label>
          <el-input v-model.number="assumptions.annualRent" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>年运营成本</label>
          <el-input v-model.number="assumptions.annualCost" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>残值</label>
          <el-input v-model.number="assumptions.residualValue" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
      </div>

      <!-- 现金流预测表 -->
      <el-table :data="cashFlowRows" border size="small" class="audit-table" style="margin-top:12px">
        <el-table-column prop="year" label="年份" width="60" align="center" />
        <el-table-column prop="revenue" label="收入" min-width="100" align="right">
          <template #default="{ row }">{{ fmtNum(row.revenue) }}</template>
        </el-table-column>
        <el-table-column prop="cost" label="成本" min-width="100" align="right">
          <template #default="{ row }">{{ fmtNum(row.cost) }}</template>
        </el-table-column>
        <el-table-column label="净现金流" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtNum(row.netCashFlow) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="discountFactor" label="折现系数" width="90" align="right">
          <template #default="{ row }">{{ row.discountFactor.toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="现值" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtNum(row.presentValue) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- DCF结果 -->
      <div class="dcf-result">
        <span>DCF现值合计：<b>{{ fmtNum(dcfTotal) }}</b></span>
        <span>可收回金额 = MAX(公允-处置费, DCF) = <b class="result-value">{{ fmtNum(recoverableAmount) }}</b></span>
      </div>
    </el-card>

    <!-- 敏感性矩阵 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span>敏感性分析矩阵</span>
      </template>
      <el-table :data="sensitivityRows" border size="small" class="audit-table">
        <el-table-column prop="label" label="折现率 \\ 增长率" width="120" />
        <el-table-column v-for="col in sensitivityCols" :key="col" :label="col + '%'" min-width="90" align="right">
          <template #default="{ row }">
            {{ fmtNum(row[col]) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-11')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-11')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：DCF 关键假设（折现率/增长率/租金）来源与合理性、敏感性分析结论、可收回金额确定。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、假设合理、测算准确。B、除下列事项外未见异常。C、关键假设不合理，需重新评估。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabRecoverable.vue — H3-11 可收回金额DCF
 * DCF模型+敏感性矩阵
 */
import { ref, reactive, computed, inject, toRef, onMounted } from 'vue'
import { useH3Impairment } from '../../composables/useH3Impairment'
import { useH3FormData } from '../../composables/useH3FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost') as any,
})

const {
  assumptions, cashFlowRows, dcfTotal, recoverableAmount,
  sensitivityRows, sensitivityCols, updateAssumptions,
} = useH3Impairment({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-11-audit-note'
const CONCLUSION_KEY = 'H3-11-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

function onAssumptionChange() {
  updateAssumptions(assumptions)
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-recoverable { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.assumptions-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.assumption-item label { display: block; font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.dcf-result { display: flex; align-items: center; gap: 24px; margin-top: 12px; padding: 10px 14px; background: var(--el-fill-color-lighter); border-radius: 4px; font-weight: 500; }
.result-value { font-size: 16px; color: var(--el-color-primary); }
.conclusion-card { margin-top: 16px; }
.action-btns { display: flex; gap: 4px; }
</style>
