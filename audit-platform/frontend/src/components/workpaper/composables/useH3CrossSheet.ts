/**
 * useH3CrossSheet — H3 投资性房地产跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('H3-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射（含双计量模式分支）：
 * - H3-2 明细 → H3-1 审定（按分类聚合：成本→原值/折旧/净值；公允→公允期末）
 * - H3-6 互转 → H3-1 转换列（三方向互转金额汇总）
 * - H3-14 租金 → 附注（年租金合计 + 按资产明细）
 * - H3-8 公允复核 → H3-1 公允变动列（公允价值变动总额）
 * - 多源 → 附注自动取数（H3-1审定/H3-6互转/H3-14租金/H3-8公允变动）
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.3
 * Requirements: 16.6-16.7
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** H3-2 成本模式明细行 JSON 结构 */
export interface H3DetailCostRowRaw {
  rowId?: string
  assetName?: string       // 资产名称
  category?: string        // 资产分类
  assetType?: string       // 资产分类（当前前端键名）
  originalCostEnd?: number // 原值期末
  costEnd?: number         // 原值期末（当前前端明细键名）
  originalCost?: number    // 入账原值/兼容旧键
  accDepEnd?: number       // 累计折旧期末
  impairmentEnd?: number   // 减值准备期末
  netValue?: number        // 净值 = 原值 - 折旧 - 减值
}

/** H3-2 公允价值模式明细行 JSON 结构 */
export interface H3DetailFairRowRaw {
  rowId?: string
  assetName?: string         // 资产名称
  category?: string          // 资产分类
  assetType?: string         // 资产分类（当前前端键名）
  fairValueEnd?: number      // 期末公允价值
  fairValueChange?: number   // 公允价值变动
}

/** H3-6 互转行 JSON 结构 */
export interface H3TransferRowRaw {
  rowId?: string
  direction?: string       // 'selfToInvest' | 'investToSelf' | 'cipToInvest'
  assetName?: string
  transferAmount?: number  // 转换金额
  sourceWp?: string        // 来源底稿 'H1' | 'H2'
  bookValue?: number       // 账面价值
  fairValue?: number       // 公允价值（公允模式下）
}

/** H3-14 租金收入行 JSON 结构（对齐 Excel 应计/已计 + 日后收款） */
export interface H3RentalRowRaw {
  rowId?: string
  assetName?: string       // 资产名称
  category?: string        // building | land
  monthlyRent?: number     // 月租金
  monthsThisYear?: number  // 本期租赁月数
  expectedRent?: number    // 应计租金
  bookedRent?: number      // 已计租金
  incomeDiff?: number      // 应计−已计
  annualRent?: number      // 年租金
  vacancyRate?: number     // 空置率
  actualIncome?: number    // 实际收入（旧字段兼容）
  futureTotal?: number     // 日后未折现收款合计
}

/** H3-8 公允价值复核行 JSON 结构 */
export interface H3FairValueReviewRowRaw {
  rowId?: string
  assetName?: string
  endingBalance?: number
  openingFairValue?: number
  assessedValue?: number
  appraisalValue?: number
  bookValue?: number
  difference?: number
  fairValueChange?: number
}

// ─── Return Types ────────────────────────────────────────────────────────────

/** H3-2 明细合计 */
export interface DetailTotals {
  assetEnd: number        // 原值/公允期末合计
  depEnd: number          // 累计折旧期末合计（公允模式=0）
  impairmentEnd: number   // 减值准备期末合计（公允模式=0）
  netValue: number        // 净值合计
  fairValueChange: number // 公允变动合计（成本模式=0）
}

/** H3-2 合计 → H3-1 审定表交叉验证 */
export type AdjudicationFromDetail =
  | { costAudited: number; depAudited: number }  // 成本模式
  | { fairAudited: number }                       // 公允价值模式

/** H3-6 互转金额汇总 → H3-1 转换列 */
export interface TransferSummary {
  fromH1: number   // 从 H1 固定资产转入金额
  toH1: number     // 转出到 H1 固定资产金额
  fromH2: number   // 从 H2 在建工程转入金额
}

/** H3-3 调整分录 → H3-1 AJE/RJE */
export interface AdjustmentSync {
  totalAje: number
  totalRje: number
  aje1503: number
  rje1503: number
  aje1504: number
  rje1504: number
  aje1505: number
  rje1505: number
}

/** H3-14 租金收入 → 附注 */
export interface RentalForDisclosure {
  annualTotal: number                    // 年租金收入合计
  byAsset: Record<string, number>        // 按资产分别的年租金
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

export function useH3CrossSheet(
  allResponses: Ref<Map<string, any>>,
  measurementModel: Ref<string>,
) {
  // ═══════════════════════════════════════════════════════════════════════════
  // 解析各 sheet 行数据（从 allResponses 读取 JSON 行数组）
  // ═══════════════════════════════════════════════════════════════════════════

  /** H3-2 成本模式明细行 */
  const detailCostRows = computed<H3DetailCostRowRaw[]>(() => {
    const resp = allResponses.value.get('H3-2-cost-rows')
    return safeParseRows<H3DetailCostRowRaw>(resp?.remark)
  })

  /** H3-2 公允价值模式明细行 */
  const detailFairRows = computed<H3DetailFairRowRaw[]>(() => {
    const resp = allResponses.value.get('H3-2-fair-rows')
    return safeParseRows<H3DetailFairRowRaw>(resp?.remark)
  })

  /** H3-6 互转审核行 */
  const transferRows = computed<H3TransferRowRaw[]>(() => {
    const resp = allResponses.value.get('H3-6-transfer-rows')
    return safeParseRows<H3TransferRowRaw>(resp?.remark)
  })

  /** H3-3 调整分录行 */
  const adjustmentRows = computed(() => {
    const resp = allResponses.value.get('H3-3-adj-rows')
    return safeParseRows<{
      entryType?: string
      accountCode?: string
      accountName?: string
      debitAmount?: number
      creditAmount?: number
    }>(resp?.remark)
  })

  /** H3-14 租金收入行（主键 contract-rows，兼容旧键 rental-rows） */
  const rentalRows = computed<H3RentalRowRaw[]>(() => {
    const primary = allResponses.value.get('H3-14-contract-rows')
    const legacy = allResponses.value.get('H3-14-rental-rows')
    const fromPrimary = safeParseRows<H3RentalRowRaw>(primary?.remark)
    if (fromPrimary.length) return fromPrimary
    return safeParseRows<H3RentalRowRaw>(legacy?.remark)
  })

  /** H3-8 公允价值复核行（主键 H3-8-calc-rows，兼容旧键 H3-8-review-rows） */
  const fairValueReviewRows = computed<H3FairValueReviewRowRaw[]>(() => {
    const primary = allResponses.value.get('H3-8-calc-rows')
    const legacy = allResponses.value.get('H3-8-review-rows')
    const fromPrimary = safeParseRows<H3FairValueReviewRowRaw>(primary?.remark)
    if (fromPrimary.length) return fromPrimary
    return safeParseRows<H3FairValueReviewRowRaw>(legacy?.remark)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 1. detailTotals — H3-2 按分类聚合（Req 16.6）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * 从 H3-2 明细行聚合合计，按当前计量模式选择数据源：
   * - 成本模式：原值期末合计 / 折旧期末合计 / 净值合计
   * - 公允模式：公允期末合计作为 assetEnd / depEnd=0 / netValue=assetEnd
   */
  const detailTotals: ComputedRef<DetailTotals> = computed(() => {
    if (measurementModel.value === 'cost') {
      let assetEnd = 0
      let depEnd = 0
      let impairmentEnd = 0
      let netValue = 0

      for (const row of detailCostRows.value) {
        const cost = _getNum(row.originalCostEnd ?? row.costEnd ?? row.originalCost)
        const dep = _getNum(row.accDepEnd)
        const impair = _getNum(row.impairmentEnd)
        assetEnd += cost
        depEnd += dep
        impairmentEnd += impair
        netValue += _getNum(row.netValue) || (cost - dep - impair)
      }

      return {
        assetEnd,
        depEnd,
        impairmentEnd,
        netValue,
        fairValueChange: 0,
      }
    }

    // 公允价值模式：公允期末合计
    let fairEnd = 0
    let fairChange = 0
    for (const row of detailFairRows.value) {
      fairEnd += _getNum(row.fairValueEnd)
      fairChange += _getNum(row.fairValueChange)
    }

    return {
      assetEnd: fairEnd,
      depEnd: 0,
      impairmentEnd: 0,
      netValue: fairEnd,
      fairValueChange: fairChange,
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. adjudicationFromDetail — H3-2 合计 → H3-1 交叉验证（Req 16.6）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * H3-2 明细合计供 H3-1 审定表交叉验证。
   * - 成本模式：返回 { costAudited, depAudited }（原值合计, 折旧合计）
   * - 公允模式：返回 { fairAudited }（公允价值期末合计）
   */
  const adjudicationFromDetail: ComputedRef<AdjudicationFromDetail> = computed(() => {
    if (measurementModel.value === 'cost') {
      const totals = detailTotals.value
      return {
        costAudited: totals.assetEnd,
        depAudited: totals.depEnd,
      }
    }

    // 公允价值模式：返回公允期末合计
    return {
      fairAudited: detailTotals.value.assetEnd,
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. transferSummary — H3-6 互转金额 → H3-1 转换列（Req 16.6-16.7）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * 从 H3-6 互转审核行聚合三方向转换金额：
   * - fromH1: 从 H1 固定资产转入（自用→投资，增加方）
   * - toH1:   转出到 H1 固定资产（投资→自用，减少方）
   * - fromH2: 从 H2 在建工程转入（在建→投资，增加方）
   *
   * direction 约定：
   * - 'selfToInvest': 自用→投资性房地产（从H1转入，fromH1 += amount）
   * - 'investToSelf': 投资性房地产→自用（转出到H1，toH1 += amount）
   * - 'cipToInvest':  在建工程→投资性房地产（从H2转入，fromH2 += amount）
   */
  const transferSummary: ComputedRef<TransferSummary> = computed(() => {
    let fromH1 = 0
    let toH1 = 0
    let fromH2 = 0

    for (const row of transferRows.value) {
      const amount = _getNum(row.transferAmount) || _getNum((row as any).transferIn) || _getNum((row as any).transferOut)
      switch (row.direction) {
        case 'selfToInvest':
          fromH1 += amount
          break
        case 'investToSelf':
          toH1 += amount
          break
        case 'cipToInvest':
          fromH2 += amount
          break
        // 未知方向忽略
      }
    }

    return { fromH1, toH1, fromH2 }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. rentalForDisclosure — H3-14 → 附注（Req 16.6）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * 从 H3-14 租金收入行聚合：
   * - annualTotal: 所有资产年租金收入合计
   * - byAsset: 按资产名称分别的年租金收入
   *
   * 使用 annualRent 字段（若无则按 monthlyRent×12 估算）。
   */
  const rentalForDisclosure: ComputedRef<RentalForDisclosure> = computed(() => {
    let annualTotal = 0
    const byAsset: Record<string, number> = {}

    for (const row of rentalRows.value) {
      // 优先应计/年租金；否则月租×12；再否则已计/实际收入
      let rent = _getNum(row.expectedRent)
      if (rent === 0) rent = _getNum(row.annualRent)
      if (rent === 0) rent = _getNum(row.monthlyRent) * 12
      if (rent === 0) rent = _getNum(row.bookedRent) || _getNum(row.actualIncome)

      const name = row.assetName || '未命名资产'
      annualTotal += rent
      byAsset[name] = (byAsset[name] || 0) + rent
    }

    return { annualTotal, byAsset }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 5. fairValueChangeTotal — H3-8 → H3-1 公允变动列（Req 16.6）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * 从 H3-8 公允价值复核行聚合"公允价值变动"总额。
   * 仅在公允价值模式下有实际意义（成本模式无公允变动），但始终返回数值。
   * 用于 H3-1(公允版本) "公允价值变动" 列的交叉验证。
   */
  const fairValueChangeTotal: ComputedRef<number> = computed(() => {
    let total = 0
    for (const row of fairValueReviewRows.value) {
      const explicit = _getNum(row.fairValueChange)
      if (explicit) {
        total += explicit
        continue
      }
      const ending = _getNum(row.endingBalance ?? row.appraisalValue ?? row.assessedValue ?? row.bookValue)
      const opening = _getNum(row.openingFairValue)
      total += ending - opening
    }
    return total
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 6. disclosureAutoFill — 多源 → 附注自动取数（Req 16.6-16.7）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * 附注披露自动取数，从多个 sheet 聚合数据供附注子节引用。
   *
   * 数据来源：
   * - H3-1 审定表数据（从 allResponses 直接读取汇总值）
   * - H3-6 互转明细（三方向转换金额）
   * - H3-14 租金明细（年租金合计/资产数量/空置率）
   * - H3-8 公允价值变动（变动总额）
   *
   * 输出字段命名规则：disc_{来源}_{含义}
   */
  const disclosureAutoFill: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {}

    // ─── 从 detailTotals 取审定合计 ─────────────────────────────────────────
    const totals = detailTotals.value
    result['disc_asset_end'] = totals.assetEnd
    result['disc_dep_end'] = totals.depEnd
    result['disc_impairment_end'] = totals.impairmentEnd
    result['disc_net_value'] = totals.netValue
    result['disc_fair_value_change'] = totals.fairValueChange

    // ─── 从 H3-2 明细行聚合期初/增减数据 ────────────────────────────────────
    if (measurementModel.value === 'cost') {
      let costBegin = 0
      let costIncrease = 0
      let costDecrease = 0
      let depBegin = 0
      let depIncrease = 0
      let depDecrease = 0

      for (const row of detailCostRows.value) {
        // 优先直接从明细行聚合（当前前端键名）；兼容旧单行详情 item
        costBegin += _getNum((row as any).costBegin ?? (row as any).originalCostBegin)
        costIncrease += _getNum((row as any).costIncrease ?? (row as any).originalCostIncrease)
        costDecrease += _getNum((row as any).costDecrease ?? (row as any).originalCostDecrease)
        depBegin += _getNum((row as any).accDepBegin)
        depIncrease += _getNum((row as any).depProvision ?? (row as any).accDepProvision)
        depDecrease += _getNum((row as any).depReversal ?? (row as any).accDepReversal)

        const resp = allResponses.value.get(`H3-2-cost-row-${row.rowId}`)
        if (resp?.remark) {
          try {
            const detail = JSON.parse(resp.remark)
            if (!costBegin) costBegin += _getNum(detail.originalCostBegin ?? detail.costBegin)
            if (!costIncrease) costIncrease += _getNum(detail.originalCostIncrease ?? detail.costIncrease)
            if (!costDecrease) costDecrease += _getNum(detail.originalCostDecrease ?? detail.costDecrease)
            if (!depBegin) depBegin += _getNum(detail.accDepBegin)
            if (!depIncrease) depIncrease += _getNum(detail.accDepProvision ?? detail.depProvision)
            if (!depDecrease) depDecrease += _getNum(detail.accDepReversal ?? detail.depReversal)
          } catch { /* 静默 */ }
        }
      }

      // 若单行详情无数据，尝试从汇总 item 获取
      if (costBegin === 0) {
        costBegin = _getNum(allResponses.value.get('H3-2-cost-begin-total')?.remark)
      }
      if (costIncrease === 0) {
        costIncrease = _getNum(allResponses.value.get('H3-2-cost-increase-total')?.remark)
      }
      if (costDecrease === 0) {
        costDecrease = _getNum(allResponses.value.get('H3-2-cost-decrease-total')?.remark)
      }

      result['disc_cost_begin'] = costBegin
      result['disc_cost_increase'] = costIncrease
      result['disc_cost_decrease'] = costDecrease
      result['disc_dep_begin'] = depBegin
      result['disc_dep_increase'] = depIncrease
      result['disc_dep_decrease'] = depDecrease
    } else {
      // 公允价值模式
      let fairBegin = 0
      let fairIncrease = 0
      let fairDecrease = 0
      let fairChange = 0

      for (const row of detailFairRows.value) {
        fairBegin += _getNum((row as any).fairValueBegin)
        fairIncrease += _getNum((row as any).fairIncrease ?? (row as any).fairValueIncrease)
        fairDecrease += _getNum((row as any).fairDecrease ?? (row as any).fairValueDecrease)
        fairChange += _getNum(row.fairValueChange)

        const resp = allResponses.value.get(`H3-2-fair-row-${row.rowId}`)
        if (resp?.remark) {
          try {
            const detail = JSON.parse(resp.remark)
            if (!fairBegin) fairBegin += _getNum(detail.fairValueBegin)
            if (!fairIncrease) fairIncrease += _getNum(detail.fairValueIncrease ?? detail.fairIncrease)
            if (!fairDecrease) fairDecrease += _getNum(detail.fairValueDecrease ?? detail.fairDecrease)
            if (!fairChange) fairChange += _getNum(detail.fairValueChange)
          } catch { /* 静默 */ }
        }
      }

      // fallback 从汇总 item 获取
      if (fairBegin === 0) {
        fairBegin = _getNum(allResponses.value.get('H3-2-fair-begin-total')?.remark)
      }
      if (fairChange === 0) {
        fairChange = fairValueChangeTotal.value
      }

      result['disc_fair_begin'] = fairBegin
      result['disc_fair_increase'] = fairIncrease
      result['disc_fair_decrease'] = fairDecrease
      result['disc_fair_change'] = fairChange
    }

    // ─── 从 H3-6 互转汇总 ───────────────────────────────────────────────────
    const transfer = transferSummary.value
    result['disc_transfer_from_h1'] = transfer.fromH1
    result['disc_transfer_to_h1'] = transfer.toH1
    result['disc_transfer_from_h2'] = transfer.fromH2
    result['disc_transfer_net'] = transfer.fromH1 + transfer.fromH2 - transfer.toH1

    // ─── 从 H3-14 租金收入 ───────────────────────────────────────────────────
    const rental = rentalForDisclosure.value
    result['disc_rental_annual'] = rental.annualTotal
    result['disc_rental_asset_count'] = Object.keys(rental.byAsset).length

    // 空置率平均值（按资产数加权简化为均值）
    let totalVacancy = 0
    let vacancyCount = 0
    for (const row of rentalRows.value) {
      const v = _getNum(row.vacancyRate)
      if (v > 0) {
        totalVacancy += v
        vacancyCount++
      }
    }
    result['disc_vacancy_rate_avg'] = vacancyCount > 0 ? totalVacancy / vacancyCount : 0

    // ─── 从 H3-8 公允价值变动 ────────────────────────────────────────────────
    result['disc_fair_value_change_total'] = fairValueChangeTotal.value

    // ─── 计量模式标识 ────────────────────────────────────────────────────────
    result['disc_measurement_model'] = measurementModel.value === 'cost' ? 1 : 2

    return result
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 7. adjustmentSync — H3-3 → H3-1 AJE/RJE（Req 4.4）
  // ═══════════════════════════════════════════════════════════════════════════

  const adjustmentSync: ComputedRef<AdjustmentSync> = computed(() => {
    let totalAje = 0
    let totalRje = 0
    let aje1503 = 0
    let rje1503 = 0
    let aje1504 = 0
    let rje1504 = 0
    let aje1505 = 0
    let rje1505 = 0

    for (const row of adjustmentRows.value) {
      const net = _getNum(row.debitAmount) - _getNum(row.creditAmount)
      const code = String(row.accountCode || '')
      const name = String(row.accountName || '')
      const is1505 = code.startsWith('1505') || /减值准备/.test(name)
      const is1504 = code.startsWith('1504') || /累计折旧|累计摊销/.test(name)
      const is1503 = code.startsWith('1503') || /投资性房地产/.test(name)
      const isRje = row.entryType === 'RJE'

      if (isRje) {
        totalRje += net
        if (is1505) rje1505 += net
        else if (is1504) rje1504 += net
        else if (is1503 || (!is1504 && !is1505 && code)) rje1503 += net
      } else {
        totalAje += net
        if (is1505) aje1505 += net
        else if (is1504) aje1504 += net
        else if (is1503 || (!is1504 && !is1505 && code)) aje1503 += net
      }
    }

    return { totalAje, totalRje, aje1503, rje1503, aje1504, rje1504, aje1505, rje1505 }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Return
  // ═══════════════════════════════════════════════════════════════════════════

  return {
    // H3-2 → H3-1 明细合计（按计量模式分支）
    detailTotals,
    // H3-2 合计 → H3-1 审定表交叉验证
    adjudicationFromDetail,
    // H3-6 → H3-1 互转金额汇总
    transferSummary,
    // H3-14 → 附注 租金收入
    rentalForDisclosure,
    // H3-8 → H3-1 公允价值变动总额
    fairValueChangeTotal,
    // H3-3 → H3-1 AJE/RJE
    adjustmentSync,
    // 多源 → 附注自动取数
    disclosureAutoFill,
  }
}

export default useH3CrossSheet
