<template>
  <F2StdCostMonthlySheet
    title="标准成本差异测试表"
    sheet-code="F2-40"
    :threshold-rate="thresholdRate"
    :default-objective="DEFAULT_OBJECTIVE"
    :projects="enrichedProjects"
    :sampling-params="samplingParams"
    :sampling-criteria="samplingCriteria"
    :test-objective="testObjective"
    :test-conclusion="testConclusion"
    :audit-note="auditNote"
    :exceed-count="exceedCount"
    :bundle-diff="bundleDiff"
    :project-totals="projectTotals"
    :wp-id="wpId"
    :project-id="projectId"
    :is-readonly="isReadonly"
    @add-project="addProject()"
    @remove-project="(id: string) => removeProject(id)"
    @update-project="(id, patch) => updateProject(id, patch)"
    @update-month="(pid, key, patch) => updateMonth(pid, key, patch)"
    @update:test-objective="(v: string) => setObjective(v)"
    @update:sampling-criteria="(v: string) => setSamplingCriteria(v)"
    @update:test-conclusion="setConclusion"
    @update:audit-note="saveAuditNote"
  />
</template>

<script setup lang="ts">
import { ref, onMounted, toRef } from 'vue'
import { useF2StdCostMonthlySheet } from '../../composables/useF2StdCostMonthlySheet'
import { F2_40_DEFAULT_OBJECTIVE } from '../../composables/useF2StdCostMonthlyFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import F2StdCostMonthlySheet from './F2StdCostMonthlySheet.vue'

const DEFAULT_OBJECTIVE = F2_40_DEFAULT_OBJECTIVE

const props = defineProps<{
  wpId?: string
  projectId?: string
  auditYear?: number
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const {
  thresholdRate,
  enrichedProjects,
  samplingParams,
  samplingCriteria,
  testObjective,
  testConclusion,
  exceedCount,
  bundleDiff,
  projectTotals,
  addProject,
  removeProject,
  updateProject,
  updateMonth,
  setObjective,
  setSamplingCriteria,
} = useF2StdCostMonthlySheet({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

function setConclusion(v: string) {
  testConclusion.value = v
}

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
</script>
