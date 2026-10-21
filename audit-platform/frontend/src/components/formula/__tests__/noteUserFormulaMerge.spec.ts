/**
 * noteUserFormulaMerge.spec.ts — Task 4.1 / ADR-FMC-04 附注用户公式合并（纯函数）
 *
 * 守护 mergeNoteUserFormulaRows 的合并口径（与后端 execute_note_formulas 一致）：
 *  - 用户编辑集按 target 去重，用户集优先（后者覆盖前者）。
 *  - 用户公式作为附加行并入预设行（互补，不覆盖预设的章节级行）。
 *  - 无合法 formula 的用户记录跳过。
 *  - 变异反证：不并入用户集时附加行消失（覆盖样本打红）。
 */
import { describe, expect, it } from 'vitest'
import {
  buildNoteFormulaRows,
  mergeNoteUserFormulaRows,
  type NoteFormulaRow,
  type NoteUserFormula,
} from '@/components/formula/noteScopeTargeting'

const PRESETS = [
  { note_section: '五、1', section_title: '货币资金', formula: "TB('1001','期末')", category: 'auto_calc', description: '库存现金', source: 'preset' },
]

function presetRows(): NoteFormulaRow[] {
  return buildNoteFormulaRows(PRESETS, { sectionId: '五、1', sectionTitle: '货币资金' })
}

describe('mergeNoteUserFormulaRows — 附注用户公式合并', () => {
  it('用户公式作为附加行并入预设行', () => {
    const user: NoteUserFormula[] = [
      { target: '2:0', formula: 'SUM(0:1, 0)', description: '合计', category: 'auto_calc', source: 'user' },
    ]
    const merged = mergeNoteUserFormulaRows(presetRows(), user, { sectionId: '五、1', sectionTitle: '货币资金' })
    // 预设 1 行 + 用户 1 行
    expect(merged.length).toBe(2)
    const userRow = merged.find((r) => r._userTarget === '2:0')
    expect(userRow).toBeTruthy()
    expect(userRow!.formula).toBe('SUM(0:1, 0)')
    expect(userRow!.formula_source).toBe('user')
  })

  it('层级标签随用户公式带到弹窗行（formula-global-settings-sync R1.4）', () => {
    const merged = mergeNoteUserFormulaRows([], [
      { target: '2:0', formula: 'X()', layer: 'project', layer_label: '本项目', pending: true },
      { target: '2:1', formula: 'Y()' },
    ])
    expect(merged[0]).toMatchObject({ _layer: 'project', _layer_label: '本项目', _pending: true })
    expect(merged[1]).toMatchObject({ _layer: undefined, _pending: false })
  })

  it('同 target 多条 → 用户集优先（保留后者，覆盖前者）', () => {
    const user: NoteUserFormula[] = [
      { target: '2:0', formula: 'OLD()', description: '旧', source: 'user' },
      { target: '2:0', formula: 'NEW()', description: '新', source: 'user' },
    ]
    const merged = mergeNoteUserFormulaRows([], user)
    const rows = merged.filter((r) => r._userTarget === '2:0')
    // 同 target 去重为一行，且是后者（NEW）
    expect(rows.length).toBe(1)
    expect(rows[0].formula).toBe('NEW()')
    expect(rows[0].formula_description).toBe('新')
  })

  it('无合法 formula 的用户记录被跳过', () => {
    const user: NoteUserFormula[] = [
      { target: '2:0', formula: '   ' },      // 空白
      { target: '2:1', formula: '' },         // 空
      { target: '2:2', formula: 'SUM(0:1,2)', source: 'user' },  // 合法
    ]
    const merged = mergeNoteUserFormulaRows([], user)
    expect(merged.map((r) => r._userTarget)).toEqual(['2:2'])
  })

  it('用户集为空 → 等价于只返回预设行（变异反证基线）', () => {
    const base = presetRows()
    expect(mergeNoteUserFormulaRows(base, [])).toEqual(base)
    expect(mergeNoteUserFormulaRows(base, null)).toEqual(base)
    expect(mergeNoteUserFormulaRows(base, undefined)).toEqual(base)
  })

  it('变异反证：不并入用户集则用户行不出现（覆盖样本打红锚）', () => {
    const user: NoteUserFormula[] = [
      { target: '3:0', formula: 'SUM(0:2,0)', source: 'user' },
    ]
    const withUser = mergeNoteUserFormulaRows(presetRows(), user)
    const withoutUser = mergeNoteUserFormulaRows(presetRows(), [])
    // 并入用户集 → 多一行；不并入 → 无该行（若 merge 丢弃用户集则 withUser 也无该行即打红）
    expect(withUser.some((r) => r._userTarget === '3:0')).toBe(true)
    expect(withoutUser.some((r) => r._userTarget === '3:0')).toBe(false)
    expect(withUser.length).toBe(withoutUser.length + 1)
  })
})
