<template>
  <div class="h5-tab-stocktake-check">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：执行油气资产盘点，核对账实差异并分析异常，为监盘小结提供依据。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-10" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.checkRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-10 盘点检查表（异常{{ state.abnormalCheckItems.value.length }}项，差异合计{{ fmtAmt(state.totalDifference.value) }}）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-10')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="state.checkRows.value" border stripe size="small" class="check-table" max-height="500">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="item" label="盘点项目" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.item" size="small" @change="state.updateCheckCell(row.rowId, 'item', $event)" />
            <span v-else>{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" @change="state.updateCheckCell(row.rowId, 'bookValue', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="actualValue" label="实盘数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.actualValue" :controls="false" size="small" @change="state.updateCheckCell(row.rowId, 'actualValue', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.actualValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'diff-warn': row.difference !== 0 }" title="差异=实盘-账面">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="diffReason" label="差异原因" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.diffReason" size="small" @change="state.updateCheckCell(row.rowId, 'diffReason', $event)" />
            <span v-else>{{ row.diffReason }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.status" size="small" @change="state.updateCheckCell(row.rowId, 'status', $event)">
              <el-option label="正常" value="正常" /><el-option label="异常" value="异常" /><el-option label="待核实" value="待核实" />
            </el-select>
            <el-tag v-else :type="row.status === '正常' ? 'success' : row.status === '异常' ? 'danger' : 'warning'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="inspector" label="盘点人" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.inspector" size="small" @change="state.updateCheckCell(row.rowId, 'inspector', $event)" />
            <span v-else>{{ row.inspector }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="inspectDate" label="盘点日期" width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.inspectDate" type="date" value-format="YYYY-MM-DD" size="small" @change="state.updateCheckCell(row.rowId, 'inspectDate', $event)" />
            <span v-else>{{ row.inspectDate }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="state.updateCheckCell(row.rowId, 'conclusion', $event)" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    <div class="action-bar" v-if="!isReadonly">
      <el-button size="small" @click="handleAddRow">+ 新增检查项</el-button>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNoteText" :autosize="{ minRows: 5 }"
        placeholder="填写盘点检查审计说明..." :disabled="isReadonly" @change="savePolishNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusionText" :autosize="{ minRows: 3 }"
        placeholder="填写盘点检查审计结论..." :disabled="isReadonly" @change="savePolishConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>差异=实盘数-账面数，自动计算</li>
        <li>异常项需说明差异原因并确认处理方案</li>
        <li>异常项汇总数据自动推送到H5-11监盘小结</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH5Stocktake } from '../../composables/useH5Stocktake'
import { useH5FormData } from '../../composables/useH5FormData'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const state = useH5Stocktake({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: (itemId: string, value: any) => formData.setResponse(itemId, value) })

// 审计说明/结论（component-local H5-10，conclusion:null）
const NOTE_KEY = 'H5-10-audit-note'
const CONCLUSION_KEY = 'H5-10-audit-conclusion'
const auditNoteText = ref('')
const auditConclusionText = ref('')
function savePolishNote(val: string): void {
  if (props.isReadonly) return
  auditNoteText.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void formData.saveResponse(NOTE_KEY, val)
}
function savePolishConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusionText.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void formData.saveResponse(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusionText.value = c.remark
})

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入盘点项目', '新增检查项', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (value) state.addCheckRow(value)
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-stocktake-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.formula-cell.diff-warn { color: var(--el-color-warning); font-weight: 600; }
.action-bar { margin: 12px 0; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
