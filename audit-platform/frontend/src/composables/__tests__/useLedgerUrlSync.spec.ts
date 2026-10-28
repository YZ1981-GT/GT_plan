/**
 * useLedgerUrlSync — 穿透状态 ↔ URL query 双向同步测试
 *
 * spec: multi-window-ledger-workbench Phase 4 Task 21
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock vue-router
const mockReplace = vi.fn()
const mockQuery: Record<string, string> = {}

vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: mockReplace }),
  useRoute: () => ({ query: mockQuery }),
}))

import { buildLedgerQuery, useLedgerUrlSync } from '../useLedgerUrlSync'

describe('buildLedgerQuery（页内同步与站外深链共用，advanced-query-linkage-closure 任务 27）', () => {
  it('凭证层级：year 在前，只写非空值', () => {
    expect(buildLedgerQuery({ level: 'voucher', account: '1002', voucherNo: '记-0223', voucherDate: '2025-03-31' }, 2025))
      .toEqual({ year: '2025', level: 'voucher', account: '1002', voucher: '记-0223', voucherDate: '2025-03-31' })
  })

  it('默认值不写（level=balance、balanceTab=account），年度缺省不写', () => {
    expect(buildLedgerQuery({ level: 'balance', account: '1001', balanceTab: 'account' })).toEqual({ account: '1001' })
    expect(buildLedgerQuery({ level: 'ledger', account: '1001' }, null)).toEqual({ level: 'ledger', account: '1001' })
  })

  it('写出的键都能被 readFromUrl 读回同一状态（往返一致）', () => {
    const state = { level: 'aux_ledger', account: '1122', auxType: '客户', auxCode: 'C001', balanceTab: 'aux' }
    Object.assign(mockQuery, buildLedgerQuery(state, '2025'))
    const back = useLedgerUrlSync().readFromUrl()
    expect(back).toMatchObject(state)
    expect(mockQuery.year).toBe('2025')
  })
})

describe('useLedgerUrlSync', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // 清空 mockQuery
    Object.keys(mockQuery).forEach(k => delete mockQuery[k])
  })

  describe('syncToUrl', () => {
    it('余额表状态不写 level（balance 是默认值）', () => {
      const { syncToUrl } = useLedgerUrlSync()
      syncToUrl({ level: 'balance', account: '' })

      expect(mockReplace).toHaveBeenCalledTimes(1)
      const query = mockReplace.mock.calls[0][0].query
      expect(query.level).toBeUndefined()
      expect(query.account).toBeUndefined()
    })

    it('序时账状态写入 level + account', () => {
      const { syncToUrl } = useLedgerUrlSync()
      syncToUrl({ level: 'ledger', account: '1001' })

      const query = mockReplace.mock.calls[0][0].query
      expect(query.level).toBe('ledger')
      expect(query.account).toBe('1001')
    })

    it('凭证状态写入完整穿透链', () => {
      const { syncToUrl } = useLedgerUrlSync()
      syncToUrl({
        level: 'voucher',
        account: '1001',
        voucherNo: 'PZ-001',
        voucherDate: '2025-06-15',
      })

      const query = mockReplace.mock.calls[0][0].query
      expect(query.level).toBe('voucher')
      expect(query.account).toBe('1001')
      expect(query.voucher).toBe('PZ-001')
      expect(query.voucherDate).toBe('2025-06-15')
    })

    it('保留现有的 year query', () => {
      mockQuery.year = '2025'
      const { syncToUrl } = useLedgerUrlSync()
      syncToUrl({ level: 'ledger', account: '6001' })

      const query = mockReplace.mock.calls[0][0].query
      expect(query.year).toBe('2025')
      expect(query.account).toBe('6001')
    })

    it('辅助余额写入 auxType + auxCode', () => {
      const { syncToUrl } = useLedgerUrlSync()
      syncToUrl({
        level: 'aux_ledger',
        account: '1122',
        auxType: '客户',
        auxCode: 'C001',
      })

      const query = mockReplace.mock.calls[0][0].query
      expect(query.auxType).toBe('客户')
      expect(query.auxCode).toBe('C001')
    })
  })

  describe('readFromUrl', () => {
    it('无 query 时返回默认值', () => {
      const { readFromUrl } = useLedgerUrlSync()
      const state = readFromUrl()

      expect(state.level).toBe('balance')
      expect(state.account).toBe('')
      expect(state.voucherNo).toBe('')
      expect(state.balanceTab).toBe('account')
    })

    it('从 query 恢复凭证状态', () => {
      Object.assign(mockQuery, {
        level: 'voucher',
        account: '1001',
        voucher: 'PZ-001',
        voucherDate: '2025-06-15',
      })
      const { readFromUrl } = useLedgerUrlSync()
      const state = readFromUrl()

      expect(state.level).toBe('voucher')
      expect(state.account).toBe('1001')
      expect(state.voucherNo).toBe('PZ-001')
      expect(state.voucherDate).toBe('2025-06-15')
    })

    it('从 query 恢复辅助余额状态', () => {
      Object.assign(mockQuery, {
        level: 'aux_ledger',
        account: '1122',
        auxType: '客户',
        auxCode: 'C001',
        balanceTab: 'aux',
      })
      const { readFromUrl } = useLedgerUrlSync()
      const state = readFromUrl()

      expect(state.level).toBe('aux_ledger')
      expect(state.auxType).toBe('客户')
      expect(state.auxCode).toBe('C001')
      expect(state.balanceTab).toBe('aux')
    })
  })
})
