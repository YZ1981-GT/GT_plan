<template>
  <div class="g14-adjustment">
    <div class="adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.addRow">+ 新增调整分录</el-button>
      <el-button size="small" :disabled="isReadonly || !adj.isBalanced.value" @click="adj.syncToDetail()">
        同步至明细表
      </el-button>
      <CycleImportExportDropdown :wp-id="wpId" api-prefix="g14" sheet="G14-3"
        :disabled="isReadonly" @imported="emit('imported')" />
      <GtReviewTrigger section-id="G14-3-adjustment" />
    </div>

    <el-table :data="adj.rows.value" size="small" border stripe data-testid="g14-adjustment-table">
      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row }">
          <GtReviewDot row-prefix="G14-aje" :row-key="row.rowId" />
          <el-input v-model="row.description" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'description', v)" />
        </template>
      </el-table-column>
      <el-table-column label="类别" width="120">
        <template #default="{ row }">
          <el-select v-model="row.category" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'category', v)">
            <el-option value="账项调整" />
            <el-option value="报表调整" />
            <el-option value="重分类调整" />
            <el-option value="其他" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" width="120">
        <template #default="{ row }">
          <el-input v-model="row.reportItem" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'reportItem', v)" />
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="120">
        <template #default="{ row }">
          <el-input v-model="row.accountName" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'accountName', v)" />
        </template>
      </el-table-column>
      <el-table-column label="附注项目" width="100">
        <template #default="{ row }">
          <el-input v-model="row.noteItem" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'noteItem', v)" />
        </template>
      </el-table-column>
      <el-table-column label="借方调整金额" width="120" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.debitAmount" size="small" :disabled="isReadonly"
            @change="(v: any) => adj.updateCell(row.rowId, 'debitAmount', v)" />
        </template>
      </el-table-column>
      <el-table-column label="贷方调整金额" width="120" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.creditAmount" size="small" :disabled="isReadonly"
            @change="(v: any) => adj.updateCell(row.rowId, 'creditAmount', v)" />
        </template>
      </el-table-column>
      <el-table-column label="索引" width="80">
        <template #default="{ row }">
          <el-input v-model="row.indexRef" size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.rowId, 'indexRef', v)" />
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
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
      <div class="hint-content">
        1. 调整分录格式与 D 循环调整分录模块一致，按实际调整事项逐笔编制。<br>
        2. 账项调整影响 G14-2 明细「调整数」；可点击「同步至明细表」将账项调整净额写入「其他」行。<br>
        3. 借贷须平衡后方可同步；G14-1 本期调整数自 G14-2 自动汇总。
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef, onMounted, onBeforeUnmount } from 'vue'
import { useG14Adjustment } from '../composables/useG14Adjustment'
import { useG14Detail } from '../composables/useG14Detail'
import type { ChecklistResponse } from '../composables/useF1FormData'
import type { GCycleCutoffFilledDetail } from '../composables/gCycleCutoffFill'
import { GCYCLE_CUTOFF_EVENT } from '../composables/gCycleCutoffFill'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtReviewDot from '../GtReviewDot.vue'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const detailHelper = useG14Detail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const adj = useG14Adjustment({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
  applyAdjustmentToDetail: (net) => {
    detailHelper.updateCell('other', 'currentAdjustment', net)
  },
})

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  adj.applyCutoffResults(detail.samples, detail.fillMode)
}

onMounted(() => {
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g14, onCutoffFilled as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g14, onCutoffFilled as EventListener)
})

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g14-adjustment { padding: 16px; }
.adj-toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
.balance-row { display: flex; gap: 24px; padding: 10px 12px; background: #fafafa; border-radius: 4px; margin-top: 12px; font-size: 13px; font-weight: 500; }
.balanced { color: #67c23a; }
.unbalanced { color: #f56c6c; font-weight: 600; }
.compile-hint { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; }
.compile-hint summary { padding: 8px 12px; cursor: pointer; font-size: 13px; color: #409eff; }
.hint-content { padding: 0 12px 12px; font-size: 12px; color: #606266; line-height: 1.8; }
</style>
