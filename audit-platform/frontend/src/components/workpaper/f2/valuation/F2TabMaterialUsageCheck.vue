<template>
  <div class="f2-val-sheet">
    <header class="sheet-header">
      <div><h3>{{ ic.title }}</h3><span class="code">{{ ic.sheetCode }}</span></div>
      <span :class="['coverage', { warn: ic.isCoverageLow.value }]">覆盖率 {{ ic.coverageRatio.value.toFixed(1) }}%</span>
    </header>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 抽取样本核查材料领用业务，逐笔核对领用部门、单号、品名、金额与领用凭证（CAS 1 号存货）。</p>
        <p>2. 覆盖率＝已查金额 ÷ 账面总额，覆盖率偏低（＜50%）自动橙色提示，应扩大样本或说明抽样理由。</p>
        <p>3. 关注材料领用是否与生产计划、BOM 耗用匹配，是否存在超额领用、以领代耗调节成本或跨期领用。</p>
        <p>4. 可用抽凭引擎按存货科目抽取领用凭证，📎附件 OCR 可自动识别单据信息辅助核对。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：验证材料领用的真实性、完整性与计价准确性，确认领用记录与生产耗用、成本归集勾稽一致，防止材料成本虚增或跨期。"
    />

    <!-- 工具栏（索引联动 + 计数） -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" /></span>
        <el-tag size="small" type="info">共 {{ ic.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <div class="meta-bar">
      <span>账面总额<el-input-number :model-value="ic.bookTotal.value" size="small" :controls="false" :disabled="isReadonly" @change="(v: number) => ic.updateBookTotal(v ?? 0)" /></span>
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
        sheet="F2-34"
        :disabled="isReadonly"
        ai-section="inspection-conclusion"
        :existing-content="ic.auditNote.value"
        :related-context="{ coverageRatio: ic.coverageRatio.value }"
        ai-title="AI 生成 · 材料领用检查结论"
        review-section="F2-34-conclusion"
        @ai-filled="(t: string) => { ic.auditNote.value = t }"
      />
    </div>

    <el-table :data="ic.rows.value" border size="small" max-height="440">
      <el-table-column prop="seq" label="序号" width="50" />
      <el-table-column label="领用部门" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.party" size="small" @change="(v: string) => ic.updateRow(row.id, { party: v })" />
          <span v-else>{{ row.party }}</span>
        </template>
      </el-table-column>
      <el-table-column label="单号" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.docNo" size="small" @change="(v: string) => ic.updateRow(row.id, { docNo: v })" />
          <span v-else>{{ row.docNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="品名" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small" @change="(v: string) => ic.updateRow(row.id, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.amount" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v: number) => ic.updateRow(row.id, { amount: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="100">
        <template #default="{ row }">
          <el-tooltip v-if="row.sampleSource" :content="row.sampleSource" placement="top">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => ic.updateRow(row.id, { voucherNo: v })" />
            <span v-else>{{ row.voucherNo }}</span>
          </el-tooltip>
          <template v-else>
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => ic.updateRow(row.id, { voucherNo: v })" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="ic.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">审计说明</span></div>
      </template>
      <el-input v-model="ic.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="填写审计说明：概述材料领用核查程序、样本覆盖率、与生产耗用勾稽情况及核对结果，以及异常事项处理。" />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, toRef } from 'vue'
import { useF2MaterialUsageCheck } from '../../composables/useF2InspectionCheck'
import { F2_INVENTORY_ACCOUNT_CODES } from '../../composables/useF2InspectionCheckFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import type { SampledVoucher, FillMode, SamplingMethod } from '../../composables/useSamplingAlgorithms'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  auditYear?: number
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const ic = useF2MaterialUsageCheck({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── 审计结论（独立持久化，F2 计价组事件；检查说明沿用 composable auditNote） ──
const CONCLUSION_KEY = 'F2-34-audit-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

/** 材料领用检查科目范围（保留原 F2_INVENTORY_ACCOUNT_CODES 值，拆为多科目数组） */
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
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.meta-bar { display: flex; gap: 16px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; font-size: var(--wp-font-size, 13px); }
.coverage { font-weight: 600; }
.coverage.warn { color: #e6a23c; }
.sampling-info { font-size: 12px; color: var(--el-text-color-secondary); background: var(--el-fill-color-light); padding: 2px 8px; border-radius: 4px; }
</style>
