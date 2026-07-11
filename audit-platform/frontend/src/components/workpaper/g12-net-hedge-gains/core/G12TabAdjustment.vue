<template>
  <div class="g12-adj-sheet">
    <div class="toolbar">
      <h3>G12-3 调整分录</h3>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.addRow()">+ 新增</el-button>
      <el-button size="small" :disabled="isReadonly || !adj.isBalanced.value" @click="adj.syncToAdjudication()">
        同步至审定表
      </el-button>
      <CycleImportExportDropdown :wp-id="wpId" api-prefix="g12" sheet="G12-3" :disabled="isReadonly" @imported="emit('imported')" />
      <el-tag size="small" type="info">共 {{ adj.rows.value.length }} 行</el-tag>
      <GtReviewTrigger section-id="G12-3-adjustment" />
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标"
      description="录入净敞口套期收益相关 AJE/RJE 调整分录，验证借贷平衡后同步至 G12-1 审定表调整数，确保审定数口径一致、可追溯。"
    />

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

    <details class="methodology-hint">
      <summary>📋 编制提示（CAS24 套期会计）</summary>
      <p>AJE=审计调整分录，RJE=重分类调整分录。科目 6103 净敞口套期收益为损益类（贷方）。借贷合计须平衡后方可「同步至审定表」，同步后 G12-1 调整数 overlay 自动更新。</p>
    </details>
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
.audit-objective { margin-bottom: 12px; }
.methodology-hint { margin-top: 16px; padding: 10px 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 0 4px 4px 0; font-size: 13px; color: #606266; }
.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.balance-row { display: flex; gap: 24px; padding: 10px 12px; background: #fafafa; border-radius: 4px; margin-top: 12px; font-size: 13px; font-weight: 500; }
.balanced { color: #67c23a; }
.unbalanced { color: #f56c6c; font-weight: 600; }
</style>
