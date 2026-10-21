import { describe, it, expect } from 'vitest'
import { getCandidateConfig, filterCandidates, TB_FIELDS, REPORT_FIELDS, type CandidateItem } from '../formulaParamCandidates'

describe('getCandidateConfig', () => {
  it('TB 第 0 参数返回 account_codes', () => {
    const cfg = getCandidateConfig('TB', 0)
    expect(cfg).not.toBeNull()
    expect(cfg!.source).toBe('account_codes')
  })

  it('TB 第 1 参数返回 static TB_FIELDS', () => {
    const cfg = getCandidateConfig('TB', 1)
    expect(cfg).not.toBeNull()
    expect(cfg!.source).toBe('static')
    expect(cfg!.staticItems).toEqual(TB_FIELDS)
  })

  it('ROW 第 0 参数返回 report_rows', () => {
    expect(getCandidateConfig('ROW', 0)?.source).toBe('report_rows')
  })

  it('REPORT 第 0 参数返回 report_rows', () => {
    expect(getCandidateConfig('REPORT', 0)?.source).toBe('report_rows')
  })

  it('REPORT 第 1 参数返回 static REPORT_FIELDS', () => {
    const cfg = getCandidateConfig('REPORT', 1)
    expect(cfg?.source).toBe('static')
    expect(cfg?.staticItems).toEqual(REPORT_FIELDS)
  })

  it('WP 第 0 参数返回 wp_codes', () => {
    expect(getCandidateConfig('WP', 0)?.source).toBe('wp_codes')
  })

  it('ADJ 第 0 参数返回 account_codes', () => {
    expect(getCandidateConfig('ADJ', 0)?.source).toBe('account_codes')
  })

  it('ADJ 第 1 参数返回 static（类型）', () => {
    expect(getCandidateConfig('ADJ', 1)?.source).toBe('static')
  })

  it('数学函数（ABS/IF）无参数补全', () => {
    expect(getCandidateConfig('ABS', 0)).toBeNull()
    expect(getCandidateConfig('IF', 0)).toBeNull()
  })

  it('未知函数返回 null', () => {
    expect(getCandidateConfig('UNKNOWN', 0)).toBeNull()
  })

  it('参数索引越界返回 null', () => {
    expect(getCandidateConfig('TB', 5)).toBeNull()
    expect(getCandidateConfig('ROW', 1)).toBeNull()
  })
})

describe('filterCandidates', () => {
  const items: CandidateItem[] = [
    { value: '1001', label: '1001 - 库存现金' },
    { value: '1002', label: '1002 - 银行存款' },
    { value: '1101', label: '1101 - 应收票据' },
    { value: '2001', label: '2001 - 短期借款' },
  ]

  it('空前缀返回全部（最多 maxItems）', () => {
    expect(filterCandidates(items, '')).toHaveLength(4)
  })

  it('按前缀过滤', () => {
    const result = filterCandidates(items, '100')
    expect(result).toHaveLength(2)
    expect(result.map(r => r.value)).toEqual(['1001', '1002'])
  })

  it('不区分大小写', () => {
    const result = filterCandidates(items, '库存')
    expect(result).toHaveLength(1)
    expect(result[0].value).toBe('1001')
  })

  it('最多返回 maxItems 条', () => {
    const many = Array.from({ length: 100 }, (_, i) => ({ value: `${i}`, label: `item ${i}` }))
    expect(filterCandidates(many, '', 50)).toHaveLength(50)
  })

  it('无匹配返回空', () => {
    expect(filterCandidates(items, 'xyz')).toHaveLength(0)
  })
})
