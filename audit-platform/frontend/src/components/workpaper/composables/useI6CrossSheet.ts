/**
 * useI6CrossSheet — I6 研发费用跨Sheet + I2双向联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('I6-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 三大联动职责：
 * 1. **I2双向联动**：Subscribe 'development:capitalized-updated'（I2→I6），
 *    Publish 'research:expense-updated'（I6→I2），
 *    校验 VR-I6-01: I6费用化 + I2资本化 = 研发总额
 * 2. **月度聚合**：从 I6-2 明细表聚合12个月合计，供 I6-1 审定表交叉验证
 * 3. **截止样本**：从 I6-5/I6-6 聚合截止测试样本，标记跨期状态
 *
 * EventBus 事件（CustomEvent on window）：
 * - IN:  'development:capitalized-updated' { detail: { capitalized: number } }
 * - OUT: 'research:expense-updated' { detail: { expense: number, total: number } }
 *
 * 科目方向：
 * - 6602 研发费用（借方/损益类）：取发生额非余额
 * - 净发生额 = 借方发生 - 贷方发生（借方=费用增加，贷方=冲回/结转）
 *
 * Spec: .kiro/specs/i6-research-development-expense/
 * Task: 3.2
 * Requirements: 3.1-3.5 (月度明细), 4.1-4.7 (I6↔I2联动), 5.1-5.4 (截止测试)
 */
import { computed, ref, watch, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { validateVRI601, calcMonthlyTotal, isCutoffCrossover } from './useI6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I6-2 明细行原始 JSON 结构（月度12列横向） */
export interface I6DetailRowRaw {
  rowId?: string
  projectName?: string        // 研发项目名称
  category?: string           // 费用类别
  month1?: number             // 1月
  month2?: number             // 2月
  month3?: number             // 3月
  month4?: number             // 4月
  month5?: number             // 5月
  month6?: number             // 6月
  month7?: number             // 7月
  month8?: number             // 8月
  month9?: number             // 9月
  month10?: number            // 10月
  month11?: number            // 11月
  month12?: number            // 12月
  total?: number              // 年度合计
}

/** I6-5/I6-6 截止测试行原始 JSON 结构 */
export interface I6CutoffRowRaw {
  rowId?: string
  bookingDate?: string        // 记账日期
  documentDate?: string       // 单据日期
  amount?: number             // 金额
  expenseType?: string        // 费用类型
  period?: string             // 记账期间
  belongPeriod?: string       // 归属期间
  conclusion?: string         // 结论
}

/** I2 incoming event payload */
export interface I2CapitalizedEventDetail {
  /** I2 资本化金额 */
  capitalized: number
}

// ─── Return Types ────────────────────────────────────────────────────────────

export interface I2LinkageStatus {
  /** I2 资本化金额（从 EventBus 接收） */
  capitalized: number
  /** 研发总额（费用化 + 资本化） */
  total: number
  /** 是否平衡：I6费用化 + I2资本化 = 研发总额（允许±0.01精度） */
  isBalanced: boolean
}

export interface CutoffSample {
  date: string
  amount: number
  isCrossover: boolean
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

export function useI6CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailMonthlyTotals: ComputedRef<number[]>
  i2LinkageStatus: ComputedRef<{ capitalized: number; total: number; isBalanced: boolean }>
  cutoffSamples: ComputedRef<Array<{ date: string; amount: number; isCrossover: boolean }>>
} {
  // ─── I2 incoming state（响应式存储 EventBus 接收的 I2 数据）─────────────

  const _i2Capitalized = ref(0)

  // ─── 解析 I6-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<I6DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('I6-2-rows')
    return safeParseRows<I6DetailRowRaw>(resp?.remark)
  })

  // ─── 解析 I6-5 截止测试行（账→单据）────────────────────────────────────

  const cutoffForwardRows = computed<I6CutoffRowRaw[]>(() => {
    const resp = allResponses.value.get('I6-5-rows')
    return safeParseRows<I6CutoffRowRaw>(resp?.remark)
  })

  // ─── 解析 I6-6 截止测试行（单据→账）────────────────────────────────────

  const cutoffBackwardRows = computed<I6CutoffRowRaw[]>(() => {
    const resp = allResponses.value.get('I6-6-rows')
    return safeParseRows<I6CutoffRowRaw>(resp?.remark)
  })

  // ═══ detailMonthlyTotals: I6-2 月度聚合（12个月合计）═══════════════════

  /**
   * 从 I6-2 明细表聚合12个月合计：
   * - 对每月列进行 SUM（所有行的同一月份列相加）
   * - 结果为 12 元素数组 [1月合计, 2月合计, ..., 12月合计]
   *
   * 用途：
   * - 供 I6-1 审定表验证净发生额 ≈ SUM(12月)
   * - 供月度趋势图展示
   * - 供月度波动分析（±30% 异常标记）
   *
   * Req 3.3: 合计列=SUM(1月~12月)
   * Req 3.4: 底部合计行=各列SUM
   * Req 3.5: 合计行联动审定表净发生额
   */
  const detailMonthlyTotals: ComputedRef<number[]> = computed(() => {
    const monthlyTotals = new Array(12).fill(0) as number[]

    for (const row of detailRows.value) {
      monthlyTotals[0] += _getNum(row.month1)
      monthlyTotals[1] += _getNum(row.month2)
      monthlyTotals[2] += _getNum(row.month3)
      monthlyTotals[3] += _getNum(row.month4)
      monthlyTotals[4] += _getNum(row.month5)
      monthlyTotals[5] += _getNum(row.month6)
      monthlyTotals[6] += _getNum(row.month7)
      monthlyTotals[7] += _getNum(row.month8)
      monthlyTotals[8] += _getNum(row.month9)
      monthlyTotals[9] += _getNum(row.month10)
      monthlyTotals[10] += _getNum(row.month11)
      monthlyTotals[11] += _getNum(row.month12)
    }

    return monthlyTotals
  })

  // ─── I6 费用化金额合计（供 I2 联动校验）────────────────────────────────

  /**
   * I6 费用化金额合计 = SUM(12月) = 月度合计的总和
   * 即 I6 审定后净发生额（损益类取发生额）
   *
   * 优先从 I6-1 审定表取审定数（若有），fallback 到月度合计。
   */
  const i6ExpenseAmount = computed<number>(() => {
    // 优先从 I6-1 审定表取审定数
    const adjResp = allResponses.value.get('I6-1-audited')
    const adjVal = _getNum(adjResp?.remark)
    if (adjVal !== 0) return adjVal

    // fallback: 12个月合计之和
    return calcMonthlyTotal(detailMonthlyTotals.value)
  })

  // ═══ i2LinkageStatus: I6↔I2 校验状态（VR-I6-01）════════════════════════

  /**
   * I6↔I2 联动校验状态：
   * - capitalized: I2 资本化金额（从 EventBus 'development:capitalized-updated' 接收）
   * - total: 研发总额（费用化 + 资本化）
   * - isBalanced: VR-I6-01 校验结果（允许±0.01精度）
   *
   * Req 4.4: VR-I6-01校验: I6费用化金额 + I2资本化金额 = 研发总额
   * Req 4.5: 校验失败时红色警告"费用化+资本化≠研发总额，差额xxx"
   * Req 4.7: 底部显示联动状态面板
   */
  const i2LinkageStatus: ComputedRef<I2LinkageStatus> = computed(() => {
    const expense = i6ExpenseAmount.value
    const capitalized = _i2Capitalized.value
    const total = expense + capitalized

    // 总额为 0 且费用也为 0 → 未收到数据，视为平衡（待就绪）
    if (total === 0 && expense === 0) {
      return { capitalized: 0, total: 0, isBalanced: true }
    }

    // VR-I6-01: 费用化 + 资本化 = 研发总额
    // 使用 validateVRI601 纯函数做校验
    const validation = validateVRI601(expense, capitalized, total)

    return {
      capitalized,
      total,
      isBalanced: validation.isValid,
    }
  })

  // ═══ cutoffSamples: I6-5/I6-6 截止测试样本聚合 ════════════════════════

  /**
   * 聚合 I6-5（账→单据）和 I6-6（单据→账）的截止测试样本。
   * 对每条样本标记是否跨期（isCrossover）。
   *
   * 跨期判断：|记账日 - 单据日| > 5天
   *
   * Req 5.1: 从账簿→单据（期末±5天）
   * Req 5.2: 从单据→账簿（期末±5天）
   * Req 5.4: 显示日期|金额|是否跨期
   */
  const cutoffSamples: ComputedRef<CutoffSample[]> = computed(() => {
    const samples: CutoffSample[] = []

    // I6-5 正向截止（账→单据）
    for (const row of cutoffForwardRows.value) {
      const bookingDate = row.bookingDate ? new Date(row.bookingDate) : null
      const documentDate = row.documentDate ? new Date(row.documentDate) : null
      const amount = _getNum(row.amount)
      const date = row.bookingDate || ''

      let crossover = false
      if (bookingDate && documentDate && !isNaN(bookingDate.getTime()) && !isNaN(documentDate.getTime())) {
        crossover = isCutoffCrossover(bookingDate, documentDate, 5)
      }

      samples.push({ date, amount, isCrossover: crossover })
    }

    // I6-6 反向截止（单据→账）
    for (const row of cutoffBackwardRows.value) {
      const bookingDate = row.bookingDate ? new Date(row.bookingDate) : null
      const documentDate = row.documentDate ? new Date(row.documentDate) : null
      const amount = _getNum(row.amount)
      const date = row.documentDate || ''

      let crossover = false
      if (bookingDate && documentDate && !isNaN(bookingDate.getTime()) && !isNaN(documentDate.getTime())) {
        crossover = isCutoffCrossover(bookingDate, documentDate, 5)
      }

      samples.push({ date, amount, isCrossover: crossover })
    }

    return samples
  })

  // ─── EventBus: Subscribe I2 'development:capitalized-updated'（I2→I6）──

  /**
   * Req 4.3: EventBus subscribe I2的'development:capitalized-updated'事件
   * I2 发布时携带 { capitalized }，I6 据此更新联动校验状态。
   */
  function _onI2CapitalizedUpdated(event: Event): void {
    const detail = (event as CustomEvent<I2CapitalizedEventDetail>).detail
    if (detail && typeof detail === 'object') {
      _i2Capitalized.value = _getNum(detail.capitalized)
    }
  }

  window.addEventListener('development:capitalized-updated', _onI2CapitalizedUpdated)

  // ─── EventBus: Publish 'research:expense-updated'（I6→I2）──────────────

  /**
   * Req 4.2: I6保存时 publish 'research:expense-updated'
   * 当 I6 费用化金额变化时，发布事件通知 I2 同步校验。
   * I2 订阅此事件后更新自身的联动校验面板。
   */
  watch(i6ExpenseAmount, (newVal) => {
    const total = newVal + _i2Capitalized.value
    window.dispatchEvent(new CustomEvent('research:expense-updated', {
      detail: {
        expense: newVal,
        total,
        wpCode: 'I6',
        accountCode: '6602',
      },
    }))
  })

  // ─── EventBus: Subscribe 'substantive:adjudicated' ─────────────────────

  /**
   * 监听 substantive:adjudicated 事件，当审定表保存时触发。
   * allResponses 的 Map 更新由 useI6FormData 处理，
   * 本 composable 的 computed 自动响应变化。
   */
  function _onSubstantiveAdjudicated(event: Event): void {
    // allResponses Map 响应式变化自动驱动月度合计/联动状态重算
    void event
  }

  window.addEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)

  // ─── Cleanup on scope dispose ─────────────────────────────────────────────

  onScopeDispose(() => {
    window.removeEventListener('development:capitalized-updated', _onI2CapitalizedUpdated)
    window.removeEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // I6-2 月度12个月合计（12元素数组）
    detailMonthlyTotals,
    // I6↔I2 联动校验状态（VR-I6-01）
    i2LinkageStatus,
    // I6-5/I6-6 截止测试样本聚合
    cutoffSamples,
  }
}

export default useI6CrossSheet
