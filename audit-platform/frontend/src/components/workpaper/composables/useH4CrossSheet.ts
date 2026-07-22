/**
 * useH4CrossSheet — H4 工程物资跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('H4-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射：
 * - H4-1 审定合计 vs H4-2 明细合计（Req 2.7）
 * - H4-4 增加合计 vs H4-1 借方发生合计（Req 3.5）
 * - H4-5 减少合计 vs H4-1 贷方发生合计（Req 3.5）
 * - H4-1 审定数 → 附注各子节自动取数
 *
 * 科目：1605工程物资（借方/资产类）
 * 审定口径（xlsx/冲突决议）：审定 = 未审 + 账项调整（AJE/RJE 在 H4-3 分列，回写 H4-1 时合并）
 * H4-4/5 vs H4-1 借/贷：以 H4-2 增减汇总为分母，检查表为样本覆盖率（非全量平衡）
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 3.2
 * Requirements: 2.7, 3.5
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 跨sheet校验结果 */
export interface CrossSheetCheck {
  /** 差额（来源A - 来源B） */
  diff: number
  /** 是否匹配（|diff| < 0.01） */
  isMatch: boolean
}

/** H4-2 明细行原始 JSON 结构 */
export interface H4DetailRowRaw {
  rowId?: string
  category?: string        // 物资分类
  name?: string            // 物资名称
  beginAmount?: number     // 期初金额
  purchaseAmount?: number  // 本期采购
  otherIncrease?: number   // 其他增加
  increaseSubtotal?: number // 入库小计
  usageAmount?: number     // 领用出库
  returnAmount?: number    // 退货
  scrapAmount?: number     // 报废
  otherDecrease?: number   // 其他减少
  endAmount?: number       // 期末原值
  endQty?: number          // 期末数量
  quantity?: number        // 兼容旧字段（=endQty）
  bookValueEnd?: number    // 未审净值
  auditedBookValue?: number
  impairEnd?: number
}

/** H4-4 增加检查行原始 JSON 结构 */
export interface H4AdditionRowRaw {
  rowId?: string
  name?: string            // 物资名称
  amount?: number          // 金额
  invoiceAmount?: number   // 发票金额
}

/** H4-5 减少检查行原始 JSON 结构 */
export interface H4DisposalRowRaw {
  rowId?: string
  name?: string            // 物资名称
  amount?: number          // 金额（兼容旧字段）
  originalCost?: number    // 原值（致同列）
  reason?: string          // 减少原因（兼容）
  disposalMethod?: string  // 减少方式
  h2Ref?: string           // 对应H2编号
}

/** H4-1 审定表汇总数据 */
export interface H4AdjudicationTotals {
  adjudicatedTotal: number   // 审定数合计
  debitTotal: number         // 借方发生合计（增加）
  creditTotal: number        // 贷方发生合计（减少）
  beginTotal: number         // 期初余额合计
  endTotal: number           // 期末余额合计
}

/** H4-3 → H4-1 调整净额同步 */
export interface H4AdjustmentSync {
  totalAje: number
  totalRje: number
  /** 1605 原值相关账项净额（借−贷） */
  emAjeNet: number
  /** 1605 原值相关报表净额 */
  emRjeNet: number
  /** 1605 减值相关账项净额（对减值段：−(借−贷)，即贷方增加准备为正） */
  impairAjeNet: number
  impairRjeNet: number
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
 * 安全提取数值，NaN/null/undefined → 0
 */
function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

/**
 * 从 allResponses 获取指定 item_id 的数值（存储在 remark 字段）
 */
function _getResponseNum(allResponses: Map<string, any>, itemId: string): number {
  const resp = allResponses.get(itemId)
  return _getNum(resp?.remark)
}

/**
 * 判断差额是否匹配（精度阈值0.01）
 */
function _checkMatch(diff: number): CrossSheetCheck {
  return {
    diff,
    isMatch: Math.abs(diff) < 0.01,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4CrossSheet(allResponses: Ref<Map<string, any>>) {
  // ═══════════════════════════════════════════════════════════════════════════
  // 解析各 sheet 行数据（从 allResponses 读取 JSON 行数组）
  // ═══════════════════════════════════════════════════════════════════════════

  /** H4-2 明细行数据 */
  const detailRows = computed<H4DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('H4-2-rows')
    return safeParseRows<H4DetailRowRaw>(resp?.remark)
  })

  /** H4-4 增加检查行数据 */
  const additionRows = computed<H4AdditionRowRaw[]>(() => {
    const resp = allResponses.value.get('H4-4-rows')
    return safeParseRows<H4AdditionRowRaw>(resp?.remark)
  })

  /** H4-5 减少检查行数据 */
  const disposalRows = computed<H4DisposalRowRaw[]>(() => {
    const resp = allResponses.value.get('H4-5-rows')
    return safeParseRows<H4DisposalRowRaw>(resp?.remark)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // H4-1 审定表汇总值（从 allResponses 直接读取汇总 item）
  // ═══════════════════════════════════════════════════════════════════════════

  /** H4-1 审定表各合计值 */
  const adjudicationTotals: ComputedRef<H4AdjudicationTotals> = computed(() => {
    const map = allResponses.value
    return {
      adjudicatedTotal: _getResponseNum(map, 'H4-1-adjudicated-total'),
      debitTotal: _getResponseNum(map, 'H4-1-debit-total'),
      creditTotal: _getResponseNum(map, 'H4-1-credit-total'),
      beginTotal: _getResponseNum(map, 'H4-1-begin-total'),
      endTotal: _getResponseNum(map, 'H4-1-end-total'),
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // H4-2 明细表合计
  // ═══════════════════════════════════════════════════════════════════════════

  /** H4-2 明细表期末余额合计（从行数据或汇总 item 获取） */
  const detailTotal = computed<number>(() => {
    // 优先从汇总 item 读取（H4-2 组件保存时写入）
    const summaryVal = _getResponseNum(allResponses.value, 'H4-2-detail-total')
    if (summaryVal !== 0) return summaryVal

    // fallback：从明细行聚合
    let total = 0
    for (const row of detailRows.value) {
      total += _getNum(row.endAmount)
    }
    return total
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // H4-4 增加检查合计
  // ═══════════════════════════════════════════════════════════════════════════

  /** H4-4 增加检查表金额合计（从行数据或汇总 item 获取） */
  const additionTotal = computed<number>(() => {
    // 优先从汇总 item 读取
    const summaryVal = _getResponseNum(allResponses.value, 'H4-4-addition-total')
    if (summaryVal !== 0) return summaryVal

    // fallback：从行数据聚合
    let total = 0
    for (const row of additionRows.value) {
      total += _getNum(row.amount)
    }
    return total
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // H4-5 减少检查合计
  // ═══════════════════════════════════════════════════════════════════════════

  /** H4-5 减少检查表金额合计（从行数据或汇总 item 获取） */
  const disposalTotal = computed<number>(() => {
    // 优先从汇总 item 读取
    const summaryVal = _getResponseNum(allResponses.value, 'H4-5-disposal-total')
    if (summaryVal !== 0) return summaryVal

    // fallback：从行数据聚合（优先 originalCost，兼容旧 amount）
    let total = 0
    for (const row of disposalRows.value) {
      total += _getNum(row.originalCost ?? row.amount)
    }
    return total
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 1. adjudicationVsDetail — H4-1审定合计 vs H4-2明细合计（Req 2.7）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * H4-1 审定数合计 与 H4-2 明细期末余额合计 的交叉验证。
   * 两者应一致（diff=0），不一致时显示黄色警告。
   *
   * 公式：diff = H4-1审定合计 - H4-2明细合计
   * isMatch: |diff| < 0.01
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheck> = computed(() => {
    const adjTotal = adjudicationTotals.value.adjudicatedTotal
    const detTotal = detailTotal.value
    return _checkMatch(adjTotal - detTotal)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. additionVsAdjudication — H4-4增加合计 vs H4-1借方发生合计（Req 3.5）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * H4-4 增加检查表金额合计 与 H4-1 借方发生合计 的交叉验证。
   * H4-4 检查的是本期增加（采购入库），对应 H4-1 借方发生额。
   *
   * 公式：diff = H4-4增加合计 - H4-1借方发生合计
   * isMatch: |diff| < 0.01
   *
   * 注意：H4-4 通常为抽样检查，合计可能 ≤ H4-1 借方合计。
   * 但若已全量检查则应一致。此处给出差异供审计人员判断。
   */
  const additionVsAdjudication: ComputedRef<CrossSheetCheck> = computed(() => {
    const addTotal = additionTotal.value
    const debitTotal = adjudicationTotals.value.debitTotal
    return _checkMatch(addTotal - debitTotal)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. disposalVsAdjudication — H4-5减少合计 vs H4-1贷方发生合计（Req 3.5）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * H4-5 减少检查表金额合计 与 H4-1 贷方发生合计 的交叉验证。
   * H4-5 检查的是本期减少（领用/退货/报废），对应 H4-1 贷方发生额。
   *
   * 公式：diff = H4-5减少合计 - H4-1贷方发生合计
   * isMatch: |diff| < 0.01
   */
  const disposalVsAdjudication: ComputedRef<CrossSheetCheck> = computed(() => {
    const dispTotal = disposalTotal.value
    const creditTotal = adjudicationTotals.value.creditTotal
    return _checkMatch(dispTotal - creditTotal)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. disclosureAutoFill — H4-1 → 附注自动取数
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * 从 H4-1 审定表聚合数据供附注披露自动填充：
   * - disc_audited: 审定数合计（科目1605期末净值）
   * - disc_begin / disc_end: 期初/期末审定净值
   * - disc_debit / disc_credit: 本期增减（来自 H4-2 汇总）
   * - disc_detail_total / disc_addition_total / disc_disposal_total
   * - disc_significant_count: 净值变动≥30% 分类数
   * - disc_significant_change: 重大变动额合计
   */
  const disclosureAutoFill: ComputedRef<Record<string, number>> = computed(() => {
    const adj = adjudicationTotals.value
    const sigCount = _getResponseNum(allResponses.value, 'H4-1-significant-change-count')
    let sigChange = 0
    const sigRaw = allResponses.value.get('H4-1-significant-changes')?.remark
    if (sigRaw) {
      try {
        const arr = typeof sigRaw === 'string' ? JSON.parse(sigRaw) : sigRaw
        if (Array.isArray(arr)) {
          for (const it of arr) sigChange += Number(it.auditedChange) || 0
        }
      } catch { /* ignore */ }
    }
    return {
      disc_audited: adj.adjudicatedTotal,
      disc_begin: adj.beginTotal,
      disc_end: adj.endTotal,
      disc_debit: adj.debitTotal,
      disc_credit: adj.creditTotal,
      disc_detail_total: detailTotal.value,
      disc_addition_total: additionTotal.value,
      disc_disposal_total: disposalTotal.value,
      disc_significant_count: sigCount,
      disc_significant_change: Math.round(sigChange * 100) / 100,
    }
  })

  /** 重大变动明细列表（附注说明可直接引用） */
  const significantChanges = computed(() => {
    const raw = allResponses.value.get('H4-1-significant-changes')?.remark
    if (!raw) return [] as Array<{
      name: string
      beginAudited: number
      endAudited: number
      auditedChange: number
      auditedChangeRate: number | null
    }>
    try {
      const arr = typeof raw === 'string' ? JSON.parse(raw) : raw
      return Array.isArray(arr) ? arr : []
    } catch {
      return []
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 5. adjustmentSync — H4-3 AJE/RJE → H4-1
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * 从 H4-3 汇总：
   * - emAjeNet/emRjeNet：1605 非减值行借−贷，回写原值段 AJE/RJE
   * - impairAjeNet/impairRjeNet：1605 减值行 −(借−贷)，回写减值段（贷方补提为正）
   */
  const adjustmentSync: ComputedRef<H4AdjustmentSync> = computed(() => {
    const resp = allResponses.value.get('H4-3-rows')
    const adjRows = safeParseRows<Record<string, any>>(resp?.remark)
    let totalAje = 0
    let totalRje = 0
    let emAjeNet = 0
    let emRjeNet = 0
    let impairAjeNet = 0
    let impairRjeNet = 0

    for (const row of adjRows) {
      const debit = _getNum(row.debitAmount ?? row.debit)
      const credit = _getNum(row.creditAmount ?? row.credit)
      const netAmount = debit - credit
      const cat = String(row.category || '').trim()
      const isRje = cat === '报表调整' || row.entryType === 'RJE'
      const code = String(row.accountCode || '')
      const isEm = code === '1605' || code.startsWith('1605')
      const blob = `${row.accountName || ''}${row.description || ''}${row.reportItem || ''}`
      const isImpair = /减值/.test(blob)

      if (isRje) {
        totalRje += netAmount
        if (isEm) {
          if (isImpair) impairRjeNet += -netAmount
          else emRjeNet += netAmount
        }
      } else {
        totalAje += netAmount
        if (isEm) {
          if (isImpair) impairAjeNet += -netAmount
          else emAjeNet += netAmount
        }
      }
    }

    return {
      totalAje,
      totalRje,
      emAjeNet,
      emRjeNet,
      impairAjeNet,
      impairRjeNet,
      rowCount: adjRows.length,
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Return
  // ═══════════════════════════════════════════════════════════════════════════

  return {
    // H4-1审定合计 vs H4-2明细合计（Req 2.7）
    adjudicationVsDetail,
    // H4-4增加合计 vs H4-1借方发生合计（Req 3.5）
    additionVsAdjudication,
    // H4-5减少合计 vs H4-1贷方发生合计（Req 3.5）
    disposalVsAdjudication,
    // H4-1 → 附注自动取数
    disclosureAutoFill,
    significantChanges,
    // H4-3 → H4-1
    adjustmentSync,
    // 中间computed（供子组件直接使用）
    adjudicationTotals,
    detailTotal,
    additionTotal,
    disposalTotal,
  }
}

export default useH4CrossSheet
