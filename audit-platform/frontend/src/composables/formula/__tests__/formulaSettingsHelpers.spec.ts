/**
 * useFormulaSettings 的小工具（spec formula-management-repair-closure）：
 * - R5 全局设置页分组：各域公式位取分组段（与后端各域 slot_key 的拼法一一对应）+ 中文名；
 * - R3.1 未接入计算的域提示：用后端 wired_reason，已接入 / 取不到域信息不提示。
 */
import { describe, expect, it } from 'vitest'
import { domainNotWiredText, slotGroupKey, slotGroupLabel } from '../useFormulaSettings'

describe('slotGroupKey / slotGroupLabel', () => {
  it.each([
    ['report', 'balance_sheet:BS-002', 'balance_sheet', '资产负债表'],
    ['report', 'income_statement:IS-001', 'income_statement', '利润表'],
    ['wp', 'D2|审定表D2-1|E8', 'D2', 'D2'],
    ['note', '五、1|t0:2:0', '五、1', '五、1'],
    ['consol_note', '八、3|2|1', '八、3', '八、3'],
    ['cross_check', 'report_note#r-001', 'report_note', 'report_note'],
    ['push', 'E1.bank_rows.four_table', 'E1', 'E1'],
    ['tb_detail', '1002', '1', '资产类科目'],
    ['tb_detail', '6001', '6', '损益类科目'],
    ['tb_detail', 'added:X1', 'added', '自定义科目'],
  ])('%s %s → %s（%s）', (domain, slot, key, label) => {
    expect(slotGroupKey(domain, slot)).toBe(key)
    expect(slotGroupLabel(domain, key)).toBe(label)
  })

  it('没有分隔符的公式位自成一组；未知分组原样显示，空分组叫「其他」', () => {
    expect(slotGroupKey('report', 'BS-002')).toBe('BS-002')
    expect(slotGroupKey('unknown', 'a:b')).toBe('a:b')
    expect(slotGroupLabel('report', 'custom_type')).toBe('custom_type')
    expect(slotGroupLabel('tb_detail', '')).toBe('其他')
  })
})

describe('domainNotWiredText', () => {
  it('已接入或没有域信息：不提示；未接入：用后端说明，缺说明时用兜底', () => {
    expect(domainNotWiredText(null)).toBe('')
    expect(domainNotWiredText({ wired: true, wired_reason: '不该显示' })).toBe('')
    expect(domainNotWiredText({ wired: false, wired_reason: '试算表科目明细公式目前只保存、不参与计算' }))
      .toBe('试算表科目明细公式目前只保存、不参与计算')
    expect(domainNotWiredText({ wired: false })).toBe('该类公式目前只保存、不参与计算。')
  })
})
