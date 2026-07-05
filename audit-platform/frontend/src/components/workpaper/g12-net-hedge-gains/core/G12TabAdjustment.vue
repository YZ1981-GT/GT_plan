<template>
  <div class="g12-adj-sheet">
    <div class="toolbar">
      <h3>G12-3 调整分录</h3>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.addRow()">+ 新增</el-button>
      <el-button size="small" :disabled="isReadonly || !adj.isBalanced.value" @click="adj.syncToAdjudication()">
        同步至审定表
      </el-button>
      <CycleImportExportDropdown :wp-id="wpId" api-prefix="g12" sheet="G12-3" :disabled="isReadonly" @imported="emit('imported')" />
      <GtReviewTrigger section-id="G12-3-adjustment" />
    </div>

    <el-table :data="adj.rows.value" border size="small" stripe style="font-size:13px">
      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          <GtReviewDot row-prefix="G12-aje" :row-key="row.rowId" />
          <el-select v-model="row.entryType" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'entryType', v)">
            <el-option label="AJE" value="AJE" /><el-option label="RJE" value="RJE" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="110">
        <template #default="{ row }">
          <el-input v-model="row.date" size="small" placeholder="YYYY-MM-DD" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'date', v)" />
        </template>
      </el-table-column>
      <el-table-column label="摘要" min-width="140">
        <template #default="{ row }">
          <el-input v-model="row.summary" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'summary', v)" />
        </template>
      </el-table-column>
      <el-table-column label="科目编码" width="90">
        <template #default="{ row }">
          <el-input v-model="row.accountCode" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'accountCode', v)" />
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="130">
        <template #default="{ row }">
          <el-input v-model="row.accountName" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'accountName', v)" />
        </template>
      </el-table-column>
      <el-table-column label="借方" width="110" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.debitAmount" size="small" :disabled="isReadonly"
            @change="(v: any) => adj.updateCell(row.rowId, 'debitAmount', v)" />
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="110" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.creditAmount" size="small" :disabled="isReadonly"
            @change="(v: any) => adj.updateCell(row.rowId, 'creditAmount', v)" />
        </template>
      </el-table-column>
      <el-table-column label="编制人" width="80">
        <template #default="{ row }">
          <el-input v-model="row.preparedBy" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'preparedBy', v)" />
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="80">
        <template #default="{ row }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'remark', v)" />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="60">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="adj.removeRow(row.rowId)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="balance-row">
      <span>借方合计：{{ fmt(adj.debitTotal.value) }}</span>
      <span>贷方合计：{{ fmt(adj.creditTotal.value) }}</span>
      <span :class="adj.isBalanced.value ? 'balanced' : 'unbalanced'">
        {{ adj.isBalanced.value ? '✓ 借贷平衡' : `✗ 差额：${fmt(Math.abs(adj.balanceDiff.value))}` }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useG12Adjustment } from '../../composables/useG12Adjustment'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtReviewDot from '../../GtReviewDot.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()
const emit = defineEmits<{ imported: [] }>()

const adj = useG12Adjustment({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

function fmt(val: number): string {
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g12-adj-sheet { padding: 12px; font-size: 13px; }
.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.balance-row { display: flex; gap: 24px; padding: 10px 12px; background: #fafafa; border-radius: 4px; margin-top: 12px; font-size: 13px; font-weight: 500; }
.balanced { color: #67c23a; }
.unbalanced { color: #f56c6c; font-weight: 600; }
</style>
