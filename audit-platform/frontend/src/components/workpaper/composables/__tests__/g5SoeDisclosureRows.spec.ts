import { describe, it, expect } from 'vitest'
import {
  insertAgingBand,
  removeAgingBand,
  createAgingRows,
  safeRate,
} from '../g5ListedDisclosureRows'
import {
  buildDefaultSoeState,
  createEmptyDerecogRow,
  parseSoeDisclosure,
  serializeSoeDisclosure,
  G5_SOE_PROVISION_METHOD_PLACEHOLDER,
} from '../g5SoeDisclosureRows'

describe('g5SoeDisclosureRows', () => {
  it('默认包含国企专有字段', () => {
    const s = buildDefaultSoeState()
    expect(s.derecogRows).toEqual([])
    expect(s.continuing).toEqual({ assetEnd: 0, liabilityEnd: 0 })
    expect(s.provisionMethodNote).toBe('')
    expect(s.natureRows.some((r) => r.rowKey === 'deposit')).toBe(true)
    expect(G5_SOE_PROVISION_METHOD_PLACEHOLDER.length).toBeGreaterThan(10)
  })

  it('serialize/parse round-trip 保留终止确认与继续涉入', () => {
    const s = buildDefaultSoeState()
    s.derecogRows = [{ ...createEmptyDerecogRow(), item: '保理转让', amount: 100, gainLoss: -5 }]
    s.continuing = { assetEnd: 20, liabilityEnd: 15 }
    s.provisionMethodNote = '按账龄组合计提'
    const parsed = parseSoeDisclosure(serializeSoeDisclosure(s))!
    expect(parsed.derecogRows[0].item).toBe('保理转让')
    expect(parsed.continuing.assetEnd).toBe(20)
    expect(parsed.provisionMethodNote).toBe('按账龄组合计提')
  })

  it('账龄「……」动态插段插在合计前', () => {
    let rows = createAgingRows()
    rows = insertAgingBand(rows, '3-4年')
    const labels = rows.map((r) => r.label)
    expect(labels).toContain('3-4年')
    expect(labels[labels.length - 1]).toBe('合计')
    expect(labels.indexOf('3-4年')).toBeLessThan(labels.indexOf('合计'))
  })

  it('可删除自定义账龄段且合计重算', () => {
    let rows = createAgingRows()
    rows = insertAgingBand(rows, '4-5年')
    rows[0].endBalance = 10
    const custom = rows.find((r) => r.label === '4-5年')!
    custom.endBalance = 5
    rows = removeAgingBand(rows, custom.id)
    expect(rows.find((r) => r.label === '4-5年')).toBeUndefined()
    expect(rows.find((r) => r.kind === 'total')!.endBalance).toBe(10)
  })

  it('ECL 率防 #DIV/0!', () => {
    expect(safeRate(1, 0)).toBeNull()
  })
})
