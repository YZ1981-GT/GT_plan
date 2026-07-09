<template>
  <div class="h2-tab-stocktake-check">
    <!-- 盘点检查表 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>盘点检查表（H2-13）</span>
          <div class="section-header-actions">
            <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportCmd">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-13')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.checkRows.value" border stripe size="small" class="check-table"
        :row-class-name="checkRowClass">
        <el-table-column prop="name" label="工程项目" min-width="130" fixed />
        <el-table-column prop="location" label="所在地点" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.location" size="small"
              @change="onCellChange(row.rowId, 'location', $event)" />
            <span v-else>{{ row.location || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面金额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amt-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="actualStatus" label="实际状态" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.actualStatus" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'actualStatus', $event)">
              <el-option label="正常施工" value="正常施工" />
              <el-option label="已完工" value="已完工" />
              <el-option label="停工" value="停工" />
              <el-option label="缓建" value="缓建" />
              <el-option label="不存在" value="不存在" />
            </el-select>
            <span v-else>{{ row.actualStatus || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="completionEstimate" label="预计进度(%)" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.completionEstimate" :controls="false"
              :min="0" :max="100" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'completionEstimate', $event)" />
            <span v-else>{{ row.completionEstimate ?? '-' }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="stopReason" label="停工原因" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && (row.actualStatus === '停工' || row.actualStatus === '缓建')"
              v-model="row.stopReason" size="small"
              @change="onCellChange(row.rowId, 'stopReason', $event)" />
            <span v-else>{{ row.stopReason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="stopDays" label="停工天数" min-width="80" align="right">
          <template #default="{ row }">
            <span :class="{ 'error-amount': (row.stopDays ?? 0) > 180 }">
              {{ row.stopDays ?? '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="existenceConfirmed" label="存在性" width="70" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.existenceConfirmed" :disabled="isReadonly"
              @change="onCellChange(row.rowId, 'existenceConfirmed', $event)" />
          </template>
        </el-table-column>
        <el-table-column prop="photoRef" label="照片编号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.photoRef" size="small"
              @change="onCellChange(row.rowId, 'photoRef', $event)" />
            <span v-else>{{ row.photoRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="onCellChange(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemove(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增检查项</el-button>
      </div>
    </el-card>

    <!-- 停工汇总 -->
    <el-alert v-if="state.stopCount.value > 0" type="warning" :closable="false" show-icon
      style="margin-bottom:12px">
      <template #title>
        发现 {{ state.stopCount.value }} 个停工/缓建项目，
        涉及金额 {{ fmtAmt(state.stopTotalAmount.value) }}，需关注减值迹象(→H2-15)
      </template>
    </el-alert>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>停工/缓建项目红色高亮，停工>180天需重点关注减值</li>
        <li>存在性确认：现场踏勘能确认工程实物存在</li>
        <li>照片编号对应审计工作底稿附件</li>
        <li>可通过"导入导出"批量处理盘点数据</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabStocktakeCheck.vue — H2-13 盘点检查
 * 盘点检查表 + 停工红色高亮 + 导入导出
 * Spec: Task 4.16 | Requirements: 11.2, 11.5
 */
import { inject, toRef, computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Stocktake } from '../../composables/useH2Stocktake'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const state = useH2Stocktake({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  phase: 'check',
})

function checkRowClass({ row }: any) {
  if (row.actualStatus === '停工' || row.actualStatus === '缓建') return 'stop-row'
  if (row.actualStatus === '不存在') return 'missing-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCheckCell(rowId, field, value)
}

function handleAddRow() {
  state.addCheckRow()
}

function handleRemove(rowId: string) {
  state.removeCheckRow(rowId)
}

function handleExportCmd(cmd: string) {
  console.log('export command:', cmd)
}

function handleAiGenerate() {
  console.log('AI generate H2-13')
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-stocktake-check { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.check-table { font-size: 13px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.stop-row) { background-color: #fef0f0 !important; }
:deep(.missing-row) { background-color: #fde2e2 !important; }
</style>
