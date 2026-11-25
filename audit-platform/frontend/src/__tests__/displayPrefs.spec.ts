/**
 * displayPrefs store 测试
 * 覆盖：density/fontSize/amountUnit/fixedColumns 扩展
 *
 * Validates: Requirements 6.1, 6.2, 6.3
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDisplayPrefsStore, TABLE_DENSITIES } from '@/stores/displayPrefs'

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
    it('setDensity 切换密度并持久化', () => {
      const store = useDisplayPrefsStore()
      store.setDensity('compact')
      expect(store.density).toBe('compact')
      // 持久化自 218d6e20c 起是账号级（服务端 + gt_display_prefs:v3:<userId> 缓存），
      // 由 stores/__tests__/displayPrefsSync.spec.ts 覆盖；旧单键 gt_display_prefs 已废弃。
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

    it('setFixedColumns 后同页读回（持久化见 displayPrefsSync.spec.ts）', () => {
      const store = useDisplayPrefsStore()
      store.setFixedColumns('report-view', ['row_name'])
      expect(store.getFixedColumns('report-view')).toEqual(['row_name'])
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

  // 原「从旧单键 gt_display_prefs 恢复偏好」随 218d6e20c 账号级偏好改造废弃
  // （旧键内容按设计不迁移，见 displayPrefsSync.spec.ts「旧键的内容不迁移到新键」），用例删除。
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

    // 零值按审计惯例显示「-」（与 GtAmountCell / displayPrefsSync 同口径）；「—」只用于缺值/非数字
    it('rawUnit + showZero=false + 值为0 → "-"', () => {
      const store = useDisplayPrefsStore()
      expect(store.fmt(0, { rawUnit: true })).toBe('-')
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
