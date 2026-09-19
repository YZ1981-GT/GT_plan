import { describe, it, expect } from 'vitest'
import {
  defaultContractCostCheckSheet,
  enrichCheckSample,
  enrichCheckSamples,
  calcCheckStats,
  migrateContractCostCheckSheet,
  emptyCheckSample,
  isBlankContractCostCheckSample,
  pruneBlankContractCostCheckSamples,
  evaluateContractCostEvidence,
} from '../useF2ContractCostCheckFormulas'

describe('useF2ContractCostCheckFormulas', () => {
  it('default sheet keeps one editable sample', () => {
    expect(defaultContractCostCheckSheet().samples).toHaveLength(1)
    expect(isBlankContractCostCheckSample(defaultContractCostCheckSheet().samples[0])).toBe(true)
  })

  it('prunes reserved blank samples and retains entered rows', () => {
    const entered = { ...emptyCheckSample(), voucherNo: '记-001' }
    expect(pruneBlankContractCostCheckSamples([
      emptyCheckSample(),
      entered,
      emptyCheckSample(),
    ])).toEqual([entered])
  })

  it('evaluates missing and mismatched supporting documents', () => {
    const checks = evaluateContractCostEvidence({
      ...emptyCheckSample(),
      voucherNo: '记-001',
      businessContent: '材料采购',
      voucherAmount: 1000,
      receiptProductName: '钢材',
      receiptAmount: 800,
    })
    expect(checks.find((item) => item.key === 'voucher')?.status).toBe('ok')
    expect(checks.find((item) => item.key === 'receipt')?.status).toBe('mismatch')
    expect(checks.find((item) => item.key === 'contract')?.status).toBe('missing')
  })

  it('flags abnormal rows', () => {
    const row = { ...emptyCheckSample(), isAbnormal: '是' as const }
    expect(enrichCheckSample(row).hasIssue).toBe(true)
  })

  it('calculates error rate from abnormal voucher amounts', () => {
    const rows = enrichCheckSamples([
      { ...emptyCheckSample(), voucherAmount: 1000, isAbnormal: '否' },
      { ...emptyCheckSample(), voucherAmount: 500, isAbnormal: '是' },
      { ...emptyCheckSample(), voucherAmount: 500, isAbnormal: '否' },
    ])
    const stats = calcCheckStats(rows)
    expect(stats.testedAmount).toBe(2000)
    expect(stats.incorrectAmount).toBe(500)
    expect(stats.errorRate).toBe(0.25)
    expect(stats.abnormalCount).toBe(1)
  })

  it('migrates legacy flat array rows', () => {
    const legacy = [{
      id: '1',
      projectName: '项目A',
      voucherNo: '记-001',
      amount: 3000,
      contractNo: 'HT-2024-01',
      isCorrect: '否',
    }]
    const sheet = migrateContractCostCheckSheet(legacy)
    expect(sheet?.samples[0].projectName).toBe('项目A')
    expect(sheet?.samples[0].voucherAmount).toBe(3000)
    expect(sheet?.samples[0].contractDateNo).toBe('HT-2024-01')
    expect(sheet?.samples[0].isAbnormal).toBe('是')
  })

  it('migrates new sheet JSON', () => {
    const legacy = {
      sampling: { populationDesc: '测试总体', method: '随机' },
      samples: [{ ...emptyCheckSample(), projectName: 'X' }],
      statNote: '无异常',
    }
    const sheet = migrateContractCostCheckSheet(legacy)
    expect(sheet?.sampling.populationDesc).toBe('测试总体')
    expect(sheet?.samples[0].projectName).toBe('X')
    expect(sheet?.statNote).toBe('无异常')
  })

  it('merges legacy params JSON', () => {
    const params = JSON.stringify({ populationAmount: 99999, scope: '1410余额' })
    const sheet = migrateContractCostCheckSheet(null, params)
    expect(sheet?.sampling.populationAmount).toBe(99999)
    expect(sheet?.sampling.populationDesc).toBe('1410余额')
  })
})
