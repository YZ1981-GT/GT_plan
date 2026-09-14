import { describe, it, expect } from 'vitest'
import {
  determineCutoffStatus,
  computeDateRange,
  type CutoffDirection,
  type CutoffStatus,
} from '../cutoffJudgment'

describe('cutoffJudgment', () => {
  describe('determineCutoffStatus', () => {
    // post_cutoff: voucherDate > cutoffDate AND amount > 0 → "可能跨期"
    it('post_cutoff: 凭证日期晚于截止日 + 借方 → 可能跨期', () => {
      expect(determineCutoffStatus('2025-01-02', '2025-01-01', 'post_cutoff', 1000)).toBe('可能跨期')
    })

    it('post_cutoff: 凭证日期晚于截止日 + 贷方 → 正常', () => {
      expect(determineCutoffStatus('2025-01-02', '2025-01-01', 'post_cutoff', -500)).toBe('正常')
    })

    it('post_cutoff: 凭证日期等于截止日 → 正常', () => {
      expect(determineCutoffStatus('2025-01-01', '2025-01-01', 'post_cutoff', 1000)).toBe('正常')
    })

    it('post_cutoff: 凭证日期早于截止日 → 正常', () => {
      expect(determineCutoffStatus('2024-12-30', '2025-01-01', 'post_cutoff', 1000)).toBe('正常')
    })

    // pre_cutoff: voucherDate < cutoffDate AND amount < 0 → "可能跨期"
    it('pre_cutoff: 凭证日期早于截止日 + 贷方 → 可能跨期', () => {
      expect(determineCutoffStatus('2024-12-30', '2025-01-01', 'pre_cutoff', -800)).toBe('可能跨期')
    })

    it('pre_cutoff: 凭证日期早于截止日 + 借方 → 正常', () => {
      expect(determineCutoffStatus('2024-12-30', '2025-01-01', 'pre_cutoff', 500)).toBe('正常')
    })

    it('pre_cutoff: 凭证日期等于截止日 → 正常', () => {
      expect(determineCutoffStatus('2025-01-01', '2025-01-01', 'pre_cutoff', -800)).toBe('正常')
    })

    // window: voucherDate in [cutoffDate - daysBefore, cutoffDate + daysAfter] → "待检查"
    it('window: 凭证日期在窗口内 → 待检查', () => {
      expect(determineCutoffStatus('2024-12-28', '2024-12-31', 'window', 100, 5, 10)).toBe('待检查')
    })

    it('window: 凭证日期恰好在窗口起始边界 → 待检查', () => {
      expect(determineCutoffStatus('2024-12-26', '2024-12-31', 'window', 100, 5, 10)).toBe('待检查')
    })

    it('window: 凭证日期恰好在窗口结束边界 → 待检查', () => {
      expect(determineCutoffStatus('2025-01-10', '2024-12-31', 'window', 100, 5, 10)).toBe('待检查')
    })

    it('window: 凭证日期在窗口之前 → 正常', () => {
      expect(determineCutoffStatus('2024-12-25', '2024-12-31', 'window', 100, 5, 10)).toBe('正常')
    })

    it('window: 凭证日期在窗口之后 → 正常', () => {
      expect(determineCutoffStatus('2025-01-11', '2024-12-31', 'window', 100, 5, 10)).toBe('正常')
    })

    // 无效日期 → "正常"
    it('无效凭证日期 → 正常', () => {
      expect(determineCutoffStatus('invalid', '2025-01-01', 'post_cutoff', 1000)).toBe('正常')
    })

    it('无效截止日期 → 正常', () => {
      expect(determineCutoffStatus('2025-01-02', 'bad-date', 'post_cutoff', 1000)).toBe('正常')
    })

    // 金额为0
    it('post_cutoff: 金额为0 → 正常', () => {
      expect(determineCutoffStatus('2025-01-02', '2025-01-01', 'post_cutoff', 0)).toBe('正常')
    })

    it('pre_cutoff: 金额为0 → 正常', () => {
      expect(determineCutoffStatus('2024-12-30', '2025-01-01', 'pre_cutoff', 0)).toBe('正常')
    })

    // 默认 daysBefore=5, daysAfter=10
    it('window: 使用默认窗口参数', () => {
      // cutoffDate=2024-12-31, window = [12-26, 01-10]
      expect(determineCutoffStatus('2024-12-31', '2024-12-31', 'window', 0)).toBe('待检查')
    })
  })

  describe('computeDateRange', () => {
    it('计算正确的日期范围', () => {
      const result = computeDateRange('2024-12-31', 5, 10)
      expect(result.start).toBe('2024-12-26')
      expect(result.end).toBe('2025-01-10')
    })

    it('daysBefore=0, daysAfter=0 → start=end=cutoffDate', () => {
      const result = computeDateRange('2025-06-15', 0, 0)
      expect(result.start).toBe('2025-06-15')
      expect(result.end).toBe('2025-06-15')
    })

    it('跨月计算', () => {
      const result = computeDateRange('2025-03-01', 3, 3)
      expect(result.start).toBe('2025-02-26')
      expect(result.end).toBe('2025-03-04')
    })

    it('无效日期返回原值', () => {
      const result = computeDateRange('not-a-date', 5, 10)
      expect(result.start).toBe('not-a-date')
      expect(result.end).toBe('not-a-date')
    })
  })
})
