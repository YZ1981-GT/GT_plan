/**
 * j1DisclosureRowModel — 行模型 / 合计口径 / 父行派生 纯函数测试
 *
 * 父行派生依据（源模板 Excel 公式）：
 * - 上市 `B20=SUM(B21:B27)`（社会保险费 = Σ 其中：医疗/工伤/生育 + 预留区）
 * - 上市 `B41=SUM(B42:B45)`（离职后福利 = Σ 其中：基本养老/失业/年金/其他）
 * - 国企 `B19=SUM(B20:B23)` / `B32=SUM(B33:B36)` 同构
 * 合计行公式显式排除这些「其中：」子行（`B35=SUM(B18:B20)+SUM(B28:B34)`）
 *
 * spec: .kiro/specs/j1-disclosure-template-alignment/ Task 4.3
 */
import { describe, expect, it } from 'vitest'
import {
  applyParentSums,
  buildDisclosureSubtotal,
  derivedParentIds,
  recalcDisclosureRow,
  type J1DisclosureRow,
} from '../j1DisclosureRowModel'

function row(
  label: string,
  begin = 0,
  increase = 0,
  decrease = 0,
  indent = 0,
): J1DisclosureRow {
  return recalcDisclosureRow({
    id: `r-${label}-${indent}`,
    label,
    category: 'short_term',
    ...(indent ? { indent } : {}),
    beginBalance: begin,
    increase,
    decrease,
    endBalance: 0,
  })
}

/** 短期薪酬骨架：社会保险费带 3 个「其中：」子项，其余为独立行 */
function shortTermRows(): J1DisclosureRow[] {
  return [
    row('工资、奖金、津贴和补贴', 100, 10, 4),
    row('社会保险费', 999, 999, 999), // 故意填错，验证被派生覆盖
    row('其中：1．医疗保险费', 10, 1, 0, 1),
    row('2．工伤保险费', 20, 2, 1, 1),
    row('3．生育保险费', 5, 1, 1, 1),
    row('住房公积金', 15, 1, 1),
  ]
}

function find(rows: J1DisclosureRow[], label: string): J1DisclosureRow {
  const hit = rows.find((r) => r.label === label)
  if (!hit) throw new Error(`未找到行：${label}`)
  return hit
}

// ─── recalcDisclosureRow ────────────────────────────────────────────────

describe('recalcDisclosureRow — 期末 = 期初 + 增加 − 减少', () => {
  it('负债贷方口径', () => {
    expect(row('x', 100, 30, 12).endBalance).toBe(118)
  })

  it('缺值按 0 处理，不产生 NaN', () => {
    const r = { ...row('x'), beginBalance: undefined as unknown as number }
    expect(recalcDisclosureRow(r).endBalance).toBe(0)
  })
})

// ─── buildDisclosureSubtotal ────────────────────────────────────────────

describe('buildDisclosureSubtotal — 只累加非缩进行', () => {
  it('排除「其中：」缩进行（源模板合计公式如此）', () => {
    const rows = shortTermRows()
    applyParentSums(rows)
    const total = buildDisclosureSubtotal('t', '合 计', 'short_term', rows)
    // 工资 100 + 社会保险费 35 + 住房公积金 15（不含医疗 10 / 工伤 20 / 生育 5）
    expect(total.beginBalance).toBe(150)
    expect(total.isSubtotal).toBe(true)
  })

  it('排除已有的 subtotal 行（防重复计入）', () => {
    const rows = [row('a', 10), { ...row('合 计', 10), isSubtotal: true }]
    expect(buildDisclosureSubtotal('t', '合 计', 'x', rows).beginBalance).toBe(10)
  })

  it('空表返回全零合计', () => {
    const total = buildDisclosureSubtotal('t', '合 计', 'x', [])
    expect([total.beginBalance, total.increase, total.decrease, total.endBalance]).toEqual([
      0, 0, 0, 0,
    ])
  })
})

// ─── derivedParentIds ───────────────────────────────────────────────────

describe('derivedParentIds — 识别派生父行', () => {
  it('非缩进行后紧跟连续缩进行 → 判为派生父行', () => {
    expect(derivedParentIds(shortTermRows())).toEqual([find(shortTermRows(), '社会保险费').id])
  })

  it('无缩进子行的行不在其中（保持可手工录入，与历史行为一致）', () => {
    const ids = derivedParentIds(shortTermRows())
    expect(ids).not.toContain(find(shortTermRows(), '工资、奖金、津贴和补贴').id)
    expect(ids).not.toContain(find(shortTermRows(), '住房公积金').id)
  })

  it('多组父子都识别（设定提存计划两组）', () => {
    const rows = [
      row('离职后福利', 0, 0, 0),
      row('其中：基本养老保险费', 1, 0, 0, 1),
      row('失业保险费', 2, 0, 0, 1),
      row('其他长期职工福利（不适用的删除）', 0, 0, 0),
      row('其中：xxx', 3, 0, 0, 1),
    ]
    expect(derivedParentIds(rows)).toEqual([rows[0].id, rows[3].id])
  })

  it('缩进行本身与合计行不判为父行', () => {
    const rows = [
      row('父', 0, 0, 0),
      row('子', 1, 0, 0, 1),
      { ...row('合 计'), isSubtotal: true },
    ]
    expect(derivedParentIds(rows)).toEqual([rows[0].id])
  })

  it('合计行截断子项区间（合计行之后的缩进行不归前一父行）', () => {
    const rows = [
      row('父', 0, 0, 0),
      { ...row('合 计'), isSubtotal: true },
      row('孤立缩进行', 5, 0, 0, 1),
    ]
    expect(derivedParentIds(rows)).toEqual([])
  })
})

// ─── applyParentSums ────────────────────────────────────────────────────

describe('applyParentSums — 父行 = Σ 紧邻缩进子行', () => {
  it('覆盖父行的期初/增加/减少，并重算期末', () => {
    const rows = shortTermRows()
    applyParentSums(rows)
    const parent = find(rows, '社会保险费')
    expect(parent.beginBalance).toBe(35) // 10 + 20 + 5
    expect(parent.increase).toBe(4) // 1 + 2 + 1
    expect(parent.decrease).toBe(2) // 0 + 1 + 1
    expect(parent.endBalance).toBe(37) // 35 + 4 − 2
  })

  it('返回被改写的父行数；值已相等时不计入（便于判断是否需落库）', () => {
    const rows = shortTermRows()
    expect(applyParentSums(rows)).toBe(1)
    expect(applyParentSums(rows)).toBe(0) // 幂等
  })

  it('无缩进子行的行完全不动（不会被清零）', () => {
    const rows = shortTermRows()
    applyParentSums(rows)
    expect(find(rows, '工资、奖金、津贴和补贴').beginBalance).toBe(100)
    expect(find(rows, '住房公积金').beginBalance).toBe(15)
  })

  it('新增子行后父行自动跟着变（对「+ 新增行」生效）', () => {
    const rows = shortTermRows()
    applyParentSums(rows)
    expect(find(rows, '社会保险费').beginBalance).toBe(35)
    // 在生育保险费后插入一个新险种子项
    rows.splice(5, 0, row('4．补充医疗保险费', 7, 0, 0, 1))
    expect(applyParentSums(rows)).toBe(1)
    expect(find(rows, '社会保险费').beginBalance).toBe(42)
  })

  it('删除子行后父行同步回落', () => {
    const rows = shortTermRows()
    applyParentSums(rows)
    rows.splice(2, 1) // 删掉医疗保险费
    applyParentSums(rows)
    expect(find(rows, '社会保险费').beginBalance).toBe(25) // 20 + 5
  })

  it('全部子行被删除后父行不再派生（退回可手工录入，值保持最后一次派生结果）', () => {
    const rows = shortTermRows()
    applyParentSums(rows)
    rows.splice(2, 3)
    expect(derivedParentIds(rows)).toEqual([])
    expect(applyParentSums(rows)).toBe(0)
    expect(find(rows, '社会保险费').beginBalance).toBe(35)
  })

  it('多组父子各自独立求和，互不串味', () => {
    const rows = [
      row('离职后福利', 0, 0, 0),
      row('其中：基本养老保险费', 10, 1, 0, 1),
      row('失业保险费', 20, 2, 0, 1),
      row('其他长期职工福利（不适用的删除）', 0, 0, 0),
      row('其中：xxx', 100, 5, 1, 1),
    ]
    applyParentSums(rows)
    expect(rows[0].beginBalance).toBe(30)
    expect(rows[3].beginBalance).toBe(100)
  })

  it('空表 / 无父子结构时返回 0 且不抛错', () => {
    expect(applyParentSums([])).toBe(0)
    expect(applyParentSums([row('a', 1), row('b', 2)])).toBe(0)
  })
})
