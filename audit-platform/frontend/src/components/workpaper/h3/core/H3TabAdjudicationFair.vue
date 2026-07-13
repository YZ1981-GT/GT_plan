<template>
  <div class="h3-tab-adjudication-fair">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为投资性房地产审定表（公允价值模式），单区块列示公允价值变动，期末公允 = 期初 + 增加 − 减少 ± 转换 + 公允价值变动。</p>
        <p>2. 公允价值模式下不计提折旧与减值（CAS3）；公允价值变动计入当期损益。</p>
        <p>3. 未审数取自试算表（科目 1503），审定数 = 未审 + AJE + RJE；采用公允价值模式须满足有活跃交易市场且可获取同类价格信息。</p>
        <p>4. 若企业采用成本模式，请切换至成本模式版本填报。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实投资性房地产（公允价值模式，科目 1503）期末公允价值的存在、准确与计量恰当，验证公允价值变动损益的合理性，为报表及附注披露提供审定依据。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ fairRows.length }} 行</el-tag>
    </div>

    <!-- 单区块：投资性房地产（公允价值） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>投资性房地产 — 公允价值模式</span>
        </div>
      </template>
      <el-table :data="fairRows" border size="small" class="audit-table" show-summary :summary-method="getFairSummary">
        <el-table-column prop="category" label="项目" min-width="120" fixed />
        <el-table-column prop="beginFair" label="期初公允" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.beginFair" size="small" :disabled="isReadonly" @change="onCellChange(row, 'beginFair')" />
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.increase" size="small" :disabled="isReadonly" @change="onCellChange(row, 'increase')" />
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.decrease" size="small" :disabled="isReadonly" @change="onCellChange(row, 'decrease')" />
          </template>
        </el-table-column>
        <el-table-column prop="transfer" label="转换" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transfer" size="small" :disabled="isReadonly" @change="onCellChange(row, 'transfer')" />
          </template>
        </el-table-column>
        <el-table-column prop="fairValueChange" label="公允价值变动" min-width="120" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.fairValueChange" size="small" :disabled="isReadonly" @change="onCellChange(row, 'fairValueChange')" />
          </template>
        </el-table-column>
        <el-table-column label="期末公允" min-width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+增加-减少±转换+公允变动">{{ fmtNum(row.endFair) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.unadjusted" size="small" :disabled="isReadonly" @change="onCellChange(row, 'unadjusted')" />
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.aje" size="small" :disabled="isReadonly" @change="onCellChange(row, 'aje')" />
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.rje" size="small" :disabled="isReadonly" @change="onCellChange(row, 'rje')" />
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="未审+AJE+RJE">{{ fmtNum(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 公允价值变动损益汇总 -->
    <el-card shadow="never" class="summary-card">
      <div class="summary-row">
        <span>公允价值变动损益合计</span>
        <span class="summary-amount">{{ fmtNum(totalFairValueChange) }}</span>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-1-fair')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-1-fair')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：程序执行情况、公允价值来源与合理性、公允价值变动损益核对、拟调整与未调整事项及其影响。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、未见异常。B、除上述调整事项外未见异常。C、存在重大未调整事项（或审计范围受限），不可确认。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabAdjudicationFair.vue — H3-1 审定表（公允价值模式）
 * 单区块公允+公允变动+TB回写+AI+💬复核
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { useH3AdjudicationFair } from '../../composables/useH3AdjudicationFair'
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
  measurementModel: ref('fair_value'),
})

const {
  rows: fairRows,
  total: fairTotal,
  fairValueChangePL: totalFairValueChange,
  updateCell: updateFairCell,
} = useH3AdjudicationFair({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-1-fair-audit-note'
const CONCLUSION_KEY = 'H3-1-fair-audit-conclusion'
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

function onCellChange(row: any, field: string) {
  updateFairCell(row.rowId, field, row[field])
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getFairSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '小计'
    const key = ['', 'beginFair', 'increase', 'decrease', 'transfer', 'fairValueChange', 'endFair', 'unadjusted', 'aje', 'rje', 'audited'][idx]
    return key ? fmtNum((fairTotal.value as any)[key] ?? 0) : ''
  })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-adjudication-fair { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.summary-card { margin-bottom: 16px; }
.summary-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; font-weight: 600; }
.summary-amount { font-size: 16px; color: var(--el-color-warning); }
.conclusion-card { margin-bottom: 16px; }
.action-btns { display: flex; gap: 4px; }
</style>
