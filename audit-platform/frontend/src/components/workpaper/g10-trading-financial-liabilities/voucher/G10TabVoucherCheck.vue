<template>
  <div class="g10-voucher-check" data-testid="g10-voucher-check">
    <div class="section-head">
      <h3 class="sheet-title">G10-7 交易性金融负债凭证检查表</h3>
      <div class="head-actions">
        <GtVoucherSamplingEngine :project-id="projectId" :account-codes="[G10_ACCOUNT_CODE]" dialog-mode @filled="onSampleFilled" />
        <G10ImportExportDropdown :wp-id="wpId" sheet="G10-7" @imported="onImported" />
        <GtReviewTrigger section-id="G10-7-voucher" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="vc.addRow()">+ 新增</el-button>
      </div>
    </div>
    <div class="summary-bar" :class="{ 'summary-error': !vc.isBalanced.value }">
      借方 {{ fmt(vc.debitTotal.value) }} · 贷方 {{ fmt(vc.creditTotal.value) }} · 差额 {{ fmt(vc.balanceDiff.value) }} · 异常 {{ vc.abnormalCount.value }} 条
    </div>
    <div class="segment-tabs">
      <el-segmented v-model="vc.activeTab.value" :options="tabOptions" size="small" />
    </div>

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
      data-testid="g10-voucher-virtual-table"
    />

    <el-table v-else :data="vc.rows.value" border stripe style="width:100%;font-size:13px" max-height="480"
      highlight-current-row :row-class-name="({ row }) => row.isAbnormal ? 'abnormal-row' : ''"
      @current-change="onRowChange">
      <el-table-column prop="seq" label="序号" width="52" align="center" fixed />
      <template v-if="vc.activeTab.value === 'basic'">
        <el-table-column label="日期" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherDate" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { voucherDate: v })" />
            <span v-else>{{ row.voucherDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { voucherNo: v })" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { businessContent: v })" />
            <span v-else>{{ row.businessContent }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { counterAccount: v })" />
            <span v-else>{{ row.counterAccount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.id, { debitAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.id, { creditAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else-if="vc.activeTab.value === 'check'">
        <el-table-column label="📎" width="52">
          <template #default="{ row }">
            <el-button size="small" link :disabled="isReadonly" @click="uploadOcr(row)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column label="支持性文件" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supportingDocDesc" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { supportingDocDesc: v })" />
            <span v-else>{{ row.supportingDocDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="(label, idx) in checkLabels" :key="idx" :label="label" width="72" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="checkValue(row, idx)"
              @change="(v: boolean) => setCheck(row, idx, v)" />
            <span v-else>{{ checkValue(row, idx) ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="索引号" width="88">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexNo" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { indexNo: v })" />
            <GtIndexChip v-else-if="row.indexNo" :value="row.indexNo" />
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="88">
          <template #default="{ row }">
            <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">{{ row.isAbnormal ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.abnormalDesc" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { abnormalDesc: v })" />
            <span v-else>{{ row.abnormalDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.riskLevel" size="small"
              @change="(v: string) => vc.updateRow(row.id, { riskLevel: v as any })">
              <el-option v-for="o in G10_RISK_LEVEL_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ row.riskLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>
      <el-table-column label="操作" width="64" v-if="!isReadonly" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="vc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="vc.activeTab.value === 'conclusion'" class="conclusion-panel" data-testid="g10-voucher-conclusion">
      <div class="conclusion-head">
        <span>抽查结论</span>
        <el-button size="small" :loading="vc.aiLoading.value" :disabled="isReadonly" @click="vc.generateAiConclusion()">🤖 AI</el-button>
      </div>
      <el-input :model-value="vc.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="汇总凭证抽查结论、异常事项及后续程序" :disabled="isReadonly" @update:model-value="vc.updateConclusion" />
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>可用抽凭引擎按科目 2101 抽取样本自动填入；「核对内容」区段逐笔核对原始凭证完整性、授权、账务处理及公允价值计量是否正确。</p>
        <p>借贷合计不平衡或存在异常凭证时汇总栏标红；异常凭证须填写异常说明并评定风险等级。</p>
        <p>抽查结论应覆盖样本范围、发现的异常事项及拟采取的后续审计程序。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, h } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { Column } from 'element-plus'
import http from '@/utils/http'
import { useG10VoucherCheck, type G10VoucherCheckRow } from '../../composables/useG10VoucherCheck'
import { G10_ACCOUNT_CODE, G10_RISK_LEVEL_OPTIONS } from '../../composables/g10Constants'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const vc = useG10VoucherCheck({
  wpId: toRef(props, 'wpId'),
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const tabOptions = [
  { label: '凭证基础', value: 'basic' },
  { label: '核对内容', value: 'check' },
  { label: '结论', value: 'conclusion' },
]
const checkLabels = ['完整', '授权', '账务正确', '公允价值正确']
const tableWidth = 960

const virtualColumns = computed<Column<any>[]>(() => [
  { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
  { key: 'voucherNo', title: '凭证编号', dataKey: 'voucherNo', width: 100 },
  { key: 'businessContent', title: '业务内容', dataKey: 'businessContent', width: 180 },
  { key: 'creditAmount', title: '贷方', dataKey: 'creditAmount', width: 100, align: 'right',
    cellRenderer: ({ rowData }: { rowData: G10VoucherCheckRow }) => h('span', fmt(rowData.creditAmount)) },
  { key: 'isAbnormal', title: '异常', dataKey: 'isAbnormal', width: 72, align: 'center',
    cellRenderer: ({ rowData }: { rowData: G10VoucherCheckRow }) => h('span', rowData.isAbnormal ? '是' : '否') },
])

function checkValue(row: G10VoucherCheckRow, idx: number): boolean {
  const keys = ['check1OriginalComplete', 'check2Authorization', 'check3Accounting', 'check4FairValueCorrect'] as const
  return row[keys[idx]]
}

function setCheck(row: G10VoucherCheckRow, idx: number, v: boolean) {
  const keys = ['check1OriginalComplete', 'check2Authorization', 'check3Accounting', 'check4FairValueCorrect'] as const
  vc.updateRow(row.id, { [keys[idx]]: v })
}

async function onImported() {
  emit('imported')
  vc.reloadFromStore()
}

function onRowChange(row: G10VoucherCheckRow | undefined) {
  if (!row) return
  const idx = vc.rows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) vc.setActiveRowIndex(idx)
}

function onSampleFilled(payload: { samples: Array<{ summary?: string; amount?: number; voucherDate?: string; voucherNo?: string }> }) {
  for (const s of payload.samples ?? []) {
    vc.mergeSample({
      businessContent: s.summary,
      creditAmount: s.amount,
      voucherDate: s.voucherDate,
      voucherNo: s.voucherNo,
      source: '抽凭',
    })
  }
}

async function uploadOcr(row: G10VoucherCheckRow) {
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
        res = await http.post(`/api/workpapers/${props.wpId}/g10/contract-ocr`, formData)
      } catch {
        res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData)
      }
      const data = res.data?.data ?? res.data ?? {}
      const summary = data.summary ?? data.extracted_fields?.businessContent ?? ''
      if (!summary) { ElMessage.warning('OCR 未识别到内容'); return }
      await ElMessageBox.confirm(`识别结果：${summary}，是否填入业务内容？`, 'OCR 确认', { type: 'info' })
      vc.updateRow(row.id, { businessContent: summary, attachment: file.name })
    } catch (e: any) {
      if (e !== 'cancel') ElMessage.warning('OCR 识别失败')
    }
  }
  input.click()
}

function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.g10-voucher-check { font-size: 13px; }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.summary-bar { padding: 8px 12px; background: #f5f7fa; font-size: 12px; margin-bottom: 8px; border-radius: 4px; }
.summary-error { background: #fef0f0; color: #f56c6c; }
.segment-tabs { margin-bottom: 8px; }
:deep(.abnormal-row) { background-color: #fdf6ec !important; }
.conclusion-panel { margin-top: 12px; padding: 12px; background: #fafafa; border-radius: 4px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-weight: 600; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
</style>
