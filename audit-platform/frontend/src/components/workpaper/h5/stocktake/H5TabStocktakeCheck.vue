<template>
  <div class="h5-tab-stocktake-check">
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-10 盘点检查表（异常{{ state.abnormalCheckItems.value.length }}项，差异合计{{ fmtAmt(state.totalDifference.value) }}）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI说明</el-button>
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
import { computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH5Stocktake } from '../../composables/useH5Stocktake'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const state = useH5Stocktake({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: () => {} })

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入盘点项目', '新增检查项', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (value) state.addCheckRow(value)
}
function handleAiGenerate() {}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-stocktake-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
