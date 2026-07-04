<script setup lang="ts">
/** F3TabAdjustment — F3-3 调整分录 | Task 6 (比照 D4TabAdjustment) */
import { toRef, inject, type Ref } from 'vue'
import { useF3Adjustment } from '../composables/useF3Adjustment'
import F3ImportExportToolbar from './F3ImportExportToolbar.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
function onImported() { reloadWorkpaperData?.() }

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const { rows, debitTotal, creditTotal, balanceDiff, isBalanced, addRow, removeRow, updateCell } = useF3Adjustment({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})
</script>

<template>
  <div class="f3-tab-adjustment">
    <details class="guidance-details"><summary>📋 编制提示</summary><p>AJE/RJE 分录，借贷须平衡。</p></details>
    <div class="toolbar">
      <el-button size="small" :disabled="isReadonly" @click="addRow">+ 新增分录</el-button>
      <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-3" :disabled="isReadonly" @imported="onImported" />
    </div>
    <el-table :data="rows" border size="small" style="font-size:13px">
      <el-table-column prop="seq" label="序号" width="60" />
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small" @change="(v: string) => updateCell(row.rowId, 'entryType', v)">
            <el-option label="AJE" value="AJE" /><el-option label="RJE" value="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.date" size="small" @change="(v: string) => updateCell(row.rowId, 'date', v)" />
          <span v-else>{{ row.date }}</span>
        </template>
      </el-table-column>
      <el-table-column label="摘要" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" @change="(v: string) => updateCell(row.rowId, 'summary', v)" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目" width="100"><template #default="{ row }">{{ row.accountCode }}</template></el-table-column>
      <el-table-column label="借方" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60">
        <template #default="{ row }"><el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button></template>
      </el-table-column>
    </el-table>
    <div class="balance-bar" :class="{ unbalanced: !isBalanced }">
      借方合计 {{ fmt(debitTotal) }} | 贷方合计 {{ fmt(creditTotal) }} | 差额 {{ fmt(balanceDiff) }}
      <span v-if="!isBalanced"> — 借贷不平衡</span>
    </div>
  </div>
</template>

<style scoped>
.f3-tab-adjustment { font-size: 13px; }
.toolbar { margin-bottom: 8px; }
.balance-bar { margin-top: 8px; text-align: right; font-weight: 600; }
.balance-bar.unbalanced { color: #f56c6c; }
</style>
