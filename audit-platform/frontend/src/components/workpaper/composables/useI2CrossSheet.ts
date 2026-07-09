/**
 * useI2CrossSheet — I2 开发支出跨Sheet + 跨底稿联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('I2-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 三大联动职责：
 * 1. **I6↔I2 双向联动**：Subscribe 'research:expense-updated'（I6→I2），
 *    Publish 'development:capitalized-updated'（I2→I6），
 *    校验 VR-I6-01: I6费用化 + I2资本化 = 研发总额
 * 2. **I2→I1 转入联动**：Publish 'development:capitalized-to-intangible'，
 *    转入金额 = I2-1 审定表"本期减少-转无形"列合计
 * 3. **I2-2 明细聚合**：从 I2-2 明细表聚合资本化金额/转入金额合计，
 *    供 I2-1 审定表交叉验证
 *
 * EventBus 事件（CustomEvent on window）：
 * - IN:  'research:expense-updated' { detail: { expense: number, total: number } }
 * - OUT: 'development:capitalized-updated' { detail: { capitalized: number } }
 * - OUT: 'development:capitalized-to-intangible' { detail: { amount: number, items: [...] } }
 *
 * Spec: .kiro/specs/i2-development-expenditure/
 * Task: 3.2
 * Requirements: 9.1-9.5 (I6↔I2双向联动), 11.1-11.3 (I2→I1转入)
 */
import { computed, ref, watch, onScopeDispose, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I2-2 明细行原始 JSON 结构 */
export interface I2DetailRowRaw {
  rowId?: string
  projectName?: string        // 研发项目名称
  projectCode?: string        // 项目编号
  phase?: string              // 研究/开发阶段
  capitalizeDate?: string     // 资本化起点日期
  // 本期投入
  materialInput?: number      // 材料投入
  laborInput?: number         // 人工投入
  depreciationInput?: number  // 折旧投入
  otherInput?: number         // 其他投入
  inputTotal?: number         // 投入合计
  // 资本化金额
  capitalizedBegin?: number   // 资本化期初
  capitalizedIncrease?: number // 本期资本化增加
  capitalizedDecrease?: number // 本期资本化减少
  capitalizedEnd?: number     // 资本化期末
  // 转入I1
  transferToIntangible?: number // 转入无形资产金额
  transferDate?: string        // 转入日期
  transferAssetName?: string   // 转入资产名称
}

/** I2-1 审定表行原始 JSON 结构 */
export interface I2AdjudicationRowRaw {
  rowId?: string
  projectName?: string         // 项目名称
  cipBegin?: number            // 期初余额
  increaseCapitalized?: number // 本期增加(资本化)
  decreaseTransfer?: number    // 本期减少-转无形资产
  decreaseExpense?: number     // 本期减少-转费用
  cipEnd?: number              // 期末余额
  unadjusted?: number          // 未审数
  aje?: number                 // AJE
  rje?: number                 // RJE
  audited?: number             // 审定数
  remark?: string
}

/** I6 incoming event payload */
export interface I6ExpenseEventDetail {
  /** I6 费用化金额 */
  expense: number
  /** 研发总额（费用化+资本化应=此值） */
  total: number
}

// ─── Return Types ────────────────────────────────────────────────────────────

export interface I2DetailTotals {
  /** 资本化金额期末合计（I2-2 所有行 capitalizedEnd 之和） */
  capitalized: number
  /** 转入无形资产合计（I2-2 所有行 transferToIntangible 之和） */
  transferred: number
}

export interface I6LinkageStatus {
  /** I6 费用化金额（从 EventBus 接收） */
  expense: number
  /** 研发总额 */
  total: number
  /** 是否平衡：I6费用化 + I2资本化 = 研发总额 */
  isBalanced: boolean
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

export function useI2CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailTotals: ComputedRef<{ capitalized: number; transferred: number }>
  i6LinkageStatus: ComputedRef<{ expense: number; total: number; isBalanced: boolean }>
  i1TransferAmount: ComputedRef<number>
} {
  // ─── I6 incoming state（响应式存储 EventBus 接收的 I6 数据）─────────────

  const _i6Expense = ref(0)
  const _i6Total = ref(0)

  // ─── 解析 I2-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<I2DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('I2-2-rows')
    return safeParseRows<I2DetailRowRaw>(resp?.remark)
  })

  // ─── 解析 I2-1 审定表行数据 ────────────────────────────────────────────

  const adjudicationRows = computed<I2AdjudicationRowRaw[]>(() => {
    const resp = allResponses.value.get('I2-1-rows')
    return safeParseRows<I2AdjudicationRowRaw>(resp?.remark)
  })

  // ─── detailTotals: I2-2 明细聚合（资本化金额 + 转入金额）─────────────

  /**
   * 从 I2-2 明细表聚合：
   * - capitalized: 所有行 capitalizedEnd 之和（资本化金额期末合计）
   * - transferred: 所有行 transferToIntangible 之和（转入无形资产合计）
   *
   * 用于与 I2-1 审定表交叉验证：
   * - 审定表"期末余额"合计应 ≈ detailTotals.capitalized
   * - 审定表"本期减少-转无形"合计应 = detailTotals.transferred
   */
  const detailTotals: ComputedRef<I2DetailTotals> = computed(() => {
    let capitalized = 0
    let transferred = 0

    for (const row of detailRows.value) {
      capitalized += _getNum(row.capitalizedEnd)
      transferred += _getNum(row.transferToIntangible)
    }

    return { capitalized, transferred }
  })

  // ─── i1TransferAmount: I2-1 审定表"本期减少-转无形"列合计（Req 11.3）──

  /**
   * 从 I2-1 审定表所有行的"本期减少-转无形资产"列求和。
   * 此值即为应联动转入 I1 无形资产增加检查的金额。
   *
   * CP-I2-10: 转入I1金额 = 审定表"转无形"列合计
   */
  const i1TransferAmount: ComputedRef<number> = computed(() => {
    let total = 0
    for (const row of adjudicationRows.value) {
      total += _getNum(row.decreaseTransfer)
    }
    return total
  })

  // ─── i2Capitalized: I2 资本化金额合计（供 I6 联动校验） ────────────────

  /**
   * I2 资本化金额合计：优先从 I2-1 审定表取"审定数"合计，
   * 若审定表无数据则 fallback 到 I2-2 明细的 capitalizedEnd 合计。
   */
  const i2Capitalized = computed<number>(() => {
    // 优先从 I2-1 审定表取审定数合计
    let audited = 0
    let hasAdjudication = false
    for (const row of adjudicationRows.value) {
      const val = _getNum(row.audited)
      if (val !== 0) hasAdjudication = true
      audited += val
    }
    if (hasAdjudication) return audited

    // fallback: 从 I2-1 期末余额合计
    let cipEnd = 0
    for (const row of adjudicationRows.value) {
      cipEnd += _getNum(row.cipEnd)
    }
    if (cipEnd !== 0) return cipEnd

    // 最终 fallback: I2-2 明细合计
    return detailTotals.value.capitalized
  })

  // ─── i6LinkageStatus: I6↔I2 校验状态（Req 9.3: VR-I6-01）─────────────

  /**
   * I6↔I2 联动校验状态：
   * - expense: I6 费用化金额（来自 EventBus 'research:expense-updated'）
   * - total: 研发总额（来自 EventBus or 本地计算 expense + capitalized）
   * - isBalanced: I6费用化 + I2资本化 = 研发总额（允许±0.01精度）
   *
   * Req 9.3: 校验 I6费用化金额 + I2资本化金额 = 研发总额
   * Req 9.4: 校验失败时显示红色警告"费用化+资本化≠研发总额，差额xxx"
   */
  const i6LinkageStatus: ComputedRef<I6LinkageStatus> = computed(() => {
    const expense = _i6Expense.value
    const total = _i6Total.value
    const capitalized = i2Capitalized.value

    // 总额为 0 且费用也为 0 → 未收到 I6 数据，视为平衡（待就绪）
    if (total === 0 && expense === 0) {
      return { expense: 0, total: 0, isBalanced: true }
    }

    // VR-I6-01: expense + capitalized = total（允许±0.01精度）
    const diff = Math.abs((expense + capitalized) - total)
    const isBalanced = diff <= 0.01

    return { expense, total, isBalanced }
  })

  // ─── EventBus: Subscribe I6 'research:expense-updated'（I6→I2）─────────

  /**
   * Req 9.2: EventBus subscribe I6的'research:expense-updated'事件
   * I6 发布时携带 { expense, total }，I2 据此更新联动校验状态。
   */
  function _onI6ExpenseUpdated(event: Event): void {
    const detail = (event as CustomEvent<I6ExpenseEventDetail>).detail
    if (detail && typeof detail === 'object') {
      _i6Expense.value = _getNum(detail.expense)
      _i6Total.value = _getNum(detail.total)
    }
  }

  window.addEventListener('research:expense-updated', _onI6ExpenseUpdated)

  // ─── EventBus: Publish 'development:capitalized-updated'（I2→I6）───────

  /**
   * 当 I2 资本化金额变化时，发布事件通知 I6 同步校验。
   * I6 订阅此事件后更新自身的联动校验面板。
   */
  watch(i2Capitalized, (newVal) => {
    window.dispatchEvent(new CustomEvent('development:capitalized-updated', {
      detail: { capitalized: newVal },
    }))
  })

  // ─── EventBus: Publish 'development:capitalized-to-intangible'（I2→I1）─

  /**
   * Req 11.1: 通过EventBus发布'development:capitalized-to-intangible'
   * 当转入金额变化时通知 I1 无形资产增加检查表。
   *
   * Req 11.3: 转入金额 = I2审定表"本期减少-转无形"列合计
   */
  watch(i1TransferAmount, (newVal) => {
    // 仅在有实际金额时发布（避免初始化 0 值噪音）
    if (newVal !== 0) {
      // 构建转入明细（逐项目）
      const items = adjudicationRows.value
        .filter((r) => _getNum(r.decreaseTransfer) !== 0)
        .map((r) => ({
          projectName: r.projectName || '未命名项目',
          amount: _getNum(r.decreaseTransfer),
        }))

      window.dispatchEvent(new CustomEvent('development:capitalized-to-intangible', {
        detail: {
          amount: newVal,
          items,
          wpCode: 'I2',
          accountCode: '1717',
        },
      }))
    }
  })

  // ─── Cleanup on scope dispose ─────────────────────────────────────────────

  onScopeDispose(() => {
    window.removeEventListener('research:expense-updated', _onI6ExpenseUpdated)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // I2-2 明细聚合（资本化金额 + 转入金额）
    detailTotals,
    // I6↔I2 联动校验状态
    i6LinkageStatus,
    // I2→I1 转入金额（审定表"转无形"列合计）
    i1TransferAmount,
  }
}

export default useI2CrossSheet
