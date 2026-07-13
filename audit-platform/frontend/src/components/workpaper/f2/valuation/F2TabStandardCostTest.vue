<template>
  <!--
    打磨要素说明：本 sheet 复用共享基座 F2ValuationTestSheet.vue 统一渲染以下要素——
    objective-alert（审计目标）、guidance-details（编制提示）、tab-toolbar + GtIndexChip（索引联动）、
    审计说明（-audit-note，本组件持久化）、审计结论。
  -->
  <F2ValuationTestSheet
    title="计价方法测试 — 标准成本差异"
    sheet-code="F2-40"
    :threshold-rate="vt.thresholdRate"
    :display-rows="vt.enrichedRows.value"
    :totals="vt.totals.value"
    :exceed-count="vt.exceedCount.value"
    :sampling-params="vt.samplingParams.value"
    :test-conclusion="vt.testConclusion.value"
    :audit-note="auditNote"
    :wp-id="wpId"
    :project-id="projectId"
    :audit-year="auditYear"
    :is-readonly="isReadonly"
    :segments="segments"
    default-segment="standard"
    objective-text="选取样本存货品种，验证标准成本差异的计算及分配是否合理，确认标准成本法下发出与结存计价的准确性。"
    guidance-text="选取样本存货品种，验证标准成本差异的计算及分配是否合理。关注差异率超过5%的样本。"
    @add-row="vt.addRow()"
    @remove-row="(id: string) => vt.removeRow(id)"
    @update-row="(id: string, patch: any) => vt.updateRow(id, patch)"
    @sampling-filled="handleSamplingFilled"
    @update:test-conclusion="(t: string) => { vt.testConclusion.value = t }"
    @update:audit-note="saveAuditNote"
  >
    <template #columns="{ segment: seg, isReadonly: ro, fmt, fmtRate, isExceed }">
      <template v-if="seg === 'standard'">
        <el-table-column label="标准单价" width="90" min-width="80">
          <template #default="{ row }">
            <el-input-number :model-value="row.stdPrice" size="small" :controls="false" :disabled="ro"
              class="compact-num" @change="(v: number) => vt.updateRow(row.rowId, { stdPrice: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="标准数量" width="90" min-width="80">
          <template #default="{ row }">
            <el-input-number :model-value="row.stdQty" size="small" :controls="false" :disabled="ro"
              class="compact-num" @change="(v: number) => vt.updateRow(row.rowId, { stdQty: v ?? 0 })" />
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="实际单价" width="90" min-width="80">
          <template #default="{ row }">
            <el-input-number :model-value="row.actPrice" size="small" :controls="false" :disabled="ro"
              class="compact-num" @change="(v: number) => vt.updateRow(row.rowId, { actPrice: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="实际数量" width="90" min-width="80">
          <template #default="{ row }">
            <el-input-number :model-value="row.actQty" size="small" :controls="false" :disabled="ro"
              class="compact-num" @change="(v: number) => vt.updateRow(row.rowId, { actQty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="账面金额" width="95" min-width="85">
          <template #default="{ row }">
            <el-input-number :model-value="row.bookIssueAmt" size="small" :controls="false" :disabled="ro"
              class="compact-num" @change="(v: number) => vt.updateRow(row.rowId, { bookIssueAmt: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="审计金额" width="95" min-width="85" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="实际单价 × 实际数量" placement="top">
              <span class="formula">{{ fmt(row.auditIssueAmt) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="差异率" width="80" min-width="70" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="(审计金额-账面金额)/账面金额×100%" placement="top">
              <span :class="{ 'spread-warn': isExceed(row) }" class="formula">{{ fmtRate(row.varianceRate) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>
    </template>
  </F2ValuationTestSheet>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, toRef } from 'vue'
import { useF2StandardCostTest } from '../../composables/useF2ValuationTestSheet'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import type { SampledVoucher, FillMode } from '../../composables/useSamplingAlgorithms'
import F2ValuationTestSheet from './F2ValuationTestSheet.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  auditYear?: number
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const vt = useF2StandardCostTest({ allResponses: toRef(props, 'allResponses'), isReadonly: toRef(props, 'isReadonly') })
const segments = [{ label: '标准成本', value: 'standard' }, { label: '实际/差异', value: 'actual' }]

const auditYear = computed(() => props.auditYear ?? new Date().getFullYear() - 1)

// ─── 审计说明（独立持久化，F2 计价组事件；测试结论沿用 composable） ────────
const NOTE_KEY = 'F2-40-audit-note'
const auditNote = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
})

function handleSamplingFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode }) {
  vt.fillFromSampling(payload.samples, payload.fillMode)
}
</script>

<style scoped>
.spread-warn { color: #f56c6c; font-weight: 600; }
</style>
