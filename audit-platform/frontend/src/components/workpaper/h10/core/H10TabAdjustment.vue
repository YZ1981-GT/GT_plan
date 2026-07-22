<template>
  <div class="h10-adjustment" data-testid="h10-adjustment">
    <div class="section-head">
      <h3 class="sheet-title">H10-3 调整分录汇总</h3>
      <div class="head-actions">
        <H10ImportExportDropdown :wp-id="wpId" sheet="H10-3" @imported="emit('imported')" />
        <GtReviewTrigger section-id="H10-3-adjustment" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="adj.addRow()">+ 新增</el-button>
      </div>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 汇总资产处置损益相关的审计调整（AJE）与重分类调整（RJE），每笔分录借贷必须平衡；6115 净额自动回写 H10-1。</p>
        <p>2. AJE 用于纠正错报（漏记、时点、金额差错）；RJE 用于报表列报重分类（如误入营业外收支应重分类至 6115）。</p>
        <p>3. 调整应注明摘要、科目代码/名称、金额、日期与制单人，并与 H10-2 账项/重分类调整列及 H10-1 勾稽一致。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：汇总资产处置损益相关的审计调整与重分类调整，确保借贷平衡、调整依据充分，并与审定表勾稽一致。" />

    <el-alert v-if="!adj.isBalanced.value" type="error" :closable="false" class="balance-alert">
      借贷不平衡，差额 {{ fmt(adj.balanceDiff.value) }}
    </el-alert>
    <el-alert v-else-if="adj.rows.value.length" type="success" :closable="false" class="balance-alert">
      借贷平衡
    </el-alert>

    <div class="stats-bar" data-testid="h10-adj-stats">
      <span>借方合计 {{ fmt(debitTotal) }}</span>
      <span>贷方合计 {{ fmt(creditTotal) }}</span>
      <span>6115净额 {{ fmt(adj.adjustmentNet.value) }}</span>
      <span>回写 AJE {{ fmt(adj.writebackPreview.value.currentAje) }} / RJE {{ fmt(adj.writebackPreview.value.currentRje) }}</span>
    </div>

    <el-table :data="adj.rows.value" border size="small" style="font-size:13px" max-height="480">
      <el-table-column label="类型" width="72">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small"
            @change="(v: 'AJE'|'RJE') => adj.updateRow(row.rowId, { entryType: v })">
            <el-option label="AJE" value="AJE" /><el-option label="RJE" value="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
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
      <el-table-column label="科目" width="110">
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
      <el-table-column label="日期" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.date" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { date: v })" />
          <span v-else>{{ row.date }}</span>
        </template>
      </el-table-column>
      <el-table-column label="制单人" width="88">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.preparedBy" size="small"
            @update:model-value="(v: string) => adj.updateRow(row.rowId, { preparedBy: v })" />
          <span v-else>{{ row.preparedBy }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="64" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="adj.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：说明各笔调整分录的依据、影响的报表项目及与审定表的勾稽情况。"
        @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：调整分录借贷平衡、依据充分，已与审定表及被审计单位沟通。"
        @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted } from 'vue'
import { useH10Adjustment } from '../../composables/useH10Adjustment'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import H10ImportExportDropdown from '../H10ImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const adj = useH10Adjustment({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const debitTotal = computed(() => adj.rows.value.reduce((s, r) => s + (r.debitAmount || 0), 0))
const creditTotal = computed(() => adj.rows.value.reduce((s, r) => s + (r.creditAmount || 0), 0))

const NOTE_KEY = 'H10-3-adjustment-audit-note'
const CONCLUSION_KEY = 'H10-3-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  props.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  props.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h10-adjustment { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.balance-alert { margin-bottom: 8px; }
.stats-bar { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 8px; font-size: 12px; color: #606266; }
.guidance-details { margin-bottom: 8px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 8px; }
.audit-note-card { margin-top: 12px; }
</style>
