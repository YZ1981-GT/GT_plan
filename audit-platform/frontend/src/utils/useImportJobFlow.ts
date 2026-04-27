import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import {
  extractImportValidationMessage,
  getImportValidationSummaryTitle,
  type ImportValidationItemLike,
  type ImportValidationSummaryLike,
} from '@/utils/importValidation'

export interface ImportQueueStatusLike<TResult = unknown> {
  progress?: number | null
  message?: string | null
  status?: string | null
  result?: TResult
}

export function shouldFinishImportPolling(status: ImportQueueStatusLike | null | undefined): boolean {
  if (!status || typeof status !== 'object') return true
  const progress = status.progress ?? 0
  return progress >= 100 || progress < 0 || status.status === 'idle'
}

export function hasImportFailed(status: ImportQueueStatusLike | null | undefined): boolean {
  const progress = status?.progress ?? 0
  return progress < 0
}

export function resolveImportCompletionToast(
  message: string | null | undefined,
  summary: ImportValidationSummaryLike | null | undefined,
): { type: 'success' | 'warning'; message: string } {
  if (summary?.has_blocking || (summary?.blocking_count ?? 0) > 0) {
    return {
      type: 'warning',
      message: message || getImportValidationSummaryTitle({
        total: summary?.total ?? 0,
        fatal: summary?.by_severity?.fatal ?? 0,
        error: summary?.by_severity?.error ?? 0,
        warning: summary?.by_severity?.warning ?? 0,
        info: summary?.by_severity?.info ?? 0,
        blocking_count: summary?.blocking_count ?? 0,
        has_blocking: summary?.has_blocking ?? (summary?.blocking_count ?? 0) > 0,
      }),
    }
  }
  return {
    type: 'success',
    message: message || '导入完成',
  }
}

export function resolveImportFailureMessage<TItem extends ImportValidationItemLike>(
  items: TItem[] | null | undefined,
  fallback: string,
): string {
  return extractImportValidationMessage(items, fallback)
}

export function useImportJobFlow<
  TResult extends { validation_summary?: ImportValidationSummaryLike | null },
  TItem extends ImportValidationItemLike,
>(
  resultSource: MaybeRefOrGetter<TResult | null | undefined>,
  validationSource: MaybeRefOrGetter<TItem[] | null | undefined>,
) {
  const result = computed(() => toValue(resultSource))
  const validation = computed(() => toValue(validationSource) || [])

  const completionToast = computed(() => resolveImportCompletionToast(
    null,
    result.value?.validation_summary,
  ))

  return {
    result,
    validation,
    completionToast,
  }
}
