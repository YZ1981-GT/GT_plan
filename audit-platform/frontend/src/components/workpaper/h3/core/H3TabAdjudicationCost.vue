<template>
  <div class="h3-tab-adjudication-cost">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为投资性房地产审定表（成本模式），列示原值与累计折旧双区块，净值 = 原值期末 − 折旧期末。</p>
        <p>2. 期初数应与上年末审定数一致；未审数取自试算表（科目 1503 投资性房地产 / 1504 累计折旧），审定数 = 未审 + AJE + RJE。</p>
        <p>3. 计量模式在成本模式与公允价值模式之间选择（CAS3）：成本模式计提折旧与减值；公允价值模式不计提折旧、以公允价值调整账面价值，请切换至公允价值版本。</p>
        <p>4. 关注三角勾稽是否平衡（期初 + 增加 − 减少 ± 转换 = 期末）。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实投资性房地产（成本模式：原值 1503 + 累计折旧 1504）期末余额的存在、准确与完整，确认调整分录恰当，为报表及附注披露提供审定依据。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ originalRows.length }} 行</el-tag>
    </div>

    <!-- 一、投资性房地产 — 原值 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>一、投资性房地产 — 原值</span>
          <span v-if="!isTriangleBalanced" class="triangle-warn">⚠ 勾稽不平</span>
        </div>
      </template>
      <el-table :data="originalRows" border size="small" class="audit-table" show-summary :summary-method="getOriginalSummary">
        <el-table-column prop="category" label="项目" min-width="120" fixed />
        <el-table-column prop="beginBalance" label="期初" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'beginBalance')" />
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="增加" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.increase" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'increase')" />
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="减少" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.decrease" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'decrease')" />
          </template>
        </el-table-column>
        <el-table-column prop="transfer" label="转换" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transfer" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'transfer')" />
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+增加-减少±转换">{{ fmtNum(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.unadjusted" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'unadjusted')" />
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.aje" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'aje')" />
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.rje" size="small" :disabled="isReadonly" @change="onOrigCellChange(row, 'rje')" />
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="未审+AJE+RJE">{{ fmtNum(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 二、累计折旧 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span>二、累计折旧</span>
      </template>
      <el-table :data="depRows" border size="small" class="audit-table" show-summary :summary-method="getDepSummary">
        <el-table-column prop="category" label="项目" min-width="120" fixed />
        <el-table-column prop="beginBalance" label="期初" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'beginBalance')" />
          </template>
        </el-table-column>
        <el-table-column prop="provision" label="计提" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.provision" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'provision')" />
          </template>
        </el-table-column>
        <el-table-column prop="reversal" label="转回" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.reversal" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'reversal')" />
          </template>
        </el-table-column>
        <el-table-column prop="transferDep" label="转换折旧" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transferDep" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'transferDep')" />
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+计提-转回±转换">{{ fmtNum(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.unadjusted" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'unadjusted')" />
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.aje" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'aje')" />
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.rje" size="small" :disabled="isReadonly" @change="onDepCellChange(row, 'rje')" />
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="未审+AJE+RJE">{{ fmtNum(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 净值合计 -->
    <el-card shadow="never" class="net-value-card">
      <div class="net-value-row">
        <span class="net-label">净值合计（原值期末 - 折旧期末）</span>
        <span class="net-amount">{{ fmtNum(netValueTotal) }}</span>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-1-cost')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-1-cost')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：程序执行情况、成本模式下原值/累计折旧勾稽核对、拟调整与未调整事项及其影响。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、未见异常。B、除上述调整事项外未见异常。C、存在重大未调整事项（或审计范围受限），不可确认。" :disabled="isReadonly" @change="saveAuditConclusion" />
      <div class="chip-row">
        <span class="chip-label">跳转：</span>
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H3-6 互转审核')">H3-6 互转审核</el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabAdjudicationCost.vue — H3-1 审定表（成本模式）
 * 双区块(原值+折旧)+三角勾稽+TB回写+AI+💬复核+GtIndexChip→H3-6
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { useH3AdjudicationCost } from '../../composables/useH3AdjudicationCost'
import type { H3CostOriginalRow, H3CostDepRow } from '../../composables/useH3AdjudicationCost'
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
  measurementModel: ref('cost'),
})

const {
  originalRows, depRows, originalTotal, depTotal, netValueTotal,
  isTriangleBalanced, updateOriginalCell, updateDepCell,
} = useH3AdjudicationCost({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-1-cost-audit-note'
const CONCLUSION_KEY = 'H3-1-cost-audit-conclusion'
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

function onOrigCellChange(row: H3CostOriginalRow, field: keyof H3CostOriginalRow) {
  updateOriginalCell(row.rowId, field, (row as any)[field])
}
function onDepCellChange(row: H3CostDepRow, field: keyof H3CostDepRow) {
  updateDepCell(row.rowId, field, (row as any)[field])
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getOriginalSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '小计'
    const key = ['', 'beginBalance', 'increase', 'decrease', 'transfer', 'endBalance', 'unadjusted', 'aje', 'rje', 'audited'][idx]
    return key ? fmtNum((originalTotal.value as any)[key] ?? 0) : ''
  })
}
function getDepSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '小计'
    const key = ['', 'beginBalance', 'provision', 'reversal', 'transferDep', 'endBalance', 'unadjusted', 'aje', 'rje', 'audited'][idx]
    return key ? fmtNum((depTotal.value as any)[key] ?? 0) : ''
  })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-adjudication-cost { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.triangle-warn { color: var(--el-color-danger); font-size: 12px; font-weight: 600; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.net-value-card { margin-bottom: 16px; }
.net-value-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; }
.net-label { font-weight: 600; }
.net-amount { font-size: 16px; font-weight: 700; color: var(--el-color-primary); }
.conclusion-card { margin-bottom: 16px; }
.action-btns { display: flex; gap: 4px; }
.chip-row { margin-top: 12px; display: flex; align-items: center; gap: 8px; }
.chip-label { font-size: 12px; color: var(--el-text-color-secondary); }
.nav-chip { cursor: pointer; }
</style>
