import { computed, type Ref } from 'vue'
import { classifyDatasetUnit } from '@/composables/classifyDatasetUnit'
import { useDatasetUnitPresentation } from '@/composables/useDatasetUnitPresentation'

export interface TrialBalanceDataSummary {
  year: number
  balance_count: number
  ledger_count: number
  amount_unit: string
  source_summary: Record<string, unknown> | null
}

export function useTrialBalanceDatasetUnit(summary: Ref<TrialBalanceDataSummary | null | undefined>) {
  const sourceSummary = computed(() => summary.value?.source_summary ?? null)
  const classification = computed(() => classifyDatasetUnit(sourceSummary.value))
  return useDatasetUnitPresentation(classification, sourceSummary)
}
