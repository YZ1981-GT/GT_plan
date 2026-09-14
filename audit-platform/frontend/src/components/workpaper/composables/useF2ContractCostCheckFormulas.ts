/**
 * F2-56 合同履约成本检查表（对齐致同源模板）
 *
 * 证据勾稽：记账凭证 ↔ 合同/验收/物流/费用分配
 */
import { calcSubtotal } from './useF2SpecialFormulaEngine'

export type YesNo = '是' | '否' | ''

export interface ContractCostCheckSample {
  id: string
  projectName: string
  accountDetail: string
  voucherNo: string
  businessContent: string
  offsetAccount: string
  offsetProject: string
  voucherAmount: number
  contractDateNo: string
  contractTerms: string
  receiptProductName: string
  receiptAmount: number
  logisticsQty: number
  logisticsDateNo: string
  logisticsProductName: string
  logisticsProvider: string
  allocQty: number
  allocMonth: string
  allocAmount: number
  allocBasis: string
  indexRef: string
  isAbnormal: YesNo
  issueDesc: string
}

export interface ContractCostCheckSampling {
  populationDesc: string
  method: string
  process: string
  populationAmount: number
  materiality: number
  tolerableMisstatement: number
  expectedMisstatement: number
  sampleSize: number
}

export interface ContractCostCheckSheet {
  sampling: ContractCostCheckSampling
  samples: ContractCostCheckSample[]
  statNote: string
}

export interface EnrichedContractCostCheck extends ContractCostCheckSample {
  hasIssue: boolean
}

export type ContractCostCheckStatus = 'ok' | 'missing' | 'mismatch'

export interface ContractCostEvidenceCheck {
  key: string
  label: string
  status: ContractCostCheckStatus
  detail: string
}

export interface ContractCostCheckStats {
  testedAmount: number
  incorrectAmount: number
  errorRate: number
  abnormalCount: number
}

export const F2_56_OBJECTIVES = [
  '验证财务报表中记录的各项合同履约成本是否真实存在；',
  '验证合同履约成本记录的完整性；',
  '验证合同履约成本是否记录在正确的会计期间、计价是否准确。',
]

export const F2_56_TEST_CHECKS = [
  '1. 原始凭证是否齐全、有效；',
  '2. 会计处理是否正确；',
  '3. 是否与合同/协议条款一致；',
  '4. 是否与到货验收、物流运输等单据勾稽；',
  '5. 费用分配依据是否合理、金额是否准确。',
]

export const F2_56_TIPS = [
  '本表以记账凭证为起点，横向勾稽合同、验收、物流、费用分配等支持性证据。',
  '测试样本应覆盖重大、异常项目，并结合随机抽样；样本量应足以支持错报风险评估。',
  '统计说明中的差错率 = 不正确金额 ÷ 测试金额，用于评价总体错报。',
]

export function newContractCostCheckId(): string {
  return `f2chk-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptySampling(): ContractCostCheckSampling {
  return {
    populationDesc: '本期合同履约成本发生额',
    method: '特定项目+随机抽样',
    process: '',
    populationAmount: 0,
    materiality: 0,
    tolerableMisstatement: 0,
    expectedMisstatement: 0,
    sampleSize: 0,
  }
}

export function emptyCheckSample(): ContractCostCheckSample {
  return {
    id: newContractCostCheckId(),
    projectName: '',
    accountDetail: '',
    voucherNo: '',
    businessContent: '',
    offsetAccount: '',
    offsetProject: '',
    voucherAmount: 0,
    contractDateNo: '',
    contractTerms: '',
    receiptProductName: '',
    receiptAmount: 0,
    logisticsQty: 0,
    logisticsDateNo: '',
    logisticsProductName: '',
    logisticsProvider: '',
    allocQty: 0,
    allocMonth: '',
    allocAmount: 0,
    allocBasis: '',
    indexRef: '',
    isAbnormal: '',
    issueDesc: '',
  }
}

export function defaultContractCostCheckSheet(): ContractCostCheckSheet {
  return {
    sampling: emptySampling(),
    samples: [emptyCheckSample()],
    statNote: '',
  }
}

export function isBlankContractCostCheckSample(row: ContractCostCheckSample): boolean {
  return (Object.entries(row) as Array<[keyof ContractCostCheckSample, unknown]>)
    .every(([key, value]) => key === 'id' || value === '' || value === 0 || value == null)
}

export function pruneBlankContractCostCheckSamples(
  rows: ContractCostCheckSample[],
): ContractCostCheckSample[] {
  const filled = rows.filter((row) => !isBlankContractCostCheckSample(row))
  return filled.length ? filled : [emptyCheckSample()]
}

export function evaluateContractCostEvidence(
  row: ContractCostCheckSample,
): ContractCostEvidenceCheck[] {
  const present = (value: unknown) => String(value ?? '').trim().length > 0
  const amountMatches = (other: number) =>
    !row.voucherAmount || !other || Math.abs(row.voucherAmount - other) <= 0.01
  return [
    {
      key: 'voucher',
      label: '记账凭证',
      status: present(row.voucherNo) && present(row.businessContent) && !!row.voucherAmount
        ? 'ok' : 'missing',
      detail: present(row.voucherNo) ? row.voucherNo : '凭证号、业务内容或金额待补充',
    },
    {
      key: 'contract',
      label: '合同/协议',
      status: present(row.contractDateNo) && present(row.contractTerms) ? 'ok' : 'missing',
      detail: present(row.contractDateNo) ? row.contractDateNo : '合同日期/编号或主要条款待补充',
    },
    {
      key: 'receipt',
      label: '到货验收',
      status: !present(row.receiptProductName) || !row.receiptAmount
        ? 'missing'
        : amountMatches(row.receiptAmount) ? 'ok' : 'mismatch',
      detail: !row.receiptAmount
        ? '验收产品或金额待补充'
        : amountMatches(row.receiptAmount) ? '与凭证金额勾稽' : '验收金额与凭证金额不一致',
    },
    {
      key: 'logistics',
      label: '物流运输',
      status: present(row.logisticsDateNo) && present(row.logisticsProductName)
        ? 'ok' : 'missing',
      detail: present(row.logisticsDateNo) ? row.logisticsDateNo : '物流日期/编号或产品名称待补充',
    },
    {
      key: 'allocation',
      label: '费用分配',
      status: !row.allocAmount || !present(row.allocBasis)
        ? 'missing'
        : amountMatches(row.allocAmount) ? 'ok' : 'mismatch',
      detail: !row.allocAmount
        ? '分配金额或依据待补充'
        : amountMatches(row.allocAmount) ? '与凭证金额勾稽' : '分配金额与凭证金额不一致',
    },
  ]
}

export function enrichCheckSample(row: ContractCostCheckSample): EnrichedContractCostCheck {
  return {
    ...row,
    hasIssue: row.isAbnormal === '是',
  }
}

export function enrichCheckSamples(rows: ContractCostCheckSample[]): EnrichedContractCostCheck[] {
  return rows.map(enrichCheckSample)
}

export function calcCheckStats(rows: EnrichedContractCostCheck[]): ContractCostCheckStats {
  const testedAmount = calcSubtotal(rows.map((r) => r.voucherAmount))
  const incorrectAmount = calcSubtotal(
    rows.filter((r) => r.isAbnormal === '是').map((r) => r.voucherAmount),
  )
  const errorRate = testedAmount ? incorrectAmount / testedAmount : 0
  return {
    testedAmount,
    incorrectAmount,
    abnormalCount: rows.filter((r) => r.isAbnormal === '是').length,
    errorRate,
  }
}

export function migrateContractCostCheckSheet(
  legacy: unknown,
  legacyParams?: string,
): ContractCostCheckSheet | null {
  const sheet = defaultContractCostCheckSheet()

  if (legacyParams) {
    try {
      const p = JSON.parse(legacyParams)
      sheet.sampling = { ...sheet.sampling, ...p }
      if (p.scope) sheet.sampling.populationDesc = p.scope || sheet.sampling.populationDesc
    } catch { /* ignore */ }
  }

  if (!legacy) return sheet

  if (typeof legacy === 'object' && legacy !== null && 'samples' in legacy) {
    const s = legacy as ContractCostCheckSheet
    return {
      ...sheet,
      ...s,
      sampling: { ...sheet.sampling, ...s.sampling },
      samples: pruneBlankContractCostCheckSamples(
        s.samples?.length ? s.samples : sheet.samples,
      ),
    }
  }

  if (Array.isArray(legacy) && legacy.length) {
    const first = legacy[0] as Record<string, unknown>
    if ('voucherNo' in first || 'projectName' in first) {
      sheet.samples = pruneBlankContractCostCheckSamples(
        (legacy as Array<Record<string, unknown>>).map((r) => ({
        ...emptyCheckSample(),
        id: String(r.id || newContractCostCheckId()),
        projectName: String(r.projectName || ''),
        accountDetail: String(r.accountDetail || ''),
        voucherNo: String(r.voucherNo || ''),
        voucherAmount: Number(r.voucherAmount ?? r.amount ?? 0),
        contractDateNo: String(r.contractDateNo || r.contractNo || ''),
        businessContent: String(r.businessContent || ''),
        offsetAccount: String(r.offsetAccount || ''),
        offsetProject: String(r.offsetProject || ''),
        contractTerms: String(r.contractTerms || ''),
        receiptProductName: String(r.receiptProductName || ''),
        receiptAmount: Number(r.receiptAmount || 0),
        logisticsQty: Number(r.logisticsQty || 0),
        logisticsDateNo: String(r.logisticsDateNo || ''),
        logisticsProductName: String(r.logisticsProductName || ''),
        logisticsProvider: String(r.logisticsProvider || ''),
        allocQty: Number(r.allocQty || 0),
        allocMonth: String(r.allocMonth || r.voucherDate || ''),
        allocAmount: Number(r.allocAmount || r.equipmentAmt || 0),
        allocBasis: String(r.allocBasis || ''),
        indexRef: String(r.indexRef || ''),
        isAbnormal: (r.isAbnormal as YesNo) ||
          (r.isCorrect === '否' ? '是' : r.isCorrect === '是' ? '否' : ''),
        issueDesc: String(r.issueDesc || ''),
        })),
      )
      return sheet
    }
  }

  return sheet
}
