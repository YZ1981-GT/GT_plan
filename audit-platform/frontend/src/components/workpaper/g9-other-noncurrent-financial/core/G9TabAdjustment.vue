<template>
  <div class="g9-adj" data-testid="g9-adjustment">
    <div class="toolbar">
      <h3>G9-3 调整分录</h3>
      <div class="head-actions">
        <GtIndexChip value="wp:G9-3" />
        <el-tag size="small" type="info">共 {{ adj.rows.value.length }} 行</el-tag>
        <G9ImportExportDropdown :wp-id="wpId" sheet="G9-3" @imported="onImported" />
        <el-button v-if="!isReadonly" size="small" @click="adj.addRow()">+ 新增</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：检查审计调整分录（AJE）与重分类分录（RJE）的依据充分、借贷平衡，并正确回写 G9-1 审定表。"
    />

    <el-alert v-if="!adj.balanceOk.value" type="error" :closable="false" class="balance-alert">
      借贷不平衡，差额 {{ adj.balanceDiff.value.toFixed(2) }}
    </el-alert>
    <el-alert
      v-else-if="adj.writebackPreview.value.closingAje !== 0 || adj.writebackPreview.value.closingRje !== 0"
      type="info" :closable="false" class="balance-alert"
      data-testid="g9-adj-writeback-hint"
    >
      已回写 G9-1「{{ G9_ADJ_WRITEBACK_ROW_KEY }}」期末 AJE {{ fmt(adj.writebackPreview.value.closingAje) }}
      / RJE {{ fmt(adj.writebackPreview.value.closingRje) }}
    </el-alert>

    <el-table :data="adj.rows.value" border size="small" style="font-size:13px" max-height="480">
      <el-table-column prop="seq" label="#" width="44" align="center" />
      <el-table-column label="类型" width="72">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { entryType: v as 'AJE' | 'RJE' })">
            <el-option label="AJE" value="AJE" /><el-option label="RJE" value="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="108">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.date" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { date: v })" />
          <span v-else>{{ row.date }}</span>
        </template>
      </el-table-column>
      <el-table-column label="摘要" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { summary: v })" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目代码" width="88">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountCode" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { accountCode: v })" />
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { accountName: v })" />
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => adj.updateRow(row.rowId, { debitAmount: v ?? 0 })" />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => adj.updateRow(row.rowId, { creditAmount: v ?? 0 })" />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="编制人" width="88">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.preparedBy" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { preparedBy: v })" />
          <span v-else>{{ row.preparedBy }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { remark: v })" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="adj.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>AJE 为审计调整分录（影响审定数），RJE 为重分类分录（影响列报）。每笔分录须借贷平衡，合计差额应为 0。</p>
        <p>涉及科目 1504 的调整将自动回写至 G9-1 审定表「{{ G9_ADJ_WRITEBACK_ROW_KEY }}」行的期末 AJE/RJE。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import { G9_ADJ_WRITEBACK_ROW_KEY } from '../../composables/g9Constants'
import { useG9Adjustment } from '../../composables/useG9Adjustment'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import type { GCycleCutoffFilledDetail } from '../../composables/gCycleCutoffFill'
import { GCYCLE_CUTOFF_EVENT } from '../../composables/gCycleCutoffFill'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const adj = useG9Adjustment({
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

function onImported() { emit('imported') }

function fmt(n: number) {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  adj.applyCutoffResults(detail.samples, detail.fillMode)
}

onMounted(() => {
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g9, onCutoffFilled as EventListener)
})
onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g9, onCutoffFilled as EventListener)
})
</script>

<style scoped>
.g9-adj { font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; margin-bottom: 8px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.balance-alert { margin-bottom: 8px; }
.audit-objective { margin-bottom: 10px; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
</style>
