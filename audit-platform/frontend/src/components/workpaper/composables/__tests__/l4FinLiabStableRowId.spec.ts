/**
 * L4-3 行模型守卫（spec l-cycle-true-adapter-registration · Task 12）。
 * 对标 l1DetailStableRowId.spec.ts：位置化行身份的反例 + 与模板公式同口径。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  L4_3_PAIR_STEMS,
  L4_3_ROWS_ITEM_ID,
  applyL4_3Formulas,
  createEmptyFinLiabRow,
  parseL4_3Rows,
  removeL4_3RowById,
  serializeL4_3Rows,
} from '../useL4FinLiabRows'

const COMPONENT = resolve(__dirname, '../../l4/classification/L4TabFinLiabOther.vue')

const stripComments = (src: string): string =>
  src.replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')

describe('L4-3 稳定行身份', () => {
  it('store item 与后端契约同名', () => {
    expect(L4_3_ROWS_ITEM_ID).toBe('L4-3-rows')
  })

  it('新增行 rowId 唯一', () => {
    const ids = new Set(Array.from({ length: 50 }, () => createEmptyFinLiabRow().rowId))
    expect(ids.size).toBe(50)
  })

  it('删中间行 ⇒ 其余行 rowId 不变（位置化缺陷的反例）', () => {
    const rows = ['甲', '乙', '丙'].map((n) => createEmptyFinLiabRow(n))
    const after = removeL4_3RowById(rows, rows[1].rowId)
    expect(after.map((r) => r.rowId)).toEqual([rows[0].rowId, rows[2].rowId])
    expect(after.map((r) => r.instrumentName)).toEqual(['甲', '丙'])
  })

  it('序列化 → 解析往返保留 rowId 与业务值', () => {
    const row = createEmptyFinLiabRow('永续债A')
    row.unauditedPriorAmount = 1000
    const back = parseL4_3Rows(serializeL4_3Rows([row]))
    expect(back).toHaveLength(1)
    expect(back[0].rowId).toBe(row.rowId)
    expect(back[0].unauditedPriorAmount).toBe(1000)
  })

  it('空表落 null；坏载荷给空表不半解析；缺 rowId 当场补铸', () => {
    expect(serializeL4_3Rows([])).toBeNull()
    expect(parseL4_3Rows('{not json')).toEqual([])
    expect(parseL4_3Rows('{"a":1}')).toEqual([])
    const minted = parseL4_3Rows(JSON.stringify([{ instrumentName: 'x' }]))
    expect(minted[0].rowId).toMatch(/\S/)
  })

  it('组件已拆除位置化旧键，并按 rowId 删行', () => {
    const src = stripComments(readFileSync(COMPONENT, 'utf-8'))
    expect(src).not.toMatch(/L4-3-row-\$\{/)
    expect(src).not.toMatch(/removeRow\(\$index\)/)
    expect(src).toMatch(/removeRow\(row\.rowId\)/)
    expect(src).toMatch(/parseL4_3Rows\(/)
  })

  it('注释剥离器非空转：注释里的旧键被剥掉、代码里的留得住', () => {
    const sample = '// L4-3-row-${n}\nconst k = `L4-3-row-${n}-data` // https://x'
    const out = stripComments(sample)
    expect(out).toMatch(/L4-3-row-\$\{n\}-data/)
    expect(out.split('\n')[0]).not.toMatch(/L4-3-row/)
  })
})

describe('L4-3 公式与模板逐行公式同口径', () => {
  it('R/S 与 AF~AM（数量、金额两套）', () => {
    const r = createEmptyFinLiabRow('x')
    const set = (stem: string, q: number, a: number) => {
      r[`${stem}Qty`] = q
      r[`${stem}Amount`] = a
    }
    set('unauditedPrior', 10, 1000)
    set('unauditedIncrease', 5, 500)
    set('unauditedDecrease', 2, 200)
    set('priorAje', 1, 100)
    set('priorRje', 0, 50)
    set('ajeIncrease', 3, 300)
    set('rjeIncrease', 0, 30)
    set('ajeDecrease', 1, 10)
    set('rjeDecrease', 0, 5)
    const f = applyL4_3Formulas(r)
    expect(f.unauditedEndAmount).toBe(1300) // S = M + O − Q
    expect(f.unauditedEndQty).toBe(13) // R = L + N − P
    expect(f.auditedPriorAmount).toBe(1150) // AG = M + U + W
    expect(f.auditedIncreaseAmount).toBe(830) // AI = O + Y + AC
    expect(f.auditedDecreaseAmount).toBe(215) // AK = Q + AA + AE
    expect(f.auditedEndAmount).toBe(1765) // AM = AG + AI − AK
    expect(f.auditedEndQty).toBe(11 + 8 - 3) // AL = AF + AH − AJ
  })

  it('十四对词干齐全（对齐模板 L..AM）', () => {
    expect(L4_3_PAIR_STEMS).toHaveLength(14)
  })
})
