/**
 * F2-12 合同履约成本 — 转入转出与库龄
 */
import { describe, it, expect } from 'vitest'
import {
  enrichRow,
  normalizeContractPerfRow,
  sumContractPerfMovement,
  type ContractPerfRow,
} from '../useF2ContractPerfSheet'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'

const segs = PRESET_SEGMENTS.THREE_YEAR

function row(partial: Partial<ContractPerfRow> & { id?: string }): ContractPerfRow {
  return normalizeContractPerfRow({ id: '1', ...partial }, segs)
}

describe('useF2ContractPerfSheet', () => {
  it('期末 = 期初 + 转入 − 转出；库龄勾稽', () => {
    const e = enrichRow(row({
      openingAmt: 1000,
      increaseAmt: 200,
      decreaseAmt: 100,
      aging: { within1: 900, y1to2: 200, y2to3: 0, over3: 0 },
    }), segs)
    expect(e.closingAmt).toBe(1100)
    expect(e.agingTotal).toBe(1100)
    expect(e.agingOk).toBe(true)
  })

  it('旧通用明细字段可迁移', () => {
    const n = normalizeContractPerfRow({
      id: 'x',
      itemCode: 'P1',
      itemName: '项目甲',
      openingAmt: 500,
      increaseAmt: 50,
      decreaseAmt: 20,
    } as any, segs)
    expect(n.projectCode).toBe('P1')
    expect(n.projectName).toBe('项目甲')
    expect(enrichRow(n, segs).closingAmt).toBe(530)
  })

  it('sumContractPerfMovement 汇总', () => {
    const mv = sumContractPerfMovement([
      { openingAmt: 100, increaseAmt: 50, decreaseAmt: 20 },
      { openingAmt: 200, increaseAmt: 0, decreaseAmt: 10 },
    ])
    expect(mv.opening).toBe(300)
    expect(mv.closing).toBe(320)
  })
})
