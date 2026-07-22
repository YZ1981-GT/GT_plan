import { describe, it, expect } from 'vitest'
import {
  findG13SourceFvMismatches,
  findG14EclMismatches,
  findG13PendingFvSources,
  formatG13SourceFvCrossMessage,
  isG13SourceFvReconciled,
  calcG1FvChangeAuditedTotal,
  sumG13DetailAuditedBySource,
} from '../gCycleExternalCross'

describe('gCycleExternalCross', () => {
  it('sumG13DetailAuditedBySource 按所属科目汇总', () => {
    const rows = [
      { rowId: 'a', belongAccount: 'G1', currentAudited: 100 },
      { rowId: 'b', belongAccount: 'G1', currentAudited: 50 },
      { rowId: 'c', belongAccount: 'G9', currentAudited: 20 },
    ]
    expect(sumG13DetailAuditedBySource(rows, 'G1')).toBe(150)
    expect(sumG13DetailAuditedBySource(rows, 'G8')).toBe(0)
  })

  it('findG13SourceFvMismatches 检测差异', () => {
    const rows = [{ rowId: 'a', belongAccount: 'G1', currentAudited: 100 }]
    const mismatches = findG13SourceFvMismatches(rows, { G1: 80 })
    expect(mismatches).toHaveLength(1)
    expect(mismatches[0].variance).toBe(20)
    expect(formatG13SourceFvCrossMessage(mismatches)).toMatch(/G13-2 与源科目/)
  })

  it('findG13SourceFvMismatches 一致时不报差异', () => {
    const rows = [{ rowId: 'a', belongAccount: 'G1', currentAudited: 100 }]
    expect(findG13SourceFvMismatches(rows, { G1: 100 })).toHaveLength(0)
  })

  it('仅有部分源数据时不判定整包已勾稽（防假绿）', () => {
    const rows = [
      { rowId: 'a', belongAccount: 'G1', currentAudited: 100 },
      { rowId: 'b', belongAccount: 'G8', currentAudited: 50 },
    ]
    // 仅 G1 有外部数且一致，G8 缺失 → 未完成
    expect(isG13SourceFvReconciled(rows, { G1: 100 })).toBe(false)
    expect(findG13PendingFvSources(rows, { G1: 100 })).toEqual(['G8'])
    // 两源齐全且一致 → 完成
    expect(isG13SourceFvReconciled(rows, { G1: 100, G8: 50 })).toBe(true)
  })

  it('findG14EclMismatches 检测 ECL 差异', () => {
    const rows = [{ rowKey: 'ar', profitLoss: 5000 }]
    const mismatches = findG14EclMismatches(rows, { ar: 4800 })
    expect(mismatches).toHaveLength(1)
    expect(mismatches[0].variance).toBe(200)
  })

  it('calcG1FvChangeAuditedTotal 仅汇总 fv-change 行', () => {
    const total = calcG1FvChangeAuditedTotal([
      { measureKey: 'cost', currentAudited: 1000 },
      { measureKey: 'fv-change', currentAudited: 120 },
      { measureKey: 'fv-change', currentAudited: 30 },
    ])
    expect(total).toBe(150)
  })
})
