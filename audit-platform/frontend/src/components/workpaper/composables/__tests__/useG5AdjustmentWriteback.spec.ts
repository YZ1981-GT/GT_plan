import { describe, it, expect } from 'vitest'
import {
  classifyG5WritebackBucket,
  computeG5WritebackNets,
  createEmptyEntry,
  entryNetForBucket,
  G5_WRITEBACK_ROW_KEYS,
} from '../useG5Adjustment'

describe('G5-4 writeback buckets', () => {
  it('classifies accounts into gross / provision / oneYear', () => {
    expect(classifyG5WritebackBucket('1531', '长期应收款')).toBe('gross')
    expect(classifyG5WritebackBucket('1532', '未实现融资收益')).toBe('gross')
    expect(classifyG5WritebackBucket('1231', '坏账准备')).toBe('provision')
    expect(classifyG5WritebackBucket('1481', '一年内到期的非流动资产')).toBe('oneYear')
    expect(classifyG5WritebackBucket('1002', '银行存款')).toBeNull()
  })

  it('provision net uses credit − debit', () => {
    const row = createEmptyEntry(1, '补提')
    row.accountCode = '1231'
    row.accountName = '坏账准备'
    row.creditAmount = 50
    row.debitAmount = 0
    expect(entryNetForBucket(row, 'provision')).toBe(50)
    expect(entryNetForBucket(row, 'gross')).toBe(-50)
  })

  it('splits mixed entries so provision does not hit gross row', () => {
    const gross = createEmptyEntry(1, '调增应收')
    gross.accountCode = '1531'
    gross.debitAmount = 100
    gross.creditAmount = 0

    const provision = createEmptyEntry(2, '补提坏账')
    provision.accountCode = '1231'
    provision.accountName = '坏账准备'
    provision.debitAmount = 0
    provision.creditAmount = 30

    const oneYear = createEmptyEntry(3, '重分类一年内')
    oneYear.accountCode = '1481'
    oneYear.accountName = '一年内到期的非流动资产'
    oneYear.debitAmount = 40
    oneYear.creditAmount = 0

    const cash = createEmptyEntry(4, '银行存款')
    cash.accountCode = '1002'
    cash.accountName = '银行存款'
    cash.creditAmount = 110
    cash.debitAmount = 0

    const nets = computeG5WritebackNets([gross, provision, oneYear, cash])
    expect(nets.gross.aje).toBe(100)
    expect(nets.provision.aje).toBe(30)
    expect(nets.oneYear.aje).toBe(40)
    expect(G5_WRITEBACK_ROW_KEYS.gross).toBe('gross-collective-business')
    expect(G5_WRITEBACK_ROW_KEYS.provision).toBe('provision-collective-business')
    expect(G5_WRITEBACK_ROW_KEYS.oneYear).toBe('gross-one-year')
  })
})
