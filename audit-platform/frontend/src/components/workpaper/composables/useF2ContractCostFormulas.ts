/**
 * F2-55 合同履约成本构成明细表（对齐致同源模板）
 *
 * 四成本要素 × (期初/增加/减少/期末/审计调整/审定)
 * 期末 = 期初 + 增加 − 减少；审定 = 期末 + 审计调整
 */
import {
  calcEndBalance,
  calcSubtotalByCategory,
  calcAuditedAmount,
  calcSubtotal,
} from './useF2SpecialFormulaEngine'

export type YesNo = '是' | '否' | ''

export const CONTRACT_COST_CATEGORIES = [
  { key: 'equipment', label: '设备/材料成本', emphasis: true },
  { key: 'construction', label: '建安及分包成本', emphasis: true },
  { key: 'labor', label: '人工费用', emphasis: false },
  { key: 'other', label: '其他费用', emphasis: false },
] as const

export type CostCategoryKey = (typeof CONTRACT_COST_CATEGORIES)[number]['key']

export interface ContractCostProject {
  id: string
  projectCode: string
  projectName: string
  contractName: string
  contractAmount: number
  opening_equipment: number
  opening_construction: number
  opening_labor: number
  opening_other: number
  increase_equipment: number
  increase_construction: number
  increase_labor: number
  increase_other: number
  decrease_equipment: number
  decrease_construction: number
  decrease_labor: number
  decrease_other: number
  matchesLedger: YesNo
  carriedByProgress: YesNo
  isDirectlyRelated: YesNo
  isRecoverable: YesNo
  adj_equipment: number
  adj_construction: number
  adj_labor: number
  adj_other: number
  remark: string
}

export interface ContractCostSheet {
  products: ContractCostProject[]
}

export interface EnrichedContractCost extends ContractCostProject {
  opening_subtotal: number
  increase_subtotal: number
  decrease_subtotal: number
  end_equipment: number
  end_construction: number
  end_labor: number
  end_other: number
  end_subtotal: number
  adj_subtotal: number
  audited_equipment: number
  audited_construction: number
  audited_labor: number
  audited_other: number
  audited_subtotal: number
  highlight: boolean
}

export interface ContractCostColumnTotals {
  opening_subtotal: number
  increase_subtotal: number
  decrease_subtotal: number
  end_subtotal: number
  adj_subtotal: number
  audited_subtotal: number
  contractAmount: number
}

export const F2_55_DEFAULT_OBJECTIVE =
  '核实合同履约成本各构成要素的完整性、计量准确性及资本化条件，确认期末审定余额与科目1410及合同台账勾稽一致。'

export const F2_55_TIPS = [
  '合同履约成本须同时满足：与合同直接相关、增加未来用于履约的资源、预期能够收回（CAS 14）。',
  '期末账面 = 期初 + 本期增加 − 本期减少；期末审定 = 期末账面 + 审计调整。',
  '设备/材料、建安分包、人工、其他四要素分别列示并自动小计；不满足资本化条件的应调整转出。',
  '期末审定合计应与合同履约成本科目余额及审定表勾稽一致。',
]

export function newContractCostId(): string {
  return `f2cc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyContractCostProject(): ContractCostProject {
  return {
    id: newContractCostId(),
    projectCode: '',
    projectName: '',
    contractName: '',
    contractAmount: 0,
    opening_equipment: 0,
    opening_construction: 0,
    opening_labor: 0,
    opening_other: 0,
    increase_equipment: 0,
    increase_construction: 0,
    increase_labor: 0,
    increase_other: 0,
    decrease_equipment: 0,
    decrease_construction: 0,
    decrease_labor: 0,
    decrease_other: 0,
    matchesLedger: '',
    carriedByProgress: '',
    isDirectlyRelated: '是',
    isRecoverable: '是',
    adj_equipment: 0,
    adj_construction: 0,
    adj_labor: 0,
    adj_other: 0,
    remark: '',
  }
}

export function defaultContractCostSheet(): ContractCostSheet {
  return {
    products: Array.from({ length: 8 }, () => emptyContractCostProject()),
  }
}

function quad(
  prefix: 'opening' | 'increase' | 'decrease' | 'adj',
  row: ContractCostProject,
): [number, number, number, number] {
  return [
    row[`${prefix}_equipment`],
    row[`${prefix}_construction`],
    row[`${prefix}_labor`],
    row[`${prefix}_other`],
  ]
}

export function enrichContractCostProject(row: ContractCostProject): EnrichedContractCost {
  const [oe, oc, ol, oo] = quad('opening', row)
  const [ie, ic, il, io] = quad('increase', row)
  const [de, dc, dl, do_] = quad('decrease', row)
  const [ae, ac, al, ao] = quad('adj', row)

  const opening_subtotal = calcSubtotalByCategory(oe, oc, ol, oo)
  const increase_subtotal = calcSubtotalByCategory(ie, ic, il, io)
  const decrease_subtotal = calcSubtotalByCategory(de, dc, dl, do_)

  const end_equipment = calcEndBalance(oe, ie, de)
  const end_construction = calcEndBalance(oc, ic, dc)
  const end_labor = calcEndBalance(ol, il, dl)
  const end_other = calcEndBalance(oo, io, do_)
  const end_subtotal = calcSubtotalByCategory(end_equipment, end_construction, end_labor, end_other)

  const adj_subtotal = calcSubtotalByCategory(ae, ac, al, ao)

  const audited_equipment = calcAuditedAmount(end_equipment, ae)
  const audited_construction = calcAuditedAmount(end_construction, ac)
  const audited_labor = calcAuditedAmount(end_labor, al)
  const audited_other = calcAuditedAmount(end_other, ao)
  const audited_subtotal = calcSubtotalByCategory(
    audited_equipment,
    audited_construction,
    audited_labor,
    audited_other,
  )

  const highlight =
    row.isRecoverable === '否' ||
    row.isDirectlyRelated === '否' ||
    row.matchesLedger === '否'

  return {
    ...row,
    opening_subtotal,
    increase_subtotal,
    decrease_subtotal,
    end_equipment,
    end_construction,
    end_labor,
    end_other,
    end_subtotal,
    adj_subtotal,
    audited_equipment,
    audited_construction,
    audited_labor,
    audited_other,
    audited_subtotal,
    highlight,
  }
}

export function enrichContractCostProjects(rows: ContractCostProject[]): EnrichedContractCost[] {
  return rows.map(enrichContractCostProject)
}

export function calcContractCostTotals(rows: EnrichedContractCost[]): ContractCostColumnTotals {
  return {
    opening_subtotal: calcSubtotal(rows.map((r) => r.opening_subtotal)),
    increase_subtotal: calcSubtotal(rows.map((r) => r.increase_subtotal)),
    decrease_subtotal: calcSubtotal(rows.map((r) => r.decrease_subtotal)),
    end_subtotal: calcSubtotal(rows.map((r) => r.end_subtotal)),
    adj_subtotal: calcSubtotal(rows.map((r) => r.adj_subtotal)),
    audited_subtotal: calcSubtotal(rows.map((r) => r.audited_subtotal)),
    contractAmount: calcSubtotal(rows.map((r) => r.contractAmount)),
  }
}

export function migrateContractCostSheet(legacy: unknown): ContractCostSheet | null {
  if (!legacy) return null

  if (typeof legacy === 'object' && legacy !== null && 'products' in legacy) {
    const sheet = legacy as ContractCostSheet
    return {
      products: sheet.products?.length ? sheet.products : defaultContractCostSheet().products,
    }
  }

  if (Array.isArray(legacy) && legacy.length) {
    return {
      products: (legacy as ContractCostProject[]).map((r) => ({
        ...emptyContractCostProject(),
        ...r,
        id: r.id || newContractCostId(),
      })),
    }
  }

  return null
}

export function periodField(
  period: 'opening' | 'increase' | 'decrease' | 'adj',
  key: CostCategoryKey,
): keyof ContractCostProject {
  return `${period}_${key}` as keyof ContractCostProject
}

export function endField(key: CostCategoryKey): keyof EnrichedContractCost {
  return `end_${key}` as keyof EnrichedContractCost
}

export function auditedField(key: CostCategoryKey): keyof EnrichedContractCost {
  return `audited_${key}` as keyof EnrichedContractCost
}
