/**
 * LedgerPenetration 虚拟滚动模式 — V3 Req 12.2.2 单测
 *
 * 验证：
 *  - 行选择 key 生成幂等
 *  - 列宽边界 [60, 800]
 *  - 排序比较器：数字优先 / 字符串 fallback
 *  - 筛选：摘要关键字（不区分大小写）+ 借/贷方向
 *  - 重置：状态归零
 *
 * 直接测试纯函数逻辑（避免 mount el-table-v2，CI 稳定）
 */
import { describe, it, expect } from 'vitest'
import { buildLedgerDisplay } from '@/utils/ledgerDisplay'

// ─── 复制被测的纯函数（保持与生产实现 1:1 对齐） ────────────────────────────

function rowKeyOf(row: any): string {
  if (!row) return ''
  if (row.id) return `id:${row.id}`
  if (row._type) return `${row._type}:${row.voucher_date || ''}:${row.summary || ''}`
  return `${row.voucher_date || ''}:${row.voucher_no || ''}:${row.summary || ''}`
}

function clampWidth(w: number): number {
  return Math.max(60, Math.min(800, w))
}

function sortRows(
  rows: any[],
  sort: { key: string; order: 'asc' | 'desc' } | null,
): any[] {
  if (!sort) return rows
  const factor = sort.order === 'desc' ? -1 : 1
  return rows.slice().sort((a: any, b: any) => {
    const av = a[sort.key]
    const bv = b[sort.key]
    const an = typeof av === 'number' ? av : parseFloat(av)
    const bn = typeof bv === 'number' ? bv : parseFloat(bv)
    if (Number.isFinite(an) && Number.isFinite(bn)) return (an - bn) * factor
    return String(av ?? '').localeCompare(String(bv ?? '')) * factor
  })
}

function filterRows(
  rows: any[],
  kw: string,
  dir: 'all' | 'debit' | 'credit',
): any[] {
  let out = rows
  const k = kw.trim().toLowerCase()
  if (k) {
    out = out.filter((r) => {
      const summary = String(r.summary || '').toLowerCase()
      const voucherNo = String(r.voucher_no || '').toLowerCase()
      return summary.includes(k) || voucherNo.includes(k)
    })
  }
  if (dir === 'debit') {
    out = out.filter((r) => Number(r.debit_amount || 0) > 0)
  } else if (dir === 'credit') {
    out = out.filter((r) => Number(r.credit_amount || 0) > 0)
  }
  return out
}

// ─── tests ──────────────────────────────────────────────────────────────────

describe('LedgerPenetration virtual mode — rowKeyOf', () => {
  it('优先使用 id', () => {
    expect(rowKeyOf({ id: 'abc-123' })).toBe('id:abc-123')
    expect(rowKeyOf({ id: 'abc-123', _type: 'normal' })).toBe('id:abc-123')
  })

  it('期初/小计行使用 _type+date+summary', () => {
    expect(rowKeyOf({ _type: 'opening', summary: '期初余额' })).toBe('opening::期初余额')
    expect(rowKeyOf({ _type: 'subtotal', voucher_date: '2025-01', summary: '本月合计' })).toBe(
      'subtotal:2025-01:本月合计',
    )
  })

  it('普通行 fallback 到 date+no+summary', () => {
    expect(rowKeyOf({ voucher_date: '2025-01-15', voucher_no: 'A001', summary: '收款' })).toBe(
      '2025-01-15:A001:收款',
    )
  })

  it('null/undefined 安全', () => {
    expect(rowKeyOf(null)).toBe('')
    expect(rowKeyOf(undefined)).toBe('')
  })

  it('相同输入产生相同 key（幂等）', () => {
    const row = { id: 42, voucher_no: 'B001' }
    expect(rowKeyOf(row)).toBe(rowKeyOf(row))
  })
})

describe('LedgerPenetration virtual mode — column width', () => {
  it('低于 60 强制为 60', () => {
    expect(clampWidth(30)).toBe(60)
    expect(clampWidth(0)).toBe(60)
    expect(clampWidth(-100)).toBe(60)
  })

  it('高于 800 强制为 800', () => {
    expect(clampWidth(1000)).toBe(800)
    expect(clampWidth(2500)).toBe(800)
  })

  it('合法范围内透传', () => {
    expect(clampWidth(120)).toBe(120)
    expect(clampWidth(60)).toBe(60)
    expect(clampWidth(800)).toBe(800)
  })
})

describe('LedgerPenetration virtual mode — sort', () => {
  const rows = [
    { id: 1, voucher_no: 'A002', debit_amount: 200, summary: '工资' },
    { id: 2, voucher_no: 'A001', debit_amount: 100, summary: '借款' },
    { id: 3, voucher_no: 'A003', debit_amount: 50, summary: '杂费' },
  ]

  it('null sort 返回原数组', () => {
    expect(sortRows(rows, null)).toBe(rows)
  })

  it('数字升序', () => {
    const out = sortRows(rows, { key: 'debit_amount', order: 'asc' })
    expect(out.map((r) => r.id)).toEqual([3, 2, 1])
  })

  it('数字降序', () => {
    const out = sortRows(rows, { key: 'debit_amount', order: 'desc' })
    expect(out.map((r) => r.id)).toEqual([1, 2, 3])
  })

  it('字符串排序（locale-aware）', () => {
    const out = sortRows(rows, { key: 'voucher_no', order: 'asc' })
    expect(out.map((r) => r.id)).toEqual([2, 1, 3])
  })

  it('排序不修改原数组', () => {
    const original = rows.slice()
    sortRows(rows, { key: 'debit_amount', order: 'desc' })
    expect(rows).toEqual(original)
  })

  it('NaN/null 字段稳定（不抛异常）', () => {
    const dirty = [{ x: null }, { x: undefined }, { x: 'abc' }, { x: 5 }]
    expect(() => sortRows(dirty, { key: 'x', order: 'asc' })).not.toThrow()
  })
})

describe('LedgerPenetration virtual mode — filter', () => {
  const rows = [
    { id: 1, summary: '工资发放', voucher_no: 'A001', debit_amount: 0, credit_amount: 1000 },
    { id: 2, summary: '工资计提', voucher_no: 'A002', debit_amount: 1000, credit_amount: 0 },
    { id: 3, summary: '差旅费', voucher_no: 'B001', debit_amount: 500, credit_amount: 0 },
  ]

  it('空关键字 + all 方向 = 全集', () => {
    expect(filterRows(rows, '', 'all')).toEqual(rows)
  })

  it('关键字命中摘要', () => {
    const out = filterRows(rows, '工资', 'all')
    expect(out.map((r) => r.id)).toEqual([1, 2])
  })

  it('关键字命中凭证号', () => {
    const out = filterRows(rows, 'B001', 'all')
    expect(out.map((r) => r.id)).toEqual([3])
  })

  it('关键字不区分大小写', () => {
    const mixed = [{ id: 1, summary: 'Salary', voucher_no: 'X', debit_amount: 0, credit_amount: 0 }]
    expect(filterRows(mixed, 'salary', 'all')).toHaveLength(1)
    expect(filterRows(mixed, 'SALARY', 'all')).toHaveLength(1)
  })

  it('仅借方过滤', () => {
    const out = filterRows(rows, '', 'debit')
    expect(out.map((r) => r.id)).toEqual([2, 3])
  })

  it('仅贷方过滤', () => {
    const out = filterRows(rows, '', 'credit')
    expect(out.map((r) => r.id)).toEqual([1])
  })

  it('关键字 + 方向叠加', () => {
    const out = filterRows(rows, '工资', 'debit')
    expect(out.map((r) => r.id)).toEqual([2])
  })

  it('无匹配返回空数组', () => {
    expect(filterRows(rows, 'nonexistent', 'all')).toEqual([])
  })

  it('空白关键字（仅空格）等同空字符串', () => {
    expect(filterRows(rows, '   ', 'all')).toEqual(rows)
  })
})

// ─── 月小计 + 运行余额（明细账核心计算）回归测试 ──────────────────────────
// 直接 import 生产实现 buildLedgerDisplay（@/utils/ledgerDisplay），
// 不再 copy 副本——确保测试真正守护生产代码（改生产即影响测试）。
// 守护 bug：月合计累加必须在「月份边界结算之后」，否则上月小计会并入本月首笔。

interface RawEntry { voucher_date: string; debit_amount: number; credit_amount: number }

describe('LedgerPenetration — 月小计 + 运行余额', () => {
  const items: RawEntry[] = [
    { voucher_date: '2025-01-10', debit_amount: 100, credit_amount: 0 },
    { voucher_date: '2025-01-20', debit_amount: 40, credit_amount: 0 },
    { voucher_date: '2025-02-05', debit_amount: 0, credit_amount: 30 },
    { voucher_date: '2025-02-15', debit_amount: 70, credit_amount: 0 },
    { voucher_date: '2025-03-01', debit_amount: 0, credit_amount: 50 },
  ]

  it('每月小计精确按月分组（不并入下月首笔）', () => {
    const rows = buildLedgerDisplay(items, 1000)
    const subtotals = rows.filter((r) => r._type === 'subtotal')
    expect(subtotals).toHaveLength(3)
    // 1月：借 140 贷 0
    expect(subtotals[0].debit_amount).toBe(140)
    expect(subtotals[0].credit_amount).toBe(0)
    // 2月：借 70 贷 30
    expect(subtotals[1].debit_amount).toBe(70)
    expect(subtotals[1].credit_amount).toBe(30)
    // 3月：借 0 贷 50
    expect(subtotals[2].debit_amount).toBe(0)
    expect(subtotals[2].credit_amount).toBe(50)
  })

  it('月小计借贷合计 = 全期借贷总额（守恒）', () => {
    const rows = buildLedgerDisplay(items, 1000)
    const subs = rows.filter((r) => r._type === 'subtotal')
    const sumD = subs.reduce((s, r) => s + (r.debit_amount ?? 0), 0)
    const sumC = subs.reduce((s, r) => s + (r.credit_amount ?? 0), 0)
    expect(sumD).toBe(210) // 100+40+70
    expect(sumC).toBe(80)  // 30+50
  })

  it('期初行余额 = 期初；末行运行余额 = 期初 + Σ借 − Σ贷', () => {
    const rows = buildLedgerDisplay(items, 1000)
    expect(rows[0]._type).toBe('opening')
    expect(rows[0].balance).toBe(1000)
    const lastNormal = [...rows].reverse().find((r) => r._type === 'normal')
    expect(lastNormal!.balance).toBe(1000 + 210 - 80) // 1130
  })

  it('月小计的 balance = 该月末运行余额', () => {
    const rows = buildLedgerDisplay(items, 1000)
    const subs = rows.filter((r) => r._type === 'subtotal')
    expect(subs[0].balance).toBe(1140) // 1月末: 1000+140
    expect(subs[1].balance).toBe(1180) // 2月末: 1140+70-30
    expect(subs[2].balance).toBe(1130) // 3月末: 1180-50
  })

  it('空数据不产生小计行', () => {
    const rows = buildLedgerDisplay([], 500)
    expect(rows).toHaveLength(1)
    expect(rows[0]._type).toBe('opening')
  })
})
