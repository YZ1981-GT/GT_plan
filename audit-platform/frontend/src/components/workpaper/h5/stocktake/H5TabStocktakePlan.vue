<template>
  <div class="h5-tab-stocktake-plan">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：制定油气资产监盘计划，明确盘点范围、方式与责任分工，为现场监盘执行提供依据。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-9" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.planRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-9 监盘计划（完成率 {{ state.planCompletionRate.value }}%）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-9')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-progress :percentage="state.planCompletionRate.value" :stroke-width="6" class="progress-bar" />
      <el-table :data="state.planRows.value" border stripe size="small" class="plan-table" max-height="500">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="item" label="盘点项目" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.item" size="small" @change="state.updatePlanCell(row.rowId, 'item', $event)" />
            <span v-else>{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="oilField" label="油田" min-width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.oilField" size="small" @change="state.updatePlanCell(row.rowId, 'oilField', $event)" />
            <span v-else>{{ row.oilField }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="location" label="位置/GPS" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.location" size="small" @change="state.updatePlanCell(row.rowId, 'location', $event)" />
            <span v-else>{{ row.location }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookCost" label="账面原值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookCost" :controls="false" size="small" @change="state.updatePlanCell(row.rowId, 'bookCost', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="method" label="盘点方式" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.method" size="small" @change="state.updatePlanCell(row.rowId, 'method', $event)">
              <el-option label="实地观察" value="实地观察" /><el-option label="确认函" value="确认函" /><el-option label="替代程序" value="替代程序" />
            </el-select>
            <span v-else>{{ row.method }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="plannedDate" label="计划日期" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.plannedDate" type="date" value-format="YYYY-MM-DD" size="small" @change="state.updatePlanCell(row.rowId, 'plannedDate', $event)" />
            <span v-else>{{ row.plannedDate }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="responsible" label="负责人" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.responsible" size="small" @change="state.updatePlanCell(row.rowId, 'responsible', $event)" />
            <span v-else>{{ row.responsible }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.status" size="small" @change="state.updatePlanCell(row.rowId, 'status', $event)">
              <el-option label="待执行" value="待执行" /><el-option label="进行中" value="进行中" /><el-option label="已完成" value="已完成" />
            </el-select>
            <el-tag v-else :type="row.status === '已完成' ? 'success' : row.status === '进行中' ? 'warning' : 'info'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="state.removePlanRow(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>
    <div class="action-bar" v-if="!isReadonly">
      <el-button size="small" @click="handleAddRow">+ 新增计划项</el-button>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNoteText" :autosize="{ minRows: 5 }"
        placeholder="填写监盘计划审计说明..." :disabled="isReadonly" @change="savePolishNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusionText" :autosize="{ minRows: 3 }"
        placeholder="填写监盘计划审计结论..." :disabled="isReadonly" @change="savePolishConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>油气资产监盘以实地观察+GPS定位为主</li>
        <li>计划完成后数据自动流入H5-10盘点检查表</li>
        <li>油气设施分散在油田/区块，注意安排充足时间</li>
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

// 审计说明/结论（component-local H5-9，conclusion:null）
const NOTE_KEY = 'H5-9-audit-note'
const CONCLUSION_KEY = 'H5-9-audit-conclusion'
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
  const { value } = await ElMessageBox.prompt('请输入盘点项目', '新增计划', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (value) state.addPlanRow(value)
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-stocktake-plan { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.progress-bar { margin-bottom: 12px; }
.plan-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.action-bar { margin: 12px 0; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
