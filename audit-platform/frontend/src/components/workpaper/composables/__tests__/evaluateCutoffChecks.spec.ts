import { describe, it, expect } from 'vitest'
import {
  assessCutoffRow,
  evaluateCutoffChecks,
  classifyCutoffTiming,
} from '../f2CutoffJudgment'

describe('evaluateCutoffChecks', () => {
  it('flags missing doc', () => {
    const checks = evaluateCutoffChecks({
      voucherNo: 'V1',
      bookDate: '2025-12-31',
      docNo: '',
      docDate: '',
      amount: 100,
      periodEnd: '2025-12-31',
    })
    expect(checks.find((c) => c.key === 'doc')?.status).toBe('missing')
  })

  it('flags early book timing', () => {
    expect(classifyCutoffTiming('2026-01-05', '2025-12-30', '2025-12-31')).toBe('early_book')
    const checks = evaluateCutoffChecks({
      voucherNo: 'V1',
      bookDate: '2025-12-30',
      docNo: 'D1',
      docDate: '2026-01-05',
      amount: 100,
      docAmount: 100,
      periodEnd: '2025-12-31',
    })
    expect(checks.find((c) => c.key === 'timing')?.status).toBe('mismatch')
    expect(assessCutoffRow({
      voucherNo: 'V1', bookDate: '2025-12-30', docNo: 'D1', docDate: '2026-01-05',
      amount: 100, docAmount: 100, periodEnd: '2025-12-31',
    }).isCorrect).toBe(false)
  })

  it('ok when same side and amounts match', () => {
    const checks = evaluateCutoffChecks({
      voucherNo: 'V1',
      bookDate: '2025-12-20',
      docNo: 'D1',
      docDate: '2025-12-18',
      amount: 50,
      docAmount: 50,
      periodEnd: '2025-12-31',
    })
    expect(checks.every((c) => c.status === 'ok')).toBe(true)
  })
})
