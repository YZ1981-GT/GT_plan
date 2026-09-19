import { describe, it, expect, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  evaluateK1VoucherChecks,
  k1VoucherCardStatus,
  isK1VoucherRowChecksComplete,
  useK1VoucherCheck,
  type K1VoucherRow,
} from '../useK1VoucherCheck'

function blankRow(partial: Partial<K1VoucherRow> = {}): K1VoucherRow {
  return {
    id: 'r1',
    debtorName: '甲公司',
    date: '2025-01-01',
    voucherNo: '记-001',
    businessContent: '借款',
    offsetAccount: '1002',
    offsetSubAccount: '',
    debitAmount: 1000,
    creditAmount: 0,
    supportingDoc: '',
    checks: [false, false, false, false, false],
    indexNo: '',
    abnormal: false,
    remark: '',
    ...partial,
  }
}

describe('evaluateK1VoucherChecks', () => {
  it('marks pending checks and warn when supportingDoc empty', () => {
    const items = evaluateK1VoucherChecks(blankRow())
    expect(items.filter((i) => i.key.startsWith('check-')).every((i) => i.status === 'pending')).toBe(true)
    expect(items.find((i) => i.key === 'supporting')?.status).toBe('warn')
  })

  it('marks ok when all five checks and supporting filled', () => {
    const row = blankRow({
      checks: [true, true, true, true, true],
      supportingDoc: '银行回单',
    })
    expect(isK1VoucherRowChecksComplete(row)).toBe(true)
    const items = evaluateK1VoucherChecks(row)
    expect(items.filter((i) => i.key.startsWith('check-')).every((i) => i.status === 'ok')).toBe(true)
    expect(k1VoucherCardStatus(row).type).toBe('success')
  })

  it('card status prefers abnormal', () => {
    expect(k1VoucherCardStatus(blankRow({ abnormal: true })).type).toBe('danger')
  })
})

describe('useK1VoucherCheck.updateVoucherRow', () => {
  it('merges patch into occurrence row', () => {
    const map = ref(new Map())
    const vc = useK1VoucherCheck({ allResponses: map })
    vc.addOccurrenceRow()
    const id = vc.occurrenceRows.value[0].id
    expect(vc.updateVoucherRow('occurrence', id, {
      debtorName: '乙公司',
      checks: [true, true, true, true, true],
      supportingDoc: '合同',
    })).toBe(true)
    expect(vc.occurrenceRows.value[0].debtorName).toBe('乙公司')
    expect(isK1VoucherRowChecksComplete(vc.occurrenceRows.value[0])).toBe(true)
  })
})
