<template>
  <div class="g8-voucher" data-testid="g8-voucher-check">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表抽取其他权益工具投资（科目1503）相关记账凭证，逐笔核对原始单据完整性、授权、账务处理及公允价值/OCI 计量正确性。</p>
        <p>2. 借贷合计应平衡；异常凭证须填列风险等级与异常说明。</p>
        <p>3. 可用抽凭引擎按方法（随机/系统/MUS 等）抽样；附件支持 OCR 识别自动填列业务内容。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：通过凭证检查核实其他权益工具投资（科目1503）交易的真实性、完整性与计量准确性，验证公允价值变动计入其他综合收益（OCI）的会计处理正确。"
    />

    <div class="section-head">
      <h3 class="sheet-title">G8-6 凭证检查表</h3>
      <div class="head-actions">
        <G8ImportExportDropdown :wp-id="wpId" sheet="G8-6" @imported="onImported" />
        <GtVoucherSamplingEngine :project-id="projectId" :account-codes="['1503']" dialog-mode @filled="onSampleFilled" />
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="vc.addRow()">+ 新增</el-button>
      </div>
    </div>
    <div class="summary-bar" :class="{ 'summary-error': !vc.balanceOk.value }">
      借方合计 {{ fmt(debitTotal) }} | 贷方合计 {{ fmt(creditTotal) }} | 差额 {{ fmt(vc.balanceDiff.value) }}
    </div>
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G8-6" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ vc.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-segmented v-model="vc.activeTab.value" :options="tabOptions" size="small" class="segment-tabs" />

    <el-table-v2
      v-if="vc.useVirtualScroll.value"
      :columns="virtualColumns"
      :data="vc.rows.value"
      :width="tableWidth"
      :height="440"
      :row-height="36"
      :header-height="40"
      fixed
      class="virtual-table"
      data-testid="g8-voucher-virtual-table"
    />

    <el-table
      v-else
      :data="vc.rows.value"
      border stripe size="small"
      style="font-size:13px;margin-top:8px"
      highlight-current-row
      :row-class-name="rowClassName"
      @current-change="onRowChange"
    >
      <el-table-column prop="seq" label="#" width="44" align="center" fixed />
      <template v-if="vc.activeTab.value === 'basic'">
        <el-table-column label="日期" width="108">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherDate" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { voucherDate: v })" />
            <span v-else>{{ row.voucherDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { voucherNo: v })" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { businessContent: v })" />
            <span v-else>{{ row.businessContent }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { counterAccount: v })" />
            <span v-else>{{ row.counterAccount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.rowId, { debitAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.rowId, { creditAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="56" align="center">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" size="small" link @click="uploadOcr(row)">OCR</el-button>
            <span v-else>{{ row.attachment || '—' }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else-if="vc.activeTab.value === 'check'">
        <el-table-column label="凭证号" prop="voucherNo" width="100" />
        <el-table-column label="支持性文件" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supportingDocDesc" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { supportingDocDesc: v })" />
            <span v-else>{{ row.supportingDocDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="完整" width="56" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.check1OriginalComplete"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { check1OriginalComplete: v })" />
            <span v-else>{{ row.check1OriginalComplete ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="授权" width="56" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.check2Authorization"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { check2Authorization: v })" />
            <span v-else>{{ row.check2Authorization ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账务" width="56" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.check3Accounting"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { check3Accounting: v })" />
            <span v-else>{{ row.check3Accounting ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允价值" width="72" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.check4FairValueCorrect"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { check4FairValueCorrect: v })" />
            <span v-else>{{ row.check4FairValueCorrect ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OCI" width="56" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.check5OCICorrect"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { check5OCICorrect: v })" />
            <span v-else>{{ row.check5OCICorrect ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="凭证号" prop="voucherNo" width="100" />
        <el-table-column label="索引" width="88">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexNo" :label="row.indexNo" :prevent-navigate="true" :validate="false" />
            <el-input v-else-if="!isReadonly" :model-value="row.indexNo" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { indexNo: v })" />
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="异常" width="64" align="center">
          <template #default="{ row }">
            <span :class="{ abnormal: row.isAbnormal }">{{ row.isAbnormal ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险" width="88">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.riskLevel" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { riskLevel: v })">
              <el-option v-for="o in vc.riskLevelOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ row.riskLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.abnormalDesc" size="small" type="textarea" :rows="1"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { abnormalDesc: v })" />
            <span v-else>{{ row.abnormalDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <el-card v-if="vc.activeTab.value === 'conclusion'" shadow="never" class="conclusion-card" data-testid="g8-voucher-conclusion">
      <template #header>
        <div class="conclusion-head">
          <span>凭证检查结论</span>
          <el-button size="small" :loading="vc.aiLoading.value" :disabled="isReadonly"
            data-testid="g8-voucher-ai-btn" @click="vc.generateAiConclusion()">🤖 AI</el-button>
        </div>
      </template>
      <el-input :model-value="vc.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" @update:model-value="vc.updateConclusion" />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header>审计说明</template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：凭证抽样方法、样本量、逐笔核对结果及发现的异常事项。" />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header>审计结论</template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写审计结论：凭证检查是否发现异常，交易真实性、完整性与计量准确性是否得到验证。" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, toRef, h, onMounted, onBeforeUnmount } from 'vue'
import type { Column } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G8ImportExportDropdown from '../G8ImportExportDropdown.vue'
import { useG8VoucherCheck, type G8VoucherRow } from '../../composables/useG8VoucherCheck'
import { calcSubtotal, parseNum } from '../../composables/useG8FormulaEngine'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import type { GCycleCutoffFilledDetail } from '../../composables/gCycleCutoffFill'
import { GCYCLE_CUTOFF_EVENT } from '../../composables/gCycleCutoffFill'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const tabOptions = [
  { label: '凭证基础', value: 'basic' },
  { label: '核对内容', value: 'check' },
  { label: '结论', value: 'conclusion' },
]

const vc = useG8VoucherCheck({
  wpId: toRef(props, 'wpId'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const AUDIT_NOTE_KEY = 'G8-6-audit-note'
const AUDIT_CONCLUSION_KEY = 'G8-6-audit-conclusion'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(AUDIT_CONCLUSION_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_KEY, { conclusion: null, remark: v })
})

const debitTotal = computed(() => calcSubtotal(vc.rows.value.map((r) => r.debitAmount)))
const creditTotal = computed(() => calcSubtotal(vc.rows.value.map((r) => r.creditAmount)))
const tableWidth = 1000

const virtualColumns = computed<Column<any>[]>(() => {
  if (vc.activeTab.value === 'basic') {
    return [
      { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
      { key: 'voucherNo', title: '凭证号', dataKey: 'voucherNo', width: 100 },
      { key: 'businessContent', title: '业务内容', dataKey: 'businessContent', width: 200 },
      { key: 'debitAmount', title: '借方', dataKey: 'debitAmount', width: 100, align: 'right',
        cellRenderer: ({ rowData }: { rowData: G8VoucherRow }) => h('span', fmt(rowData.debitAmount)) },
      { key: 'creditAmount', title: '贷方', dataKey: 'creditAmount', width: 100, align: 'right',
        cellRenderer: ({ rowData }: { rowData: G8VoucherRow }) => h('span', fmt(rowData.creditAmount)) },
    ]
  }
  if (vc.activeTab.value === 'check') {
    return [
      { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
      { key: 'voucherNo', title: '凭证号', dataKey: 'voucherNo', width: 100 },
      { key: 'supportingDocDesc', title: '支持性文件', dataKey: 'supportingDocDesc', width: 180 },
      { key: 'check5OCICorrect', title: 'OCI', dataKey: 'check5OCICorrect', width: 72, align: 'center',
        cellRenderer: ({ rowData }: { rowData: G8VoucherRow }) => h('span', rowData.check5OCICorrect ? '✓' : '✗') },
      { key: 'isAbnormal', title: '异常', dataKey: 'isAbnormal', width: 72, align: 'center',
        cellRenderer: ({ rowData }: { rowData: G8VoucherRow }) => h('span', rowData.isAbnormal ? '是' : '否') },
    ]
  }
  return [
    { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
    { key: 'voucherNo', title: '凭证号', dataKey: 'voucherNo', width: 100 },
    { key: 'indexNo', title: '索引', dataKey: 'indexNo', width: 88 },
    { key: 'isAbnormal', title: '异常', dataKey: 'isAbnormal', width: 72, align: 'center',
      cellRenderer: ({ rowData }: { rowData: G8VoucherRow }) => h('span', rowData.isAbnormal ? '是' : '否') },
    { key: 'riskLevel', title: '风险', dataKey: 'riskLevel', width: 80 },
    { key: 'abnormalDesc', title: '异常说明', dataKey: 'abnormalDesc', width: 200 },
  ]
})

function onImported() {
  emit('imported')
  vc.reloadFromStore()
}

function onRowChange(row: G8VoucherRow | undefined) {
  if (!row) return
  const idx = vc.rows.value.findIndex((r) => r.rowId === row.rowId)
  if (idx >= 0) vc.setActiveRowIndex(idx)
}

function rowClassName({ row }: { row: G8VoucherRow }) {
  return row.isAbnormal ? 'abnormal-row' : ''
}

function onSampleFilled(payload: { samples: Array<{ summary?: string; amount?: number; voucherDate?: string; voucherNo?: string }> }) {
  for (const s of payload.samples ?? []) {
    vc.mergeSample({
      businessContent: s.summary,
      debitAmount: parseNum(s.amount),
      voucherDate: s.voucherDate,
      voucherNo: s.voucherNo,
      source: '抽凭',
    })
  }
}

async function uploadOcr(row: G8VoucherRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const formData = new FormData()
      formData.append('file', file)
      let res
      try {
        res = await http.post(`/api/workpapers/${props.wpId}/g8/contract-ocr`, formData)
      } catch {
        res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData)
      }
      const data = res.data?.data ?? res.data ?? {}
      const summary = data.summary ?? data.extracted_fields?.businessContent ?? ''
      if (!summary) { ElMessage.warning('OCR 未识别到内容'); return }
      await ElMessageBox.confirm(`识别结果：${summary}，是否填入业务内容？`, 'OCR 确认', { type: 'info' })
      vc.updateRow(row.rowId, { businessContent: summary, attachment: file.name })
    } catch (e: any) {
      if (e !== 'cancel') ElMessage.warning('OCR 识别失败')
    }
  }
  input.click()
}

function fmt(v: number) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  vc.applyCutoffResults(detail.samples, detail.fillMode)
}

onMounted(() => {
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g8, onCutoffFilled as EventListener)
})
onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g8, onCutoffFilled as EventListener)
})
</script>

<style scoped>
.g8-voucher { font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 10px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 10px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }
.section-head { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.summary-bar { padding: 8px 12px; background: #f5f7fa; font-size: 12px; margin-bottom: 8px; border-radius: 4px; }
.summary-error { background: #fef0f0; color: #f56c6c; }
.segment-tabs { margin-bottom: 8px; }
.virtual-table { margin-top: 8px; }
:deep(.abnormal-row) { background-color: #fdf6ec !important; }
.abnormal { color: #f56c6c; font-weight: 600; }
.conclusion-card { margin-top: 12px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; }
</style>
