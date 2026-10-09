/**
 * I3 披露层行身份：从「位置」改成「值」（spec `i1-i3-disclosure-positional-identity-and-classification-source`）
 *
 * 覆盖 Task 4~7 / Task 9：
 *   · 族 A′ `cgu_allocation`：删中间一行后重新取数，剩余行 rowId 不变（ID-6 组合判据）
 *   · 族 B 矩阵行：上游无 rowId 时按被投资单位复用旧 id，不回落下标
 *   · 族 D 批量预填：同一毫秒两次批量也不撞 id
 *   · grandfather：已落库的旧格式 `cgu-3` 原值保留，不被重写成新格式
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() } }))

import {
  useI3Disclosure,
  _stableRowId,
  _rowIdReuser,
  LEGACY_POSITIONAL_ROW_ID_RE,
} from '../useI3Disclosure'
import { draftTitleRowsFromI18 } from '../i1DisclosureEnhance'

const NEW_FORMAT_RE = /^(cgu|bv|imp|perf|ap|tc-i18)-[0-9a-z]+-[0-9a-z]{4,6}$/

function detailRow(investee: string, cguName: string, extra: Record<string, unknown> = {}) {
  return { investee, cguName, costOpening: 100, costAudited: 100, impAudited: 0, ...extra }
}

function setup(detail: any[], persisted: Record<string, unknown> = {}) {
  const map = new Map<string, any>()
  map.set('I3-2-rows', { remark: JSON.stringify(detail) })
  for (const [k, v] of Object.entries(persisted)) map.set(k, { remark: JSON.stringify(v) })
  const allResponses = ref(map)
  const saved: Record<string, any> = {}
  const d = useI3Disclosure(ref('wp-1'), ref('p-1'), allResponses as any, {
    variant: ref('listed'),
    onSave: (itemId, value) => { saved[itemId] = JSON.parse(JSON.stringify(value)) },
  })
  const setDetail = (rows: any[]) => {
    // 只换 I3-2 明细，不触发 _loadData 之外的副作用：直接改 map 内容
    map.set('I3-2-rows', { remark: JSON.stringify(rows) })
  }
  return { d, saved, setDetail }
}

describe('ID-1 生成器', () => {
  it('新格式符合 design 正则，且签名不接受下标', () => {
    expect(_stableRowId('cgu')).toMatch(NEW_FORMAT_RE)
    expect(_stableRowId.length).toBe(1)
  })

  it('旧格式正则只认「前缀 + 纯数字」', () => {
    expect(LEGACY_POSITIONAL_ROW_ID_RE.test('cgu-3')).toBe(true)
    expect(LEGACY_POSITIONAL_ROW_ID_RE.test('tc-i18-0')).toBe(true)
    expect(LEGACY_POSITIONAL_ROW_ID_RE.test(_stableRowId('cgu'))).toBe(false)
  })

  it('reuser 按值逐个消费，同名多行不共用一个 id', () => {
    const reuse = _rowIdReuser([{ rowId: 'a1', n: 'X' }, { rowId: 'a2', n: 'X' }], (r) => r.n)
    expect(reuse('X', 'cgu')).toBe('a1')
    expect(reuse('X', 'cgu')).toBe('a2')
    expect(reuse('X', 'cgu')).toMatch(NEW_FORMAT_RE)
  })
})

describe('族 D：同一毫秒两次批量预填不撞 id（修复前 `perf-${Date.now()}-${added}` 必撞）', () => {
  beforeEach(() => { vi.spyOn(Date, 'now').mockReturnValue(1_700_000_000_000) })
  afterEach(() => { vi.restoreAllMocks() })

  it('seedPerformanceFromBookValue × 2 + seedAssumptionFromCgu × 2', () => {
    const { d } = setup([])
    d.bookValueRows.value = [
      { rowId: 'bv-x1', investee: 'A公司', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isAutoFilled: false },
    ]
    d.seedPerformanceFromBookValue()
    d.bookValueRows.value = [
      { rowId: 'bv-x2', investee: 'B公司', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isAutoFilled: false },
    ]
    d.seedPerformanceFromBookValue()
    const perfIds = d.performanceRows.value.map((r) => r.rowId)
    expect(perfIds).toHaveLength(2)
    expect(new Set(perfIds).size).toBe(2)

    d.sectionRows.value.cgu_allocation = [{ rowId: 'c1', name: 'CGU-1', amount: 0, description: '', remark: '' }]
    d.seedAssumptionFromCgu()
    d.sectionRows.value.cgu_allocation = [{ rowId: 'c2', name: 'CGU-2', amount: 0, description: '', remark: '' }]
    d.seedAssumptionFromCgu()
    const apIds = d.assumptionParamRows.value.map((r) => r.rowId)
    expect(apIds).toHaveLength(2)
    expect(new Set(apIds).size).toBe(2)
  })
})

describe('ID-6 组合判据：按下标删中间一行 × 行身份（族 A′ / 族 B）', () => {
  it('5 个 CGU 删第 3 个后重新取数，剩余 4 行 rowId == 原 1/2/4/5 行', () => {
    const names = ['CGU-1', 'CGU-2', 'CGU-3', 'CGU-4', 'CGU-5']
    const detail = names.map((c, k) => detailRow(`公司${k + 1}`, c))
    const { d, setDetail } = setup(detail)
    d.pullFromDetailRows({ overwrite: true })
    const before = new Map(d.sectionRows.value.cgu_allocation.map((r) => [r.name, r.rowId]))
    const bvBefore = new Map(d.bookValueRows.value.map((r) => [r.investee, r.rowId]))
    expect(new Set(before.values()).size).toBe(5)

    const after = detail.filter((_, k) => k !== 2)
    setDetail(after)
    d.pullFromDetailRows({ overwrite: true })
    const cgu = d.sectionRows.value.cgu_allocation
    expect(cgu.map((r) => r.name)).toEqual(['CGU-1', 'CGU-2', 'CGU-4', 'CGU-5'])
    for (const r of cgu) expect(r.rowId).toBe(before.get(r.name))
    for (const r of d.bookValueRows.value) expect(r.rowId).toBe(bvBefore.get(r.investee))
  })

  it('上游 I3-2 行自带 rowId 时仍以上游为准（不被旧池反向覆盖）', () => {
    const { d } = setup([detailRow('公司1', 'CGU-1', { rowId: 'up-1' })])
    d.bookValueRows.value = [
      { rowId: 'bv-0', investee: '公司1', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isAutoFilled: false },
    ]
    d.pullFromDetailRows({ overwrite: true })
    expect(d.bookValueRows.value[0].rowId).toBe('bv-up-1')
    expect(d.impairmentRows.value[0].rowId).toBe('imp-up-1')
  })

  it('上游无 rowId 的新行生成新格式 id，不再是 `bv-0` / `cgu-0`', () => {
    const { d } = setup([detailRow('公司1', 'CGU-1'), detailRow('公司2', 'CGU-2')])
    d.pullFromDetailRows({ overwrite: true })
    for (const r of [...d.bookValueRows.value, ...d.impairmentRows.value, ...d.sectionRows.value.cgu_allocation]) {
      expect(r.rowId).toMatch(NEW_FORMAT_RE)
    }
  })
})

describe('ID-P4 grandfather：已落库旧格式 id 原值保留', () => {
  it('历史 `cgu-3` / `bv-0` 重读后不变，重新取数后（同名）仍不变', () => {
    const persisted = {
      'I3-disc-listed-cgu_allocation-rows': [{ rowId: 'cgu-3', name: 'CGU-A', amount: 1, description: '', remark: '' }],
      'I3-disc-listed-book-value-matrix': [
        { rowId: 'bv-0', investee: '公司A', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isAutoFilled: true },
      ],
    }
    const { d, saved } = setup([detailRow('公司A', 'CGU-A'), detailRow('公司B', 'CGU-B')], persisted)
    // ① 重读：原值
    expect(d.sectionRows.value.cgu_allocation[0].rowId).toBe('cgu-3')
    expect(d.bookValueRows.value[0].rowId).toBe('bv-0')
    // ② 重新取数：同名行沿用旧 id，新行才用新格式
    d.pullFromDetailRows({ overwrite: true })
    const byName = new Map(d.sectionRows.value.cgu_allocation.map((r) => [r.name, r.rowId]))
    expect(byName.get('CGU-A')).toBe('cgu-3')
    expect(byName.get('CGU-B')).toMatch(NEW_FORMAT_RE)
    expect(d.bookValueRows.value.find((r) => r.investee === '公司A')?.rowId).toBe('bv-0')
    // ③ 落库载荷与内存一致（写入后重读不随行序变）
    const cguSaved = saved['I3-disc-listed-cgu_allocation-rows'] as any[]
    expect(cguSaved.find((r) => r.name === 'CGU-A').rowId).toBe('cgu-3')
  })
})

describe('族 B：i1DisclosureEnhance.draftTitleRowsFromI18', () => {
  it('有上游 rowId 用上游；无则新格式，不回落 filter 后下标', () => {
    const rows = draftTitleRowsFromI18([
      { rowId: 'r9', name: '土地A', hasCertificate: 'N', netBookValue: 1 },
      { name: '专利B', hasCertificate: 'N', netBookValue: 2 },
    ])
    expect(rows[0].rowId).toBe('tc-i18-r9')
    expect(rows[1].rowId).toMatch(NEW_FORMAT_RE)
    expect(rows[1].rowId).not.toBe('tc-i18-1')
  })
})
