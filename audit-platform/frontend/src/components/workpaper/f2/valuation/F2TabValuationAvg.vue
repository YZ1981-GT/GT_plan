<template>
  <F2ValuationTestSheet
    title="计价方法测试 — 月末一次加权平均"
    sheet-code="F2-38"
    :threshold-rate="vt.thresholdRate"
    :display-rows="vt.enrichedRows.value"
    :totals="vt.totals.value"
    :exceed-count="vt.exceedCount.value"
    :sampling-params="vt.samplingParams.value"
    :test-conclusion="vt.testConclusion.value"
    :wp-id="wpId"
    :project-id="projectId"
    :audit-year="auditYear"
    :is-readonly="isReadonly"
    :segments="segments"
    default-segment="inventory"
    guidance-text="选取样本存货品种，核对企业月末一次加权平均法计算的发出成本是否正确。关注差异率超过1%的样本。"
    @add-row="vt.addRow()"
    @remove-row="(id: string) => vt.removeRow(id)"
    @update-row="(id: string, patch: any) => vt.updateRow(id, patch)"
    @sampling-filled="handleSamplingFilled"
    @update:test-conclusion="(t: string) => { vt.testConclusion.value = t }"
  >
    <template #columns="{ segment: seg, isReadonly: ro, fmt, fmtRate, isExceed }">
      <template v-if="seg === 'inventory'">
        <el-table-column label="期初数量" width="90" min-width="80">
          <template #default="{ row }">
            <el-input-number :model-value="row.openingQty" size="small" :controls="false" :disabled="ro"
              class="compact-num" @change="(v: number) => vt.updateRow(row.rowId, { openingQty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="期初金额" width="95" min-width="85">
          <template #default="{ row }">
            <el-input-number :model-value="row.openingAmt" size="small" :controls="false" :disabled="ro"
              class="compact-num" @change="(v: number) => vt.updateRow(row.rowId, { openingAmt: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="入库数量" width="90" min-width="80">
          <template #default="{ row }">
            <el-input-number :model-value="row.inboundQty" size="small" :controls="false" :disabled="ro"
              class="compact-num" @change="(v: number) => vt.updateRow(row.rowId, { inboundQty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="入库金额" width="95" min-width="85">
          <template #default="{ row }">
            <el-input-number :model-value="row.inboundAmt" size="small" :controls="false" :disabled="ro"
              class="compact-num" @change="(v: number) => vt.updateRow(row.rowId, { inboundAmt: v ?? 0 })" />
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="发出数量" width="90" min-width="80">
          <template #default="{ row }">
            <el-input-number :model-value="row.issueQty" size="small" :controls="false" :disabled="ro"
              class="compact-num" @change="(v: number) => vt.updateRow(row.rowId, { issueQty: v ?? 0 })" />
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
            <el-tooltip content="加权平均单价 × 发出数量" placement="top">
              <span class="formula">{{ fmt(row.auditIssueAmt) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="差异额" width="90" min-width="80" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="审计金额 - 账面金额" placement="top">
              <span class="formula">{{ fmt(row.varianceAmt) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="差异率" width="80" min-width="70" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="差异额 / 账面金额 × 100%" placement="top">
              <span :class="{ 'spread-warn': isExceed(row) }" class="formula">{{ fmtRate(row.varianceRate) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>
    </template>
  </F2ValuationTestSheet>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useF2WeightedAvgTest } from '../../composables/useF2ValuationTestSheet'
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

const vt = useF2WeightedAvgTest({ allResponses: toRef(props, 'allResponses'), isReadonly: toRef(props, 'isReadonly') })
const segments = [{ label: '期初/入库', value: 'inventory' }, { label: '发出/差异', value: 'verify' }]

const auditYear = computed(() => props.auditYear ?? new Date().getFullYear() - 1)

function handleSamplingFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode }) {
  vt.fillFromSampling(payload.samples, payload.fillMode)
}
</script>

<style scoped>
.spread-warn { color: #f56c6c; font-weight: 600; }
</style>
