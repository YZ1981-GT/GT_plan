<template>
  <div class="g5-voucher-check">
    <div class="section-head">
      <h3 class="sheet-title">G5-12 凭证检查表</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-12" />
        <el-tag size="small" type="info">共 {{ vc.rows.value.length }} 行</el-tag>
        <GtReviewTrigger section-id="g5-12-voucher-check" />
        <GtVoucherSamplingEngine :project-id="props.projectId" :account-codes="[G5_ACCOUNT_CODE]" dialog-mode @filled="onSampleFilled" />
        <G5ImportExportDropdown :wp-id="props.wpId" sheet="G5-12" @imported="onImported" />
        <el-button size="small" type="primary" plain @click="vc.addRow()" :disabled="props.readonly">+ 新增</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：对长期应收款重要凭证执行检查：核对摘要、对方科目、金额、日期、凭证号与业务实质，识别异常凭证并形成结论。
    </el-alert>

    <div class="summary-bar" :class="{ 'summary-error': Math.abs(vc.debitTotal.value) > 0.01 }">
      借贷差额汇总：{{ fmt(vc.debitTotal.value) }} · 异常 {{ vc.abnormalCount.value }} 条
    </div>

    <div class="segment-tabs">
      <el-segmented v-model="vc.activeTab.value" :options="tabOptions" size="small" />
    </div>

    <el-table :data="vc.rows.value" border stripe style="width:100%;font-size:13px" max-height="480"
      highlight-current-row @current-change="onRowChange">
      <el-table-column prop="seq" label="序号" width="55" align="center" fixed />
      <template v-if="vc.activeTab.value === 'basic'">
        <el-table-column label="摘要" min-width="120">
          <template #default="{ row }"><el-input v-model="row.summary" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="对方科目" width="110">
          <template #default="{ row }"><el-input v-model="row.counterAccount" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="金额" width="110" align="right">
          <template #default="{ row }"><el-input-number v-model="row.amount" size="small" :controls="false" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="凭证日期" width="120">
          <template #default="{ row }"><el-input v-model="row.voucherDate" size="small" placeholder="YYYY-MM-DD" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row }"><el-input v-model="row.voucherNo" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="债务人" width="100">
          <template #default="{ row }"><el-input v-model="row.debtor" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="业务类型" width="100">
          <template #default="{ row }"><el-input v-model="row.businessType" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="附件" width="80">
          <template #default="{ row }">
            <el-button size="small" link @click="uploadOcr(row)" :disabled="props.readonly">📎</el-button>
            <span v-if="row.attachment" class="attach-tag">{{ row.attachment }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else-if="vc.activeTab.value === 'check'">
        <el-table-column v-for="n in 7" :key="n" :label="`核对${n}`" width="70" align="center">
          <template #default="{ row }">
            <el-select :model-value="(row as any)[`check${n}`]" size="small" :disabled="props.readonly"
              @change="(v: string) => updateCheck(row, `check${n}`, v)">
              <el-option label="✓" value="✓" /><el-option label="✗" value="✗" /><el-option label="-" value="" />
            </el-select>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="是否异常" width="90">
          <template #default="{ row }">
            <el-tag :type="row.isAbnormal === '是' ? 'danger' : 'success'" size="small">{{ row.isAbnormal }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="160">
          <template #default="{ row }"><el-input v-model="row.conclusion" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="索引" width="80">
          <template #default="{ row }"><GtIndexChip v-if="row.indexRef" :label="row.indexRef" /></template>
        </el-table-column>
        <el-table-column label="来源" width="70">
          <template #default="{ row }"><el-tag v-if="row.source" size="small" type="info">{{ row.source }}</el-tag></template>
        </el-table-column>
      </template>
    </el-table>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="props.readonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述抽凭方法与样本量、凭证检查结果、异常凭证识别及处理情况。"
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
        <li>可用抽凭引擎按科目 1531 抽取样本，或用附件 📎 上传凭证 OCR 自动填入</li>
        <li>"凭证基础"录入摘要/对方科目/金额/日期/凭证号；"核对内容"逐项打勾（✓/✗）</li>
        <li>"结论"区标记是否异常并填写审计结论，来源标签区分手工/抽凭</li>
        <li>借贷差额汇总应为 0，异常条数需在结论中说明处理情况</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted } from 'vue'
import { useG5VoucherCheck } from '../../composables/useG5VoucherCheck'
import type { VoucherCheckRow } from '../../composables/useG5VoucherCheck'
import { G5_ACCOUNT_CODE } from '../../composables/g5Constants'
import { useG5LonRecFormData } from '../../composables/useG5LonRecFormData'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const vc = useG5VoucherCheck()

// ─── 审计说明 / 审计结论（持久化 checklist_responses，item_id 前缀 G5-）───
const g5Notes = useG5LonRecFormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const auditConclusion = ref('')
const G5_NOTE_KEY = 'G5-12-audit-note'
const G5_CONCLUSION_KEY = 'G5-12-audit-conclusion'
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
const tabOptions = [
  { label: '凭证基础', value: 'basic' },
  { label: '核对内容', value: 'check' },
  { label: '结论', value: 'conclusion' },
]

function onRowChange(row: any) {
  if (!row) return
  const idx = vc.rows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) vc.activeRowIndex.value = idx
}

function updateCheck(row: VoucherCheckRow, field: string, val: string) {
  ;(row as any)[field] = val
  vc.recalcRow(row)
}

function onImported(rows: unknown[]) { vc.loadRows(rows as any) }
function onSampleFilled(payload: { samples: Array<{ summary?: string; amount?: number; voucherDate?: string; voucherNo?: string }> }) {
  for (const s of payload.samples ?? []) {
    vc.mergeSample({ summary: s.summary, amount: s.amount, voucherDate: s.voucherDate, voucherNo: s.voucherNo, source: '抽凭' })
  }
}
function uploadOcr(row: VoucherCheckRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData)
      const data = res.data?.data ?? res.data ?? {}
      const summary = data.summary ?? data.extracted_fields?.summary ?? data.extracted_fields?.businessContent ?? ''
      const voucherNo = data.extracted_fields?.voucherNo ?? data.voucher_no ?? ''
      const voucherDate = data.extracted_fields?.voucherDate ?? data.voucher_date ?? ''
      const amount = data.extracted_fields?.amount ?? data.amount ?? null
      if (!summary && !voucherNo) { ElMessage.warning('OCR 未识别到有效内容'); return }
      const display = [
        summary ? `摘要：${summary}` : '',
        voucherNo ? `凭证号：${voucherNo}` : '',
        voucherDate ? `日期：${voucherDate}` : '',
        amount ? `金额：${amount}` : '',
      ].filter(Boolean).join('\n')
      await ElMessageBox.confirm(display, 'OCR 识别结果确认', { type: 'info', confirmButtonText: '填入当前行', cancelButtonText: '取消' })
      // merge OCR result into row
      if (summary) row.summary = summary
      if (voucherNo) row.voucherNo = voucherNo
      if (voucherDate) row.voucherDate = voucherDate
      if (amount && !isNaN(Number(amount))) row.amount = Number(amount)
      row.attachment = file.name
      vc.recalcRow(row)
    } catch (e: any) {
      if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('OCR 识别失败')
    }
  }
  input.click()
}
function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.g5-voucher-check { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.summary-bar { padding: 8px 12px; background: #f5f7fa; font-size: 12px; margin-bottom: 8px; border-radius: 4px; }
.summary-error { background: #fef0f0; color: #f56c6c; }
.segment-tabs { margin-bottom: 8px; }
.attach-tag { font-size: 11px; color: #909399; }
.audit-objective { margin-bottom: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
