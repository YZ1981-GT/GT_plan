<template>
  <div class="g12-disc">
    <div class="section-head">
      <h3 class="sheet-title">{{ dis.title.value }}</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="dis.syncFromG12Adjudication()">从 G12-1 同步</el-button>
        <el-button size="small" :loading="dis.aiLoading.value" :disabled="isReadonly"
          @click="dis.generateAiConclusion()">🤖 AI辅助</el-button>
        <GtReviewTrigger section-id="G12-disclosure-soe" />
      </div>
    </div>

    <GCycleGuideStrip
      label="主闭环"
      :steps="[...G12_CORE_WORKFLOW_STEPS]"
      :active-index="wf.activeIndex.value"
      :completed-indices="wf.completedIndices.value"
    />
    <G12CoreWorkflowChecklist :readiness="wf.readiness.value" compact />

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标"
      description="按国企披露口径列报净敞口套期收益分项来源及合计，核对与 G12-1 审定数（6103）一致，编制附注披露说明。"
    />

    <el-alert v-if="dis.adjudicatedAmount.value != null" type="success" :closable="false" class="sync-hint">
      已同步审定数（6103）：{{ fmt(dis.adjudicatedAmount.value) }}
      <el-button link size="small" @click="dis.pullLatestAdjudicated()">刷新</el-button>
    </el-alert>

    <el-alert
      v-if="dis.reconciliationDiff.value != null"
      :type="dis.reconciliationDiff.value === 0 ? 'success' : 'warning'"
      :closable="false"
      show-icon
      class="reconciliation"
    >
      附注合计与 G12-1 审定数勾稽{{ dis.reconciliationDiff.value === 0 ? '一致' : '存在差异' }}。
      差异：{{ fmt(dis.reconciliationDiff.value) }}。
      <span v-if="dis.reconciliationDiff.value !== 0">请核对 G12-2 明细分项（被套期 FV / CF 储备）与审定表。</span>
    </el-alert>

    <p class="table-caption">净敞口套期收益</p>

    <el-table :data="dis.displayRows.value" border size="small" style="font-size:13px" max-height="320"
      data-testid="g12-disclosure-soe-table"
      :row-class-name="rowClassName">
      <el-table-column :label="dis.soeColumnLabel.value" prop="label" min-width="360" fixed />
      <el-table-column label="本期发生额" width="160" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentAmount" size="small"
            :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'currentAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期发生额" width="160" align="right">
        <template #default="{ row }">
          <span>{{ fmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="note-card">
      <template #header>附注说明</template>
      <el-input :model-value="dis.noteText.value" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly" @update:model-value="dis.updateNoteText" />
    </el-card>

        
    <GCycleDisclosureExtras
      cycle-label="G12 净敞口套期（国企）"
      :account-code="G12_ACCOUNT_CODE"
      :adjudicated-amount="dis.adjudicatedAmount.value"
      :disclosure-total="dis.totalRow.value.currentAmount"
      :formula-map="[...G12_DISCLOSURE_FORMULA_MAP]"
      :is-readonly="isReadonly"
      @refresh="dis.pullLatestAdjudicated()"
    />

    <details class="methodology-hint">
      <summary>📋 编制提示（CAS24 套期会计）</summary>
      <p><strong>本页在主闭环中的位置：第 3 步</strong> — {{ G12_CORE_WORKFLOW_HINT }}</p>
      <p>国企口径列示两项来源（被套期 FV 转入损益、CF 储备转入损益）。点「从 G12-1 同步」后确认勾稽条为绿色，再编写附注说明。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed } from 'vue'
import { useG12Disclosure } from '../../composables/useG12Disclosure'
import { G12_ACCOUNT_CODE, G12_CORE_WORKFLOW_HINT, G12_CORE_WORKFLOW_STEPS, G12_DISCLOSURE_FORMULA_MAP } from '../../composables/g12Constants'
import { useG12CoreWorkflow } from '../../composables/useG12CoreWorkflow'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GCycleDisclosureExtras from '../../shared/GCycleDisclosureExtras.vue'
import GCycleGuideStrip from '../../shared/GCycleGuideStrip.vue'
import G12CoreWorkflowChecklist from '../shared/G12CoreWorkflowChecklist.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const dis = useG12Disclosure({
  variant: 'soe',
  allResponses: toRef(props, 'allResponses'),
  wpId: toRef(props, 'wpId'),
  isReadonly: computed(() => props.isReadonly),
  debouncedSave: props.debouncedSave,
})

const wf = useG12CoreWorkflow({ allResponses: toRef(props, 'allResponses'), pageCode: '附注国企' })

function rowClassName({ row }: { row: { rowKey: string } }): string {
  return row.rowKey === 'total' ? 'g12-row-total' : ''
}

function fmt(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g12-disc { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 12px; }
.sync-hint { margin-bottom: 12px; }
.reconciliation { margin-bottom: 12px; }
.table-caption { margin: 0 0 8px; font-weight: 600; font-size: 14px; }
.formula-cell { border-bottom: 1px dashed #909399; background: #fafafa; cursor: help; }
.methodology-hint { margin-top: 16px; padding: 10px 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 0 4px 4px 0; font-size: var(--wp-font-size, 13px); color: #606266; }
.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.note-card { margin-top: 12px; }
:deep(.g12-row-total) { font-weight: 700; background: #f5f7fa; }
</style>
