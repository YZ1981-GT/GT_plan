import { describe, it, expect } from 'vitest'
import {
  suggestSampleSize,
  getFrequencyOptions,
  SAMPLE_SIZE_TABLE,
  isPctEntry,
  isRangeFixedEntry,
  isFixedEntry,
  type SampleSizeResult,
} from '../useSampleSizeEngine'

// ─── suggestSampleSize ──────────────────────────────────────

describe('suggestSampleSize', () => {
  describe('固定区间频率', () => {
    it('每年：totalCount=1 → min=1, max=1', () => {
      const r = suggestSampleSize('每年', 1)
      expect(r.min).toBe(1)
      expect(r.max).toBe(1)
      expect(r.note).toBeUndefined()
    })

    it('每季度：totalCount=4 → min=2, max=2', () => {
      const r = suggestSampleSize('每季度', 4)
      expect(r.min).toBe(2)
      expect(r.max).toBe(2)
    })

    it('每月：totalCount=12 → min=2, max=5', () => {
      const r = suggestSampleSize('每月', 12)
      expect(r.min).toBe(2)
      expect(r.max).toBe(5)
    })

    it('每周：totalCount=52 → min=5, max=15', () => {
      const r = suggestSampleSize('每周', 52)
      expect(r.min).toBe(5)
      expect(r.max).toBe(15)
    })

    it('每天：totalCount=250 → min=20, max=40', () => {
      const r = suggestSampleSize('每天', 250)
      expect(r.min).toBe(20)
      expect(r.max).toBe(40)
    })

    it('每天多次：totalCount=500 → min=25, max=60', () => {
      const r = suggestSampleSize('每天多次', 500)
      expect(r.min).toBe(25)
      expect(r.max).toBe(60)
    })
  })

  describe('百分比区间（每半月）', () => {
    it('totalCount=100 → 10%=10, 20%=20', () => {
      const r = suggestSampleSize('每半月', 100)
      expect(r.min).toBe(10)
      expect(r.max).toBe(20)
      expect(r.note).toContain('10%~20%')
    })

    it('totalCount=200 → 10%=20, 20%=40（正好到cap）', () => {
      const r = suggestSampleSize('每半月', 200)
      expect(r.min).toBe(20)
      expect(r.max).toBe(40)
    })

    it('totalCount=249 → ceil(24.9)=25, ceil(49.8)=50 但cap=40', () => {
      const r = suggestSampleSize('每半月', 249)
      expect(r.min).toBe(25)
      expect(r.max).toBe(40)  // 受 cap 限制
    })

    it('totalCount=53（最小范围）→ ceil(5.3)=6, ceil(10.6)=11', () => {
      const r = suggestSampleSize('每半月', 53)
      expect(r.min).toBe(6)
      expect(r.max).toBe(11)
    })
  })

  describe('边界与异常', () => {
    it('totalCount=0 → 返回 0,0 + 提示', () => {
      const r = suggestSampleSize('每月', 0)
      expect(r.min).toBe(0)
      expect(r.max).toBe(0)
      expect(r.note).toBeDefined()
    })

    it('totalCount=-1 → 返回 0,0 + 提示', () => {
      const r = suggestSampleSize('每周', -1)
      expect(r.min).toBe(0)
      expect(r.max).toBe(0)
      expect(r.note).toContain('无法确定')
    })

    it('频率空字符串 → 返回 0,0 + 提示', () => {
      const r = suggestSampleSize('', 100)
      expect(r.min).toBe(0)
      expect(r.max).toBe(0)
      expect(r.note).toBeDefined()
    })

    it('未知频率 → 返回 0,0 + 未知提示', () => {
      const r = suggestSampleSize('不存在的频率', 100)
      expect(r.min).toBe(0)
      expect(r.max).toBe(0)
      expect(r.note).toContain('未知控制频率')
    })
  })

  describe('min ≤ max 恒成立', () => {
    it('所有固定频率 min ≤ max', () => {
      const fixedFreqs = ['每年', '每季度', '每月', '每周', '每天', '每天多次']
      for (const freq of fixedFreqs) {
        const r = suggestSampleSize(freq, 100)
        expect(r.min).toBeLessThanOrEqual(r.max)
      }
    })

    it('百分比频率各种totalCount下 min ≤ max', () => {
      const counts = [53, 60, 100, 150, 200, 249]
      for (const c of counts) {
        const r = suggestSampleSize('每半月', c)
        expect(r.min).toBeLessThanOrEqual(r.max)
      }
    })
  })
})

// ─── getFrequencyOptions ────────────────────────────────────

describe('getFrequencyOptions', () => {
  it('返回所有频率选项', () => {
    const options = getFrequencyOptions()
    expect(options).toHaveLength(SAMPLE_SIZE_TABLE.length)
    expect(options).toContain('每年')
    expect(options).toContain('每季度')
    expect(options).toContain('每月')
    expect(options).toContain('每周')
    expect(options).toContain('每半月')
    expect(options).toContain('每天')
    expect(options).toContain('每天多次')
  })

  it('选项顺序与表一致', () => {
    const options = getFrequencyOptions()
    expect(options[0]).toBe('每年')
    expect(options[options.length - 1]).toBe('每天多次')
  })
})

// ─── SAMPLE_SIZE_TABLE 结构 ──────────────────────────────────

describe('SAMPLE_SIZE_TABLE', () => {
  it('共7条记录', () => {
    expect(SAMPLE_SIZE_TABLE).toHaveLength(7)
  })

  it('仅1条百分比区间（每半月）', () => {
    const pctEntries = SAMPLE_SIZE_TABLE.filter(isPctEntry)
    expect(pctEntries).toHaveLength(1)
    expect(pctEntries[0].frequency).toBe('每半月')
  })

  it('仅1条范围固定区间（每天多次）', () => {
    const rangeFixedEntries = SAMPLE_SIZE_TABLE.filter(isRangeFixedEntry)
    expect(rangeFixedEntries).toHaveLength(1)
    expect(rangeFixedEntries[0].frequency).toBe('每天多次')
  })

  it('固定区间所有条目 min ≤ max', () => {
    for (const entry of SAMPLE_SIZE_TABLE) {
      if (!isPctEntry(entry)) {
        expect(entry.min).toBeLessThanOrEqual(entry.max)
      }
    }
  })
})
