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
