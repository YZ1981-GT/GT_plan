<template>
  <div class="g5-voucher-check">
    <div class="section-head">
      <h3 class="sheet-title">G5-12 凭证检查表</h3>
      <div class="head-actions">
        <GtVoucherSamplingEngine :project-id="props.projectId" :account-codes="[G5_ACCOUNT_CODE]" dialog-mode @filled="onSampleFilled" />
        <G5ImportExportDropdown :wp-id="props.wpId" sheet="G5-12" @imported="onImported" />
        <el-button size="small" type="primary" plain @click="vc.addRow()" :disabled="props.readonly">+ 新增</el-button>
      </div>
    </div>

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
  </div>
</template>

<script setup lang="ts">
import { useG5VoucherCheck } from '../../composables/useG5VoucherCheck'
import type { VoucherCheckRow } from '../../composables/useG5VoucherCheck'
import { G5_ACCOUNT_CODE } from '../../composables/g5Constants'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const vc = useG5VoucherCheck()
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
function uploadOcr(_row: VoucherCheckRow) { /* OCR 集成占位 */ }
function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.g5-voucher-check { font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.summary-bar { padding: 8px 12px; background: #f5f7fa; font-size: 12px; margin-bottom: 8px; border-radius: 4px; }
.summary-error { background: #fef0f0; color: #f56c6c; }
.segment-tabs { margin-bottom: 8px; }
.attach-tag { font-size: 11px; color: #909399; }
</style>
