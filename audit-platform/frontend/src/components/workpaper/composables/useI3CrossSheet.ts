/**
 * useI3CrossSheet — I3 商誉跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('I3-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射（数据流图）：
 * - I3-2 明细表 → 按CGU聚合 → I3-1 审定表（商誉原值/减值/净额小计）
 * - I3-3 调整分录 → AJE/RJE → I3-1 审定表
 * - I3-6 减值测试 → 按CGU减值金额 → I3-1 审定表"本期减少(减值)"
 * - I3-7 DCF测试 → 可收回金额 → I3-6 减值测试
 * - I3-8 复核过程 → 公司测试评价 → I3-6 辅助判断
 * - I3-4 入账测算 → 初始确认 → I3-2 明细表
 * - I3-1 审定表 → 审定数回写 → TB 1711
 * - I3-1 + I3-6 → 附注披露（审定数 + 减值明细）
 *
 * 科目方向：
 * - 1711 商誉（借方/资产类）：期末=期初+借-贷
 * - 商誉不摊销！仅年度减值测试（期末=期初+新并购-减值）
 * - 商誉减值不可转回
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Task: 3.2
 * Requirements: 2.1-2.8, 3.3, 5.1-5.5, 9.2-9.3, 10.1-10.2
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I3-2 明细行原始 JSON 结构（30列3区段） */
export interface I3DetailRowRaw {
  rowId?: string
  investee?: string             // 被投资单位名称
  acquisitionDate?: string      // 并购日期
  consideration?: number        // 对价

  // 入账区段
  mergerCost?: number           // 合并成本
  netAssetFairValue?: number    // 可辨认净资产公允价值
  goodwillOriginal?: number     // 商誉原值(=合并成本-净资产公允)

  // 减值区段
  accImpairmentBegin?: number   // 累计减值期初
  currentImpairment?: number    // 本期减值
  accImpairmentEnd?: number     // 累计减值期末
  netValueEnd?: number          // 期末净额(=原值-累计减值)

  // CGU分配
  cguName?: string              // 所属资产组(CGU)名称
}

/** I3-3 调整分录行原始 JSON 结构 */
export interface I3AdjustmentRowRaw {
  rowId?: string
  description?: string          // 调整事项
  entryType?: string            // AJE / RJE
  accountCode?: string          // 科目代码
  accountName?: string          // 科目名称
  summary?: string              // 摘要
  debitAmount?: number          // 借方
  creditAmount?: number         // 贷方
  indexRef?: string             // 索引
  remark?: string
}

/** I3-6 减值测试行原始 JSON 结构（按CGU） */
export interface I3ImpairmentTestRowRaw {
  rowId?: string
  cguName?: string              // 资产组(CGU)名称
  goodwillAmount?: number       // 包含商誉金额
  cguBookValue?: number         // 资产组账面(含商誉)
  recoverableAmount?: number    // 可收回金额(来自I3-7 DCF)
  impairmentAmount?: number     // 减值金额 = MAX(账面-可收回, 0)
  goodwillImpairment?: number   // 商誉分摊减值(先冲商誉)
  otherAssetImpairment?: number // 其他资产分摊减值
}

/** I3-7 DCF可收回金额测试结果 */
export interface I3RecoverableResultRaw {
  rowId?: string
  cguName?: string              // 资产组(CGU)名称
  fairValueLessDisposal?: number // 公允价值-处置费用
  valueInUse?: number           // 使用价值(DCF)
  recoverableAmount?: number    // 可收回金额=MAX(公允-处置, DCF)
}

/** I3-4 入账测算结果 */
export interface I3InitialValueRowRaw {
  rowId?: string
  investee?: string             // 被投资单位
  mergerCost?: number           // 合并成本
  netAssetFairValue?: number    // 可辨认净资产公允价值份额
  goodwillAmount?: number       // 商誉=合并成本-净资产公允
}

// ─── Return Types ────────────────────────────────────────────────────────────

/** I3-2 明细合计 → I3-1 审定表交叉验证 */
export interface I3DetailTotals {
  goodwillOriginalTotal: number   // 商誉原值合计
  accImpairmentTotal: number      // 累计减值合计
  netValueTotal: number           // 期末净额合计
  currentImpairmentTotal: number  // 本期减值合计
  byCgu: Record<string, {         // 按CGU聚合
    goodwillOriginal: number
    accImpairment: number
    netValue: number
    currentImpairment: number
  }>
}

/** I3-6 减值测试结果 → I3-1 审定表 */
export interface I3ImpairmentResult {
  totalImpairment: number         // 本期减值总额（所有CGU）
  byCgu: Record<string, {
    impairmentAmount: number       // 减值金额
    goodwillImpairment: number     // 商誉承担
    otherImpairment: number        // 其他资产承担
    recoverableAmount: number      // 可收回金额
  }>
}

/** I3-3 调整分录 → I3-1 审定表 AJE/RJE */
export interface I3AdjustmentSync {
  totalAje: number                // AJE调整净额
  totalRje: number                // RJE重分类净额
}

/** 附注披露自动取数 */
export interface I3DisclosureData {
  [key: string]: number
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

export function useI3CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailTotals: ComputedRef<I3DetailTotals>
  impairmentResult: ComputedRef<I3ImpairmentResult>
  adjustmentSync: ComputedRef<I3AdjustmentSync>
  disclosureAutoFill: ComputedRef<I3DisclosureData>
  recoverableByCgu: ComputedRef<Record<string, number>>
  initialValueRows: ComputedRef<I3InitialValueRowRaw[]>
} {
  // ─── 解析 I3-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<I3DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('I3-2-rows')
    return safeParseRows<I3DetailRowRaw>(resp?.remark)
  })

  // ─── 解析 I3-3 调整分录行数据 ──────────────────────────────────────────

  const adjustmentRows = computed<I3AdjustmentRowRaw[]>(() => {
    const resp = allResponses.value.get('I3-3-rows')
    return safeParseRows<I3AdjustmentRowRaw>(resp?.remark)
  })

  // ─── 解析 I3-6 减值测试行数据 ──────────────────────────────────────────

  const impairmentTestRows = computed<I3ImpairmentTestRowRaw[]>(() => {
    const resp = allResponses.value.get('I3-6-rows')
    return safeParseRows<I3ImpairmentTestRowRaw>(resp?.remark)
  })

  // ─── 解析 I3-7 DCF可收回金额结果 ──────────────────────────────────────

  const recoverableRows = computed<I3RecoverableResultRaw[]>(() => {
    const resp = allResponses.value.get('I3-7-rows')
    return safeParseRows<I3RecoverableResultRaw>(resp?.remark)
  })

  // ─── 解析 I3-4 入账测算行数据 ──────────────────────────────────────────

  const initialValueRows = computed<I3InitialValueRowRaw[]>(() => {
    const resp = allResponses.value.get('I3-4-rows')
    return safeParseRows<I3InitialValueRowRaw>(resp?.remark)
  })

  // ═══ aggregateDetailTotals: I3-2 明细 → 按CGU聚合 → I3-1 审定（Req 3.3）══

  /**
   * 从 I3-2 明细行聚合商誉合计+按CGU分组：
   * - goodwillOriginalTotal: 所有行商誉原值合计
   * - accImpairmentTotal: 所有行累计减值合计
   * - netValueTotal: 所有行期末净额合计
   * - currentImpairmentTotal: 所有行本期减值合计
   * - byCgu: 按CGU名称分组聚合
   *
   * 用于与 I3-1 审定表小计交叉验证。
   * 商誉特殊：无摊销项，净额=原值-累计减值。
   */
  const detailTotals: ComputedRef<I3DetailTotals> = computed(() => {
    let goodwillOriginalTotal = 0
    let accImpairmentTotal = 0
    let netValueTotal = 0
    let currentImpairmentTotal = 0
    const byCgu: Record<string, { goodwillOriginal: number; accImpairment: number; netValue: number; currentImpairment: number }> = {}

    for (const row of detailRows.value) {
      const original = _getNum(row.goodwillOriginal)
      const accImp = _getNum(row.accImpairmentEnd)
      const netVal = _getNum(row.netValueEnd)
      const curImp = _getNum(row.currentImpairment)

      goodwillOriginalTotal += original
      accImpairmentTotal += accImp
      netValueTotal += netVal
      currentImpairmentTotal += curImp

      // 按CGU聚合
      const cgu = row.cguName || '未分配CGU'
      if (!byCgu[cgu]) {
        byCgu[cgu] = { goodwillOriginal: 0, accImpairment: 0, netValue: 0, currentImpairment: 0 }
      }
      byCgu[cgu].goodwillOriginal += original
      byCgu[cgu].accImpairment += accImp
      byCgu[cgu].netValue += netVal
      byCgu[cgu].currentImpairment += curImp
    }

    return { goodwillOriginalTotal, accImpairmentTotal, netValueTotal, currentImpairmentTotal, byCgu }
  })

  // ═══ getImpairmentFromTest: I3-6/I3-7 → I3-1 减值列（Req 5.1-5.5）════

  /**
   * 从 I3-6 减值测试结果聚合本期减值金额（按CGU），供 I3-1 审定表"本期减少(减值)"列：
   * - totalImpairment: 所有CGU本期减值总额
   * - byCgu: 每个CGU的减值详情（减值金额/商誉承担/其他资产承担/可收回金额）
   *
   * 联动关系：
   * - I3-7 DCF结果 → I3-6 可收回金额列
   * - I3-6 减值金额 = MAX(资产组账面 - 可收回金额, 0)
   * - I3-6 分摊规则：先冲商誉（至零为止），剩余按比例分摊
   * - I3-6 减值总额 → I3-1 "本期减少(减值)"列
   */
  const impairmentResult: ComputedRef<I3ImpairmentResult> = computed(() => {
    let totalImpairment = 0
    const byCgu: Record<string, { impairmentAmount: number; goodwillImpairment: number; otherImpairment: number; recoverableAmount: number }> = {}

    for (const row of impairmentTestRows.value) {
      const cgu = row.cguName || '未命名CGU'
      const impairment = _getNum(row.impairmentAmount)
      const gwImpairment = _getNum(row.goodwillImpairment)
      const otherImpairment = _getNum(row.otherAssetImpairment)
      const recoverable = _getNum(row.recoverableAmount)

      totalImpairment += gwImpairment  // 商誉承担的减值才流入I3-1

      byCgu[cgu] = {
        impairmentAmount: impairment,
        goodwillImpairment: gwImpairment,
        otherImpairment,
        recoverableAmount: recoverable,
      }
    }

    return { totalImpairment, byCgu }
  })

  // ═══ recoverableByCgu: I3-7 DCF → I3-6 可收回金额（Req 6.4）══════════

  /**
   * 从 I3-7 可收回金额测试结果按CGU映射，供 I3-6 减值测试"可收回金额"列读取：
   * { 'CGU-A': 12000000, 'CGU-B': 8500000, ... }
   *
   * I3-7 每行的 recoverableAmount = MAX(公允价值-处置费用, DCF使用价值)
   */
  const recoverableByCgu: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {}

    for (const row of recoverableRows.value) {
      const cgu = row.cguName || '未命名CGU'
      result[cgu] = _getNum(row.recoverableAmount)
    }

    return result
  })

  // ═══ getAjeRjeFromAdjustment: I3-3 → I3-1 AJE/RJE（Req 10.1-10.2）════

  /**
   * 从 I3-3 调整分录汇总 AJE/RJE 合计金额，同步到 I3-1 审定表对应列：
   * - totalAje: 所有类型=AJE分录的净额（借方-贷方）之和
   * - totalRje: 所有类型=RJE分录的净额之和
   *
   * 科目方向（1711商誉为借方/资产类）：
   * - 借方增加 → 净额正数 → 审定数增加
   * - 贷方减少(减值) → 净额负数 → 审定数减少
   */
  const adjustmentSync: ComputedRef<I3AdjustmentSync> = computed(() => {
    let totalAje = 0
    let totalRje = 0

    for (const row of adjustmentRows.value) {
      const debit = _getNum(row.debitAmount)
      const credit = _getNum(row.creditAmount)
      // 资产类借方科目：净额 = 借方 - 贷方
      const netAmount = debit - credit

      if (row.entryType === 'AJE') {
        totalAje += netAmount
      } else if (row.entryType === 'RJE') {
        totalRje += netAmount
      }
    }

    return { totalAje, totalRje }
  })

  // ═══ publishAuditedToDisclosure: I3-1 + I3-6 → 附注（Req 9.2-9.3）════

  /**
   * 附注披露自动取数，从多个 sheet 聚合数据供附注上市/国企引用：
   *
   * 第(1)子节 — 商誉账面价值（从I3-2明细聚合）：
   * - disc_goodwill_original: 商誉原值合计
   * - disc_goodwill_impairment: 累计减值合计
   * - disc_goodwill_net: 净额合计（原值-累计减值，无摊销！）
   * - disc_goodwill_current_impairment: 本期减值合计
   *
   * 第(2)子节 — 减值测试明细（从I3-6按CGU）：
   * - disc_cgu_count: 资产组(CGU)数量
   * - disc_total_impairment: 本期商誉减值总额
   * - disc_total_recoverable: 所有CGU可收回金额合计
   * - disc_total_book_value: 所有CGU资产组账面合计
   *
   * 第(3)子节 — 调整分录影响：
   * - disc_aje_amount: AJE调整净额
   * - disc_rje_amount: RJE重分类净额
   *
   * 第(4)子节 — 投资统计（从I3-2明细）：
   * - disc_investee_count: 被投资单位数量
   */
  const disclosureAutoFill: ComputedRef<I3DisclosureData> = computed(() => {
    const result: I3DisclosureData = {}

    // ─ 第(1)子节：从 I3-2 明细聚合商誉账面价值
    const totals = detailTotals.value
    result['disc_goodwill_original'] = totals.goodwillOriginalTotal
    result['disc_goodwill_impairment'] = totals.accImpairmentTotal
    result['disc_goodwill_net'] = totals.netValueTotal
    result['disc_goodwill_current_impairment'] = totals.currentImpairmentTotal

    // ─ 第(2)子节：从 I3-6 减值测试按CGU聚合
    const impResult = impairmentResult.value
    const cguNames = Object.keys(impResult.byCgu)
    result['disc_cgu_count'] = cguNames.length
    result['disc_total_impairment'] = impResult.totalImpairment

    let totalRecoverable = 0
    let totalBookValue = 0
    for (const row of impairmentTestRows.value) {
      totalRecoverable += _getNum(row.recoverableAmount)
      totalBookValue += _getNum(row.cguBookValue)
    }
    result['disc_total_recoverable'] = totalRecoverable
    result['disc_total_book_value'] = totalBookValue

    // ─ 第(3)子节：调整分录影响
    const adjSync = adjustmentSync.value
    result['disc_aje_amount'] = adjSync.totalAje
    result['disc_rje_amount'] = adjSync.totalRje

    // ─ 第(4)子节：投资统计
    result['disc_investee_count'] = detailRows.value.length

    return result
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // I3-2 → I3-1 明细按CGU聚合（商誉原值/减值/净额）
    detailTotals,
    // I3-6/I3-7 → I3-1 减值结果（先冲商誉再分摊）
    impairmentResult,
    // I3-3 → I3-1 AJE/RJE同步
    adjustmentSync,
    // I3-1 + I3-6 → 附注自动取数
    disclosureAutoFill,
    // I3-7 → I3-6 可收回金额按CGU映射
    recoverableByCgu,
    // I3-4 入账测算行（供I3-2初始确认引用）
    initialValueRows,
  }
}

export default useI3CrossSheet
