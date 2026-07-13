<template>
  <div class="g12-disc">
    <div class="section-head">
      <h3 class="sheet-title">{{ dis.title.value }}</h3>
      <div class="head-actions">
        <el-button size="small" :loading="dis.aiLoading.value" :disabled="isReadonly"
          @click="dis.generateAiConclusion()">🤖 AI辅助</el-button>
        <GtReviewTrigger section-id="G12-disclosure-soe" />
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标"
      description="按国企披露口径列报净敞口套期收益的本期发生额及变动，核对合计与 G12-1 审定数（6103）一致，编制附注披露说明。"
    />

    <el-table :data="dis.displayRows.value" border size="small" style="font-size:13px" max-height="400"
      data-testid="g12-disclosure-soe-table"
      :row-class-name="rowClassName">
      <el-table-column label="项目" prop="label" width="220" fixed />
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
          <span>{{ fmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" width="120" align="right">
        <template #default="{ row }"><span class="formula-cell" title="变动额 = 本期发生额 − 上期发生额">{{ fmt(row.changeAmount) }}</span></template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.remark" size="small"
            @change="(v: string) => dis.updateField(row.rowKey, 'remark', v)" />
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="note-card">
      <template #header>附注说明</template>
      <el-input :model-value="dis.noteText.value" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly" @update:model-value="dis.updateNoteText" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>审计说明</template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：国企披露口径核对、与 G12-1 审定数勾稽情况及差异说明。"
        @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="note-card">
      <template #header>审计结论</template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写审计结论：披露内容是否恰当、完整，是否符合准则要求。"
        @change="saveAuditConclusion" />
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
      <p>国企口径按套期类型分项披露净敞口套期收益（6103）本期发生额。合计须与 G12-1 审定数勾稽一致；发布审定数后经 EventBus 自动同步。附注说明须涵盖套期策略与有效性评价结论。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, onMounted } from 'vue'
import { useG12Disclosure } from '../../composables/useG12Disclosure'
import { G12_ACCOUNT_CODE, G12_DISCLOSURE_FORMULA_MAP } from '../../composables/g12Constants'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GCycleDisclosureExtras from '../../shared/GCycleDisclosureExtras.vue'

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

const NOTE_KEY = 'G12-disclosure-soe-audit-note'
const CONCLUSION_KEY = 'G12-disclosure-soe-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

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
.formula-cell { border-bottom: 1px dashed #909399; background: #fafafa; cursor: help; }
.methodology-hint { margin-top: 16px; padding: 10px 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 0 4px 4px 0; font-size: var(--wp-font-size, 13px); color: #606266; }
.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.note-card { margin-top: 12px; }
:deep(.g12-row-total) { font-weight: 700; background: #f5f7fa; }
</style>
