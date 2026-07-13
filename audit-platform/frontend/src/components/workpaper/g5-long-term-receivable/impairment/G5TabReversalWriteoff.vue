<template>
  <div class="g5-reversal-writeoff">
    <div class="section-head">
      <h3 class="sheet-title">G5-11 坏账准备转回核销检查</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-11" />
        <GtReviewTrigger section-id="g5-11-reversal-writeoff" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：检查长期应收款坏账准备的转回与核销：验证转回金额不超过累计计提、核销的审批完整性，关注关联交易异常。
    </el-alert>

    <div class="segment-tabs">
      <el-segmented v-model="rw.activeTab.value" :options="tabOptions" size="small" />
      <div class="tab-actions">
        <G5ImportExportDropdown :wp-id="props.wpId" sheet="G5-11" @imported="onImported" />
        <el-button v-if="rw.activeTab.value === 'reversal'" size="small" type="primary" plain @click="rw.addReversalRow()" :disabled="props.readonly">+ 新增转回</el-button>
        <el-button v-else size="small" type="primary" plain @click="rw.addWriteoffRow()" :disabled="props.readonly">+ 新增核销</el-button>
      </div>
    </div>

    <el-table v-show="rw.activeTab.value === 'reversal'" :data="rw.reversalRows.value" border stripe style="width:100%;font-size:13px" max-height="450"
      highlight-current-row @current-change="onRowChange"
      :row-class-name="({ row }) => !row.isValid ? 'row-error' : row.isRelatedParty ? 'row-related' : ''">
      <el-table-column prop="seq" label="序号" width="55" align="center" />
      <el-table-column label="债务人" min-width="120">
        <template #default="{ row }"><el-input v-model="row.debtor" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="累计计提" width="110" align="right">
        <template #default="{ row }"><el-input-number v-model="row.accumulatedProvision" size="small" :controls="false" :disabled="props.readonly" @change="rw.recalcReversal(row)" /></template>
      </el-table-column>
      <el-table-column label="转回金额" width="110" align="right">
        <template #default="{ row }"><el-input-number v-model="row.reversalAmount" size="small" :controls="false" :disabled="props.readonly" @change="rw.recalcReversal(row)" /></template>
      </el-table-column>
      <el-table-column label="关联交易" width="80">
        <template #default="{ row }"><el-checkbox v-model="row.isRelatedParty" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="原因" min-width="120">
        <template #default="{ row }"><el-input v-model="row.reason" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="索引" width="70">
        <template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
    </el-table>

    <el-table v-show="rw.activeTab.value === 'writeoff'" :data="rw.writeoffRows.value" border stripe style="width:100%;font-size:13px" max-height="450"
      highlight-current-row @current-change="onRowChange"
      :row-class-name="({ row }) => row.isRelatedParty ? 'row-related' : ''">
      <el-table-column prop="seq" label="序号" width="55" align="center" />
      <el-table-column label="债务人" min-width="120">
        <template #default="{ row }"><el-input v-model="row.debtor" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="核销金额" width="110" align="right">
        <template #default="{ row }"><el-input-number v-model="row.writeoffAmount" size="small" :controls="false" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="审批状态" width="100">
        <template #default="{ row }"><el-input v-model="row.approvalStatus" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="关联交易" width="80">
        <template #default="{ row }"><el-checkbox v-model="row.isRelatedParty" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="原因" min-width="120">
        <template #default="{ row }"><el-input v-model="row.reason" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="索引" width="70">
        <template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
    </el-table>

    <div v-if="rw.invalidReversals.value.length" class="error-bar">
      ⚠ {{ rw.invalidReversals.value.length }} 条转回金额超过累计计提
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="props.readonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述转回是否超累计计提、核销审批完整性、关联交易异常识别及处理情况。"
        @change="(val: string) => saveAuditNote(val)" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="props.readonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项，不可确认。"
        @change="(val: string) => saveAuditConclusion(val)" />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>转回金额不得超过累计计提金额，超出者红色标记（异常）</li>
        <li>核销须有完整审批手续，关注核销依据与后续追偿</li>
        <li>关联交易的转回/核销单独标记（橙色），警惕通过转回调节利润</li>
        <li>转回原因、核销原因须逐笔说明并保留支持性证据（CAS 22）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted } from 'vue'
import { useG5ReversalWriteoff } from '../../composables/useG5ReversalWriteoff'
import { useG5LonRecFormData } from '../../composables/useG5LonRecFormData'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const rw = useG5ReversalWriteoff()

// ─── 审计说明 / 审计结论（持久化 checklist_responses，item_id 前缀 G5-）───
const g5Notes = useG5LonRecFormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const auditConclusion = ref('')
const G5_NOTE_KEY = 'G5-11-audit-note'
const G5_CONCLUSION_KEY = 'G5-11-audit-conclusion'
function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.readonly) return
  auditConclusion.value = val
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val })
}
onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
const tabOptions = [{ label: '转回检查', value: 'reversal' }, { label: '核销检查', value: 'writeoff' }]

function onRowChange(row: any) {
  if (!row) return
  const idx = rw.activeTab.value === 'reversal'
    ? rw.reversalRows.value.findIndex(r => r.id === row.id)
    : rw.writeoffRows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) rw.activeRowIndex.value = idx
}

function onImported(rows: unknown[]) {
  const reversal = (rows as any[]).filter(r => r.section === 'reversal' || r.checkZone === 'reversal')
  const writeoff = (rows as any[]).filter(r => r.section === 'writeoff' || r.checkZone === 'writeoff')
  if (reversal.length) rw.loadReversalRows(reversal)
  if (writeoff.length) rw.loadWriteoffRows(writeoff)
  if (!reversal.length && !writeoff.length && Array.isArray(rows)) rw.loadReversalRows(rows as any)
}
</script>

<style scoped>
.g5-reversal-writeoff { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.segment-tabs { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.tab-actions { margin-left: auto; display: flex; gap: 8px; }
.error-bar { margin-top: 8px; padding: 8px 12px; background: #fef0f0; color: #f56c6c; font-size: 12px; border-radius: 4px; }
:deep(.row-error) { background-color: #fef0f0 !important; }
:deep(.row-related) { background-color: #fdf6ec !important; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
