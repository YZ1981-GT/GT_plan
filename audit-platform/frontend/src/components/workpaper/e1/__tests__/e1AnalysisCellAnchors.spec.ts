/**
 * E1-14 模板单元格 → 网页位置（spec wp-deeplink-cell-locate-closure 需求 4.1 / 4.2）。
 * 模板逐格一致性由后端 test_e1_analysis_anchor_template_contract.py 读模板校验。
 */
import { describe, expect, it } from 'vitest'
import { resolveE1AnalysisAnchor } from '../e1AnalysisCellAnchors'

describe('resolveE1AnalysisAnchor', () => {
  it.each([
    ['C16', { kind: 'cell', section: 'composition', table: 'composition', rowIndex: 1, columnLabel: '本期金额' }],
    ['I15', { kind: 'cell', section: 'composition', rowIndex: 0, columnLabel: '本期变动率' }],
    ['D17', { kind: 'cell', section: 'composition', rowIndex: 2, columnLabel: '本期结构比' }],
    ['E15', { kind: 'cell', section: 'composition', rowIndex: 0, columnLabel: '上期金额' }],
    ['G16', { kind: 'cell', section: 'composition', rowIndex: 1, columnLabel: '前期金额' }],
    ['F15', { kind: 'row', section: 'composition', rowIndex: 0 }],
    ['J17', { kind: 'row', section: 'composition', rowIndex: 2 }],
    ['C22', { kind: 'cell', section: 'other', rowIndex: 0, columnLabel: '本期金额' }],
    ['G28', { kind: 'cell', section: 'other', rowIndex: 6, columnLabel: '前期金额' }],
    ['D25', { kind: 'row', section: 'other', rowIndex: 3 }],
    ['C34', { kind: 'cell', section: 'ratios', rowIndex: 0, columnLabel: '本期' }],
    ['F40', { kind: 'cell', section: 'ratios', rowIndex: 6, columnLabel: '本期变动' }],
    ['G35', { kind: 'row', section: 'ratios', rowIndex: 1 }],
    ['H34', { kind: 'cell', section: 'ratios', rowIndex: 0, columnLabel: '差异原因及合理性' }],
    ['K41', { kind: 'cell', section: 'ratios', rowIndex: 7, columnLabel: '差异原因及合理性' }],
    ['B30', { kind: 'block', section: 'other', block: 'f3-2' }],
    ['A44', { kind: 'block', block: 'note' }],
    ['B48', { kind: 'block', block: 'note' }],
    ['A50', { kind: 'block', block: 'conclusion' }],
    ['c16', { kind: 'cell', rowIndex: 1, columnLabel: '本期金额' }],
  ])('%s', (cell, expected) => {
    expect(resolveE1AnalysisAnchor(cell)).toMatchObject(expected)
  })

  it.each(['C10', 'A10', 'C18', 'I18', 'C29', 'C13', 'Z99', 'abc', '', null, undefined])(
    '%s 在网页视图里没有对应位置 → null', (cell) => {
      expect(resolveE1AnalysisAnchor(cell as any)).toBeNull()
    },
  )

  it('审计说明 / 结论卡片在页签外，不要求切区段', () => {
    expect(resolveE1AnalysisAnchor('A43')?.section).toBeUndefined()
    expect(resolveE1AnalysisAnchor('A50')?.section).toBeUndefined()
  })
})
