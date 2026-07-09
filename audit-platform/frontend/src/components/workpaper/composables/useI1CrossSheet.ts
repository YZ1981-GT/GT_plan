/**
 * useI1CrossSheet — I1 无形资产跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('I1-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射：
 * - I1-2 明细 → I1 审定（按分类聚合原值/摊销/减值合计）
 * - I1-3 调整 → I1 审定（AJE/RJE同步）
 * - I1-10/I1-11 摊销测算 → I1-9 摊销分配（按资产聚合摊销额）
 * - I1-2/I1-1/I1-9 → 附注（审定数/明细/摊销分配自动取数）
 *
 * 科目方向：
 * - 1701 无形资产（借方/资产类）：期末=期初+借-贷
 * - 1702 累计摊销（贷方/备抵类）：期末=期初+贷-借
 * - 1703 减值准备（贷方/备抵类）：期末=期初+贷-借
 *
 * Spec: .kiro/specs/i1-intangible-assets/
 * Task: 3.2
 * Requirements: 2.4-2.9, 10.2, 11.7
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I1-2 明细行原始 JSON 结构 */
export interface I1DetailRowRaw {
  rowId?: string
  category?: string            // 资产分类（专利/商标/著作权/土地使用权/软件等）
  name?: string               // 资产名称
  acquisitionDate?: string    // 取得日期
  usefulLifeMonths?: number   // 使用寿命（月）
  salvageRate?: number        // 残值率
  amortizationMethod?: string // 摊销方法

  // 原值变动区段
  costBegin?: number          // 原值期初
  costIncrease?: number       // 原值增加
  costDecrease?: number       // 原值减少
  costEnd?: number            // 原值期末

  // 摊销区段
  accAmortBegin?: number      // 累计摊销期初
  amortProvision?: number     // 本期摊销
  amortTransferOut?: number   // 摊销转出
  accAmortEnd?: number        // 累计摊销期末
  netValue?: number           // 净值=原值-摊销-减值

  // 减值区段
  impairmentBegin?: number    // 减值期初
  impairmentProvision?: number // 本期计提
  impairmentReversal?: number  // 本期转回（无形资产减值不得转回，仅特殊情况）
  impairmentEnd?: number      // 减值期末
}

/** I1-10/I1-11 摊销测算行原始 JSON 结构 */
export interface I1AmortizationRowRaw {
  rowId?: string
  name?: string               // 资产名称
  cost?: number               // 原值
  salvage?: number            // 残值
  accAmort?: number           // 累计摊销
  impairment?: number         // 减值准备（I1-11含减值版本使用）
  remainingMonths?: number    // 剩余月数
  periodAmortization?: number // 本期摊销合计
  monthlyAmort?: number       // 月摊销额
}

/** I1-3 调整分录行原始 JSON 结构 */
export interface I1AdjustmentRowRaw {
  rowId?: string
  description?: string        // 调整事项
  entryType?: string          // AJE / RJE
  accountCode?: string        // 科目代码
  accountName?: string        // 科目名称
  summary?: string            // 摘要
  debitAmount?: number        // 借方
  creditAmount?: number       // 贷方
  indexRef?: string           // 索引
  remark?: string
}

/** I1-9 摊销分配行原始 JSON 结构 */
export interface I1AmortAllocRowRaw {
  rowId?: string
  name?: string               // 资产名称
  totalAmort?: number         // 摊销总额
  managementExpense?: number  // 管理费用
  sellingExpense?: number     // 销售费用
  manufacturingCost?: number  // 制造费用
  rdExpense?: number          // 研发费用
  otherExpense?: number       // 其他
}

// ─── Return Types ────────────────────────────────────────────────────────────

/** I1-2 明细合计 → I1 审定表交叉验证 */
export interface I1DetailTotals {
  cost: number      // 原值期末合计
  accAmort: number  // 累计摊销期末合计
  impairment: number // 减值准备期末合计
}

/** 审定数从明细汇总 */
export interface I1AdjudicationFromDetail {
  costAudited: number   // 原值审定数（=明细原值期末合计）
  amortAudited: number  // 摊销审定数（=明细摊销期末合计）
  impairAudited: number // 减值审定数（=明细减值期末合计）
}

/** 摊销分配按资产结构（I1-10/11 → I1-9） */
export interface I1AmortizationForAlloc {
  byAsset: Record<string, number>  // 按资产名称聚合本期摊销额
  total: number                     // 摊销总额
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

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI1CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailTotals: ComputedRef<I1DetailTotals>
  adjudicationFromDetail: ComputedRef<I1AdjudicationFromDetail>
  amortizationForAlloc: ComputedRef<I1AmortizationForAlloc>
  disclosureAutoFill: ComputedRef<Record<string, number>>
} {
  // ─── 解析 I1-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<I1DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('I1-2-rows')
    return safeParseRows<I1DetailRowRaw>(resp?.remark)
  })

  // ─── 解析 I1-10/I1-11 摊销测算行数据（互斥分支，优先取有数据的一方）───

  const amortizationRows = computed<I1AmortizationRowRaw[]>(() => {
    // 优先取 I1-11（含减值），若无则取 I1-10（不含减值）
    const resp11 = allResponses.value.get('I1-11-rows')
    const rows11 = safeParseRows<I1AmortizationRowRaw>(resp11?.remark)
    if (rows11.length > 0) return rows11

    const resp10 = allResponses.value.get('I1-10-rows')
    return safeParseRows<I1AmortizationRowRaw>(resp10?.remark)
  })

  // ─── 解析 I1-3 调整分录行数据 ──────────────────────────────────────────

  const adjustmentRows = computed<I1AdjustmentRowRaw[]>(() => {
    const resp = allResponses.value.get('I1-3-rows')
    return safeParseRows<I1AdjustmentRowRaw>(resp?.remark)
  })

  // ─── detailTotals: I1-2 明细聚合原值/摊销/减值合计（Req 2.4-2.7）──────

  /**
   * 从 I1-2 明细行聚合三科目期末合计：
   * - cost: 所有行 costEnd 之和（科目1701原值期末）
   * - accAmort: 所有行 accAmortEnd 之和（科目1702摊销期末）
   * - impairment: 所有行 impairmentEnd 之和（科目1703减值期末）
   *
   * 用于与 I1 审定表三区块小计交叉验证。
   */
  const detailTotals: ComputedRef<I1DetailTotals> = computed(() => {
    let cost = 0
    let accAmort = 0
    let impairment = 0

    for (const row of detailRows.value) {
      cost += _getNum(row.costEnd)
      accAmort += _getNum(row.accAmortEnd)
      impairment += _getNum(row.impairmentEnd)
    }

    return { cost, accAmort, impairment }
  })

  // ─── adjudicationFromDetail: I1-2 合计 → I1 审定表（Req 2.4-2.9）──────

  /**
   * I1-2 明细合计供 I1 审定表三区块交叉验证：
   * - costAudited: 原值期末合计（= I1 审定表"无形资产-原值"小计审定数）
   * - amortAudited: 摊销期末合计（= I1 审定表"累计摊销"小计审定数）
   * - impairAudited: 减值期末合计（= I1 审定表"减值准备"小计审定数）
   *
   * 当审定表对应小计 ≠ 此合计时显示黄色警告。
   */
  const adjudicationFromDetail: ComputedRef<I1AdjudicationFromDetail> = computed(() => {
    const totals = detailTotals.value
    return {
      costAudited: totals.cost,
      amortAudited: totals.accAmort,
      impairAudited: totals.impairment,
    }
  })

  // ─── amortizationForAlloc: I1-10/11 → I1-9 按资产摊销额（Req 10.2, 11.7）

  /**
   * 从 I1-10 或 I1-11 摊销测算行按资产聚合本期摊销合计，供 I1-9 分配表使用。
   * byAsset: { '某专利权': 12000, '某商标权': 8000, ... }
   * total: 所有资产本期摊销之和
   *
   * I1-9 摊销分配表校验：各行摊销总额应来自此处 byAsset 对应值。
   * I1-9 底部合计行 = total（与摊销测算表合计交叉验证）。
   */
  const amortizationForAlloc: ComputedRef<I1AmortizationForAlloc> = computed(() => {
    const byAsset: Record<string, number> = {}
    let total = 0

    for (const row of amortizationRows.value) {
      const assetName = row.name || '未命名资产'
      const amount = _getNum(row.periodAmortization)
      byAsset[assetName] = (byAsset[assetName] || 0) + amount
      total += amount
    }

    return { byAsset, total }
  })

  // ─── disclosureAutoFill: 多sheet → 附注自动取数（Req 2.4-2.9）─────────

  /**
   * 附注披露自动取数，从多个 sheet 聚合数据供附注子节引用：
   *
   * 第(1)子节 — 无形资产明细变动矩阵（从I1-2聚合）：
   * - disc_cost_begin / disc_cost_increase / disc_cost_decrease / disc_cost_end
   * - disc_amort_begin / disc_amort_provision / disc_amort_transfer / disc_amort_end
   * - disc_impair_begin / disc_impair_provision / disc_impair_reversal / disc_impair_end
   * - disc_net_value: 净值合计（原值-摊销-减值）
   *
   * 第(2)子节 — 摊销费用分配（从I1-9合计或amortizationForAlloc取）：
   * - disc_amort_total: 本期摊销总额
   * - disc_amort_mgmt: 管理费用
   * - disc_amort_sell: 销售费用
   * - disc_amort_mfg: 制造费用
   * - disc_amort_rd: 研发费用
   *
   * 第(3)子节 — 统计：
   * - disc_asset_count: 资产数量
   * - disc_indefinite_count: 使用寿命不确定的资产数量
   */
  const disclosureAutoFill: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {}

    // ─ 第(1)子节：从 I1-2 明细行聚合附注原值/摊销/减值矩阵
    let costBegin = 0
    let costIncrease = 0
    let costDecrease = 0
    let costEnd = 0
    let amortBegin = 0
    let amortProvision = 0
    let amortTransfer = 0
    let amortEnd = 0
    let impairBegin = 0
    let impairProvision = 0
    let impairReversal = 0
    let impairEnd = 0
    let assetCount = 0
    let indefiniteCount = 0

    for (const row of detailRows.value) {
      costBegin += _getNum(row.costBegin)
      costIncrease += _getNum(row.costIncrease)
      costDecrease += _getNum(row.costDecrease)
      costEnd += _getNum(row.costEnd)
      amortBegin += _getNum(row.accAmortBegin)
      amortProvision += _getNum(row.amortProvision)
      amortTransfer += _getNum(row.amortTransferOut)
      amortEnd += _getNum(row.accAmortEnd)
      impairBegin += _getNum(row.impairmentBegin)
      impairProvision += _getNum(row.impairmentProvision)
      impairReversal += _getNum(row.impairmentReversal)
      impairEnd += _getNum(row.impairmentEnd)
      assetCount++

      // 使用寿命不确定 = 0 或 undefined 表示不摊销
      const life = _getNum(row.usefulLifeMonths)
      if (life <= 0) {
        indefiniteCount++
      }
    }

    result['disc_cost_begin'] = costBegin
    result['disc_cost_increase'] = costIncrease
    result['disc_cost_decrease'] = costDecrease
    result['disc_cost_end'] = costEnd
    result['disc_amort_begin'] = amortBegin
    result['disc_amort_provision'] = amortProvision
    result['disc_amort_transfer'] = amortTransfer
    result['disc_amort_end'] = amortEnd
    result['disc_impair_begin'] = impairBegin
    result['disc_impair_provision'] = impairProvision
    result['disc_impair_reversal'] = impairReversal
    result['disc_impair_end'] = impairEnd
    result['disc_net_value'] = costEnd - amortEnd - impairEnd

    // ─ 第(2)子节：摊销费用分配（从I1-9行读取或从amortizationForAlloc取合计）
    const allocResp = allResponses.value.get('I1-9-rows')
    const allocRows = safeParseRows<I1AmortAllocRowRaw>(allocResp?.remark)

    let amortMgmt = 0
    let amortSell = 0
    let amortMfg = 0
    let amortRd = 0
    let amortOther = 0

    if (allocRows.length > 0) {
      for (const row of allocRows) {
        amortMgmt += _getNum(row.managementExpense)
        amortSell += _getNum(row.sellingExpense)
        amortMfg += _getNum(row.manufacturingCost)
        amortRd += _getNum(row.rdExpense)
        amortOther += _getNum(row.otherExpense)
      }
    }

    result['disc_amort_total'] = amortizationForAlloc.value.total
    result['disc_amort_mgmt'] = amortMgmt
    result['disc_amort_sell'] = amortSell
    result['disc_amort_mfg'] = amortMfg
    result['disc_amort_rd'] = amortRd
    result['disc_amort_other'] = amortOther

    // ─ 第(3)子节：统计
    result['disc_asset_count'] = assetCount
    result['disc_indefinite_count'] = indefiniteCount

    return result
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // I1-2 → I1 明细合计（原值/摊销/减值三科目）
    detailTotals,
    // I1-2 合计 → I1 审定表三区块交叉验证
    adjudicationFromDetail,
    // I1-10/11 → I1-9 摊销分配
    amortizationForAlloc,
    // 多sheet → 附注自动取数
    disclosureAutoFill,
  }
}

export default useI1CrossSheet
