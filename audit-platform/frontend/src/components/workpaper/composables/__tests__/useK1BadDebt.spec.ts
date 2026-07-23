import { describe, expect, it } from 'vitest'
import {
  parseK13Payload,
  recalcK1BadDebtMainRow,
  recalcStageClosing,
  flattenK13ForImport,
  sumK13Column,
  defaultStageMovements,
} from '../useK1BadDebt'

describe('useK1BadDebt K1-3', () => {
  it('默认结构：单项/组合/合计 + 三阶段矩阵', () => {
    const p = parseK13Payload(null)
    expect(p.version).toBe(2)
    expect(p.mainRows.filter((r) => r.isFixed)).toHaveLength(3)
    expect(p.stageMovements.length).toBeGreaterThanOrEqual(10)
    expect(p.stageMovements.some((r) => r.key === 'closing')).toBe(true)
  })

  it('滚动公式：期末审定 = 期初 + 计提 - 转回 - 核销 + 调整', () => {
    const row = recalcK1BadDebtMainRow({
      id: 't', category: 'individual', label: '测试', isSubRow: false, isFixed: true,
      priorBook: 100, priorAdj: 0, priorAudited: 0,
      currentProvision: 50, currentOtherIncrease: 0,
      currentReversal: 10, currentWriteOff: 5, currentOtherDecrease: 0,
      currentBook: 0, currentAdj: 2, currentAudited: 0, reason: '',
    })
    expect(row.priorAudited).toBe(100)
    expect(row.currentBook).toBe(135)
    expect(row.currentAudited).toBe(137)
  })

  it('三阶段期末 = 各行代数和', () => {
    const moves = defaultStageMovements()
    moves.find((r) => r.key === 'opening')!.stage1 = 100
    moves.find((r) => r.key === 'provision')!.stage1 = 20
    const next = recalcStageClosing(moves)
    const closing = next.find((r) => r.key === 'closing')!
    expect(closing.stage1).toBe(120)
  })

  it('V1 扁平行可迁移', () => {
    const legacy = [{
      id: '1', label: 'A公司', beginBadDebt: 10, provision: 5, reversal: 1, writeoff: 0,
      endBadDebt: 14, provisionRate: null, receivableEnd: 0, stage: 1, remark: '原因',
    }]
    const p = parseK13Payload(JSON.stringify(legacy))
    expect(p.mainRows.some((r) => r.isSubRow && r.label === 'A公司')).toBe(true)
    const flat = flattenK13ForImport(p)
    expect(flat[0].label).toBe('A公司')
    expect(flat[0].endBadDebt).toBe(14)
  })

  it('sumK13Column 从合计行取转回/核销', () => {
    const p = parseK13Payload(null)
    const total = p.mainRows.find((r) => r.category === 'total')!
    total.currentReversal = 30
    total.currentWriteOff = 12
    expect(sumK13Column(p, 'reversal')).toBe(30)
    expect(sumK13Column(p, 'writeoff')).toBe(12)
  })
})
