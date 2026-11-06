/**
 * displayPrefs store 测试
 * 覆盖：density/fontSize/amountUnit/fixedColumns 扩展
 *
 * Validates: Requirements 6.1, 6.2, 6.3
 *
 * 2026-11-05（platform-global-display-settings-closure 任务 4）：偏好改为服务端权威 +
 * 按账号分区缓存，未分区的旧键 `gt_display_prefs` 只删除不读写，所以原先三条
 * 「持久化 / 恢复到 gt_display_prefs」的断言改为断言该键不再被使用；零值占位统一
 * 为 '-'（与 GtAmountCell 的审计惯例一致）。跨账号缓存、epoch 与冲突重放见
 * `src/stores/__tests__/displayPrefsSync.spec.ts`。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDisplayPrefsStore, TABLE_DENSITIES } from '@/stores/displayPrefs'
import { DISPLAY_PREFERENCES_LEGACY_KEY } from '@/utils/displayPreferencesNormalizer'

describe('useDisplayPrefsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('默认值正确', () => {
    const store = useDisplayPrefsStore()
    expect(store.amountUnit).toBe('yuan')
    expect(store.fontSize).toBe('sm')
    expect(store.density).toBe('default')
    expect(store.showZero).toBe(false)
    expect(store.negativeRed).toBe(true)
    expect(store.highlightThreshold).toBe(0.2)
  })

  describe('density 密度', () => {
    it('setDensity 切换密度，且不写未分区的旧缓存键', () => {
      const store = useDisplayPrefsStore()
      store.setDensity('compact')
      expect(store.density).toBe('compact')

      // 旧键不再是偏好的存储位置（按账号分区的缓存由 displayPrefsSync.spec.ts 覆盖）
      expect(localStorage.getItem(DISPLAY_PREFERENCES_LEGACY_KEY)).toBeNull()
    })

    it('tableDensity 返回 el-table size 值', () => {
      const store = useDisplayPrefsStore()
      expect(store.tableDensity).toBe('default')

      store.setDensity('compact')
      expect(store.tableDensity).toBe('small')

      store.setDensity('comfortable')
      expect(store.tableDensity).toBe('large')
    })

    it('densityConfig 返回配置对象', () => {
      const store = useDisplayPrefsStore()
      store.setDensity('compact')
      expect(store.densityConfig).toEqual(TABLE_DENSITIES.compact)
      expect(store.densityConfig.rowHeight).toBe('32px')
    })

    it('densityOptions 包含三个选项', () => {
      const store = useDisplayPrefsStore()
      expect(store.densityOptions).toHaveLength(3)
      expect(store.densityOptions.map(o => o.value)).toEqual(['compact', 'default', 'comfortable'])
    })
  })

  describe('fixedColumns 固定列', () => {
    it('setFixedColumns 设置页面固定列', () => {
      const store = useDisplayPrefsStore()
      store.setFixedColumns('trial-balance', ['code', 'name'])
      expect(store.getFixedColumns('trial-balance')).toEqual(['code', 'name'])
    })

    it('getFixedColumns 对未设置页面返回空数组', () => {
      const store = useDisplayPrefsStore()
      expect(store.getFixedColumns('nonexistent')).toEqual([])
    })

    it('fixedColumns 生效于当前屏幕，且不写未分区的旧缓存键', () => {
      const store = useDisplayPrefsStore()
      expect(store.setFixedColumns('report-view', ['row_name'])).toBe(true)
      expect(store.getFixedColumns('report-view')).toEqual(['row_name'])

      expect(localStorage.getItem(DISPLAY_PREFERENCES_LEGACY_KEY)).toBeNull()
    })

    it('多页面固定列互不干扰', () => {
      const store = useDisplayPrefsStore()
      store.setFixedColumns('page-a', ['col1'])
      store.setFixedColumns('page-b', ['col2', 'col3'])

      expect(store.getFixedColumns('page-a')).toEqual(['col1'])
      expect(store.getFixedColumns('page-b')).toEqual(['col2', 'col3'])
    })
  })

  describe('fontSize 字号', () => {
    it('setFontSize 切换字号', () => {
      const store = useDisplayPrefsStore()
      store.setFontSize('lg')
      expect(store.fontSize).toBe('lg')
      expect(store.fontConfig.tableFont).toBe('14px')
    })

    it('fontOptions 包含四个选项', () => {
      const store = useDisplayPrefsStore()
      expect(store.fontOptions).toHaveLength(4)
    })
  })

  describe('amountUnit 金额单位', () => {
    it('setUnit 切换单位', () => {
      const store = useDisplayPrefsStore()
      store.setUnit('yuan')
      expect(store.amountUnit).toBe('yuan')
      expect(store.unitSuffix).toBe('元')
      expect(store.unitDivisor).toBe(1)
    })

    it('fmt 按单位格式化金额', () => {
      const store = useDisplayPrefsStore()
      store.setUnit('wan')
      // 10000 元 / 10000 = 1.00 万元
      expect(store.fmt(10000)).toBe('1.00')
      // 0 不显示（showZero=false）
      expect(store.fmt(0)).toBe('-')
    })

    it('fmt 万元单位格式化', () => {
      const store = useDisplayPrefsStore()
      store.setUnit('wan')
      expect(store.fmt(12345678)).toBe('1,234.57')
    })
  })

  describe('amountClass 条件样式', () => {
    it('负数且 negativeRed=true 返回 negative 类', () => {
      const store = useDisplayPrefsStore()
      expect(store.amountClass(-100)).toContain('gt-amount--negative')
    })

    it('正数不返回 negative 类', () => {
      const store = useDisplayPrefsStore()
      expect(store.amountClass(100)).not.toContain('gt-amount--negative')
    })

    it('变动超阈值返回 highlight 类', () => {
      const store = useDisplayPrefsStore()
      store.setHighlightThreshold(0.1) // 10%
      // 从 100 变到 120 = 20% 变动率 > 10% 阈值
      expect(store.amountClass(120, 100)).toContain('gt-amount--highlight')
    })

    it('变动未超阈值不返回 highlight', () => {
      const store = useDisplayPrefsStore()
      store.setHighlightThreshold(0.5) // 50%
      // 从 100 变到 120 = 20% < 50%
      expect(store.amountClass(120, 100)).not.toContain('gt-amount--highlight')
    })
  })

  describe('localStorage 恢复', () => {
    it('未分区的旧键不迁移、不读取，store 保持平台默认', () => {
      localStorage.setItem(DISPLAY_PREFERENCES_LEGACY_KEY, JSON.stringify({
        amountUnit: 'wan',
        fontSize: 'lg',
        density: 'comfortable',
        showZero: true,
        decimals: 4,
        negativeRed: false,
        highlightThreshold: 0,
        fixedColumns: { 'test-page': ['col1'] },
      }))

      const store = useDisplayPrefsStore()
      expect(store.amountUnit).toBe('yuan')
      expect(store.fontSize).toBe('sm')
      expect(store.density).toBe('default')
      expect(store.showZero).toBe(false)
      expect(store.decimals).toBe(2)
      expect(store.getFixedColumns('test-page')).toEqual([])
    })
  })
})

describe('displayPrefs 格式化统一出口', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  describe('fmt null/非数字 guard', () => {
    it('null → "—"', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmt(null)).toBe('—')
    })

    it('undefined → "—"', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmt(undefined)).toBe('—')
    })

    it('非数字字符串 → "—"', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmt('abc')).toBe('—')
    })

    it('NaN → "—"', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmt(NaN)).toBe('—')
    })
  })

  describe('fmt rawUnit 选项', () => {
    it('rawUnit=true 不做单位换算', () => {
      const store = useDisplayPrefsStore()
      store.setUnit('wan')
      // 正常 fmt 会除以 10000：10000 → 1.00
      expect(store.fmt(10000)).toBe('1.00')
      // rawUnit=true：10000 原样格式化
      expect(store.fmt(10000, { rawUnit: true })).toBe('10,000.00')
    })

    it('rawUnit + showZero=false + 值为0 → "-"（与非 rawUnit、GtAmountCell 同一占位）', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmt(0, { rawUnit: true })).toBe('-')
      expect(store.fmt(0)).toBe('-')
    })
  })

  describe('fmtAmount 别名', () => {
    it('fmtAmount 与 fmt 返回相同结果', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmtAmount(12345)).toBe(store.fmt(12345))
      expect(store.fmtAmount(null)).toBe(store.fmt(null))
    })
  })

  describe('fmtPercent', () => {
    it('正常数值格式化为百分比', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmtPercent(12.345)).toBe('12.3%')
      expect(store.fmtPercent(12.345, 2)).toBe('12.35%')
    })

    it('null → "—"', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmtPercent(null)).toBe('—')
    })

    it('非数字 → "—"', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmtPercent('abc')).toBe('—')
    })
  })

  describe('fmtDateTime', () => {
    it('null → "-"', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmtDateTime(null)).toBe('-')
    })

    it('undefined → "-"', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmtDateTime(undefined)).toBe('-')
    })

    it('非法日期 → "-"', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmtDateTime('not-a-date')).toBe('-')
    })

    it('有效 ISO 字符串返回非空格式化结果', () => {
      const store = useDisplayPrefsStore()
      const result = store.fmtDateTime('2025-06-15T14:30:00')
      expect(result).not.toBe('-')
      expect(result.length).toBeGreaterThan(5)
    })
  })
})
