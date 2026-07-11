<template>
  <div class="g9-voucher" data-testid="g9-voucher-check">
    <div class="section-head">
      <h3 class="sheet-title">G9-6 凭证检查表</h3>
      <div class="head-actions">
        <GtIndexChip value="wp:G9-6" />
        <el-tag size="small" type="info">共 {{ vc.rows.value.length }} 行</el-tag>
        <G9ImportExportDropdown :wp-id="wpId" sheet="G9-6" @imported="onImported" />
        <GtVoucherSamplingEngine :project-id="projectId" :account-codes="['1504']" dialog-mode @filled="onSampleFilled" />
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="vc.addRow()">+ 新增</el-button>
      </div>
    </div>
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：抽取其他非流动金融资产相关凭证，核对原始单据、授权、账务处理、分类、公允价值与减值，识别异常并评估风险。"
    />

    <div class="summary-bar" :class="{ 'summary-error': !vc.balanceOk.value }">
      借方合计 {{ fmt(debitTotal) }} | 贷方合计 {{ fmt(creditTotal) }} | 差额 {{ fmt(vc.balanceDiff.value) }}
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
      data-testid="g9-voucher-virtual-table"
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
            <span v-else>{{ row.attachmentRef || '—' }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else-if="vc.activeTab.value === 'check'">
        <el-table-column label="凭证号" prop="voucherNo" width="100" />
        <el-table-column label="支持性文件" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supportDoc" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { supportDoc: v })" />
            <span v-else>{{ row.supportDoc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原始" width="56" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.checkOriginal"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { checkOriginal: v })" />
            <span v-else>{{ row.checkOriginal ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="授权" width="56" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.checkAuthorized"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { checkAuthorized: v })" />
            <span v-else>{{ row.checkAuthorized ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账务" width="56" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.checkAccounting"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { checkAccounting: v })" />
            <span v-else>{{ row.checkAccounting ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="56" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.checkClassification"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { checkClassification: v })" />
            <span v-else>{{ row.checkClassification ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允价值" width="72" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.checkFairValue"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { checkFairValue: v })" />
            <span v-else>{{ row.checkFairValue ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值" width="56" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.checkImpairment"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { checkImpairment: v })" />
            <span v-else>{{ row.checkImpairment ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="凭证号" prop="voucherNo" width="100" />
        <el-table-column label="索引" width="88">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :label="row.indexRef" :prevent-navigate="true" :validate="false" />
            <el-input v-else-if="!isReadonly" :model-value="row.indexRef" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { indexRef: v })" />
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
        <el-table-column label="处理建议" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.suggestion" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { suggestion: v })" />
            <span v-else>{{ row.suggestion }}</span>
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

    <el-card v-if="vc.activeTab.value === 'conclusion'" shadow="never" class="conclusion-card" data-testid="g9-voucher-conclusion">
      <template #header>
        <div class="conclusion-head">
          <span>凭证检查结论</span>
          <el-button size="small" :loading="vc.aiLoading.value" :disabled="isReadonly"
            data-testid="g9-voucher-ai-btn" @click="vc.generateAiConclusion()">🤖 AI</el-button>
        </div>
      </template>
      <el-input :model-value="vc.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" @update:model-value="vc.updateConclusion" />
    </el-card>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>按 CAS 1301 审计抽样：通过抽凭引擎按科目 1504 选取样本，或按截止基准日窗口一键取数（跨期自动标注）。</p>
        <p>核对内容任一项为「否」则该凭证自动标记为异常；借贷合计差额应为 0。异常凭证须填写风险等级、异常说明与处理建议。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, h, onMounted, onBeforeUnmount } from 'vue'
import type { Column } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import { useG9VoucherCheck, type G9VoucherRow } from '../../composables/useG9VoucherCheck'
import { calcSubtotal, parseNum } from '../../composables/useG9FormulaEngine'
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

const vc = useG9VoucherCheck({
  wpId: toRef(props, 'wpId'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
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
        cellRenderer: ({ rowData }: { rowData: G9VoucherRow }) => h('span', fmt(rowData.debitAmount)) },
      { key: 'creditAmount', title: '贷方', dataKey: 'creditAmount', width: 100, align: 'right',
        cellRenderer: ({ rowData }: { rowData: G9VoucherRow }) => h('span', fmt(rowData.creditAmount)) },
    ]
  }
  if (vc.activeTab.value === 'check') {
    return [
      { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
      { key: 'voucherNo', title: '凭证号', dataKey: 'voucherNo', width: 100 },
      { key: 'supportDoc', title: '支持性文件', dataKey: 'supportDoc', width: 180 },
      { key: 'checkFairValue', title: '公允价值', dataKey: 'checkFairValue', width: 80, align: 'center',
        cellRenderer: ({ rowData }: { rowData: G9VoucherRow }) => h('span', rowData.checkFairValue ? '✓' : '✗') },
      { key: 'isAbnormal', title: '异常', dataKey: 'isAbnormal', width: 72, align: 'center',
        cellRenderer: ({ rowData }: { rowData: G9VoucherRow }) => h('span', rowData.isAbnormal ? '是' : '否') },
    ]
  }
  return [
    { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
    { key: 'voucherNo', title: '凭证号', dataKey: 'voucherNo', width: 100 },
    { key: 'indexRef', title: '索引', dataKey: 'indexRef', width: 88 },
    { key: 'isAbnormal', title: '异常', dataKey: 'isAbnormal', width: 72, align: 'center',
      cellRenderer: ({ rowData }: { rowData: G9VoucherRow }) => h('span', rowData.isAbnormal ? '是' : '否') },
    { key: 'riskLevel', title: '风险', dataKey: 'riskLevel', width: 80 },
    { key: 'abnormalDesc', title: '异常说明', dataKey: 'abnormalDesc', width: 200 },
  ]
})

function onImported() {
  emit('imported')
  vc.reloadFromStore()
}

function onRowChange(row: G9VoucherRow | undefined) {
  if (!row) return
  const idx = vc.rows.value.findIndex((r) => r.rowId === row.rowId)
  if (idx >= 0) vc.setActiveRowIndex(idx)
}

function rowClassName({ row }: { row: G9VoucherRow }) {
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

async function uploadOcr(row: G9VoucherRow) {
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
        res = await http.post(`/api/workpapers/${props.wpId}/g9/contract-ocr`, formData)
      } catch {
        res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData)
      }
      const data = res.data?.data ?? res.data ?? {}
      const summary = data.summary ?? data.extracted_fields?.businessContent ?? ''
      if (!summary) { ElMessage.warning('OCR 未识别到内容'); return }
      await ElMessageBox.confirm(`识别结果：${summary}，是否填入业务内容？`, 'OCR 确认', { type: 'info' })
      vc.updateRow(row.rowId, { businessContent: summary, attachmentRef: file.name })
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
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g9, onCutoffFilled as EventListener)
})
onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g9, onCutoffFilled as EventListener)
})
</script>

<style scoped>
.g9-voucher { font-size: 13px; }
.section-head { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.audit-objective { margin-bottom: 8px; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.summary-bar { padding: 8px 12px; background: #f5f7fa; font-size: 12px; margin-bottom: 8px; border-radius: 4px; }
.summary-error { background: #fef0f0; color: #f56c6c; }
.segment-tabs { margin-bottom: 8px; }
.virtual-table { margin-top: 8px; }
:deep(.abnormal-row) { background-color: #fdf6ec !important; }
.abnormal { color: #f56c6c; font-weight: 600; }
.conclusion-card { margin-top: 12px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; }
</style>
