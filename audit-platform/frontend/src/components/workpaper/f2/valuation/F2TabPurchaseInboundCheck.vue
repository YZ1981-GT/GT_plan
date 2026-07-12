<template>
  <div class="f2-val-sheet">
    <header class="sheet-header">
      <div><h3>{{ ic.title }}</h3><span class="code">{{ ic.sheetCode }}</span></div>
      <span :class="['coverage', { warn: ic.isCoverageLow.value }]">
        覆盖率 {{ ic.coverageRatio.value.toFixed(1) }}%
      </span>
    </header>

    <div class="meta-bar">
      <span>{{ ic.partyLabel }}检查</span>
      <span>账面总额
        <el-input-number :model-value="ic.bookTotal.value" size="small" :controls="false" :disabled="isReadonly"
          @change="(v: number) => ic.updateBookTotal(v ?? 0)" />
      </span>
      <span>已查 {{ ic.checkedTotal.value.toLocaleString() }}</span>
      <span v-if="samplingInfo" class="sampling-info">
        抽样方法: {{ samplingInfo.method }} | 样本量: {{ samplingInfo.count }}
      </span>
      <GtVoucherSamplingEngine
        v-if="!isReadonly && wpId && projectId"
        :project-id="projectId"
        :account-codes="inventoryAccountCodes"
        :phase="'final'"
        dialog-mode
        @filled="handleSamplingFilled"
      />
      <el-button size="small" type="primary" :disabled="isReadonly" @click="ic.addRow()">+ 新增</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-val"
        sheet="F2-33"
        :disabled="isReadonly"
        ai-section="inspection-conclusion"
        :existing-content="ic.auditNote.value"
        :related-context="{ coverageRatio: ic.coverageRatio.value }"
        ai-title="AI 生成 · 采购入库检查结论"
        review-section="F2-33-conclusion"
        @ai-filled="(t: string) => { ic.auditNote.value = t }"
      />
    </div>

    <el-table :data="ic.rows.value" border size="small" max-height="440">
      <el-table-column prop="seq" label="序号" width="50" />
      <el-table-column :label="ic.partyLabel" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.party" size="small"
            @change="(v: string) => ic.updateRow(row.id, { party: v })" />
          <span v-else>{{ row.party }}</span>
        </template>
      </el-table-column>
      <el-table-column label="单号" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.docNo" size="small"
            @change="(v: string) => ic.updateRow(row.id, { docNo: v })" />
          <span v-else>{{ row.docNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="品名" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
            @change="(v: string) => ic.updateRow(row.id, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.amount" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => ic.updateRow(row.id, { amount: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="100">
        <template #default="{ row }">
          <el-tooltip v-if="row.sampleSource" :content="row.sampleSource" placement="top">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small"
              @change="(v: string) => ic.updateRow(row.id, { voucherNo: v })" />
            <span v-else>{{ row.voucherNo }}</span>
          </el-tooltip>
          <template v-else>
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small"
              @change="(v: string) => ic.updateRow(row.id, { voucherNo: v })" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
            @change="(v: string) => ic.updateRow(row.id, { remark: v })" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="wpId && !isReadonly" label="📎" width="45" align="center">
        <template #default="{ row }">
          <el-upload
            :show-file-list="false"
            :auto-upload="false"
            accept=".pdf,.png,.jpg,.jpeg"
            :disabled="ocrLoadingId === row.id"
            @change="(uploadFile: any) => handleOcrUpload(row.id, uploadFile?.raw)"
          >
            <el-button link size="small" :loading="ocrLoadingId === row.id">📎</el-button>
          </el-upload>
        </template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="ic.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <footer class="footer">
      <h4>检查结论</h4>
      <el-input v-model="ic.auditNote.value" type="textarea" :rows="2" :disabled="isReadonly" />
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, type Ref } from 'vue'
import { useF2PurchaseInboundCheck } from '../../composables/useF2InspectionCheck'
import { useF2PurchaseOcr } from '../../composables/useF2PurchaseOcr'
import { F2_INVENTORY_ACCOUNT_CODES } from '../../composables/useF2InspectionCheckFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import type { SampledVoucher, FillMode, SamplingMethod } from '../../composables/useSamplingAlgorithms'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  auditYear?: number
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const ic = useF2PurchaseInboundCheck({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const { ocrLoadingId, uploadAndMerge } = useF2PurchaseOcr(
  toRef(() => props.wpId || '') as Ref<string>,
)

/** 采购入库检查科目范围（保留原 F2_INVENTORY_ACCOUNT_CODES 值 1401~1411，拆为多科目数组） */
const inventoryAccountCodes = F2_INVENTORY_ACCOUNT_CODES.split(',')

/** 抽样参数区展示信息（引擎返回后自动更新） */
const samplingInfo = ref<{ method: string; count: number } | null>(null)

/** 抽样方法中文映射 */
const METHOD_LABELS: Record<string, string> = {
  random: '随机抽样',
  stratified: '分层抽样',
  specific_item: '特定项目',
  systematic: '系统抽样',
  mus: '货币单位抽样',
}

function handleSamplingFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode; method?: SamplingMethod }) {
  ic.fillFromSampling(payload.samples, payload.fillMode, payload.method)
  // 自动更新抽样参数区
  samplingInfo.value = {
    method: METHOD_LABELS[payload.method || 'random'] || payload.method || '随机抽样',
    count: payload.samples.length,
  }
}

function handleOcrUpload(rowId: string, file?: File) {
  if (!file || !props.wpId) return
  void uploadAndMerge(rowId, file, (id, patch) => ic.updateRow(id, patch))
}
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.meta-bar { display: flex; gap: 16px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; font-size: var(--wp-font-size, 13px); }
.coverage { font-size: var(--wp-font-size, 13px); font-weight: 600; }
.coverage.warn { color: #e6a23c; }
.sampling-info { font-size: 12px; color: var(--el-text-color-secondary); background: var(--el-fill-color-light); padding: 2px 8px; border-radius: 4px; }
</style>
