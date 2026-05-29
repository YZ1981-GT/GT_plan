/**
 * useWpAutoFill — 底稿自动刷数 composable
 *
 * 从 render-config 返回的 fill_results 中提取自动填充数据，
 * 提供 cell 级别的 auto-fill 状态和格式化显示。
 *
 * 锚定 spec workpaper-editor-slimdown Task 16.4
 * Validates: US-15（HTML 底稿自动刷数 + 全链路跳转）
 */

import { computed, type Ref } from 'vue'

export interface AutoFillResult {
  value: number | string | null
  source: string
  label: string
  status: 'ok' | 'unavailable'
}

export interface AutoFillCell {
  autoFill: AutoFillResult | null
  displayValue: string
  tooltipContent: string
  isUnavailable: boolean
}

/**
 * 格式化金额数值（千分位 + 2 位小数）
 */
function formatAmount(value: number | string | null): string {
  if (value === null || value === undefined) return '—'
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num)) return String(value)
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function useWpAutoFill(fillResults: Ref<Record<string, AutoFillResult> | null | undefined>) {
  /**
   * 获取指定 cell 的自动填充信息
   */
  function getAutoFillCell(sheetName: string, cellRef: string): AutoFillCell {
    const key = `${sheetName}!${cellRef}`
    const result = fillResults.value?.[key] ?? null

    if (!result) {
      return {
        autoFill: null,
        displayValue: '',
        tooltipContent: '',
        isUnavailable: false,
      }
    }

    const displayValue = result.status === 'ok' ? formatAmount(result.value) : '—'
    const tooltipContent = result.label
      ? `来自 ${result.source} — ${result.label}`
      : `来自 ${result.source}`

    return {
      autoFill: result,
      displayValue,
      tooltipContent,
      isUnavailable: result.status === 'unavailable',
    }
  }

  /**
   * 检查某个 sheet 是否有任何自动填充 cell
   */
  const hasAutoFillCells = computed(() => {
    if (!fillResults.value) return false
    return Object.keys(fillResults.value).length > 0
  })

  /**
   * 获取指定 sheet 的所有自动填充 cell keys
   */
  function getSheetAutoFillKeys(sheetName: string): string[] {
    if (!fillResults.value) return []
    const prefix = `${sheetName}!`
    return Object.keys(fillResults.value).filter(k => k.startsWith(prefix))
  }

  /**
   * 获取所有不可用的 cell（用于高亮显示）
   */
  const unavailableCells = computed(() => {
    if (!fillResults.value) return []
    return Object.entries(fillResults.value)
      .filter(([, v]) => v.status === 'unavailable')
      .map(([k]) => k)
  })

  return {
    getAutoFillCell,
    hasAutoFillCells,
    getSheetAutoFillKeys,
    unavailableCells,
    formatAmount,
  }
}
