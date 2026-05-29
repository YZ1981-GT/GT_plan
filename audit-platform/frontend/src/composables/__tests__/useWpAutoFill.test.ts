/**
 * Tests for useWpAutoFill composable
 *
 * 锚定 spec workpaper-editor-slimdown Task 16.4
 * Validates: US-15（HTML 底稿自动刷数）
 */

import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useWpAutoFill, type AutoFillResult } from '../useWpAutoFill'

describe('useWpAutoFill', () => {
  describe('getAutoFillCell', () => {
    it('returns empty cell when fillResults is null', () => {
      const fillResults = ref(null)
      const { getAutoFillCell } = useWpAutoFill(fillResults)

      const cell = getAutoFillCell('Sheet1', 'B7')
      expect(cell.autoFill).toBeNull()
      expect(cell.displayValue).toBe('')
      expect(cell.isUnavailable).toBe(false)
    })

    it('returns empty cell when key not found', () => {
      const fillResults = ref<Record<string, AutoFillResult>>({
        'Sheet1!A1': { value: 100, source: 'TB:1001:期末', label: '测试', status: 'ok' },
      })
      const { getAutoFillCell } = useWpAutoFill(fillResults)

      const cell = getAutoFillCell('Sheet1', 'B7')
      expect(cell.autoFill).toBeNull()
    })

    it('returns ok cell with formatted value', () => {
      const fillResults = ref<Record<string, AutoFillResult>>({
        'Sheet1!B7': { value: 42772704.06, source: 'TB:1122:期末', label: '应收账款', status: 'ok' },
      })
      const { getAutoFillCell } = useWpAutoFill(fillResults)

      const cell = getAutoFillCell('Sheet1', 'B7')
      expect(cell.autoFill).not.toBeNull()
      expect(cell.autoFill!.status).toBe('ok')
      expect(cell.displayValue).toContain('42,772,704.06')
      expect(cell.tooltipContent).toBe('来自 TB:1122:期末 — 应收账款')
      expect(cell.isUnavailable).toBe(false)
    })

    it('returns unavailable cell with dash', () => {
      const fillResults = ref<Record<string, AutoFillResult>>({
        'Sheet1!C5': { value: null, source: 'TB:9999:期末', label: '', status: 'unavailable' },
      })
      const { getAutoFillCell } = useWpAutoFill(fillResults)

      const cell = getAutoFillCell('Sheet1', 'C5')
      expect(cell.autoFill!.status).toBe('unavailable')
      expect(cell.displayValue).toBe('—')
      expect(cell.isUnavailable).toBe(true)
      expect(cell.tooltipContent).toBe('来自 TB:9999:期末')
    })

    it('tooltip without label shows only source', () => {
      const fillResults = ref<Record<string, AutoFillResult>>({
        'Sheet1!A1': { value: 100, source: 'REPORT:R001:amount', label: '', status: 'ok' },
      })
      const { getAutoFillCell } = useWpAutoFill(fillResults)

      const cell = getAutoFillCell('Sheet1', 'A1')
      expect(cell.tooltipContent).toBe('来自 REPORT:R001:amount')
    })
  })

  describe('hasAutoFillCells', () => {
    it('returns false when fillResults is null', () => {
      const fillResults = ref(null)
      const { hasAutoFillCells } = useWpAutoFill(fillResults)
      expect(hasAutoFillCells.value).toBe(false)
    })

    it('returns false when fillResults is empty', () => {
      const fillResults = ref<Record<string, AutoFillResult>>({})
      const { hasAutoFillCells } = useWpAutoFill(fillResults)
      expect(hasAutoFillCells.value).toBe(false)
    })

    it('returns true when fillResults has entries', () => {
      const fillResults = ref<Record<string, AutoFillResult>>({
        'Sheet1!A1': { value: 100, source: 'TB:1001:期末', label: '', status: 'ok' },
      })
      const { hasAutoFillCells } = useWpAutoFill(fillResults)
      expect(hasAutoFillCells.value).toBe(true)
    })
  })

  describe('getSheetAutoFillKeys', () => {
    it('returns empty array when no results', () => {
      const fillResults = ref(null)
      const { getSheetAutoFillKeys } = useWpAutoFill(fillResults)
      expect(getSheetAutoFillKeys('Sheet1')).toEqual([])
    })

    it('filters keys by sheet name', () => {
      const fillResults = ref<Record<string, AutoFillResult>>({
        'Sheet1!A1': { value: 1, source: 'TB:1001:期末', label: '', status: 'ok' },
        'Sheet1!B2': { value: 2, source: 'TB:1002:期末', label: '', status: 'ok' },
        'Sheet2!C3': { value: 3, source: 'TB:1003:期末', label: '', status: 'ok' },
      })
      const { getSheetAutoFillKeys } = useWpAutoFill(fillResults)

      const keys = getSheetAutoFillKeys('Sheet1')
      expect(keys).toHaveLength(2)
      expect(keys).toContain('Sheet1!A1')
      expect(keys).toContain('Sheet1!B2')
    })
  })

  describe('unavailableCells', () => {
    it('returns empty when all ok', () => {
      const fillResults = ref<Record<string, AutoFillResult>>({
        'Sheet1!A1': { value: 100, source: 'TB:1001:期末', label: '', status: 'ok' },
      })
      const { unavailableCells } = useWpAutoFill(fillResults)
      expect(unavailableCells.value).toEqual([])
    })

    it('returns unavailable cell keys', () => {
      const fillResults = ref<Record<string, AutoFillResult>>({
        'Sheet1!A1': { value: 100, source: 'TB:1001:期末', label: '', status: 'ok' },
        'Sheet1!B2': { value: null, source: 'TB:9999:期末', label: '', status: 'unavailable' },
        'Sheet2!C3': { value: null, source: 'WP:X:Y:Z', label: '', status: 'unavailable' },
      })
      const { unavailableCells } = useWpAutoFill(fillResults)
      expect(unavailableCells.value).toHaveLength(2)
      expect(unavailableCells.value).toContain('Sheet1!B2')
      expect(unavailableCells.value).toContain('Sheet2!C3')
    })
  })

  describe('formatAmount', () => {
    it('formats number with thousands separator', () => {
      const fillResults = ref(null)
      const { formatAmount } = useWpAutoFill(fillResults)

      expect(formatAmount(1234567.89)).toContain('1,234,567.89')
    })

    it('returns dash for null', () => {
      const fillResults = ref(null)
      const { formatAmount } = useWpAutoFill(fillResults)

      expect(formatAmount(null)).toBe('—')
    })

    it('handles string numbers', () => {
      const fillResults = ref(null)
      const { formatAmount } = useWpAutoFill(fillResults)

      const result = formatAmount('42772704.06')
      expect(result).toContain('42,772,704.06')
    })
  })
})
