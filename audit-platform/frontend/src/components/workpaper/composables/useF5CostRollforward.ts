/**
 * useF5CostRollforward — F5-7 成本倒轧表（4区结构化验证，本循环核心审计逻辑）
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Task 5.5
 *
 * 4区公式链：
 *  ① 材料流转：投入生产 = 期初原材料 + 购入 - 期末原材料 - 其他发出
 *  ② 成本构成：产品总成本 = 投入生产 + 直接人工 + 制造费用
 *  ③ 成本结转：完工产品成本 = 期初在产品 + 产品总成本 - 期末在产品
 *  ④ 营业成本：本期营业成本 = 期初产成品 + 完工产品成本 - 期末产成品 - 其他发出
 * 校验区：审定表营业成本(F5-1取) - 倒轧营业成本 = 差异；|差异|>重要性水平 红色
 * TB自动取数：1401原材料 / 1404在产品 / 1405产成品（期初/期末）
 * 可编辑字段：购入/直接人工/制造费用/其他发出；只读：TB取数/公式
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcCostRollforward,
  calcTotalProductionCost,
  calcFinishedGoodsCost,
  calcCOGS,
} from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface UseF5CostRollforwardOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  /** 重要性水平（用于校验区差异高亮） */
  materiality?: Ref<number>
  /** 从 F5-1 审定表取得的审定营业成本（EventBus/inject 提供） */
  adjudicatedCOGS?: Ref<number>
}

/** 4区结构化数据（含计算字段） */
export interface CostRollforwardData {
  // 材料流转区
  openingMaterial: number // 期初原材料(TB)
  purchase: number // 本期购入(编辑)
  closingMaterial: number // 期末原材料(TB)
  otherIssue1: number // 其他发出(编辑)
  materialInput: number // =投入生产(公式)
  // 成本构成区
  directLabor: number // 直接人工(编辑)
  overhead: number // 制造费用(编辑)
  totalProductionCost: number // =产品总成本(公式)
  // 成本结转区
  openingWIP: number // 期初在产品(TB)
  closingWIP: number // 期末在产品(TB)
  finishedGoodsCost: number // =完工产品成本(公式)
  // 营业成本区
  openingFG: number // 期初产成品(TB)
  closingFG: number // 期末产成品(TB)
  otherIssue2: number // 其他发出(编辑)
  cogs: number // =本期营业成本(公式)
  // 校验区
  adjudicatedCOGS: number // 审定表营业成本(F5-1取)
  rollforwardVariance: number // =差异(公式)
}

/** 可编辑字段白名单 */
const EDITABLE_FIELDS = ['purchase', 'directLabor', 'overhead', 'otherIssue1', 'otherIssue2'] as const
/** TB 自动取数字段（只读） */
const TB_FIELDS = ['openingMaterial', 'closingMaterial', 'openingWIP', 'closingWIP', 'openingFG', 'closingFG'] as const

const STORAGE_KEY = 'F5-7-cost-rollforward'
const CONCLUSION_KEY = 'F5-7-conclusion'

interface StoredRollforward {
  openingMaterial: number
  purchase: number
  closingMaterial: number
  otherIssue1: number
  directLabor: number
  overhead: number
  openingWIP: number
  closingWIP: number
  openingFG: number
  closingFG: number
  otherIssue2: number
}

function safeParse(jsonStr: string | null | undefined): Partial<StoredRollforward> {
  if (!jsonStr) return {}
  try {
    const parsed = JSON.parse(jsonStr)
    return typeof parsed === 'object' && parsed !== null ? parsed : {}
  } catch {
    return {}
  }
}

export function useF5CostRollforward(options: UseF5CostRollforwardOptions) {
  const { allResponses, isReadonly, materiality, adjudicatedCOGS } = options
  const readonly = isReadonly ?? computed(() => false)
  const materialityRef = materiality ?? computed(() => 0)
  const extAdjudicated = adjudicatedCOGS ?? computed(() => 0)

  const stored = computed<Partial<StoredRollforward>>(() =>
    safeParse(allResponses.value.get(STORAGE_KEY)?.remark),
  )

  const data: ComputedRef<CostRollforwardData> = computed(() => {
    const s = stored.value
    const openingMaterial = parseNum(s.openingMaterial)
    const purchase = parseNum(s.purchase)
    const closingMaterial = parseNum(s.closingMaterial)
    const otherIssue1 = parseNum(s.otherIssue1)
    const materialInput = calcCostRollforward(openingMaterial, purchase, closingMaterial, otherIssue1)

    const directLabor = parseNum(s.directLabor)
    const overhead = parseNum(s.overhead)
    const totalProductionCost = calcTotalProductionCost(materialInput, directLabor, overhead)

    const openingWIP = parseNum(s.openingWIP)
    const closingWIP = parseNum(s.closingWIP)
    const finishedGoodsCost = calcFinishedGoodsCost(openingWIP, totalProductionCost, closingWIP)

    const openingFG = parseNum(s.openingFG)
    const closingFG = parseNum(s.closingFG)
    const otherIssue2 = parseNum(s.otherIssue2)
    const cogs = calcCOGS(openingFG, finishedGoodsCost, closingFG, otherIssue2)

    // 校验区：优先用外部注入的审定营业成本（EventBus），否则用本地存储
    const localAdjudicated = parseNum(allResponses.value.get('F5-7-adjudicated-cogs')?.remark)
    const adjudicated = extAdjudicated.value || localAdjudicated
    const rollforwardVariance = adjudicated - cogs

    return {
      openingMaterial, purchase, closingMaterial, otherIssue1, materialInput,
      directLabor, overhead, totalProductionCost,
      openingWIP, closingWIP, finishedGoodsCost,
      openingFG, closingFG, otherIssue2, cogs,
      adjudicatedCOGS: adjudicated,
      rollforwardVariance,
    }
  })

  /** 校验区差异是否超重要性水平（红色） */
  const varianceExceedsMateriality = computed(() => {
    const m = materialityRef.value
    if (m <= 0) return Math.abs(data.value.rollforwardVariance) > 0.01
    return Math.abs(data.value.rollforwardVariance) > m
  })

  const auditConclusion = computed<string>({
    get: () => allResponses.value.get(CONCLUSION_KEY)?.remark ?? '',
    set: (val) => {
      allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
    },
  })

  function isEditable(field: string): boolean {
    return (EDITABLE_FIELDS as readonly string[]).includes(field)
  }

  function isTbField(field: string): boolean {
    return (TB_FIELDS as readonly string[]).includes(field)
  }

  function persist(next: Partial<StoredRollforward>): void {
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(next) })
  }

  /** 编辑字段（仅白名单可写；TB字段可通过 setTbValue 写入） */
  function updateField(field: string, value: number | string): void {
    if (readonly.value) return
    if (!isEditable(field) && !isTbField(field)) return
    const next = { ...stored.value, [field]: parseNum(value) }
    persist(next)
  }

  /** TB 自动取数写入（1401/1404/1405 期初期末） */
  function setTbValues(values: Partial<Record<(typeof TB_FIELDS)[number], number>>): void {
    const next = { ...stored.value }
    for (const [k, v] of Object.entries(values)) {
      ;(next as any)[k] = parseNum(v)
    }
    persist(next)
  }

  /** 设置审定营业成本（来自 F5-1 EventBus，用于校验区） */
  function setAdjudicatedCOGS(amount: number): void {
    allResponses.value.set('F5-7-adjudicated-cogs', {
      item_id: 'F5-7-adjudicated-cogs',
      conclusion: null,
      remark: String(parseNum(amount)),
    })
  }

  return {
    data,
    varianceExceedsMateriality,
    auditConclusion,
    isEditable,
    isTbField,
    updateField,
    setTbValues,
    setAdjudicatedCOGS,
    editableFields: EDITABLE_FIELDS,
    tbFields: TB_FIELDS,
  }
}

export default useF5CostRollforward
