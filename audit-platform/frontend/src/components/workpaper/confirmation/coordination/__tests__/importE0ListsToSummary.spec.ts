import { describe, it, expect } from 'vitest'
import {
  isConfirmFlagYes,
  buildSummaryRowsFromListRows,
  dedupeSummaryRows,
  E0_LIST_ACCOUNT_TYPE,
} from '../importE0ListsToSummary'
import type { ConfirmationRow } from '../../confirmationTypes'

describe('importE0ListsToSummary', () => {
  describe('isConfirmFlagYes', () => {
    it('识别多种「是」表示', () => {
      expect(isConfirmFlagYes({ 是否函证: '是' })).toBe(true)
      expect(isConfirmFlagYes({ 是否函证: 'Y' })).toBe(true)
      expect(isConfirmFlagYes({ 是否发函: '√' })).toBe(true)
      expect(isConfirmFlagYes({ confirm_flag: 'true' })).toBe(true)
    })
    it('识别「否」/空为 false', () => {
      expect(isConfirmFlagYes({ 是否函证: '否' })).toBe(false)
      expect(isConfirmFlagYes({ 是否函证: '' })).toBe(false)
      expect(isConfirmFlagYes({})).toBe(false)
    })
  })

  describe('buildSummaryRowsFromListRows (Property 14)', () => {
    it('仅取「是否函证=是」的行', () => {
      const rows = [
        { 开户银行: '工商银行', 是否函证: '是', 账户余额: 1000 },
        { 开户银行: '建设银行', 是否函证: '否', 账户余额: 2000 },
      ]
      const out = buildSummaryRowsFromListRows(rows, 'E0-3')
      expect(out).toHaveLength(1)
      expect(out[0].entity_name).toBe('工商银行')
    })

    it('account_type 按来源品种置值', () => {
      expect(buildSummaryRowsFromListRows([{ 借款人: 'A', 是否函证: '是' }], 'E0-4')[0].account_type).toBe('短期借款')
      expect(buildSummaryRowsFromListRows([{ 被询证单位: 'B', 是否函证: '是' }], 'E0-5')[0].account_type).toBe('应付票据')
      expect(buildSummaryRowsFromListRows([{ 理财产品名称: 'C', 是否函证: '是' }], 'E0-6')[0].account_type).toBe('理财产品')
    })

    it('E0-3 按账户类型细分银行存款/其他货币资金', () => {
      const rows = [
        { 开户银行: '工行', 是否函证: '是', 账户类型: '基本户' },
        { 开户银行: '中行', 是否函证: '是', 账户类型: '保证金账户' },
      ]
      const out = buildSummaryRowsFromListRows(rows, 'E0-3')
      expect(out[0].account_type).toBe('银行存款')
      expect(out[1].account_type).toBe('其他货币资金')
    })

    it('无单位名称的行跳过', () => {
      const out = buildSummaryRowsFromListRows([{ 是否函证: '是', 账户余额: 100 }], 'E0-3')
      expect(out).toHaveLength(0)
    })

    it('金额与索引号正确映射', () => {
      const out = buildSummaryRowsFromListRows(
        [{ 开户银行: '工行', 是否函证: '是', 账户余额: '5000', 索引号: 'E0-001' }],
        'E0-3',
      )
      expect(out[0].amount).toBe(5000)
      expect(out[0].confirm_index).toBe('E0-001')
    })
  })

  describe('dedupeSummaryRows (Property 14 去重)', () => {
    it('已存在的 entity_name+account_type 不重复追加', () => {
      const existing: ConfirmationRow[] = [
        { _row_id: '1', entity_name: '工行', account_type: '银行存款' } as ConfirmationRow,
      ]
      const candidates = [
        { entity_name: '工行', account_type: '银行存款' },
        { entity_name: '中行', account_type: '银行存款' },
      ]
      const out = dedupeSummaryRows(candidates, existing)
      expect(out).toHaveLength(1)
      expect(out[0].entity_name).toBe('中行')
    })

    it('候选内部同 key 也去重', () => {
      const candidates = [
        { entity_name: '工行', account_type: '银行存款' },
        { entity_name: '工行', account_type: '银行存款' },
      ]
      expect(dedupeSummaryRows(candidates, [])).toHaveLength(1)
    })
  })

  it('E0_LIST_ACCOUNT_TYPE 覆盖 E0-3~E0-6', () => {
    expect(Object.keys(E0_LIST_ACCOUNT_TYPE).sort()).toEqual(['E0-3', 'E0-4', 'E0-5', 'E0-6'])
  })
})
