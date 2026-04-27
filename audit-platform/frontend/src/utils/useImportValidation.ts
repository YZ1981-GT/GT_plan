import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import {
  getImportValidationAlertType,
  getImportValidationSummaryTitle,
  groupImportValidationItems,
  resolveImportValidationSummary,
  type ImportValidationItemLike,
  type ImportValidationSummaryLike,
} from '@/utils/importValidation'

export function useImportValidation<
  TItem extends ImportValidationItemLike,
  TSummary extends ImportValidationSummaryLike,
>(
  itemsSource: MaybeRefOrGetter<TItem[] | null | undefined>,
  summarySource?: MaybeRefOrGetter<TSummary | null | undefined>,
) {
  const items = computed(() => toValue(itemsSource) || [])
  const validationSummary = computed(() => resolveImportValidationSummary(
    items.value,
    summarySource ? toValue(summarySource) : undefined,
  ))
  const groupedValidationItems = computed(() => groupImportValidationItems(items.value))
  const validationSummaryAlertType = computed(() => getImportValidationAlertType(validationSummary.value))
  const validationSummaryTitle = computed(() => getImportValidationSummaryTitle(validationSummary.value))

  return {
    items,
    validationSummary,
    groupedValidationItems,
    validationSummaryAlertType,
    validationSummaryTitle,
  }
}
