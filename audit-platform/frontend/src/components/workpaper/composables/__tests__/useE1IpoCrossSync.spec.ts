/**
 * E1 IPO 横切：E1-15→30 / E1-31→32 / 日记账合并 — 纯函数单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  parseE15AccountList,
  readE15BookInterest,
  previewE15Accounts,
  mapDepositTypeFromE15,
  buildGroupsFromE15Accounts,
  expandMonthlyToDailyBalances,
  mergeE15GroupsIntoExisting,
} from '../useE1DepositDailyMatch'
import { collectE31SuspectCandidates } from '../useE1KeyPersonFlow'
import {
  mergeJournalLineLists,
  createEmptyJournalLine,
} from '../useE1BankFlowReconcile'

describe('E1-15 → E1-30 sync helpers', () => {
  it('parseE15AccountList accepts array / accounts / rows', () => {
    expect(parseE15AccountList(JSON.stringify([{ bank: 'A' }]))).toHaveLength(1)
    expect(parseE15AccountList(JSON.stringify({ accounts: [{ bank: 'B' }] }))).toHaveLength(1)
    expect(parseE15AccountList(JSON.stringify({ rows: [{ bank: 'C' }] }))).toHaveLength(1)
    expect(parseE15AccountList('')).toEqual([])
    expect(parseE15AccountList('{bad')).toEqual([])
  })

  it('mapDepositTypeFromE15 classifies deposit types', () => {
    expect(mapDepositTypeFromE15('七天通知')).toBe('notice')
    expect(mapDepositTypeFromE15('大额存单')).toBe('cd')
    expect(mapDepositTypeFromE15('活期')).toBe('demand')
  })

  it('readE15BookInterest prefers summary then per-account', () => {
    expect(readE15BookInterest(JSON.stringify({ bookInterest: 123 }), [])).toBe(123)
    expect(readE15BookInterest(null, [
      { bookInterests: [10, 20] },
      { bookInterests: [5] },
    ])).toBe(35)
  })

  it('previewE15Accounts summarizes banks', () => {
    const p = previewE15Accounts(
      [{ bank: '工行' }, { bank: '工行' }, { bank: '建行' }],
      99,
      2,
    )
    expect(p.accountCount).toBe(3)
    expect(p.bookInterest).toBe(99)
    expect(p.existingGroups).toBe(2)
    expect(p.banks).toContain('工行')
    expect(p.banks).toContain('建行')
  })

  it('buildGroupsFromE15Accounts + expand monthly balances', () => {
    const groups = buildGroupsFromE15Accounts([
      { bank: '工行', accountNo: '11', depositType: '活期', annualRate: 0.003, balances: [100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].accounts[0].accountNo).toBe('11')
    const { balances, daysFilled } = expandMonthlyToDailyBalances(2024, groups, {}, false)
    expect(daysFilled).toBe(31)
    expect(balances['2024-01-15'][groups[0]._acctId]).toBe(100)
  })

  it('mergeE15GroupsIntoExisting keeps existing account ids', () => {
    const existing = [{
      id: 'dg1',
      depositType: 'demand' as const,
      bank: '工行',
      annualRate: 0.002,
      accounts: [{ id: 'da-old', accountNo: '11' }],
    }]
    const incoming = buildGroupsFromE15Accounts([
      { bank: '工行', accountNo: '11', type: '活期', annualRate: 0.003, balances: [50] },
      { bank: '建行', accountNo: '22', type: '活期', annualRate: 0.0025, balances: [80] },
    ])
    const m = mergeE15GroupsIntoExisting(existing, incoming)
    expect(m.addedAccounts).toBe(1)
    expect(m.groups.some(g => g.accounts.some(a => a.id === 'da-old'))).toBe(true)
    expect(m.stashed.some(s => s._acctId === 'da-old')).toBe(true)
  })

  it('expandMonthlyToDailyBalances skipExisting does not overwrite', () => {
    const groups = buildGroupsFromE15Accounts([
      { bank: '工行', accountNo: '11', balances: [100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
    ])
    const acctId = groups[0]._acctId
    const existing = { '2024-01-01': { [acctId]: 999 } }
    const { balances, daysFilled } = expandMonthlyToDailyBalances(2024, groups, existing, true)
    expect(balances['2024-01-01'][acctId]).toBe(999)
    expect(daysFilled).toBe(30)
  })
})

describe('E1-31 → E1-32 seed helpers', () => {
  it('collectE31SuspectCandidates picks third-party / inconsistent / large unmatched', () => {
    const pack31 = {
      largeThresholdBookToBank: 1000,
      largeThresholdBankToBook: 1000,
      bookToBank: [
        { thirdParty: '是', infoConsistent: '是', debit: 100, credit: 0, payerPayee: '甲', sDate: '2024-01-01' },
        { thirdParty: '否', infoConsistent: '否', debit: 50, credit: 0, counterparty: '乙', vDate: '2024-01-02' },
        { thirdParty: '否', infoConsistent: '', debit: 5000, credit: 0, payerPayee: '丙', sDate: '2024-01-03' },
        { thirdParty: '否', infoConsistent: '是', debit: 9000, credit: 0, payerPayee: '丁', sDate: '2024-01-04' },
      ],
      bankToBook: [
        { thirdParty: '否', infoConsistent: '否', stmtAmount: 200, debit: 0, credit: 0, payerPayee: '戊', sDate: '2024-01-05' },
      ],
    }
    const r = collectE31SuspectCandidates(pack31)
    expect(r.candidates.length).toBe(4)
    expect(r.third).toBe(1)
    expect(r.candidates.find(c => c.counterpartyName === '丁')).toBeUndefined()
    expect(r.candidates.find(c => c.counterpartyName === '丙')?.income).toBe(5000)
    expect(r.candidates.find(c => c.counterpartyName === '戊')?.income).toBe(200)
  })

  it('collectE31SuspectCandidates dedupes and handles empty pack', () => {
    expect(collectE31SuspectCandidates(null).candidates).toEqual([])
    const r = collectE31SuspectCandidates({
      bookToBank: [
        { thirdParty: '是', debit: 1, payerPayee: 'X', sDate: '2024-01-01' },
        { thirdParty: '是', debit: 1, payerPayee: 'X', sDate: '2024-01-01' },
      ],
    })
    expect(r.candidates).toHaveLength(1)
  })
})

describe('mergeJournalLineLists', () => {
  const a = { ...createEmptyJournalLine(), id: '1', voucherNo: 'V1', date: '2024-01-01', debit: 10, credit: 0 }
  const b = { ...createEmptyJournalLine(), id: '2', voucherNo: 'V2', date: '2024-01-02', debit: 0, credit: 20 }
  const b2 = { ...createEmptyJournalLine(), id: '3', voucherNo: 'V2', date: '2024-01-02', debit: 0, credit: 20, businessContent: '更新' }

  it('append concatenates', () => {
    expect(mergeJournalLineLists([a], [b], 'append')).toHaveLength(2)
  })

  it('replace overwrites', () => {
    expect(mergeJournalLineLists([a], [b], 'replace')).toEqual([b])
  })

  it('merge dedupes by voucher+date+amt', () => {
    const out = mergeJournalLineLists([a, b], [b2], 'merge')
    expect(out).toHaveLength(2)
    expect(out.find(j => j.voucherNo === 'V2')?.businessContent).toBe('更新')
  })
})
