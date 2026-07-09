/**
 * useH1CrossSheet — H1 固定资产跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('H1-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射：
 * - H1-2 明细 → H1-1 审定（按分类聚合原值/折旧/减值合计）
 * - H1-3 调整 → H1-1 审定（AJE/RJE同步）
 * - H1-12 折旧 → H1-13 分配（按分类聚合折旧额）
 * - H1-4 闲置 → H1-14 减值（闲置资产列表供减值迹象引入）
 * - H1-1/H1-4/H1-19 → 附注（审定/闲置/经营租出自动取数）
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.2
 * Requirements: 17.1-17.9
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** H1-2 明细行原始 JSON 结构 */
export interface H1DetailRowRaw {
  rowId?: string
  category?: string           // 资产分类
  name?: string              // 资产名称
  originalCostBegin?: number // 原值期初
  originalCostIncrease?: number
  originalCostDecrease?: number
  originalCostEnd?: number   // 原值期末
  accDepBegin?: number       // 累计折旧期初
  accDepProvision?: number   // 本期计提
  accDepReversal?: number    // 本期转回
  accDepEnd?: number         // 累计折旧期末
  impairmentBegin?: number   // 减值准备期初
  impairmentProvision?: number
  impairmentReversal?: number
  impairmentEnd?: number     // 减值准备期末
  netValue?: number
}

/** H1-3 调整分录行原始 JSON 结构 */
export interface H1AdjustmentRowRaw {
  rowId?: string
  description?: string       // 调整事项说明
  entryType?: string         // AJE / RJE
  reportItem?: string
  accountCode?: string
  accountName?: string
  noteItem?: string
  summary?: string
  debitAmount?: number       // 借方金额
  creditAmount?: number      // 贷方金额
  counterAccount?: string
  indexRef?: string
  remark?: string
}

/** H1-4 闲置资产行原始 JSON 结构 */
export interface H1IdleAssetRowRaw {
  rowId?: string
  name?: string              // 资产名称
  assetNo?: string
  originalCost?: number
  accDep?: number
  netValue?: number          // 净值
  idleReason?: string
  idleStartDate?: string
  hasImpairment?: string     // 是否计提减值
  impairmentAmount?: number
  disposalSuggestion?: string
  remark?: string
}

/** H1-12 折旧测算行原始 JSON 结构 */
export interface H1DepreciationRowRaw {
  rowId?: string
  category?: string          // 资产分类
  originalCost?: number
  salvageRate?: number
  usefulLife?: number
  annualDepreciation?: number
  periodDepreciation?: number  // 本期折旧合计
  accDepEnd?: number
  bookDepreciation?: number    // 账面折旧
  difference?: number
}

/** H1-19 经营租出行原始 JSON 结构 */
export interface H1OperatingLeaseRowRaw {
  rowId?: string
  lessee?: string            // 承租方
  assetName?: string
  originalCost?: number
  netValue?: number
  leaseStart?: string
  leaseEnd?: string
  leaseTerm?: number
  annualRent?: number
  monthlyRent?: number
  totalRentIncome?: number
  depAlloc?: number
  maintenanceCost?: number
  netIncome?: number
  returnRate?: number
}

/** 跨sheet详细合计结构 */
export interface DetailTotals {
  originalCost: number
  accDep: number
  impairment: number
}

/** 审定数从明细汇总 */
export interface AdjudicationFromDetail {
  costAudited: number
  depAudited: number
}

/** 折旧分配按分类结构 */
export interface DepreciationForAlloc {
  byCategory: Record<string, number>
  total: number
}

/** 闲置资产供减值引入 */
export interface IdleAssetForImpairment {
  name: string
  netValue: number
}

/** 调整分录同步结构 */
export interface AdjustmentSync {
  totalAje: number
  totalRje: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析 JSON 数组字符串，失败回退空数组
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 安全提取数值，NaN/null/undefined → 0
 */
function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

/**
 * 从 allResponses Map 中获取指定 item_id 的 remark，并尝试解析为数值
 */
function _getNumFromMap(map: Map<string, ChecklistItem>, itemId: string): number {
  const item = map.get(itemId)
  if (!item) return 0
  const raw = item.remark ?? item.conclusion
  return _getNum(raw)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1CrossSheet(allResponses: Ref<Map<string, any>>) {
  // ─── 解析 H1-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<H1DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('H1-2-rows')
    return safeParseRows<H1DetailRowRaw>(resp?.remark)
  })

  // ─── 解析 H1-3 调整分录行数据 ──────────────────────────────────────────

  const adjustmentRows = computed<H1AdjustmentRowRaw[]>(() => {
    const resp = allResponses.value.get('H1-3-rows')
    return safeParseRows<H1AdjustmentRowRaw>(resp?.remark)
  })

  // ─── 解析 H1-4 闲置资产行数据 ──────────────────────────────────────────

  const idleRows = computed<H1IdleAssetRowRaw[]>(() => {
    const resp = allResponses.value.get('H1-4-rows')
    return safeParseRows<H1IdleAssetRowRaw>(resp?.remark)
  })

  // ─── 解析 H1-12 折旧测算行数据 ─────────────────────────────────────────

  const depreciationRows = computed<H1DepreciationRowRaw[]>(() => {
    const resp = allResponses.value.get('H1-12-rows')
    return safeParseRows<H1DepreciationRowRaw>(resp?.remark)
  })

  // ─── 解析 H1-19 经营租出行数据 ─────────────────────────────────────────

  const operatingLeaseRows = computed<H1OperatingLeaseRowRaw[]>(() => {
    const resp = allResponses.value.get('H1-19-rows')
    return safeParseRows<H1OperatingLeaseRowRaw>(resp?.remark)
  })

  // ─── detailTotals: H1-2 按分类聚合原值/折旧/减值（Req 17.1）───────────

  /**
   * 从 H1-2 明细行聚合合计：
   * - originalCost: 所有行的 originalCostEnd 之和
   * - accDep: 所有行的 accDepEnd 之和
   * - impairment: 所有行的 impairmentEnd 之和
   */
  const detailTotals: ComputedRef<DetailTotals> = computed(() => {
    let originalCost = 0
    let accDep = 0
    let impairment = 0

    for (const row of detailRows.value) {
      originalCost += _getNum(row.originalCostEnd)
      accDep += _getNum(row.accDepEnd)
      impairment += _getNum(row.impairmentEnd)
    }

    return { originalCost, accDep, impairment }
  })

  // ─── adjudicationFromDetail: H1-2 合计 → H1-1（Req 17.1）──────────────

  /**
   * H1-2 明细合计供 H1-1 审定表交叉验证：
   * - costAudited: 原值合计（=H1-1原值小计审定数）
   * - depAudited: 折旧合计（=H1-1折旧小计审定数）
   */
  const adjudicationFromDetail: ComputedRef<AdjudicationFromDetail> = computed(() => {
    const totals = detailTotals.value
    return {
      costAudited: totals.originalCost,
      depAudited: totals.accDep,
    }
  })

  // ─── depreciationForAlloc: H1-12 → H1-13 按分类折旧额（Req 17.1）─────

  /**
   * 从 H1-12 折旧测算行按资产分类聚合本期折旧合计，供 H1-13 分配表使用。
   * byCategory: { '房屋建筑物': 120000, '运输设备': 80000, ... }
   * total: 所有分类折旧之和
   */
  const depreciationForAlloc: ComputedRef<DepreciationForAlloc> = computed(() => {
    const byCategory: Record<string, number> = {}
    let total = 0

    for (const row of depreciationRows.value) {
      const cat = row.category || '未分类'
      const amount = _getNum(row.periodDepreciation)
      byCategory[cat] = (byCategory[cat] || 0) + amount
      total += amount
    }

    return { byCategory, total }
  })

  // ─── idleAssetsForImpairment: H1-4 → H1-14（Req 17.1）─────────────────

  /**
   * 从 H1-4 闲置检查表提取有减值迹象的资产列表供 H1-14 引入。
   * 筛选条件：净值 > 0 的闲置资产（不论是否已计提减值）。
   */
  const idleAssetsForImpairment: ComputedRef<IdleAssetForImpairment[]> = computed(() => {
    const result: IdleAssetForImpairment[] = []

    for (const row of idleRows.value) {
      const netValue = _getNum(row.netValue)
      if (netValue > 0) {
        result.push({
          name: row.name || '未命名资产',
          netValue,
        })
      }
    }

    return result
  })

  // ─── disclosureAutoFill: H1-1/H1-4/H1-19 → 附注各子节（Req 17.6）────

  /**
   * 附注披露自动取数，从多个 sheet 聚合数据供附注子节引用：
   * - disc_cost_begin / disc_cost_end: 原值期初/期末（从H1-2聚合）
   * - disc_cost_increase / disc_cost_decrease: 原值增加/减少
   * - disc_dep_begin / disc_dep_end: 折旧期初/期末
   * - disc_dep_provision / disc_dep_reversal: 折旧计提/转回
   * - disc_impairment_begin / disc_impairment_end: 减值期初/期末
   * - disc_net_value: 净值合计
   * - disc_idle_count: 闲置资产数量
   * - disc_idle_net_value: 闲置净值合计
   * - disc_lease_count: 经营租出数量
   * - disc_lease_total_rent: 经营租出总租金
   */
  const disclosureAutoFill: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {}

    // ─ 从 H1-2 明细行聚合附注第(1)子节数据（原值/折旧/减值矩阵）
    let costBegin = 0
    let costIncrease = 0
    let costDecrease = 0
    let costEnd = 0
    let depBegin = 0
    let depProvision = 0
    let depReversal = 0
    let depEnd = 0
    let impBegin = 0
    let impProvision = 0
    let impReversal = 0
    let impEnd = 0

    for (const row of detailRows.value) {
      costBegin += _getNum(row.originalCostBegin)
      costIncrease += _getNum(row.originalCostIncrease)
      costDecrease += _getNum(row.originalCostDecrease)
      costEnd += _getNum(row.originalCostEnd)
      depBegin += _getNum(row.accDepBegin)
      depProvision += _getNum(row.accDepProvision)
      depReversal += _getNum(row.accDepReversal)
      depEnd += _getNum(row.accDepEnd)
      impBegin += _getNum(row.impairmentBegin)
      impProvision += _getNum(row.impairmentProvision)
      impReversal += _getNum(row.impairmentReversal)
      impEnd += _getNum(row.impairmentEnd)
    }

    result['disc_cost_begin'] = costBegin
    result['disc_cost_increase'] = costIncrease
    result['disc_cost_decrease'] = costDecrease
    result['disc_cost_end'] = costEnd
    result['disc_dep_begin'] = depBegin
    result['disc_dep_provision'] = depProvision
    result['disc_dep_reversal'] = depReversal
    result['disc_dep_end'] = depEnd
    result['disc_impairment_begin'] = impBegin
    result['disc_impairment_provision'] = impProvision
    result['disc_impairment_reversal'] = impReversal
    result['disc_impairment_end'] = impEnd
    result['disc_net_value'] = costEnd - depEnd - impEnd

    // ─ 从 H1-4 闲置检查表取附注第(2)子节数据
    let idleCount = 0
    let idleNetValue = 0
    for (const row of idleRows.value) {
      idleCount++
      idleNetValue += _getNum(row.netValue)
    }
    result['disc_idle_count'] = idleCount
    result['disc_idle_net_value'] = idleNetValue

    // ─ 从 H1-19 经营租出取附注第(4)子节数据
    let leaseCount = 0
    let leaseTotalRent = 0
    for (const row of operatingLeaseRows.value) {
      leaseCount++
      leaseTotalRent += _getNum(row.totalRentIncome)
    }
    result['disc_lease_count'] = leaseCount
    result['disc_lease_total_rent'] = leaseTotalRent

    return result
  })

  // ─── adjustmentSync: H1-3 AJE/RJE → H1-1（Req 17.7）──────────────────

  /**
   * 从 H1-3 调整分录汇总 AJE/RJE 合计金额，同步到 H1-1 审定表对应列。
   * - totalAje: 所有类别=AJE分录的净额（借方-贷方）之和
   * - totalRje: 所有类别=RJE分录的净额之和
   */
  const adjustmentSync: ComputedRef<AdjustmentSync> = computed(() => {
    let totalAje = 0
    let totalRje = 0

    for (const row of adjustmentRows.value) {
      const debit = _getNum(row.debitAmount)
      const credit = _getNum(row.creditAmount)
      // 资产类借方科目：借方增加/贷方减少 → 净额 = 借方 - 贷方
      const netAmount = debit - credit

      if (row.entryType === 'AJE') {
        totalAje += netAmount
      } else if (row.entryType === 'RJE') {
        totalRje += netAmount
      }
    }

    return { totalAje, totalRje }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // H1-2 → H1-1 明细合计
    detailTotals,
    // H1-2 合计 → H1-1 审定表交叉验证
    adjudicationFromDetail,
    // H1-12 → H1-13 折旧分配
    depreciationForAlloc,
    // H1-4 → H1-14 闲置资产减值引入
    idleAssetsForImpairment,
    // H1-1/H1-4/H1-19 → 附注自动取数
    disclosureAutoFill,
    // H1-3 → H1-1 AJE/RJE同步
    adjustmentSync,
  }
}

export default useH1CrossSheet
