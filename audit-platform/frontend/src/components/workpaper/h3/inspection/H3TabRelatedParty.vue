<template>
  <div class="h3-tab-related-party">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表核查投资性房地产相关的关联方交易（出租/购入/处置/转换），关注定价公允性与商业实质。</p>
        <p>2. 差异率 =（交易金额 − 市场价参考）/ 市场价 × 100%，&gt;10% 红色高亮需重点关注与解释。</p>
        <p>3. 核对定价方式、审批文件与市场价依据；关注是否存在利益输送或非公允关联交易。</p>
        <p>4. 关联交易结果应与附注关联方披露一致（CAS36）。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：识别并核查投资性房地产相关关联方交易的完整性、定价公允性与商业实质，评估对财务报表及披露的影响。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-13" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增关联交易</el-button>
      <el-dropdown size="small" class="export-dropdown">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item>导出模板</el-dropdown-item>
            <el-dropdown-item>导出数据</el-dropdown-item>
            <el-dropdown-item>导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 11列关联交易表 -->
    <el-table :data="rows" border size="small" class="audit-table" :row-class-name="getRowClass" show-summary :summary-method="getSummary">
      <el-table-column prop="seq" label="序号" width="50" align="center" />
      <el-table-column prop="relatedParty" label="关联方" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-model="row.relatedParty" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="relationship" label="关联关系" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.relationship" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="transType" label="交易类型" width="100">
        <template #default="{ row, $index }">
          <el-select v-model="row.transType" size="small" :disabled="isReadonly" @change="onCellChange($index, row)">
            <el-option label="出租" value="出租" />
            <el-option label="购入" value="购入" />
            <el-option label="处置" value="处置" />
            <el-option label="转换" value="转换" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="amount" label="金额" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.amount" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="pricingMethod" label="定价方式" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.pricingMethod" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="marketRef" label="市场价参考" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.marketRef" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column label="差异率" width="90" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span
            class="formula-value"
            :class="{ 'text-danger': Math.abs(calcDiffRate(row)) > 10 }"
            title="(金额-市场价)/市场价×100%"
          >
            {{ row.marketRef ? calcDiffRate(row).toFixed(1) + '%' : '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="approvalDoc" label="审批文件" width="70" align="center">
        <template #default="{ row, $index }">
          <el-checkbox v-model="row.approvalDoc" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="审计结论" min-width="100">
        <template #default="{ row, $index }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="onCellChange($index, row)">
            <el-option label="无异常" value="无异常" />
            <el-option label="需关注" value="需关注" />
            <el-option label="不合理" value="不合理" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-13')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-13')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：关联方及关联关系识别、定价公允性核查、市场价对比及异常事项。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、关联交易完整披露、定价公允。B、除下列事项外未见异常。C、存在非公允关联交易，需关注并披露。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabRelatedParty.vue — H3-13 关联交易
 * el-table 11列+差异率>10%红色+合计行
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { useH3RelatedParty } from '../../composables/useH3RelatedParty'
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
  rows, addRow, updateRow, totalAmount,
} = useH3RelatedParty({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-13-audit-note'
const CONCLUSION_KEY = 'H3-13-audit-conclusion'
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

function onCellChange(index: number, row: any) { updateRow(index, row) }

function calcDiffRate(row: any): number {
  if (!row.marketRef || row.marketRef === 0) return 0
  return ((row.amount - row.marketRef) / row.marketRef) * 100
}

function getRowClass({ row }: { row: any }): string {
  if (Math.abs(calcDiffRate(row)) > 10) return 'row-danger'
  return ''
}

function getSummary({ columns }: { columns: any[] }) {
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    if (idx === 4) return fmtNum(totalAmount.value)
    return ''
  })
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
.h3-tab-related-party { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.row-danger) { background-color: #fef0f0 !important; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-danger { color: var(--el-color-danger); }
.conclusion-card { margin-top: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.export-dropdown { margin-left: auto; }
</style>
