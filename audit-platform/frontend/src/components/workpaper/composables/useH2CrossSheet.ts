/**
 * useH2CrossSheet — H2 在建工程跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('H2-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射：
 * - H2-2 明细 → H2-1 审定（按工程聚合期末/增加/减少/转固）
 * - H2-5 转固时点检查 → H2-1 转固列（转固合计交叉验证）
 * - H2-10/H2-11 利息资本化 → H2-2 利息列（资本化金额分摊）
 * - H2-2 明细 → H2-4 分析表（各工程期初/增加/期末/预算/工期）
 * - H2-1 审定 → 附注各子节（审定数自动取数）
 * - H2-3 调整分录 → H2-1 账项调整（1604 AJE/RJE 净额）
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.2
 * Requirements: 14.6-14.7
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { resolveActiveInterestCapResult } from './h2InterestCapBranch'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** H2-2 明细行原始 JSON 结构 */
export interface H2DetailRowRaw {
  rowId?: string
  name?: string              // 工程名称
  budget?: number            // 预算金额
  startDate?: string         // 开工日期
  plannedEndDate?: string    // 预计竣工日期
  completionRate?: number    // 完工进度
  accumulatedInput?: number  // 累计投入
  cipBegin?: number          // 期初余额
  increaseMaterial?: number  // 本期增加-材料
  increaseLabor?: number     // 本期增加-人工
  increaseMachinery?: number // 本期增加-机械
  increaseInterest?: number  // 本期增加-利息
  increaseOther?: number     // 本期增加-其他
  increaseTotal?: number     // 本期增加合计
  decrease?: number          // 本期减少
  transferOut?: number       // 转出（非转固）
  transferDate?: string      // 转固日期
  transferAmount?: number    // 转固金额
  transferToH1?: string      // 转入H1科目
  endAudited?: number        // 审定期末
  remainingCip?: number      // 剩余在建
  cipEnd?: number            // 期末余额
}

/** H2-5 转固时点检查行原始 JSON 结构 */
export interface H2TransferRowRaw {
  rowId?: string
  name?: string              // 工程名称
  transferDate?: string      // 转固日期
  transferAmount?: number    // 转固金额
  condition1?: string        // 条件1-实体建造完成
  condition2?: string        // 条件2-达到设计要求
  condition3?: string        // 条件3-试运转合格
  condition4?: string        // 条件4-竣工决算已办or可确定
  condition5?: string        // 条件5-已投入使用or可使用
  allConditionsMet?: boolean // 五条件全满足
  timelyTransfer?: string    // 是否及时转固
  delayDays?: number         // 延迟天数
  h1Asset?: string           // 对应H1资产
  h1Amount?: number          // H1入账金额
  difference?: number        // 差异
  remark?: string
}

/** H2-10/H2-11 利息资本化结果 JSON 结构 */
export interface H2InterestCapResult {
  totalCap?: number          // 应予资本化金额合计
  byProject?: Record<string, number>  // 按工程项目分摊
  capRate?: number           // 加权资本化率
  branch?: 'noBorrow' | 'withBorrow'  // 分支
}

/** H2-1 审定表行原始 JSON 结构（xlsx 12 列；兼容旧字段别名） */
export interface H2AdjudicationRowRaw {
  rowId?: string
  name?: string
  /** 期初未审 */
  beginUnadjusted?: number
  /** 期初账项调整 */
  beginAdjustment?: number
  /** 期初审定 = 未审 + 账项调整 */
  beginAudited?: number
  /** 期末未审 */
  endUnadjusted?: number
  /** 期末账项调整 */
  endAdjustment?: number
  /** 期末审定 */
  endAudited?: number
  unadjustedChange?: number
  unadjustedChangeRate?: number | null
  auditedChange?: number
  auditedChangeRate?: number | null
  /** @deprecated 旧字段：映射为 beginUnadjusted */
  cipBegin?: number
  /** @deprecated 旧字段：映射为 endUnadjusted */
  cipEnd?: number
  /** @deprecated 旧字段：映射为 endAudited */
  audited?: number
  /** @deprecated 旧增减列（属 H2-2，不应再写入 H2-1） */
  increase?: number
  decrease?: number
  transfer?: number
  unadjusted?: number
  aje?: number
  rje?: number
  impairment?: number
  remark?: string
}

// ─── Return Types ────────────────────────────────────────────────────────────

export interface DetailTotals {
  /** 未审期末原值合计 */
  cipEnd: number
  /** 审定期末原值合计（优先用于与 H2-1 勾稽） */
  endAudited: number
  increase: number
  decrease: number
  transfer: number
}

export interface AdjudicationFromDetail {
  auditedTotal: number
}

export interface TransferSummary {
  totalTransfer: number
  items: Array<{ name: string; amount: number }>
}

export interface InterestCapForDetail {
  totalCap: number
  byProject: Record<string, number>
}

export interface AdjustmentSync {
  /** 账项调整净额（全部分录借−贷；兼容旧口径） */
  totalAje: number
  /** 报表调整净额 */
  totalRje: number
  /** 科目 1604 账项净额（供 H2-1 期末账项调整回写） */
  cipAjeNet: number
  /** 科目 1604 报表调整净额 */
  cipRjeNet: number
  rowCount: number
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
 * 安全解析 JSON 对象，失败回退 null
 */
function safeParseObject<T>(jsonStr: string | null | undefined): T | null {
  if (!jsonStr) return null
  try {
    const parsed = JSON.parse(jsonStr)
    return (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) ? parsed as T : null
  } catch {
    return null
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

/** 兼容旧 JSON：endAudited 缺失时用 未审+账项调整（或 aje+rje） */
function _resolveEndAudited(row: H2AdjudicationRowRaw, endUnadj: number): number {
  if (row.endAudited != null) return _getNum(row.endAudited)
  if (row.audited != null) return _getNum(row.audited)
  if (row.endAdjustment != null) return endUnadj + _getNum(row.endAdjustment)
  return endUnadj + _getNum(row.aje) + _getNum(row.rje)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2CrossSheet(allResponses: Ref<Map<string, any>>) {
  // ─── 解析 H2-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<H2DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('H2-2-rows')
    return safeParseRows<H2DetailRowRaw>(resp?.remark)
  })

  // ─── 解析 H2-5 转固时点检查行数据 ──────────────────────────────────────

  const transferRows = computed<H2TransferRowRaw[]>(() => {
    const resp = allResponses.value.get('H2-5-rows')
    return safeParseRows<H2TransferRowRaw>(resp?.remark)
  })

  // ─── 解析 H2-10/H2-11 利息资本化结果（按互斥分支，避免串支） ──────────

  const interestCapResult = computed<H2InterestCapResult | null>(() => {
    const active = resolveActiveInterestCapResult(allResponses.value)
    return active as H2InterestCapResult | null
  })

  // ─── 解析 H2-1 审定表行数据 ────────────────────────────────────────────

  const adjudicationRows = computed<H2AdjudicationRowRaw[]>(() => {
    const resp = allResponses.value.get('H2-1-rows')
    return safeParseRows<H2AdjudicationRowRaw>(resp?.remark)
  })

  // ─── detailTotals: H2-2 按工程聚合期末/增加/减少/转固（Req 14.6）──────

  /**
   * 从 H2-2 明细行聚合合计：
   * - cipEnd: 未审期末原值合计
   * - endAudited: 审定期末原值合计（与 H2-1 勾稽优先口径）
   * - increase / decrease / transfer: 增减与转固
   */
  const detailTotals: ComputedRef<DetailTotals> = computed(() => {
    let cipEnd = 0
    let endAudited = 0
    let increase = 0
    let decrease = 0
    let transfer = 0

    for (const row of detailRows.value) {
      cipEnd += _getNum(row.cipEnd)
      // 无审定字段时回退未审期末（旧数据兼容）
      endAudited += _getNum(row.endAudited) || _getNum(row.cipEnd)
      const rowIncrease = _getNum(row.increaseTotal) ||
        (_getNum(row.increaseMaterial) + _getNum(row.increaseLabor) +
         _getNum(row.increaseMachinery) + _getNum(row.increaseInterest) +
         _getNum(row.increaseOther))
      increase += rowIncrease
      decrease += _getNum(row.decrease) + _getNum(row.transferOut)
      transfer += _getNum(row.transferAmount)
    }

    return { cipEnd, endAudited, increase, decrease, transfer }
  })

  // ─── adjudicationFromDetail: H2-2 合计 → H2-1 审定表（Req 14.6）───────

  /**
   * H2-2 明细表的审定期末合计，供 H2-1 审定表交叉验证。
   */
  const adjudicationFromDetail: ComputedRef<AdjudicationFromDetail> = computed(() => {
    return {
      auditedTotal: detailTotals.value.endAudited,
    }
  })

  // ─── transferSummary: H2-5 转固合计 → H2-1 转固列（Req 14.6）──────────

  /**
   * 从 H2-5 转固时点检查表聚合转固信息：
   * - totalTransfer: 所有转固行金额之和
   * - items: 各工程转固明细（名称+金额）
   *
   * 用于与 H2-1"本期转固"列合计交叉验证。
   */
  const transferSummary: ComputedRef<TransferSummary> = computed(() => {
    let totalTransfer = 0
    const items: Array<{ name: string; amount: number }> = []

    for (const row of transferRows.value) {
      const amount = _getNum(row.transferAmount)
      totalTransfer += amount
      if (amount !== 0) {
        items.push({
          name: row.name || '未命名工程',
          amount,
        })
      }
    }

    return { totalTransfer, items }
  })

  // ─── interestCapForDetail: H2-10/11 资本化金额 → H2-2 利息列（Req 14.6）

  /**
   * 从 H2-10 或 H2-11 利息资本化计算结果读取：
   * - totalCap: 应予资本化金额合计
   * - byProject: 按工程项目分摊的资本化金额
   *
   * 供 H2-2 明细表"利息"列交叉验证（各工程利息列之和应=totalCap）。
   */
  const interestCapForDetail: ComputedRef<InterestCapForDetail> = computed(() => {
    const result = interestCapResult.value
    if (!result) {
      return { totalCap: 0, byProject: {} }
    }
    return {
      totalCap: _getNum(result.totalCap),
      byProject: result.byProject ?? {},
    }
  })

  // ─── analysisFromDetail: H2-2 → H2-4 分析表取数（Req 14.6）────────────

  /**
   * 从 H2-2 明细表聚合分析指标供 H2-4 分析表使用：
   * - total_budget: 预算合计
   * - total_accumulated: 累计投入合计
   * - total_cip_begin: 期初合计
   * - total_cip_end: 期末合计
   * - total_increase: 增加合计
   * - total_decrease: 减少合计
   * - total_transfer: 转固合计
   * - project_count: 工程项目数量
   * - completed_count: 完工率≥100%的项目数
   * - overdue_count: 逾期项目数（H2-4用于判断）
   */
  const analysisFromDetail: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {
      total_budget: 0,
      total_accumulated: 0,
      total_cip_begin: 0,
      total_cip_end: 0,
      total_increase: 0,
      total_decrease: 0,
      total_transfer: 0,
      project_count: 0,
      completed_count: 0,
      overdue_count: 0,
    }

    const now = Date.now()

    for (const row of detailRows.value) {
      result['total_budget'] += _getNum(row.budget)
      result['total_accumulated'] += _getNum(row.accumulatedInput)
      result['total_cip_begin'] += _getNum(row.cipBegin)
      result['total_cip_end'] += _getNum(row.cipEnd)

      const rowIncrease = _getNum(row.increaseTotal) ||
        (_getNum(row.increaseMaterial) + _getNum(row.increaseLabor) +
         _getNum(row.increaseMachinery) + _getNum(row.increaseInterest) +
         _getNum(row.increaseOther))
      result['total_increase'] += rowIncrease
      result['total_decrease'] += _getNum(row.decrease)
      result['total_transfer'] += _getNum(row.transferAmount)
      result['project_count']++

      // 完工率≥100%
      const rate = _getNum(row.completionRate)
      if (rate >= 100) {
        result['completed_count']++
      }

      // 逾期判断：预计竣工日期已过且尚未转固
      if (row.plannedEndDate && !row.transferDate) {
        const planned = new Date(row.plannedEndDate).getTime()
        if (Number.isFinite(planned) && planned < now) {
          result['overdue_count']++
        }
      }
    }

    return result
  })

  // ─── disclosureAutoFill: H2-1 审定数 → 附注各子节（Req 14.6）──────────

  /**
   * 从 H2-1 审定表聚合数据供附注披露自动填充。
   * 期初/期末/审定取自 H2-1；增减/转固取自 H2-2（H2-1 无增减列，见 conflict #2/#3）。
   */
  const disclosureAutoFill: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {
      disc_cip_begin: 0,
      disc_cip_end: 0,
      disc_increase: 0,
      disc_decrease: 0,
      disc_transfer: 0,
      disc_audited: 0,
      disc_impairment: 0,
      disc_interest_cap: 0,
      disc_project_count: 0,
    }

    for (const row of adjudicationRows.value) {
      const beginUnadj = _getNum(row.beginUnadjusted ?? row.cipBegin ?? row.unadjusted)
      const endUnadj = _getNum(row.endUnadjusted ?? row.cipEnd)
      const endAud = _resolveEndAudited(row, endUnadj)
      result['disc_cip_begin'] += beginUnadj
      result['disc_cip_end'] += endUnadj
      result['disc_audited'] += endAud
      result['disc_impairment'] += _getNum(row.impairment)
      result['disc_project_count']++
    }

    // 增减/转固：权威来源为 H2-2（非 H2-1）
    result['disc_increase'] = detailTotals.value.increase
    result['disc_decrease'] = detailTotals.value.decrease
    result['disc_transfer'] = detailTotals.value.transfer

    // 减值准备合计优先取 H2-1-impair-rows 期末审定
    const impairResp = allResponses.value.get('H2-1-impair-rows')
    const impairRows = safeParseRows<H2AdjudicationRowRaw>(impairResp?.remark)
    if (impairRows.length > 0) {
      result['disc_impairment'] = impairRows.reduce((s, r) => {
        const endUnadj = _getNum(r.endUnadjusted ?? r.cipEnd)
        return s + _resolveEndAudited(r, endUnadj)
      }, 0)
    }

    // 利息资本化金额从 H2-10/11 取
    result['disc_interest_cap'] = interestCapForDetail.value.totalCap

    return result
  })

  // ─── adjustmentSync: H2-3 AJE/RJE → H2-1（对齐 H1-3→H1-1）───────────────

  /**
   * 从 H2-3 调整分录汇总 AJE/RJE：
   * - totalAje/totalRje：全表净额
   * - cipAjeNet/cipRjeNet：仅科目 1604（含明细）的借−贷净额，供审定表期末账项调整回写
   * 兼容 Excel「类别=账项调整/报表调整/其他」与旧存档 AJE/RJE、debit/credit。
   */
  const adjustmentSync: ComputedRef<AdjustmentSync> = computed(() => {
    const resp = allResponses.value.get('H2-3-rows')
    const adjRows = safeParseRows<Record<string, any>>(resp?.remark)
    let totalAje = 0
    let totalRje = 0
    let cipAjeNet = 0
    let cipRjeNet = 0

    for (const row of adjRows) {
      const debit = _getNum(row.debitAmount ?? row.debit)
      const credit = _getNum(row.creditAmount ?? row.credit)
      const netAmount = debit - credit
      const cat = String(row.category || '').trim()
      const isRje = cat === '报表调整' || row.entryType === 'RJE'
      const code = String(row.accountCode || '')
      const isCip = code === '1604' || code.startsWith('1604')

      if (isRje) {
        totalRje += netAmount
        if (isCip) cipRjeNet += netAmount
      } else {
        totalAje += netAmount
        if (isCip) cipAjeNet += netAmount
      }
    }

    return {
      totalAje,
      totalRje,
      cipAjeNet,
      cipRjeNet,
      rowCount: adjRows.length,
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // H2-2 → H2-1 明细合计（期末/增加/减少/转固）
    detailTotals,
    // H2-2 合计 → H2-1 审定表交叉验证
    adjudicationFromDetail,
    // H2-5 → H2-1 转固合计交叉验证
    transferSummary,
    // H2-10/11 → H2-2 利息列交叉验证
    interestCapForDetail,
    // H2-2 → H2-4 分析表取数
    analysisFromDetail,
    // H2-1 → 附注各子节自动取数
    disclosureAutoFill,
    // H2-3 → H2-1 AJE/RJE 同步
    adjustmentSync,
  }
}

export default useH2CrossSheet
