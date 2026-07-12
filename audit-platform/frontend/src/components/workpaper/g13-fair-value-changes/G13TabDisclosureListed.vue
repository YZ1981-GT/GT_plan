<template>
  <div class="g13-disclosure">
    <div class="section-head">
      <h3 class="sheet-title">{{ dis.title.value }}</h3>
      <div class="head-actions">
        <el-button size="small" :loading="dis.aiLoading.value" :disabled="isReadonly"
          @click="dis.generateAiConclusion()">🤖 AI辅助</el-button>
        <el-button size="small" :disabled="isReadonly" @click="dis.syncFromDetail()">从明细同步</el-button>
        <GtReviewTrigger section-id="G13-disclosure-listed" />
      </div>
    </div>

    <el-alert v-if="dis.adjudicatedAmount.value != null" type="success" :closable="false" class="sync-hint">
      已同步审定数（6101）：{{ fmt(dis.adjudicatedAmount.value) }}
      <el-button link size="small" @click="dis.pullLatestAdjudicated()">刷新</el-button>
    </el-alert>

    <el-table :data="dis.displayRows.value" border size="small" style="font-size:13px" max-height="480"
      data-testid="g13-disclosure-listed-table"
      :row-class-name="rowClassName">
      <el-table-column label="产生公允价值变动收益的来源" prop="label" min-width="280" fixed />
      <el-table-column label="本期发生额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentAmount" size="small"
            :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'currentAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期发生额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.priorAmount" size="small"
            :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'priorAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" width="120" align="right">
        <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
      </el-table-column>
      <el-table-column label="备注" min-width="80">
        <template #default="{ row }">
          <el-input v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.remark" size="small"
            @change="(v: string) => dis.updateField(row.rowKey, 'remark', v)" />
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="note-card">
      <template #header>附注说明</template>
      <el-input :model-value="dis.noteText.value" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }"
        :disabled="isReadonly" placeholder="公允价值变动收益附注披露说明…"
        @update:model-value="dis.updateNoteText" />
    </el-card>

    <GCycleDisclosureExtras
      cycle-label="G13 公允价值变动"
      :account-code="G13_ACCOUNT_CODE"
      :adjudicated-amount="dis.adjudicatedAmount.value"
      :disclosure-total="dis.totalRow.value.currentAmount"
      :formula-map="[...G13_DISCLOSURE_FORMULA_MAP]"
      :manual-formula-notes="['从明细同步：按 G13-2 belongAccount 汇总至附注各行']"
      :is-readonly="isReadonly"
      @refresh="onReconcileRefresh"
    />

    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <p>1. 上市公司口径披露 9 类公允价值变动收益来源+合计；本期发生额可「从明细同步」按 G13-2 所属科目汇总。</p>
      <p>2. 上期发生额自 G13-1 审定表上期审定数带入；变动额=本期-上期，用于附注文字说明佐证。</p>
      <p>3. 「发布审定数」后本组件自动同步审定合计（6101）（CAS 39 公允价值计量 / CAS 30 财务报表列报）。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef, computed } from 'vue'
import { useG13Disclosure } from '../composables/useG13Disclosure'
import { G13_ACCOUNT_CODE, G13_DISCLOSURE_FORMULA_MAP } from '../composables/g13Constants'
import type { ChecklistResponse } from '../composables/useF1FormData'
import GCycleDisclosureExtras from '../shared/GCycleDisclosureExtras.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const dis = useG13Disclosure({
  variant: 'listed',
  allResponses: toRef(props, 'allResponses'),
  wpId: toRef(props, 'wpId'),
  isReadonly: computed(() => props.isReadonly),
  debouncedSave: props.debouncedSave,
})

function rowClassName({ row }: { row: { rowKey: string } }): string {
  return row.rowKey === 'total' ? 'g13-row-total' : ''
}

function fmt(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onReconcileRefresh(): void {
  dis.pullLatestAdjudicated()
  dis.syncFromDetail()
}
</script>

<style scoped>
.g13-disclosure { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.sync-hint { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #fafafa; display: inline-block; width: 100%; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266; }
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
:deep(.g13-row-total) { font-weight: 700; background: #f5f7fa; }
</style>
