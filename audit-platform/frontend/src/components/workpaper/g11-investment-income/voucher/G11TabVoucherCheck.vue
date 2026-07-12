<template>
  <div class="g11-voucher-check">
    <div class="section-head">
      <h3 class="sheet-title">G11-5 投资收益凭证检查表</h3>
      <div class="head-actions">
        <GtVoucherSamplingEngine :project-id="projectId" :account-codes="[G11_ACCOUNT_CODE]" dialog-mode @filled="onSampleFilled" />
        <G11ImportExportDropdown :wp-id="wpId" sheet="G11-5" @imported="onImported" />
        <GtReviewTrigger section-id="G11-5-voucher" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="vc.addRow()">+ 新增</el-button>
      </div>
    </div>
    <div class="summary-bar" :class="{ 'summary-error': !vc.isBalanced.value }">
      贷方合计 {{ fmt(vc.creditTotal.value) }} · 异常 {{ vc.abnormalCount.value }} 条
    </div>
    <div class="segment-tabs">
      <el-segmented v-model="vc.activeTab.value" :options="tabOptions" size="small" />
    </div>
    <el-table :data="vc.rows.value" border stripe style="width:100%;font-size:13px" max-height="480"
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
        <el-table-column label="贷方金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.id, { creditAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="附件" width="72">
          <template #default="{ row }">
            <el-button size="small" link :disabled="isReadonly" @click="uploadOcr(row)">📎</el-button>
          </template>
        </el-table-column>
      </template>
      <template v-else-if="vc.activeTab.value === 'check'">
        <el-table-column label="支持性文件" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supportingDocDesc" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { supportingDocDesc: v })" />
            <span v-else>{{ row.supportingDocDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="(label, idx) in checkLabels" :key="idx" :label="label" width="72" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="(row as any)[`check${idx + 1}`]"
              @change="(v: boolean) => vc.updateRow(row.id, { [`check${idx + 1}`]: v } as any)" />
            <span v-else>{{ (row as any)[`check${idx + 1}`] ? '✓' : '✗' }}</span>
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
              <el-option label="高" value="high" /><el-option label="中" value="medium" /><el-option label="低" value="low" />
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
    <div v-if="vc.activeTab.value === 'conclusion'" class="conclusion-panel" data-testid="g11-voucher-conclusion">
      <div class="conclusion-head">
        <span>抽查结论</span>
        <el-button size="small" :loading="vc.aiLoading.value" :disabled="isReadonly" @click="vc.generateAiConclusion()">🤖 AI</el-button>
      </div>
      <el-input
        :model-value="vc.conclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="汇总凭证抽查结论、异常事项及后续程序"
        :disabled="isReadonly"
        @update:model-value="vc.updateConclusion"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useG11VoucherCheck, type G11VoucherCheckRow } from '../../composables/useG11VoucherCheck'
import { G11_ACCOUNT_CODE } from '../../composables/g11Constants'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'
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

const vc = useG11VoucherCheck({
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
const checkLabels = ['完整', '授权', '金额正确', '期间恰当', '账务正确']

async function onImported() {
  emit('imported')
  vc.reloadFromStore()
}

function onRowChange(row: G11VoucherCheckRow | undefined) {
  if (!row) return
  const idx = vc.rows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) vc.activeRowIndex.value = idx
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

async function uploadOcr(row: G11VoucherCheckRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(`/api/workpapers/${props.wpId}/g11/contract-ocr`, formData)
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
.g11-voucher-check { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.summary-bar { padding: 8px 12px; background: #f5f7fa; font-size: 12px; margin-bottom: 8px; border-radius: 4px; }
.summary-error { background: #fef0f0; color: #f56c6c; }
.segment-tabs { margin-bottom: 8px; }
:deep(.abnormal-row) { background-color: #fdf6ec !important; }
.conclusion-panel { margin-top: 12px; padding: 12px; background: #fafafa; border-radius: 4px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-weight: 600; }
</style>
