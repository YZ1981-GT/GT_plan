import { describe, it, expect } from 'vitest'
import { resolveColumnLabel, QUERY_COLUMN_LABELS } from '../queryColumnLabels'

describe('resolveColumnLabel — 列标签三级兜底 (Property 1)', () => {
  it('共享映射命中 → 返回中文标签', () => {
    expect(resolveColumnLabel('account_code')).toBe('科目编码')
    expect(resolveColumnLabel('current_period_amount')).toBe('本期金额')
    expect(resolveColumnLabel('review_status')).toBe('复核状态')
  })

  it('映射命中时忽略后端 title（映射优先）', () => {
    expect(resolveColumnLabel('account_code', 'AcctCode')).toBe('科目编码')
  })

  it('未命中映射但 title 非空且 ≠ key → 返回 title', () => {
    expect(resolveColumnLabel('some_new_col', '新列')).toBe('新列')
  })

  it('未命中映射且 title === key → 返回 key', () => {
    expect(resolveColumnLabel('foo_bar', 'foo_bar')).toBe('foo_bar')
  })

  it('未命中映射且无 title → 返回 key 原样 (Property 2: 未知 key 不留空)', () => {
    expect(resolveColumnLabel('unknown_col')).toBe('unknown_col')
  })

  it('空 key 不抛错', () => {
    expect(resolveColumnLabel('')).toBe('')
    expect(resolveColumnLabel('', '兜底')).toBe('兜底')
  })

  it('映射覆盖 Dialog 原有键与 Tab/Builder 补齐键', () => {
    // Dialog 原有
    expect(QUERY_COLUMN_LABELS['row_code']).toBe('行次')
    expect(QUERY_COLUMN_LABELS['non_common_ratio']).toBe('持股比例')
    // 补齐（后端 _query_* 实际返回的 key）
    expect(QUERY_COLUMN_LABELS['standard_account_code']).toBeTruthy()
    expect(QUERY_COLUMN_LABELS['unadjusted_amount']).toBeTruthy()
    expect(QUERY_COLUMN_LABELS['adjustment_no']).toBeTruthy()
    expect(QUERY_COLUMN_LABELS['work_date']).toBeTruthy()
    expect(QUERY_COLUMN_LABELS['cell_ref']).toBeTruthy()
  })
})
