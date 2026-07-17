import { describe, it, expect } from 'vitest'
import {
  assessCutoffRow,
  classifyCutoffTiming,
  detectEvidenceGap,
} from '../f2CutoffJudgment'

describe('f2CutoffJudgment', () => {
  it('same side → ok', () => {
    expect(classifyCutoffTiming('2025-12-20', '2025-12-25', '2025-12-31')).toBe('ok')
    expect(classifyCutoffTiming('2026-01-02', '2026-01-05', '2025-12-31')).toBe('ok')
  })

  it('book before / doc after → early_book', () => {
    expect(classifyCutoffTiming('2026-01-05', '2025-12-28', '2025-12-31')).toBe('early_book')
  })

  it('doc before / book after → late_book', () => {
    expect(classifyCutoffTiming('2025-12-28', '2026-01-05', '2025-12-31')).toBe('late_book')
  })

  it('detects missing doc / book / amount mismatch', () => {
    expect(detectEvidenceGap({
      voucherNo: '记-1', bookDate: '2025-12-30', docNo: '', docDate: '', amount: 100,
    })).toBe('missing_doc')
    expect(detectEvidenceGap({
      voucherNo: '', bookDate: '', docNo: 'RK-1', docDate: '2025-12-30', amount: 0,
    })).toBe('missing_book')
    expect(detectEvidenceGap({
      voucherNo: '记-1', bookDate: '2025-12-30', docNo: 'RK-1', docDate: '2025-12-30',
      amount: 100, docAmount: 120,
    })).toBe('amount_mismatch')
  })

  it('assess combines timing + evidence', () => {
    const j = assessCutoffRow({
      docDate: '2026-01-02',
      bookDate: '2025-12-30',
      periodEnd: '2025-12-31',
      voucherNo: 'V1',
      docNo: 'D1',
      amount: 10,
    })
    expect(j.timing).toBe('early_book')
    expect(j.isCorrect).toBe(false)
    expect(j.isCrossPeriod).toBe(true)
  })
})
