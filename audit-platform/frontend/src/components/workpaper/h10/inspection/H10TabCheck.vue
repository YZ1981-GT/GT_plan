<template>
  <div class="h10-check" data-testid="h10-check">
    <div class="section-head">
      <h3 class="sheet-title">H10-4 资产处置检查表</h3>
      <div class="head-actions">
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly || !wpId || !projectId"
          data-testid="h10-open-sampling"
          @click="showSamplingDialog = true"
        >
          抽凭引擎(6115)
        </el-button>
        <GtReviewTrigger section-id="H10-4-check" />
      </div>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 逐项检查资产处置的审批程序、评估依据、定价合理性、税务处理、会计时点、收入确认、费用分摊及关联方情况。</p>
        <p>2. 关注处置时点是否恰当（风险报酬转移），处置定价是否公允，关联方处置是否履行审批并按公允价格执行（CAS 36）。</p>
        <p>3. 抽凭核对：①原始凭证齐全 ②记账凭证与原始凭证相符 ③账务处理正确 ④记录于恰当期间 ⑤处置审批及定价公允（含关联方）。</p>
        <p>4. 检查比例偏低应扩大样本或说明原因；不合规项目评估错报并视情况编制 H10-3 调整。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：检查资产处置的审批、评估、定价、税务与会计时点合规性，识别异常或关联方处置事项，为处置损益的合规性提供审计证据。" />

    <div class="sample-reason" data-testid="h10-check-sample-reason">
      <span class="sample-label">样本选取原因：</span>
      <el-checkbox-group v-model="sampleReasons" :disabled="isReadonly" size="small" @change="saveSampleReasons">
        <el-checkbox label="large">大额</el-checkbox>
        <el-checkbox label="related">关联方</el-checkbox>
        <el-checkbox label="frequent">大额交易频繁</el-checkbox>
        <el-checkbox label="abnormal">异常</el-checkbox>
        <el-checkbox label="other">其他</el-checkbox>
      </el-checkbox-group>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" :type="check.sampleRatioLow.value ? 'warning' : 'success'" data-testid="h10-sample-ratio">
          抽查比例 {{ (check.sampleRatio.value * 100).toFixed(0) }}%
          <template v-if="check.detailPopulation.value">
            （{{ Math.max(check.rows.value.filter(r => !!r.voucherRef).length, check.sampledVoucherCount.value) }}/{{ check.detailPopulation.value }}）
          </template>
        </el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H10-4" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ check.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-alert
      v-if="check.sampleRatioLow.value"
      type="warning"
      :closable="false"
      class="summary-alert"
      data-testid="h10-sample-ratio-warn"
      :title="`抽查比例低于建议门槛 ${(H10_CHECK_MIN_SAMPLE_RATIO * 100).toFixed(0)}%，请扩大样本或在审计说明中解释原因。`"
    />

    <el-alert v-if="check.nonCompliantSummary.value" type="warning" :closable="false" class="summary-alert">
      {{ check.nonCompliantSummary.value }}
    </el-alert>
    <el-table :data="check.rows.value" border size="small" style="font-size:13px" max-height="560">
      <el-table-column prop="seq" label="序号" width="48" align="center" fixed />
      <el-table-column label="资产名称" min-width="120" fixed>
        <template #default="{ row }">
          <span>{{ row.assetName || `行${row.seq}` }}</span>
        </template>
      </el-table-column>
      <el-table-column v-for="col in checkColumns" :key="col.field" :label="col.label" width="96" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row[col.field]" size="small"
            @change="(v: string) => check.updateRow(row.id, { [col.field]: v })">
            <el-option v-for="o in check.complianceOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
          <el-tag v-else size="small" :type="tagType(row[col.field])">{{ labelOf(row[col.field]) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="合规" width="72" align="center" fixed="right">
        <template #default="{ row }">
          <el-tag :type="check.rowIsCompliant(row) ? 'success' : 'danger'" size="small">
            {{ check.rowIsCompliant(row) ? '合规' : '不合规' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="凭证索引" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherRef" size="small"
            @update:model-value="(v: string) => check.updateRow(row.id, { voucherRef: v })" />
          <GtIndexChip v-else-if="row.voucherRef" :value="row.voucherRef" />
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
            @update:model-value="(v: string) => check.updateRow(row.id, { remark: v })" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="compliance-bar">合规率 {{ (check.complianceRate.value * 100).toFixed(0) }}%</div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述检查范围与方法、合规性检查结果、不合规项目的原因分析及错报影响评估。"
        @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项调整外，其余未见异常。C、存在重大未调整事项或范围受限，不可确认。"
        @change="saveAuditConclusion" />
    </el-card>

    <el-dialog
      v-model="showSamplingDialog"
      title="抽凭引擎 — 资产处置损益(6115)"
      width="90%"
      top="5vh"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && wpId && projectId"
        account-code="6115"
        phase="final"
        default-method="mus"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="samplingYear"
        @filled="onSamplesFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, onMounted, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { useH10Check, H10_CHECK_MIN_SAMPLE_RATIO, type H10CheckRow } from '../../composables/useH10Check'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  year?: number
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const check = useH10Check({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const NOTE_KEY = 'H10-4-check-audit-note'
const CONCLUSION_KEY = 'H10-4-check-audit-conclusion'
const SAMPLE_KEY = 'H10-4-check-sample-reasons'
const auditNote = ref('')
const auditConclusion = ref('')
const sampleReasons = ref<string[]>([])
const showSamplingDialog = ref(false)
const samplingYear = computed(() => props.year ?? new Date().getFullYear())

function saveSampleReasons(val: string[]): void {
  if (props.isReadonly) return
  sampleReasons.value = val
  const remark = JSON.stringify(val)
  props.allResponses.set(SAMPLE_KEY, { item_id: SAMPLE_KEY, conclusion: null, remark })
  props.debouncedSave(SAMPLE_KEY, { conclusion: null, remark })
}

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

function onSamplesFilled(payload: { samples?: any[] } | any[]): void {
  showSamplingDialog.value = false
  const samples = Array.isArray(payload) ? payload : (payload?.samples ?? [])
  if (!Array.isArray(samples) || !samples.length) return
  const n = check.fillFromSampledVouchers(samples)
  ElMessage.success(`已填入 ${n} 笔抽凭样本`)
  if (check.sampleRatioLow.value) {
    ElMessage.warning(`抽查比例 ${(check.sampleRatio.value * 100).toFixed(0)}% 仍低于建议门槛`)
  }
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
  const s = props.allResponses.get(SAMPLE_KEY)
  if (s?.remark) {
    try {
      const parsed = JSON.parse(s.remark)
      if (Array.isArray(parsed)) sampleReasons.value = parsed
    } catch { /* ignore */ }
  }
})

const checkColumns: Array<{ field: keyof H10CheckRow; label: string }> = [
  { field: 'approvalProcess', label: '审批程序' },
  { field: 'appraisalBasis', label: '评估依据' },
  { field: 'pricingReasonableness', label: '定价合理' },
  { field: 'taxTreatment', label: '税务处理' },
  { field: 'accountingTiming', label: '会计时点' },
  { field: 'revenueRecognition', label: '收入确认' },
  { field: 'expenseAllocation', label: '费用分摊' },
  { field: 'relatedParty', label: '关联方' },
  { field: 'auditConclusion', label: '审计结论' },
]

function labelOf(v: string) {
  return check.complianceOptions.find((o) => o.value === v)?.label ?? (v || '-')
}

function tagType(v: string) {
  if (v === 'compliant') return 'success'
  if (v === 'non_compliant') return 'danger'
  return 'info'
}
</script>

<style scoped>
.h10-check { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; }
.summary-alert { margin-bottom: 8px; }
.compliance-bar { margin-top: 8px; font-size: 12px; color: #606266; }
.guidance-details { margin-bottom: 8px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 8px; }
.sample-reason { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 12px; }
.sample-label { color: #606266; white-space: nowrap; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 12px; }
</style>
