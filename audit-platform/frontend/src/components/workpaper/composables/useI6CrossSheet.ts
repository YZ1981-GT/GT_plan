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
import { validateVRI601, calcMonthlyTotal } from './useI6FormulaEngine'
import { isCutoffPeriodCrossing } from './useI2FormulaEngine'

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

/** I6-5/I6-6 截止测试行原始 JSON 结构（兼容新旧字段） */
export interface I6CutoffRowRaw {
  rowId?: string
  recordDate?: string
  bookingDate?: string
  documentDate?: string
  amount?: number
  documentAmount?: number
  expenseType?: string
  description?: string
  period?: string
  recordPeriod?: string
  belongPeriod?: string
  isCrossPeriod?: boolean
  conclusion?: string
}

/** I2 incoming event payload */
export interface I2CapitalizedEventDetail {
  /** I2 资本化金额 */
  capitalized?: number
  /** 兼容 useI6Adjudication 旧字段名 */
  capitalizedAmount?: number
  /** I2 侧认定的研发总额（优先作为 VR-I6-01 期望值） */
  total?: number
}

// ─── Return Types ────────────────────────────────────────────────────────────

export interface I2LinkageStatus {
  /** I6 费用化金额（审定发生额） */
  expense: number
  /** I2 资本化金额（从 EventBus 接收） */
  capitalized: number
  /** 实际合计（费用化 + 资本化） */
  total: number
  /** VR-I6-01 期望值（手工 / I2 事件 / 回退为 actual） */
  expectedTotal: number
  /** 是否已收到 I2 资本化数据（或从持久化恢复） */
  ready: boolean
  /** 是否平衡：I6费用化 + I2资本化 = 研发总额（允许±0.01精度） */
  isBalanced: boolean
  /** 差额（正=超出，负=不足） */
  difference: number
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
  i2LinkageStatus: ComputedRef<I2LinkageStatus>
  cutoffSamples: ComputedRef<Array<{ date: string; amount: number; isCrossover: boolean }>>
} {
  // ─── I2 incoming state（响应式存储 EventBus 接收的 I2 数据）─────────────

  const _i2Capitalized = ref(0)
  const _i2PublishedTotal = ref(0)
  const _expectedResearchTotal = ref(0)
  const _i2Ready = ref(false)

  // ─── 解析 I6-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<I6DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('I6-2-detail-rows') ?? allResponses.value.get('I6-2-rows')
    const raw = resp?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed.map((r: any) => {
        if (Array.isArray(r.months)) {
          const m = r.months
          return {
            category: r.category ?? r.name ?? r.projectName,
            month1: _getNum(m[0]), month2: _getNum(m[1]), month3: _getNum(m[2]),
            month4: _getNum(m[3]), month5: _getNum(m[4]), month6: _getNum(m[5]),
            month7: _getNum(m[6]), month8: _getNum(m[7]), month9: _getNum(m[8]),
            month10: _getNum(m[9]), month11: _getNum(m[10]), month12: _getNum(m[11]),
            total: _getNum(r.unadjTotal ?? r.total ?? calcMonthlyTotal(m)),
          }
        }
        return r as I6DetailRowRaw
      })
    } catch {
      return []
    }
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
    const adjResp = allResponses.value.get('I6-adj-audited-total')
      ?? allResponses.value.get('I6-1-audited')
    const adjVal = _getNum(adjResp?.remark)
    if (adjVal !== 0) return adjVal

    // fallback: 12个月合计之和
    return calcMonthlyTotal(detailMonthlyTotals.value)
  })

  function _hydrateLinkageFromResponses(): void {
    const capResp = allResponses.value.get('I6-adj-capitalized-i2')
    if (capResp?.remark != null && capResp.remark !== '') {
      _i2Capitalized.value = _getNum(capResp.remark)
      _i2Ready.value = true
    }
    const expectedResp = allResponses.value.get('I6-adj-expected-total')
    if (expectedResp?.remark != null && expectedResp.remark !== '') {
      _expectedResearchTotal.value = _getNum(expectedResp.remark)
    }
  }

  watch(allResponses, () => {
    _hydrateLinkageFromResponses()
  }, { immediate: true, deep: true })

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
    const actualTotal = expense + capitalized

    if (!_i2Ready.value) {
      return {
        expense,
        capitalized,
        total: actualTotal,
        expectedTotal: 0,
        ready: false,
        isBalanced: false,
        difference: 0,
      }
    }

    const expectedTotal = _expectedResearchTotal.value
      || _i2PublishedTotal.value
      || actualTotal
    const validation = validateVRI601(expense, capitalized, expectedTotal)

    return {
      expense,
      capitalized,
      total: actualTotal,
      expectedTotal,
      ready: true,
      isBalanced: validation.isValid,
      difference: validation.difference,
    }
  })

  // ═══ cutoffSamples: I6-5/I6-6 截止测试样本聚合 ════════════════════════

  /**
   * 聚合 I6-5（账→单据）和 I6-6（单据→账）的截止测试样本。
   * 跨期判断：单据日与记账日分处截止日两侧；无截止日则降级为记账期间≠归属期间。
   */
  const cutoffSamples: ComputedRef<CutoffSample[]> = computed(() => {
    const samples: CutoffSample[] = []
    const criteriaRaw = allResponses.value.get('I6-5-sample-criteria')?.remark
      ?? allResponses.value.get('I6-6-sample-criteria')?.remark
    let cutoffDateStr = ''
    try {
      const parsed = typeof criteriaRaw === 'string' ? JSON.parse(criteriaRaw) : criteriaRaw
      cutoffDateStr = String(parsed?.cutoffDate ?? '')
    } catch { /* ignore */ }
    const cutoffDate = cutoffDateStr ? new Date(`${cutoffDateStr}T00:00:00`) : null

    function _crossover(row: I6CutoffRowRaw): boolean {
      if (row.isCrossPeriod != null) return Boolean(row.isCrossPeriod)
      const rec = row.recordDate ?? row.bookingDate ?? ''
      const doc = row.documentDate ?? ''
      const rd = rec ? new Date(`${rec}T00:00:00`) : null
      const dd = doc ? new Date(`${doc}T00:00:00`) : null
      if (rd && dd && cutoffDate && !Number.isNaN(rd.getTime()) && !Number.isNaN(dd.getTime())) {
        return isCutoffPeriodCrossing(dd, rd, cutoffDate)
      }
      const rp = row.recordPeriod ?? row.period ?? ''
      const bp = row.belongPeriod ?? ''
      return !!(rp && bp && rp !== bp)
    }

    for (const row of cutoffForwardRows.value) {
      samples.push({
        date: row.recordDate ?? row.bookingDate ?? '',
        amount: _getNum(row.amount ?? row.documentAmount),
        isCrossover: _crossover(row),
      })
    }

    for (const row of cutoffBackwardRows.value) {
      samples.push({
        date: row.documentDate ?? '',
        amount: _getNum(row.documentAmount ?? row.amount),
        isCrossover: _crossover(row),
      })
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
      const cap = detail.capitalized ?? detail.capitalizedAmount
      if (cap != null) {
        _i2Capitalized.value = _getNum(cap)
        _i2Ready.value = true
      }
      if (detail.total != null) {
        _i2PublishedTotal.value = _getNum(detail.total)
      }
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
