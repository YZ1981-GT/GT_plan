<template>
  <div class="g8-adj" data-testid="g8-adjustment">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表登记其他权益工具投资（科目1503）相关审计调整分录（AJE）与重分类分录（RJE），须借贷平衡。</p>
        <p>2. 涉及公允价值变动的调整应同步计入其他综合收益（OCI），处置时累计 OCI 可转入留存收益（不经损益）。</p>
        <p>3. 期末账项调整合计自动回写 G8-1 审定表对应行。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：记录并复核其他权益工具投资（科目1503）的审计调整与重分类分录，确认调整依据充分、借贷平衡，并正确回写审定表。"
      class="objective-alert"
    />

    <div class="toolbar">
      <h3>G8-3 调整分录</h3>
      <div class="head-actions">
        <G8ImportExportDropdown :wp-id="wpId" sheet="G8-3" @imported="onImported" />
        <GtReviewTrigger section-id="G8-3-adjustment" />
        <el-button v-if="!isReadonly" size="small" data-testid="g8-adj-add" @click="adj.addRow()">+ 新增</el-button>
      </div>
    </div>

    <el-alert v-if="!adj.balanceOk.value" type="error" :closable="false" class="balance-alert" data-testid="g8-adj-balance-error">
      借贷不平衡，差额 {{ adj.balanceDiff.value.toFixed(2) }}
    </el-alert>
    <el-alert
      v-else-if="adj.writebackPreview.value.closingAdjustment !== 0"
      type="info" :closable="false" class="balance-alert"
      data-testid="g8-adj-writeback-hint"
    >
      已回写 G8-1「{{ G8_ADJ_WRITEBACK_ROW_KEY }}」期末账项调整 {{ fmt(adj.writebackPreview.value.closingAdjustment) }}
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
      <el-table-column label="科目名称" width="140">
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

    <el-card shadow="never" class="audit-note-card">
      <template #header>审计说明</template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：调整分录的依据、性质（AJE/RJE）及对 OCI/留存收益的影响。" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>审计结论</template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写审计结论：调整分录是否恰当、借贷是否平衡、是否已正确回写审定表。" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G8ImportExportDropdown from '../G8ImportExportDropdown.vue'
import { G8_ADJ_WRITEBACK_ROW_KEY } from '../../composables/g8Constants'
import { useG8Adjustment } from '../../composables/useG8Adjustment'
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

const adj = useG8Adjustment({
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const AUDIT_NOTE_KEY = 'G8-3-audit-note'
const AUDIT_CONCLUSION_KEY = 'G8-3-audit-conclusion'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(AUDIT_CONCLUSION_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_KEY, { conclusion: null, remark: v })
})

function fmt(n: number) {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onImported() { emit('imported') }

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  adj.applyCutoffResults(detail.samples, detail.fillMode)
}

onMounted(() => {
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g8, onCutoffFilled as EventListener)
})
onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g8, onCutoffFilled as EventListener)
})
</script>

<style scoped>
.g8-adj { font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; margin-bottom: 8px; align-items: center; }
.head-actions { display: flex; gap: 8px; }
.balance-alert { margin-bottom: 8px; }
.guidance-details { margin-bottom: 10px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 10px; }
.audit-note-card { margin-top: 12px; }
</style>
