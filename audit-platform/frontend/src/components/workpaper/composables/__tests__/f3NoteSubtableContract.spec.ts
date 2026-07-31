/**
 * F3 应付票据披露子表 ↔ note_template 契约（接入平台共享 helper）
 *
 * F3 曾是 F 类唯一没有此守卫的循环，代价是国企披露列头长期沿用上市口径
 * （种类/上年年末余额，源模板国企为 类别/期初余额，3 列错 2 列）。
 *
 * Spec: .kiro/specs/f-cycle-disclosure-parity/ R1 / R2 / R4
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  F3_NOTE_SECTION,
  F3_LISTED_SUBTABLE,
  F3_SOE_SUBTABLE,
  F3_LISTED_YFPJ_COLUMNS,
  F3_SOE_YFPJ_COLUMNS,
  buildF3NoteTexts,
  buildF3SyncPayload,
  orderF3ClassRows,
} from '../f3NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'F3',
  variants: [
    {
      variant: 'listed',
      section: F3_NOTE_SECTION.listed,
      subtables: F3_LISTED_SUBTABLE,
      columns: { [F3_LISTED_SUBTABLE.notesPayable]: F3_LISTED_YFPJ_COLUMNS },
    },
    {
      variant: 'soe',
      section: F3_NOTE_SECTION.soe,
      subtables: F3_SOE_SUBTABLE,
      columns: { [F3_SOE_SUBTABLE.notesPayable]: F3_SOE_YFPJ_COLUMNS },
    },
  ],
})

describe('F3 两变体列头口径', () => {
  it('R1 国企标签列为「类别」、第 3 列为「期初余额」', () => {
    expect(F3_SOE_YFPJ_COLUMNS.map((c) => c.label)).toEqual(['类别', '期末余额', '期初余额'])
  })

  it('R1 上市标签列为「种类」、第 3 列为「上年年末余额」', () => {
    expect(F3_LISTED_YFPJ_COLUMNS.map((c) => c.label)).toEqual([
      '种类', '期末余额', '上年年末余额',
    ])
  })

  it('R1 两变体列头必须不同（反向断言，防退回共用一份）', () => {
    expect(F3_LISTED_YFPJ_COLUMNS.map((c) => c.label))
      .not.toEqual(F3_SOE_YFPJ_COLUMNS.map((c) => c.label))
  })

  it('字段 key 不随变体变化（只有 label 分变体）', () => {
    expect(F3_LISTED_YFPJ_COLUMNS.map((c) => c.key))
      .toEqual(F3_SOE_YFPJ_COLUMNS.map((c) => c.key))
  })

  it('载荷按变体取列头', () => {
    const args = [
      [{ label: '银行承兑汇票', endAmount: 10, priorAmount: 8 }],
      { label: '合计', endAmount: 10, priorAmount: 8 },
      '说明',
    ] as const
    const listed = buildF3SyncPayload('listed', 'wp-1', ['listed_standalone'], ...args)
    const soe = buildF3SyncPayload('soe', 'wp-2', ['soe_standalone'], ...args)
    expect(listed.columns![F3_LISTED_SUBTABLE.notesPayable][0].label).toBe('种类')
    expect(soe.columns![F3_SOE_SUBTABLE.notesPayable][0].label).toBe('类别')
    expect(soe.columns![F3_SOE_SUBTABLE.notesPayable][2].label).toBe('期初余额')
  })
})

describe('F3 分类行序（源 xlsx r7 银行 → r8 商业）', () => {
  it('R2 银行承兑汇票排在商业承兑汇票之前', () => {
    const rows = orderF3ClassRows([
      { label: '商业承兑汇票', endAmount: 2, priorAmount: 1 },
      { label: '银行承兑汇票', endAmount: 5, priorAmount: 4 },
    ])
    expect(rows.map((r) => r.label)).toEqual(['银行承兑汇票', '商业承兑汇票'])
  })

  it('R2 缺失的种类补 0 行，仍保持源模板行序', () => {
    const rows = orderF3ClassRows([{ label: '商业承兑汇票', endAmount: 2, priorAmount: 1 }])
    expect(rows.map((r) => r.label)).toEqual(['银行承兑汇票', '商业承兑汇票'])
    expect(rows[0]).toMatchObject({ endAmount: 0, priorAmount: 0 })
  })

  it('供应链票据仅在来源提供时出现，且排在两种承兑汇票之后', () => {
    const rows = orderF3ClassRows([
      { label: '供应链票据', endAmount: 3, priorAmount: 0 },
      { label: '商业承兑汇票', endAmount: 2, priorAmount: 1 },
    ])
    expect(rows.map((r) => r.label)).toEqual([
      '银行承兑汇票', '商业承兑汇票', '供应链票据',
    ])
  })
})

describe('F3 _note_texts', () => {
  it('R5 带非空中文 title，且不等于 section', () => {
    const [row] = buildF3NoteTexts('listed', '本期末已到期未支付的应付票据总额为 100 万元。')
    expect(row).toMatchObject({ section: 'listed-note', title: '已到期未支付的应付票据说明' })
    expect(row.title).not.toBe(row.section)
    expect(/[a-z-]{6,}/.test(row.title)).toBe(false)
  })

  it('R5 空文本被过滤（不覆盖附注既有正文）', () => {
    expect(buildF3NoteTexts('soe', '   ')).toEqual([])
    const payload = buildF3SyncPayload(
      'soe', 'wp', ['soe_standalone'], [], { label: '合计', endAmount: 0, priorAmount: 0 }, '',
    )
    expect(payload.sub_table_data._note_texts).toEqual([])
  })
})
