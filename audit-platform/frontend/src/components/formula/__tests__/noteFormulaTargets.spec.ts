/** 附注公式目标串（与后端 note_formula_tables.formula_key 同一写法；spec note-pull-header-formula-closure R3） */
import { describe, expect, it } from 'vitest'
import { describeApplyResult, describeFormulaTarget, formulaKey, parseFormulaKey } from '../noteFormulaTargets'

const TABLES = [
  { index: 0, name: '按账龄', rows: ['1年以内', '合计'], columns: ['期末数', '期初数'] },
  { index: 2, name: '坏账准备变动', rows: ['按单项', '合计'], columns: ['期初数', '期末数'] },
]

describe('noteFormulaTargets', () => {
  it('第 1 张表沿用 行:列，其余带 t{n}', () => {
    expect(formulaKey({ table: 0, row: 3, col: 1 })).toBe('3:1')
    expect(formulaKey({ table: 2, row: 3, col: 1 })).toBe('t2:3:1')
    expect(parseFormulaKey('t2:3:1')).toEqual({ table: 2, row: 3, col: 1 })
    expect(parseFormulaKey(' 3 : 1 ')).toEqual({ table: 0, row: 3, col: 1 })
    for (const bad of ['', 'R1', '3', 't:1:2', '1:2:3', null]) expect(parseFormulaKey(bad)).toBeNull()
  })

  it('可读目标；认不出或超出范围原样返回', () => {
    expect(describeFormulaTarget('t2:1:0', TABLES)).toBe('坏账准备变动 · 合计 · 期初数')
    expect(describeFormulaTarget('1:1', TABLES)).toBe('按账龄 · 合计 · 期初数')
    expect(describeFormulaTarget('t1:0:0', TABLES)).toBe('t1:0:0')
    expect(describeFormulaTarget('t2:5:0', TABLES)).toBe('t2:5:0')
  })

  it('应用结果提示：没写入的按原因计数（前 3 种）', () => {
    const results = [
      ...Array(3).fill({ status: 'skipped', reason: '引用的单元格都没有数' }),
      { status: 'skipped', reason: '审核类公式不回填单元格' },
      { status: 'ok' },
    ]
    expect(describeApplyResult({ executed: 5, updated: 1, results }))
      .toBe('公式已应用：执行 5 个，更新 1 个单元格；4 个未写入（引用的单元格都没有数 3 个、审核类公式不回填单元格 1 个）')
    expect(describeApplyResult({ executed: 0, updated: 0 }, '已重新生成')).toBe('已重新生成：执行 0 个，更新 0 个单元格')
  })
})
