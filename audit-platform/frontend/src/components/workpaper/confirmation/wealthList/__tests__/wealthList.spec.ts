/**
 * wealthList.spec.ts — E0-6 理财产品发函记录表 专属组件契约
 *
 * 锁死点（源模板 `理财产品发函记录表E0-6` 为唯一裁决者）：
 * - 11 列 label 与单元格逐字（守卫后端另有 openpyxl 直读交叉比对）
 * - 「产品净值」是总额口径 → 合计 = Σ 净值，**不是** Σ(份额 × 净值)
 * - 汇总键 = 索引号 + 产品名称（源 E0-1 F 列 SUMIFS 的两个 criteria）
 * - 已到期判定 = 到期日 ≤ 报表截止日；任一为空不判定
 * - 源模板无「是否函证」列 → 数据不因此被过滤
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  WEALTH_LIST_COLUMN_SOURCE,
  WEALTH_LIST_HEADER_NOTE,
  type WealthProductRow,
} from '../wealthListTypes'
import {
  WEALTH_PRODUCT_TYPES,
  WEALTH_RESTRICTED_OPTIONS,
} from '../wealthListEnums'
import {
  buildWealthListMetrics,
  hasSummaryKey,
  isMatured,
  isRestricted,
  rowQualityStatus,
  toNum,
} from '../composables/useWealthListData'

// 源模板 R5 逐字（openpyxl 读值：A5..K5）
const SOURCE_HEADERS_A5_K5 = [
  '索引号',
  '报表截止日',
  '开户行名称及收件人',
  '产品名称',
  '产品类型（封闭式/开放式）',
  '币种',
  '持有份额',
  '产品净值',
  '购买日',
  '到期日',
  '是否被用于担保或存在其他使用限制',
]

describe('E0-6 列集与源模板逐字一致', () => {
  it('11 列，顺序与 label 逐字命中源 A5:K5', () => {
    expect(WEALTH_LIST_COLUMN_SOURCE).toHaveLength(11)
    expect(WEALTH_LIST_COLUMN_SOURCE.map((c) => c.label)).toEqual(SOURCE_HEADERS_A5_K5)
  })

  it('单元格引用为 A5..K5 连续', () => {
    expect(WEALTH_LIST_COLUMN_SOURCE.map((c) => c.cell)).toEqual([
      'A5', 'B5', 'C5', 'D5', 'E5', 'F5', 'G5', 'H5', 'I5', 'J5', 'K5',
    ])
  })

  it('field 名唯一', () => {
    const fields = WEALTH_LIST_COLUMN_SOURCE.map((c) => c.field)
    expect(new Set(fields).size).toBe(fields.length)
  })

  it('枚举取自源模板：产品类型两项、是否受限两项', () => {
    expect([...WEALTH_PRODUCT_TYPES]).toEqual(['封闭式', '开放式'])
    expect([...WEALTH_RESTRICTED_OPTIONS]).toEqual(['是', '否'])
  })

  it('顶部说明明确「产品净值为总额口径」且「持有份额不参与金额计算」', () => {
    expect(WEALTH_LIST_HEADER_NOTE).toContain('总额口径')
    expect(WEALTH_LIST_HEADER_NOTE).toContain('不参与金额计算')
  })

  it('反向自检：源模板没有「是否函证」列', () => {
    expect(SOURCE_HEADERS_A5_K5).not.toContain('是否函证')
    expect(WEALTH_LIST_COLUMN_SOURCE.map((c) => c.label)).not.toContain('是否函证')
  })
})

describe('汇总键（对应 E0-1 F 列 SUMIFS 的两个 criteria）', () => {
  it('索引号与产品名称同时非空才算完整', () => {
    expect(hasSummaryKey({ confirm_index: 'E0-6-1', product_name: 'A产品' })).toBe(true)
    expect(hasSummaryKey({ confirm_index: 'E0-6-1' })).toBe(false)
    expect(hasSummaryKey({ product_name: 'A产品' })).toBe(false)
    expect(hasSummaryKey({})).toBe(false)
  })

  it('纯空白不算填写', () => {
    expect(hasSummaryKey({ confirm_index: '  ', product_name: 'A' })).toBe(false)
  })
})

describe('已到期判定', () => {
  it('到期日 ≤ 报表截止日 → 已到期', () => {
    expect(isMatured({ maturity_date: '2025-12-31', cutoff_date: '2025-12-31' })).toBe(true)
    expect(isMatured({ maturity_date: '2025-06-30', cutoff_date: '2025-12-31' })).toBe(true)
  })

  it('到期日晚于截止日 → 未到期', () => {
    expect(isMatured({ maturity_date: '2026-06-30', cutoff_date: '2025-12-31' })).toBe(false)
  })

  it('任一为空不判定（不猜测）', () => {
    expect(isMatured({ maturity_date: '2025-01-01' })).toBe(false)
    expect(isMatured({ cutoff_date: '2025-12-31' })).toBe(false)
    expect(isMatured({})).toBe(false)
  })
})

describe('受限判定', () => {
  it('仅「是」算受限', () => {
    expect(isRestricted({ restricted: '是' })).toBe(true)
    expect(isRestricted({ restricted: '否' })).toBe(false)
    expect(isRestricted({})).toBe(false)
  })
})

describe('看板指标', () => {
  const rows: WealthProductRow[] = [
    {
      confirm_index: 'E0-6-1', product_name: 'A产品', product_type: '封闭式',
      units_held: 1000, net_value: 1000000, restricted: '否',
      cutoff_date: '2025-12-31', maturity_date: '2026-06-30',
    },
    {
      confirm_index: 'E0-6-2', product_name: 'B产品', product_type: '开放式',
      units_held: 500, net_value: 500000, restricted: '是',
      cutoff_date: '2025-12-31', maturity_date: '2025-11-30',
    },
    // 汇总键缺失（无产品名称）
    {
      confirm_index: 'E0-6-3', product_type: '开放式',
      units_held: 200, net_value: 200000, restricted: '否',
      bank_and_recipient: '某行',
    },
  ]

  it('金额合计 = Σ 产品净值（不乘份额）', () => {
    const m = buildWealthListMetrics(rows)
    expect(m.net_value_total).toBe(1_700_000)
    // 反向自检：若误按 Σ(份额×净值) 会是 10 亿量级
    expect(m.net_value_total).not.toBe(1000 * 1000000 + 500 * 500000 + 200 * 200000)
  })

  it('份额合计独立求和', () => {
    expect(buildWealthListMetrics(rows).units_total).toBe(1700)
  })

  it('受限笔数与受限金额', () => {
    const m = buildWealthListMetrics(rows)
    expect(m.restricted_count).toBe(1)
    expect(m.restricted_amount).toBe(500_000)
  })

  it('已到期笔数', () => {
    expect(buildWealthListMetrics(rows).matured_count).toBe(1)
  })

  it('封闭式/开放式分布', () => {
    const m = buildWealthListMetrics(rows)
    expect(m.closed_count).toBe(1)
    expect(m.open_count).toBe(2)
  })

  it('汇总键缺失笔数', () => {
    expect(buildWealthListMetrics(rows).missing_key_count).toBe(1)
  })

  it('空表全零且不抛', () => {
    const m = buildWealthListMetrics([])
    expect(m.total_count).toBe(0)
    expect(m.net_value_total).toBe(0)
    expect(m.missing_key_count).toBe(0)
  })
})

describe('行质量状态', () => {
  it('全空白新行不打警示', () => {
    expect(rowQualityStatus({})).toBe('ok')
  })

  it('有内容但缺汇总键 → danger', () => {
    expect(rowQualityStatus({ bank_and_recipient: '某行', net_value: 100 })).toBe('danger')
  })

  it('键完整但已到期 → warning', () => {
    expect(rowQualityStatus({
      confirm_index: 'E0-6-1', product_name: 'A', net_value: 100,
      cutoff_date: '2025-12-31', maturity_date: '2025-01-01',
    })).toBe('warning')
  })

  it('键完整、未到期、金额为 0 → warning', () => {
    expect(rowQualityStatus({
      confirm_index: 'E0-6-1', product_name: 'A', net_value: 0,
      bank_and_recipient: '某行',
    })).toBe('warning')
  })

  it('键完整、未到期、有金额 → ok', () => {
    expect(rowQualityStatus({
      confirm_index: 'E0-6-1', product_name: 'A', net_value: 100,
      cutoff_date: '2025-12-31', maturity_date: '2026-12-31',
    })).toBe('ok')
  })
})

describe('数值归一', () => {
  it('非有限值一律 0（防 NaN 进合计）', () => {
    expect(toNum(undefined)).toBe(0)
    expect(toNum(null)).toBe(0)
    expect(toNum('abc')).toBe(0)
    expect(toNum(Infinity)).toBe(0)
    expect(toNum(NaN)).toBe(0)
    expect(toNum('1234.5')).toBe(1234.5)
  })
})

describe('Property: 指标恒不产生 NaN / Infinity（PBT）', () => {
  const amount = () => fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })

  it('任意行集下 net_value_total / restricted_amount 有限，计数不超过总行数', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            confirm_index: fc.option(fc.string(), { nil: undefined }),
            product_name: fc.option(fc.string(), { nil: undefined }),
            net_value: fc.option(amount(), { nil: undefined }),
            units_held: fc.option(amount(), { nil: undefined }),
            restricted: fc.option(fc.constantFrom('是', '否'), { nil: undefined }),
            product_type: fc.option(fc.constantFrom('封闭式', '开放式'), { nil: undefined }),
          }),
          { maxLength: 40 },
        ),
        (raw) => {
          const m = buildWealthListMetrics(raw as WealthProductRow[])
          expect(Number.isFinite(m.net_value_total)).toBe(true)
          expect(Number.isFinite(m.restricted_amount)).toBe(true)
          expect(Number.isFinite(m.units_total)).toBe(true)
          expect(m.total_count).toBe(raw.length)
          for (const k of [
            'restricted_count', 'matured_count', 'closed_count',
            'open_count', 'missing_key_count', 'zero_amount_count',
          ] as const) {
            expect(m[k]).toBeGreaterThanOrEqual(0)
            expect(m[k]).toBeLessThanOrEqual(raw.length)
          }
        },
      ),
      { numRuns: 60 },
    )
  })

  it('受限金额 ⊆ 全部金额：受限行金额之和与独立累加一致', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            net_value: amount(),
            restricted: fc.constantFrom('是', '否'),
          }),
          { maxLength: 30 },
        ),
        (raw) => {
          const m = buildWealthListMetrics(raw as WealthProductRow[])
          const expected = Math.round(
            raw.filter((r) => r.restricted === '是').reduce((s, r) => s + r.net_value, 0) * 100,
          ) / 100
          expect(m.restricted_amount).toBeCloseTo(expected, 2)
        },
      ),
      { numRuns: 60 },
    )
  })
})
