/**
 * 显示偏好共享 normalizer 合同测试
 *
 * spec: platform-global-display-settings-closure 任务 4（design §3）
 * 约束：服务端响应与本机缓存都必须逐字段归一；任何一处损坏只回落自身默认值，
 * 不得抛异常、不得把越界值送进 Intl/Decimal。
 *
 * Validates: Requirements AC-04（损坏 JSON、decimals=999、范围保护）、AC-10（小数位）
 */
import { describe, it, expect } from 'vitest'
import {
  DISPLAY_PREFERENCES_CACHE_PREFIX,
  DISPLAY_PREFERENCES_CACHE_TTL_MS,
  DISPLAY_PREFERENCES_LEGACY_KEY,
  DISPLAY_PREFERENCES_MAX_FIXED_COLUMNS_PER_PAGE,
  DISPLAY_PREFERENCES_MAX_FIXED_PAGE_KEYS,
  DISPLAY_PREFERENCES_MAX_FIXED_STORAGE_BYTES,
  cloneDisplayPreferences,
  createDefaultDisplayPreferences,
  fixedColumnsFitStorage,
  isValidDisplayPreferenceScalar,
  isValidFixedColumnsPageKey,
  normalizeDecimals,
  normalizeDisplayPreferenceScalar,
  normalizeDisplayPreferences,
  normalizeFixedColumns,
  normalizeFixedColumnsColumns,
  toDisplayPreferencesPatchWire,
} from '@/utils/displayPreferencesNormalizer'

const SAVED_AT = '2026-11-01T00:00:00+00:00'

describe('显示偏好常量', () => {
  it('缓存键前缀按账号分区，旧键只用于删除', () => {
    expect(DISPLAY_PREFERENCES_CACHE_PREFIX).toBe('gt_display_prefs:v3:')
    expect(DISPLAY_PREFERENCES_LEGACY_KEY).toBe('gt_display_prefs')
    expect(DISPLAY_PREFERENCES_CACHE_PREFIX.startsWith(DISPLAY_PREFERENCES_LEGACY_KEY)).toBe(true)
    expect(DISPLAY_PREFERENCES_CACHE_PREFIX).not.toBe(DISPLAY_PREFERENCES_LEGACY_KEY)
  })

  it('TTL 恰为 30 天', () => {
    expect(DISPLAY_PREFERENCES_CACHE_TTL_MS).toBe(30 * 24 * 60 * 60 * 1000)
    expect(DISPLAY_PREFERENCES_CACHE_TTL_MS).toBe(2_592_000_000)
  })

  it('固定列上限与线协议一致', () => {
    expect(DISPLAY_PREFERENCES_MAX_FIXED_PAGE_KEYS).toBe(100)
    expect(DISPLAY_PREFERENCES_MAX_FIXED_COLUMNS_PER_PAGE).toBe(20)
    expect(DISPLAY_PREFERENCES_MAX_FIXED_STORAGE_BYTES).toBe(64 * 1024)
  })
})

describe('createDefaultDisplayPreferences', () => {
  it('完整默认合同：元、sm、2 位、0.2 阈值、空固定列', () => {
    expect(createDefaultDisplayPreferences()).toEqual({
      amountUnitOverride: null,
      fontSize: 'sm',
      showZero: false,
      decimals: 2,
      negativeRed: true,
      highlightThreshold: 0.2,
      density: 'default',
      gridEditMode: 'excel',
      fixedColumns: {},
      revision: 0,
      updatedAt: null,
    })
  })

  it('每次调用返回独立的 fixedColumns 对象', () => {
    const first = createDefaultDisplayPreferences()
    first.fixedColumns['page'] = { columns: ['a'], savedAt: SAVED_AT }
    expect(createDefaultDisplayPreferences().fixedColumns).toEqual({})
  })
})

describe('normalizeDisplayPreferences 字段归一', () => {
  it('接受服务端 snake_case 线格式', () => {
    const result = normalizeDisplayPreferences({
      amount_unit_override: 'wan',
      font_size: 'lg',
      show_zero: true,
      decimals: 4,
      negative_red: false,
      highlight_threshold: 0.5,
      density: 'compact',
      grid_edit_mode: 'classic',
      fixed_columns: { 'trial-balance': { columns: ['code'], saved_at: SAVED_AT } },
      revision: 7,
      updated_at: SAVED_AT,
    })
    expect(result).toEqual({
      amountUnitOverride: 'wan',
      fontSize: 'lg',
      showZero: true,
      decimals: 4,
      negativeRed: false,
      highlightThreshold: 0.5,
      density: 'compact',
      gridEditMode: 'classic',
      fixedColumns: { 'trial-balance': { columns: ['code'], savedAt: SAVED_AT } },
      revision: 7,
      updatedAt: SAVED_AT,
    })
  })

  it('接受本机缓存的 camelCase 格式', () => {
    const result = normalizeDisplayPreferences({
      amountUnitOverride: 'qian',
      fontSize: 'md',
      fixedColumns: { 'report-view:normal': { columns: ['row_code'], savedAt: SAVED_AT } },
      revision: 3,
    })
    expect(result.amountUnitOverride).toBe('qian')
    expect(result.fontSize).toBe('md')
    expect(result.fixedColumns['report-view:normal'].columns).toEqual(['row_code'])
    expect(result.revision).toBe(3)
  })

  it('非对象输入回落完整默认值', () => {
    for (const value of [null, undefined, 42, 'x', [], true]) {
      expect(normalizeDisplayPreferences(value)).toEqual(createDefaultDisplayPreferences())
    }
  })

  it('amount_unit_override 显式 null 保留为跟随项目', () => {
    expect(normalizeDisplayPreferences({ amount_unit_override: null }).amountUnitOverride).toBeNull()
  })

  it('非法枚举逐字段回落，不影响其他字段', () => {
    const result = normalizeDisplayPreferences({
      amount_unit_override: 'dollar',
      font_size: 'xxl',
      density: 'loose',
      grid_edit_mode: 'vim',
      show_zero: 'yes',
      negative_red: 1,
      decimals: 4,
    })
    expect(result.amountUnitOverride).toBeNull()
    expect(result.fontSize).toBe('sm')
    expect(result.density).toBe('default')
    expect(result.gridEditMode).toBe('excel')
    expect(result.showZero).toBe(false)
    expect(result.negativeRed).toBe(true)
    // 合法字段不被相邻的损坏字段牵连
    expect(result.decimals).toBe(4)
  })

  it('decimals 越界、非整数、字符串全部回落 2', () => {
    expect(normalizeDecimals(999)).toBe(2)
    expect(normalizeDecimals(-1)).toBe(2)
    expect(normalizeDecimals(7)).toBe(2)
    expect(normalizeDecimals(2.5)).toBe(2)
    expect(normalizeDecimals('3')).toBe(2)
    expect(normalizeDecimals(NaN)).toBe(2)
    expect(normalizeDecimals(Infinity)).toBe(2)
    expect(normalizeDecimals(0)).toBe(0)
    expect(normalizeDecimals(6)).toBe(6)
  })

  it('decimals=999 的损坏缓存不会进入格式化路径', () => {
    expect(normalizeDisplayPreferences({ decimals: 999 }).decimals).toBe(2)
  })

  it('highlight_threshold 只接受 0~1 且最多 4 位小数的有限值', () => {
    expect(normalizeDisplayPreferences({ highlight_threshold: 0 }).highlightThreshold).toBe(0)
    expect(normalizeDisplayPreferences({ highlight_threshold: 1 }).highlightThreshold).toBe(1)
    expect(normalizeDisplayPreferences({ highlight_threshold: 0.1234 }).highlightThreshold).toBe(0.1234)
    expect(normalizeDisplayPreferences({ highlight_threshold: 0.12345 }).highlightThreshold).toBe(0.2)
    expect(normalizeDisplayPreferences({ highlight_threshold: -0.1 }).highlightThreshold).toBe(0.2)
    expect(normalizeDisplayPreferences({ highlight_threshold: 1.5 }).highlightThreshold).toBe(0.2)
    expect(normalizeDisplayPreferences({ highlight_threshold: 1e-7 }).highlightThreshold).toBe(0.2)
    expect(normalizeDisplayPreferences({ highlight_threshold: NaN }).highlightThreshold).toBe(0.2)
  })

  it('revision 与 updated_at 非法时回落', () => {
    expect(normalizeDisplayPreferences({ revision: -1 }).revision).toBe(0)
    expect(normalizeDisplayPreferences({ revision: 1.5 }).revision).toBe(0)
    expect(normalizeDisplayPreferences({ revision: '5' }).revision).toBe(0)
    expect(normalizeDisplayPreferences({ updated_at: 'not-a-date' }).updatedAt).toBeNull()
    expect(normalizeDisplayPreferences({ updated_at: '' }).updatedAt).toBeNull()
    expect(normalizeDisplayPreferences({ updated_at: SAVED_AT }).updatedAt).toBe(SAVED_AT)
  })
})

describe('fixed_columns 归一与上限', () => {
  it('列数组校验：类型、长度、去重、上限 20', () => {
    expect(normalizeFixedColumnsColumns(['a', 'b'])).toEqual(['a', 'b'])
    expect(normalizeFixedColumnsColumns([])).toEqual([])
    expect(normalizeFixedColumnsColumns(['a', 'a'])).toBeNull()
    expect(normalizeFixedColumnsColumns(['a', 1])).toBeNull()
    expect(normalizeFixedColumnsColumns([''])).toBeNull()
    expect(normalizeFixedColumnsColumns(['x'.repeat(101)])).toBeNull()
    expect(normalizeFixedColumnsColumns(['x'.repeat(100)])).toEqual(['x'.repeat(100)])
    expect(normalizeFixedColumnsColumns(Array.from({ length: 20 }, (_, i) => `c${i}`))).toHaveLength(20)
    expect(normalizeFixedColumnsColumns(Array.from({ length: 21 }, (_, i) => `c${i}`))).toBeNull()
    expect(normalizeFixedColumnsColumns('a,b')).toBeNull()
  })

  it('pageKey 长度 1~100', () => {
    expect(isValidFixedColumnsPageKey('a')).toBe(true)
    expect(isValidFixedColumnsPageKey('k'.repeat(100))).toBe(true)
    expect(isValidFixedColumnsPageKey('')).toBe(false)
    expect(isValidFixedColumnsPageKey('k'.repeat(101))).toBe(false)
    expect(isValidFixedColumnsPageKey(7)).toBe(false)
  })

  it('旧的裸数组值不再被接受（线协议已改为 {columns, saved_at}）', () => {
    expect(normalizeFixedColumns({ 'trial-balance': ['code', 'name'] })).toEqual({})
  })

  it('缺少 saved_at 或 saved_at 非法的条目被丢弃', () => {
    expect(normalizeFixedColumns({ a: { columns: ['x'] } })).toEqual({})
    expect(normalizeFixedColumns({ a: { columns: ['x'], saved_at: 'bad' } })).toEqual({})
    expect(normalizeFixedColumns({ a: { columns: ['x'], saved_at: SAVED_AT } })).toEqual({
      a: { columns: ['x'], savedAt: SAVED_AT },
    })
  })

  it('超过 100 个键时按键名排序截断到 100', () => {
    const source: Record<string, unknown> = {}
    for (let i = 0; i < 130; i += 1) {
      source[`page-${String(i).padStart(3, '0')}`] = { columns: ['a'], saved_at: SAVED_AT }
    }
    const normalized = normalizeFixedColumns(source)
    expect(Object.keys(normalized)).toHaveLength(DISPLAY_PREFERENCES_MAX_FIXED_PAGE_KEYS)
    expect(normalized['page-000']).toBeDefined()
    expect(normalized['page-099']).toBeDefined()
    expect(normalized['page-100']).toBeUndefined()
  })

  it('规范 JSON 超过 64KiB 时整份固定列丢弃', () => {
    const big: Record<string, unknown> = {}
    for (let i = 0; i < 100; i += 1) {
      big[`page-${String(i).padStart(3, '0')}-${'k'.repeat(70)}`] = {
        columns: Array.from({ length: 20 }, (_, c) => `column-${c}-${'v'.repeat(80)}`),
        saved_at: SAVED_AT,
      }
    }
    expect(fixedColumnsFitStorage(big as never)).toBe(false)
    expect(normalizeFixedColumns(big)).toEqual({})
  })

  it('空固定列与小载荷在存储限制内', () => {
    expect(fixedColumnsFitStorage({})).toBe(true)
    expect(fixedColumnsFitStorage({ a: { columns: ['x'], savedAt: SAVED_AT } })).toBe(true)
  })
})

describe('逐字段校验与归一（缓存恢复用）', () => {
  it('isValidDisplayPreferenceScalar 对每个字段闭合', () => {
    expect(isValidDisplayPreferenceScalar('amountUnitOverride', null)).toBe(true)
    expect(isValidDisplayPreferenceScalar('amountUnitOverride', 'wan')).toBe(true)
    expect(isValidDisplayPreferenceScalar('amountUnitOverride', 'dollar')).toBe(false)
    expect(isValidDisplayPreferenceScalar('fontSize', 'lg')).toBe(true)
    expect(isValidDisplayPreferenceScalar('fontSize', 'xxl')).toBe(false)
    expect(isValidDisplayPreferenceScalar('showZero', true)).toBe(true)
    expect(isValidDisplayPreferenceScalar('showZero', 'true')).toBe(false)
    expect(isValidDisplayPreferenceScalar('decimals', 6)).toBe(true)
    expect(isValidDisplayPreferenceScalar('decimals', 999)).toBe(false)
    expect(isValidDisplayPreferenceScalar('highlightThreshold', 0.25)).toBe(true)
    expect(isValidDisplayPreferenceScalar('highlightThreshold', 0.123456)).toBe(false)
    expect(isValidDisplayPreferenceScalar('density', 'comfortable')).toBe(true)
    expect(isValidDisplayPreferenceScalar('density', 'loose')).toBe(false)
    expect(isValidDisplayPreferenceScalar('gridEditMode', 'click')).toBe(true)
    expect(isValidDisplayPreferenceScalar('gridEditMode', 'vim')).toBe(false)
  })

  it('normalizeDisplayPreferenceScalar 把越界值收进安全范围', () => {
    expect(normalizeDisplayPreferenceScalar('decimals', 999)).toBe(2)
    expect(normalizeDisplayPreferenceScalar('highlightThreshold', 5)).toBe(0.2)
    expect(normalizeDisplayPreferenceScalar('amountUnitOverride', 'dollar')).toBeNull()
    expect(normalizeDisplayPreferenceScalar('amountUnitOverride', null)).toBeNull()
    expect(normalizeDisplayPreferenceScalar('fontSize', undefined)).toBe('sm')
    expect(normalizeDisplayPreferenceScalar('density', 'compact')).toBe('compact')
    expect(normalizeDisplayPreferenceScalar('showZero', 'x')).toBe(false)
    expect(normalizeDisplayPreferenceScalar('negativeRed', 'x')).toBe(true)
    expect(normalizeDisplayPreferenceScalar('gridEditMode', 42)).toBe('excel')
  })
})

describe('cloneDisplayPreferences', () => {
  it('固定列深拷贝，改副本不影响原值', () => {
    const source = createDefaultDisplayPreferences()
    source.fixedColumns['page'] = { columns: ['a', 'b'], savedAt: SAVED_AT }
    const copy = cloneDisplayPreferences(source)
    copy.fixedColumns['page'].columns.push('c')
    delete copy.fixedColumns['other']
    expect(source.fixedColumns['page'].columns).toEqual(['a', 'b'])
    expect(copy.fixedColumns['page'].savedAt).toBe(SAVED_AT)
  })
})

describe('toDisplayPreferencesPatchWire', () => {
  it('只发送已提交字段，不补未提交字段', () => {
    const wire = toDisplayPreferencesPatchWire({ baseRevision: 4, fontSize: 'lg' })
    expect(wire).toEqual({ base_revision: 4, font_size: 'lg' })
    expect('amount_unit_override' in wire).toBe(false)
    expect('decimals' in wire).toBe(false)
  })

  it('跟随项目单位时显式发送 amount_unit_override: null', () => {
    const wire = toDisplayPreferencesPatchWire({ baseRevision: 1, amountUnitOverride: null })
    expect('amount_unit_override' in wire).toBe(true)
    expect(wire.amount_unit_override).toBeNull()
  })

  it('固定列只发送 columns（saved_at 由服务端写）', () => {
    const wire = toDisplayPreferencesPatchWire({
      baseRevision: 2,
      fixedColumns: { 'trial-balance': { columns: ['code'] } },
    })
    expect(wire.fixed_columns).toEqual({ 'trial-balance': { columns: ['code'] } })
  })

  it('全部标量字段逐一映射为 snake_case', () => {
    const wire = toDisplayPreferencesPatchWire({
      baseRevision: 9,
      amountUnitOverride: 'wan',
      fontSize: 'md',
      showZero: true,
      decimals: 3,
      negativeRed: false,
      highlightThreshold: 0.3,
      density: 'compact',
      gridEditMode: 'classic',
    })
    expect(wire).toEqual({
      base_revision: 9,
      amount_unit_override: 'wan',
      font_size: 'md',
      show_zero: true,
      decimals: 3,
      negative_red: false,
      highlight_threshold: 0.3,
      density: 'compact',
      grid_edit_mode: 'classic',
    })
  })
})
