<script setup lang="ts">
/** F2TabAdjustment — F2-14 调整分录 | Task 15.4 */
import { toRef, inject, type Ref } from 'vue'
import { useF2Adjustment } from '../../composables/useF2Adjustment'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const {
  rows, debitTotal, creditTotal, balanceDiff, isBalanced, accountOptions,
  addRow, removeRow, updateCell, publishAdjustments,
} = useF2Adjustment({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})
</script>

<template>
  <div class="f2-tab-adjustment">
    <details class="guidance-details"><summary>📋 编制提示</summary><p>存货 AJE/RJE 分录，借贷须平衡；保存后自动联动 F2-1 账项调整行。</p></details>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增分录</el-button>
      <el-button size="small" :disabled="isReadonly" @click="publishAdjustments">同步至审定表</el-button>
      <CycleImportExportDropdown
        :wp-id="wpId"
        api-prefix="f2"
        sheet="F2-14"
        :disabled="isReadonly"
        @imported="onImported"
      />
      <F2ReviewChip section-id="F2-14-adjustment" />
    </div>

    <el-table :data="rows" border size="small" style="font-size:13px">
      <el-table-column prop="seq" label="序号" width="55" />
      <el-table-column label="调整事项说明" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" @change="(v: string) => updateCell(row.rowId, 'summary', v)" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目编码" width="100">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.accountCode" size="small" filterable
            @change="(v: string) => updateCell(row.rowId, 'accountCode', v)">
            <el-option v-for="a in accountOptions" :key="a.code" :label="a.code" :value="a.code" />
          </el-select>
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="130">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.accountName" size="small" filterable
            @change="(v: string) => updateCell(row.rowId, 'accountName', v)">
            <el-option v-for="a in accountOptions" :key="a.name" :label="a.name" :value="a.name" />
          </el-select>
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small" @change="(v: string) => updateCell(row.rowId, 'entryType', v)">
            <el-option label="AJE" value="AJE" /><el-option label="RJE" value="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="80">
        <template #default="{ row }">
          <GtIndexChip v-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
          <el-input v-else-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(v: string) => updateCell(row.rowId, 'indexRef', v)" />
        </template>
      </el-table-column>
      <el-table-column label="附注项目" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.noteItem" size="small" @change="(v: string) => updateCell(row.rowId, 'noteItem', v)" />
          <span v-else>{{ row.noteItem }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="balance-bar" :class="{ unbalanced: !isBalanced }">
      借方合计 {{ fmt(debitTotal) }} | 贷方合计 {{ fmt(creditTotal) }} | 差额 {{ fmt(balanceDiff) }}
      <span v-if="!isBalanced"> — 借贷不平衡</span>
    </div>
  </div>
</template>

<style scoped>
.f2-tab-adjustment { font-size: 13px; padding: 12px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
.balance-bar { margin-top: 8px; text-align: right; font-weight: 600; }
.balance-bar.unbalanced { color: #f56c6c; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
</style>
