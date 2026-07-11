<template>
  <div class="g13-adjustment">
    <el-alert type="info" :closable="false" show-icon class="audit-objective"
      title="审计目标：复核公允价值变动收益（6101）相关审计调整分录（AJE/RJE）借贷平衡、科目正确，并同步回明细表 G13-2（CAS 39 公允价值计量）" />

    <div class="adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.addRow">+ 新增调整分录</el-button>
      <el-button size="small" :disabled="isReadonly || !adj.isBalanced.value" @click="adj.syncToDetail()">
        同步至明细表
      </el-button>
      <el-tag size="small" type="info" effect="plain" data-testid="g13-adjustment-count">共 {{ adj.rows.value.length }} 行</el-tag>
      <GtIndexChip value="wp:G13-3" :validate="false" />
      <CycleImportExportDropdown :wp-id="wpId" api-prefix="g13" sheet="G13-3"
        :disabled="isReadonly" @imported="emit('imported')" />
      <GtReviewTrigger section-id="G13-3-adjustment" />
    </div>

    <el-table :data="adj.rows.value" size="small" border stripe style="font-size:13px" data-testid="g13-adjustment-table">
      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          <GtReviewDot row-prefix="G13-aje" :row-key="row.rowId" />
          <el-select v-model="row.entryType" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'entryType', v)">
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="110">
        <template #default="{ row }">
          <el-input v-model="row.date" size="small" :disabled="isReadonly"
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
      <el-table-column label="科目名称" width="120">
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
      <span>借方合计：{{ fmtAmount(adj.debitTotal.value) }}</span>
      <span>贷方合计：{{ fmtAmount(adj.creditTotal.value) }}</span>
      <span :class="adj.isBalanced.value ? 'balanced' : 'unbalanced'">
        {{ adj.isBalanced.value ? '✓ 借贷平衡' : `✗ 差额：${fmtAmount(Math.abs(adj.balanceDiff.value))}` }}
      </span>
    </div>

    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <p>1. AJE=审计调整分录，RJE=重分类调整分录；每笔分录借贷必须平衡后方可「同步至明细表」。</p>
      <p>2. 公允价值变动损益科目编码 6101，借方增加对应损失、贷方增加对应收益；净额同步回 G13-2 明细表其他行。</p>
      <p>3. 可经「截止性测试」结果一键回填基准日附近的跨期分录（CAS 39 公允价值计量）。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef, onMounted, onBeforeUnmount } from 'vue'
import { useG13Adjustment } from '../composables/useG13Adjustment'
import { useG13Detail } from '../composables/useG13Detail'
import type { ChecklistResponse } from '../composables/useF1FormData'
import type { GCycleCutoffFilledDetail } from '../composables/gCycleCutoffFill'
import { GCYCLE_CUTOFF_EVENT } from '../composables/gCycleCutoffFill'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtIndexChip from '../GtIndexChip.vue'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const detailHelper = useG13Detail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const adj = useG13Adjustment({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
  applyAdjustmentToDetail: (net) => {
    const otherRow = detailHelper.rows.value.find((r) => !r.belongAccount)
    if (otherRow) {
      detailHelper.updateCell(otherRow.rowId, 'adjustment', net)
    }
  },
})

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  adj.applyCutoffResults(detail.samples, detail.fillMode)
}

onMounted(() => {
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g13, onCutoffFilled as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g13, onCutoffFilled as EventListener)
})

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g13-adjustment { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.compile-hint { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266; }
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
.adj-toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }
.balance-row { display: flex; gap: 24px; padding: 10px 12px; background: #fafafa; border-radius: 4px; margin-top: 12px; font-size: 13px; font-weight: 500; }
.balanced { color: #67c23a; }
.unbalanced { color: #f56c6c; font-weight: 600; }
</style>
