<template>
  <F2ValuationMonthlySheet
    title="计价方法测试表 — 先进先出"
    sheet-code="F2-39"
    method="fifo"
    method-label="先进先出法"
    :threshold-rate="thresholdRate"
    :default-objective="DEFAULT_OBJECTIVE"
    :projects="enrichedProjects"
    :sampling-params="samplingParams"
    :sampling-criteria="samplingCriteria"
    :test-objective="testObjective"
    :test-conclusion="testConclusion"
    :audit-note="auditNote"
    :exceed-count="exceedCount"
    :bundle-variance="bundleVariance"
    :project-totals="projectTotals"
    :wp-id="wpId"
    :project-id="projectId"
    :is-readonly="isReadonly"
    @add-project="addProject()"
    @remove-project="(id: string) => removeProject(id)"
    @update-project="(id: string, patch) => updateProject(id, patch)"
    @update-month="(pid, key, patch) => updateMonth(pid, key, patch)"
    @update:test-objective="(v: string) => setObjective(v)"
    @update:sampling-criteria="(v: string) => setSamplingCriteria(v)"
    @update:test-conclusion="setConclusion"
    @update:audit-note="saveAuditNote"
  />
</template>

<script setup lang="ts">
import { ref, onMounted, toRef } from 'vue'
import { useF2FifoMonthly } from '../../composables/useF2ValuationMonthlySheet'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import F2ValuationMonthlySheet from './F2ValuationMonthlySheet.vue'

const DEFAULT_OBJECTIVE =
  '验证存货计价及分摊是否正确，披露是否恰当；选取样本存货品种，按先进先出法重新计算发出成本，核对企业账面结转是否正确、方法运用是否一贯。'

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
  bundleVariance,
  projectTotals,
  addProject,
  removeProject,
  updateProject,
  updateMonth,
  setObjective,
  setSamplingCriteria,
} = useF2FifoMonthly({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

function setConclusion(v: string) {
  testConclusion.value = v
}

const NOTE_KEY = 'F2-39-audit-note'
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
