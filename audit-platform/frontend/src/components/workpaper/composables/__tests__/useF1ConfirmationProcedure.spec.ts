/**
 * useF1ConfirmationProcedure 纯函数单测
 */
import { describe, it, expect } from 'vitest'
import {
  parseConfirmationCandidates,
  computeConfirmationCoverage,
  markRowsConfirmedInJson,
  isConfirmedMarked,
} from '../useF1ConfirmationProcedure'

describe('useF1ConfirmationProcedure helpers', () => {
  const sampleJson = JSON.stringify([
    { rowId: '__subtotal__', customerName: '合计', endAudited: 1000 },
    { rowId: 'r1', customerName: '甲公司', endAudited: 800, isConfirmed: 'Y' },
    { rowId: 'r2', customerName: '乙公司', endAudited: 200, isConfirmed: '' },
    { rowId: 'r3', customerName: '丙公司', endAudited: 0, isConfirmed: '' },
  ])

  it('parseConfirmationCandidates excludes meta rows and zero balance', () => {
    const rows = parseConfirmationCandidates(sampleJson)
    expect(rows).toHaveLength(2)
    expect(rows[0].customerName).toBe('甲公司')
    expect(rows[1].customerName).toBe('乙公司')
  })

  it('computeConfirmationCoverage uses confirmed balance ratio', () => {
    const rows = parseConfirmationCandidates(sampleJson)
    const cov = computeConfirmationCoverage(rows)
    expect(cov.totalAccounts).toBe(2)
    expect(cov.totalBalance).toBe(1000)
    expect(cov.confirmedBalance).toBe(800)
    expect(cov.coverageRatio).toBeCloseTo(80)
  })

  it('isConfirmedMarked accepts Y and 是', () => {
    expect(isConfirmedMarked('Y')).toBe(true)
    expect(isConfirmedMarked('是')).toBe(true)
    expect(isConfirmedMarked('N')).toBe(false)
  })

  it('markRowsConfirmedInJson updates only selected unmarked rows', () => {
    const { json, changed } = markRowsConfirmedInJson(sampleJson, ['r2'])
    expect(changed).toBe(1)
    const parsed = JSON.parse(json)
    expect(parsed.find((r: any) => r.rowId === 'r2').isConfirmed).toBe('Y')
    expect(parsed.find((r: any) => r.rowId === 'r1').isConfirmed).toBe('Y')
  })

  it('markRowsConfirmedInJson is idempotent for already confirmed', () => {
    const { changed } = markRowsConfirmedInJson(sampleJson, ['r1'])
    expect(changed).toBe(0)
  })
})
