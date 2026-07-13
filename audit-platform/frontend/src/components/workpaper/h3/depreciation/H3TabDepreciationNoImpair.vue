<template>
  <div class="h3-tab-depreciation-no-impair">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为投资性房地产折旧测算（不含减值，直线法），仅适用于成本模式；公允价值模式不计提折旧。</p>
        <p>2. 月折旧 = 原值 × (1 − 残值率) / 使用年限 / 12；测算累计 = 月折旧 × 已计提月数；差异 = 测算累计 − 账面累计。</p>
        <p>3. 关注差异（红色高亮，&gt;0.01）行的原因；测算累计合计应与账面累计合计核对一致。</p>
        <p>4. 若资产存在减值，请使用「含减值」版本重新测算折旧。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：复核投资性房地产（成本模式）折旧计提的准确性，验证直线法参数与账面累计折旧的一致性。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-7" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- 成本模式限定提示 -->
    <el-alert title="折旧测算 — 不含减值（直线法）" type="info" :closable="false" show-icon class="mode-alert">
      本表仅适用于成本模式，计算月折旧=原值×(1-残值率)/使用年限/12
    </el-alert>

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增资产行</el-button>
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

    <!-- 28列折旧测算表（不含减值） -->
    <el-table :data="rows" border size="small" class="audit-table" :row-class-name="getRowClass" show-summary :summary-method="getSummary">
      <el-table-column prop="assetName" label="资产名称" min-width="120" fixed />
      <el-table-column prop="originalCost" label="原值" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.originalCost" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="salvageRate" label="残值率" width="80" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.salvageRate" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="usefulLife" label="年限(年)" width="80" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.usefulLife" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="elapsedYears" label="已用(年)" width="80" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.elapsedYears" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column label="月折旧" min-width="100" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="原值×(1-残值率)/年限/12">{{ fmtNum(row.monthlyDep) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="年折旧" min-width="100" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="月折旧×12">{{ fmtNum(row.annualDep) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="测算累计" min-width="100" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="月折旧×已用月数">{{ fmtNum(row.accDepCalc) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accDepBook" label="账面累计" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.accDepBook" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column label="差异" min-width="90" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" :class="{ 'text-danger': Math.abs(row.difference) > 0.01 }">
            {{ fmtNum(row.difference) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计验证 -->
    <div class="summary-row">
      <span>测算累计合计：<b>{{ fmtNum(totalAccDepCalc) }}</b></span>
      <span>账面累计合计：<b>{{ fmtNum(totalAccDepBook) }}</b></span>
      <span>差异合计：<b :class="{ 'text-danger': Math.abs(totalDifference) > 0.01 }">{{ fmtNum(totalDifference) }}</b></span>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-7-no-impair')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-7-no-impair')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：折旧参数（残值率/年限）合理性、测算与账面累计折旧差异及原因。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、折旧测算准确，与账面无重大差异。B、除下列差异外未见异常。C、存在重大未调整差异，不可确认。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabDepreciationNoImpair.vue — H3-7(A) 折旧不含减值
 * 28列42公式+差异高亮（仅成本模式）
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { useH3Depreciation } from '../../composables/useH3Depreciation'
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
  rows, addRow, updateRow, totalAccDepCalc, totalAccDepBook, totalDifference,
} = useH3Depreciation({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-7-noimpair-audit-note'
const CONCLUSION_KEY = 'H3-7-noimpair-audit-conclusion'
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

function getRowClass({ row }: { row: any }): string {
  if (Math.abs(row.difference) > 0.01) return 'row-warn'
  return ''
}

function getSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '合计'
    if (idx === 7) return fmtNum(totalAccDepCalc.value)
    if (idx === 8) return fmtNum(totalAccDepBook.value)
    if (idx === 9) return fmtNum(totalDifference.value)
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
.h3-tab-depreciation-no-impair { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.mode-alert { margin-bottom: 16px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.audit-table :deep(.row-warn) { background-color: #fef9e7 !important; }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-danger { color: var(--el-color-danger); }
.summary-row { display: flex; align-items: center; gap: 16px; margin: 12px 0; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.conclusion-card { margin-top: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.export-dropdown { margin-left: auto; }
</style>
