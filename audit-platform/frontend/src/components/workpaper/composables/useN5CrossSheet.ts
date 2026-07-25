/**
 * useN5CrossSheet — N5 所得税费用跨sheet引擎 + N1/N3/I6/I2/A跨底稿联动
 *
 * Spec: .kiro/specs/n5-income-tax-expense/
 * Task: 3.2
 * Requirements: 2.6, 3.4-3.6, 5.3, 8.3-8.4, 11.1-11.4
 *
 * 职责：
 * 1. adjudicationVsCalc — N5-1审定表(当期+递延+合计) vs N5-4/N5-8计算结果交叉验证
 * 2. deferredReconcile — 订阅N1/N3递延所得税本期变动，核对递延所得税费用
 * 3. rdFromI6I2 — 从I6研发费用/I2开发支出获取研发费用（费用化+资本化）
 * 4. profitFromIncomeStatement — 从A类利润表获取会计利润总额
 * 5. effectiveTaxRate — 有效税率=所得税费用/会计利润总额
 *
 * 联动方向：
 *   N1递延税资产 → 'deferred-tax:asset-updated'   → deferredReconcile.n1Change
 *   N3递延税负债 → 'deferred-tax:liability-updated' → deferredReconcile.n3Change
 *   A利润表 → profitFromIncomeStatement.accountingProfit
 *   I6/I2研发费用 → rdFromI6I2.expensed / capitalized
 *   N5-4当期所得税 ↔ N5-1审定表 → adjudicationVsCalc
 *   N5-8递延所得税 ↔ N5-1审定表 → adjudicationVsCalc
 *
 * 科目：6801 所得税费用（借方/损益类！取发生额）
 */
import { computed, ref, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import { calcDeferredTaxExpense } from './useN5IncomeTaxEngine'
import { calcEffectiveTaxRate } from './useN5FormulaEngine'
import type { ChecklistResponse } from './useN5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** N5-1审定表 vs N5-4/N5-8 计算结果交叉验证 */
export interface AdjudicationVsCalcResult {
  /** 当期所得税费用（N5-4计算表结果） */
  current: number
  /** 递延所得税费用（N5-8核对表结果） */
  deferred: number
  /** 所得税费用合计 = 当期 + 递延 */
  total: number
}

/** N1/N3递延所得税核对结果 */
export interface DeferredReconcileResult {
  /** N1递延所得税资产本期变动额（资产增加为正） */
  n1Change: number
  /** N3递延所得税负债本期变动额（负债增加为正） */
  n3Change: number
  /** 递延所得税费用 = 递延税负债增 - 递延税资产增 */
  deferredExpense: number
}

/** I6/I2研发费用取数结果 */
export interface RdFromI6I2Result {
  /** 费用化研发费用（I6，当期加计扣除） */
  expensed: number
  /** 资本化研发费用（I2开发支出，按摊销加计） */
  capitalized: number
}

/** A类利润表会计利润 */
export interface ProfitFromIncomeStatementResult {
  /** 会计利润总额 */
  accountingProfit: number
}

/** 有效税率 */
export interface EffectiveTaxRateResult {
  /** 有效税率 = 所得税费用 / 会计利润总额（会计利润为0时返回null） */
  rate: number | null
}

/** EventBus 'deferred-tax:asset-updated' 载荷（来自N1） */
export interface DeferredTaxAssetUpdatedPayload {
  accountCode: string
  auditedAmount: number
  periodChange: number
  wpCode: string
  timestamp: number
}

/** EventBus 'deferred-tax:liability-updated' 载荷（来自N3） */
export interface DeferredTaxLiabilityUpdatedPayload {
  wpCode: string
  endBalance: number
  beginBalance: number
  change: number
  timestamp: number
}

/** 跨底稿引用定义 */
export interface CrossWpReference {
  /** 目标底稿编码 */
  targetWpCode: string
  /** 引用说明 */
  label: string
  /** 引用方向：from=从目标引入, to=输出到目标 */
  direction: 'from' | 'to'
}

/** useN5CrossSheet 选项 */
export interface UseN5CrossSheetOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析数字，NaN/null/undefined → 0
 */
function parseNum(v: any): number {
  if (v == null) return 0
  if (typeof v === 'string') {
    try { v = JSON.parse(v) } catch { /* ignore */ }
  }
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 从 allResponses 获取指定 item_id 的 conclusion 数值
 */
export function getResponseNum(allResponses: Map<string, ChecklistResponse>, itemId: string): number {
  const resp = allResponses.get(itemId)
  return parseNum(resp?.conclusion)
}

/**
 * 从 allResponses 获取指定 item_id 的 remark 数值（备用，供sheet-specific composable使用）
 */
export function getRemarkNum(allResponses: Map<string, ChecklistResponse>, itemId: string): number {
  const resp = allResponses.get(itemId)
  return parseNum(resp?.remark)
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * N5 跨sheet引擎 + N1/N3/I6/I2/A跨底稿联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useN5FormData）
 * @param options - wpId / projectId 用于跨底稿API调用
 */
export function useN5CrossSheet(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  options?: UseN5CrossSheetOptions,
) {
  // ─── EventBus 订阅的递延税数据（reactive refs） ────────────────────────────

  /** N1递延所得税资产本期变动额（订阅 'deferred-tax:asset-updated'） */
  const _n1Change = ref(0)
  /** N3递延所得税负债本期变动额（订阅 'deferred-tax:liability-updated'） */
  const _n3Change = ref(0)

  /** I6研发费用（费用化）——从EventBus或API获取 */
  const _rdExpensed = ref(0)
  /** I2开发支出（资本化）——从EventBus或API获取 */
  const _rdCapitalized = ref(0)

  /** A类利润表会计利润总额 */
  const _accountingProfit = ref(0)

  // ─── EventBus handlers ──────────────────────────────────────────────────────

  /**
   * N1递延所得税资产更新
   * 载荷: { accountCode, auditedAmount, periodChange, wpCode, timestamp }
   * 取 periodChange（本期变动额=期末-期初，资产增加为正）
   */
  function _onDeferredTaxAssetUpdated(payload: any): void {
    _n1Change.value = parseNum(payload?.periodChange)
    // 持久化到 checklist_responses 避免会话丢失
    _persistCrossData('N5-cross-n1-change', _n1Change.value)
  }

  /**
   * N3递延所得税负债更新
   * 载荷: { wpCode, endBalance, beginBalance, change, timestamp }
   * 取 change（本期变动额=期末-期初，负债增加为正）
   */
  function _onDeferredTaxLiabilityUpdated(payload: any): void {
    _n3Change.value = parseNum(payload?.change)
    // 持久化到 checklist_responses 避免会话丢失
    _persistCrossData('N5-cross-n3-change', _n3Change.value)
  }

  /**
   * 持久化跨底稿数据到 checklist_responses
   * 铁律：EventBus跨表值必须持久化到checklist_responses + render策略回读seed
   */
  async function _persistCrossData(itemId: string, value: number): Promise<void> {
    if (!options?.wpId?.value) return
    try {
      await api.put(`/api/workpapers/${options.wpId.value}/checklist-responses`, {
        project_id: options.projectId?.value,
        items: [{ item_id: itemId, conclusion: String(value), remark: null }],
      })
    } catch {
      // 持久化失败不阻塞UI
    }
  }

  // ─── 订阅 EventBus ─────────────────────────────────────────────────────────

  eventBus.on('deferred-tax:asset-updated', _onDeferredTaxAssetUpdated)
  eventBus.on('deferred-tax:liability-updated', _onDeferredTaxLiabilityUpdated)

  // ─── 初始化：从 allResponses 恢复已持久化的跨底稿数据 ─────────────────────

  /**
   * 从 checklist_responses 恢复上次保存的跨底稿数据
   * （EventBus 仅同会话有效，需从持久化数据恢复）
   */
  function _restoreFromResponses(): void {
    const n1Resp = allResponses.value.get('N5-cross-n1-change')
    if (n1Resp?.conclusion) _n1Change.value = parseNum(n1Resp.conclusion)

    const n3Resp = allResponses.value.get('N5-cross-n3-change')
    if (n3Resp?.conclusion) _n3Change.value = parseNum(n3Resp.conclusion)

    const rdExpResp = allResponses.value.get('N5-cross-i6-expensed')
    if (rdExpResp?.conclusion) _rdExpensed.value = parseNum(rdExpResp.conclusion)

    const rdCapResp = allResponses.value.get('N5-cross-i2-capitalized')
    if (rdCapResp?.conclusion) _rdCapitalized.value = parseNum(rdCapResp.conclusion)

    const profitResp = allResponses.value.get('N5-cross-a-profit')
    if (profitResp?.conclusion) _accountingProfit.value = parseNum(profitResp.conclusion)
  }

  // 初次恢复
  _restoreFromResponses()

  // ─── 1. adjudicationVsCalc — N5-1审定表 vs N5-4/N5-8 ─────────────────────

  /**
   * N5-1 审定表各行金额 vs 来源计算表结果交叉验证：
   * - 当期所得税费用 ↔ N5-4 当期所得税费用计算表结果
   * - 递延所得税费用 ↔ N5-8 递延所得税费用核对表结果
   * - 合计 = 当期 + 递延
   *
   * 数据来源：
   * - N5-4 当期所得税: item_id "N5-4-currentTax"（conclusion=当期所得税金额）
   * - N5-8 递延所得税: item_id "N5-8-deferredExpense"（conclusion=递延所得税费用金额）
   */
  const adjudicationVsCalc: ComputedRef<AdjudicationVsCalcResult> = computed(() => {
    // 🔴 N5-4/N5-8 通过 syncCurrentTaxToAdjudication/syncDeferredExpenseToAdjudication 将计算结果
    //    回填至审定表 sheet（item_id "N5-1-current-tax" / "N5-1-deferred-tax"），
    //    而非 "N5-4-currentTax" / "N5-8-deferredExpense"（从不写入）。读回填键才有值。
    const current = getResponseNum(allResponses.value, 'N5-1-current-tax')
    const deferred = getResponseNum(allResponses.value, 'N5-1-deferred-tax')
    const total = parseFloat((current + deferred).toFixed(2))

    return { current, deferred, total }
  })

  // ─── 2. deferredReconcile — N1/N3递延所得税核对 ───────────────────────────

  /**
   * 递延所得税费用核对（N5-8核心）：
   * - n1Change: N1递延所得税资产本期变动（资产增加为正，减少所得税费用）
   * - n3Change: N3递延所得税负债本期变动（负债增加为正，增加所得税费用）
   * - deferredExpense: 递延所得税费用 = 递延税负债增 - 递延税资产增
   *
   * 来源：EventBus 'deferred-tax:asset-updated'(N1) + 'deferred-tax:liability-updated'(N3)
   * 持久化：checklist_responses "N5-cross-n1-change" / "N5-cross-n3-change"
   */
  const deferredReconcile: ComputedRef<DeferredReconcileResult> = computed(() => {
    const n1Change = _n1Change.value
    const n3Change = _n3Change.value
    const deferredExpense = calcDeferredTaxExpense(n3Change, n1Change)

    return { n1Change, n3Change, deferredExpense }
  })

  // ─── 3. rdFromI6I2 — I6研发费用 + I2开发支出 ──────────────────────────────

  /**
   * 研发费用（费用化+资本化）来源：
   * - I6研发费用底稿：费用化研发费用（当期全额加计扣除）
   * - I2开发支出底稿：资本化研发费用（按无形资产摊销加计）
   *
   * 数据来源优先级：
   * 1. EventBus 实时推送（同会话）
   * 2. checklist_responses 持久化恢复（跨会话）
   * 3. API 跨底稿拉取（初始化）
   */
  const rdFromI6I2: ComputedRef<RdFromI6I2Result> = computed(() => {
    return {
      expensed: _rdExpensed.value,
      capitalized: _rdCapitalized.value,
    }
  })

  // ─── 4. profitFromIncomeStatement — A类利润表会计利润 ──────────────────────

  /**
   * 会计利润总额：取自A类利润表
   * N5-4当期所得税计算的起点：应纳税所得额=会计利润±纳税调整
   *
   * 数据来源：
   * 1. checklist_responses 持久化恢复 "N5-cross-a-profit"
   * 2. API 跨底稿拉取
   */
  const profitFromIncomeStatement: ComputedRef<ProfitFromIncomeStatementResult> = computed(() => {
    return {
      accountingProfit: _accountingProfit.value,
    }
  })

  // ─── 5. effectiveTaxRate — 有效税率 ───────────────────────────────────────

  /**
   * 有效税率 = 所得税费用合计 / 会计利润总额
   * 会计利润为0时返回null（避免除零），显示"—"
   *
   * 用途：合理性分析，异常税率预警
   */
  const effectiveTaxRate: ComputedRef<EffectiveTaxRateResult> = computed(() => {
    const incomeTaxTotal = adjudicationVsCalc.value.total
    const profit = _accountingProfit.value
    const rate = calcEffectiveTaxRate(incomeTaxTotal, profit)
    return { rate: Number.isFinite(rate) ? rate : null }
  })

  // ─── 6. fetchCrossWorkpaperData — 跨底稿API拉取 ──────────────────────────

  /**
   * 跨底稿数据拉取（初始化时调用）：
   * - N1递延所得税资产变动 → deferredReconcile.n1Change
   * - N3递延所得税负债变动 → deferredReconcile.n3Change
   * - I6研发费用 → rdFromI6I2.expensed
   * - I2开发支出 → rdFromI6I2.capitalized
   * - A利润表会计利润 → profitFromIncomeStatement.accountingProfit
   *
   * 通过 wp-index/by-code 查找目标底稿wpId，再读取其 checklist_responses。
   * 失败不阻塞：黄色提示对应底稿未编制。
   */
  async function fetchCrossWorkpaperData(): Promise<void> {
    if (!options?.projectId?.value) return

    const pid = options.projectId.value

    // 并行拉取各底稿数据
    await Promise.allSettled([
      _fetchN1Data(pid),
      _fetchN3Data(pid),
      _fetchI6Data(pid),
      _fetchI2Data(pid),
      _fetchProfitData(pid),
    ])
  }

  /** 拉取N1递延所得税资产数据 */
  async function _fetchN1Data(pid: string): Promise<void> {
    try {
      const wpData: any = await api.get(
        `/api/projects/${pid}/wp-index/by-code/N1`,
        { _silent: true } as any,
      )
      const wpId = wpData?.working_paper_id || wpData?.wp_id || wpData?.id
      if (!wpId) return

      const res = await api.get(
        `/api/workpapers/${wpId}/checklist-responses`,
        { _silent: true } as any,
      )
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])

      // 🔴 N1的期初/期末审定合计 → 本期变动。useN1Adjudication._persistTotals 写
      //    "N1-1-total-begin"/"N1-1-total-audited"（存于 remark 字段），非 begin-balance/end-balance-total。
      const beginResp = responses.find((r: any) => r.item_id === 'N1-1-total-begin')
      const endResp = responses.find((r: any) => r.item_id === 'N1-1-total-audited')
      const begin = parseNum(beginResp?.remark ?? beginResp?.conclusion)
      const end = parseNum(endResp?.remark ?? endResp?.conclusion)
      if (begin !== 0 || end !== 0) {
        _n1Change.value = parseFloat((end - begin).toFixed(2))
        _persistCrossData('N5-cross-n1-change', _n1Change.value)
      }
    } catch {
      // N1未创建或无数据，不阻塞
    }
  }

  /** 拉取N3递延所得税负债数据 */
  async function _fetchN3Data(pid: string): Promise<void> {
    try {
      const wpData: any = await api.get(
        `/api/projects/${pid}/wp-index/by-code/N3`,
        { _silent: true } as any,
      )
      const wpId = wpData?.working_paper_id || wpData?.wp_id || wpData?.id
      if (!wpId) return

      const res = await api.get(
        `/api/workpapers/${wpId}/checklist-responses`,
        { _silent: true } as any,
      )
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])

      // 🔴 N3递延所得税负债本期变动额。useN3Adjudication.saveAndSync 写 "N3-1-change-total"
      //    （期末审定−期初审定，存于 conclusion），直接取用；回退按 end-begin 现算。
      const changeResp = responses.find((r: any) => r.item_id === 'N3-1-change-total')
      const endResp = responses.find((r: any) => r.item_id === 'N3-1-end-balance-total')
      if (changeResp && (changeResp.conclusion != null || changeResp.remark != null)) {
        _n3Change.value = parseNum(changeResp.conclusion ?? changeResp.remark)
        _persistCrossData('N5-cross-n3-change', _n3Change.value)
      } else if (endResp) {
        _n3Change.value = parseNum(endResp.conclusion ?? endResp.remark)
        _persistCrossData('N5-cross-n3-change', _n3Change.value)
      }
    } catch {
      // N3未创建或无数据，不阻塞
    }
  }

  /** 拉取I6研发费用数据（费用化研发费用） */
  async function _fetchI6Data(pid: string): Promise<void> {
    try {
      const wpData: any = await api.get(
        `/api/projects/${pid}/wp-index/by-code/I6`,
        { _silent: true } as any,
      )
      const wpId = wpData?.working_paper_id || wpData?.wp_id || wpData?.id
      if (!wpId) return

      const res = await api.get(
        `/api/workpapers/${wpId}/checklist-responses`,
        { _silent: true } as any,
      )
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])

      // I6 研发费用审定本期发生额
      const rdResp = responses.find((r: any) => r.item_id === 'I6-1-audited-total')
      const rdAmount = parseNum(rdResp?.conclusion)
      if (rdAmount !== 0) {
        _rdExpensed.value = rdAmount
        _persistCrossData('N5-cross-i6-expensed', rdAmount)
      }
    } catch {
      // I6未创建或无数据，不阻塞
    }
  }

  /** 拉取I2开发支出数据（资本化研发费用） */
  async function _fetchI2Data(pid: string): Promise<void> {
    try {
      const wpData: any = await api.get(
        `/api/projects/${pid}/wp-index/by-code/I2`,
        { _silent: true } as any,
      )
      const wpId = wpData?.working_paper_id || wpData?.wp_id || wpData?.id
      if (!wpId) return

      const res = await api.get(
        `/api/workpapers/${wpId}/checklist-responses`,
        { _silent: true } as any,
      )
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])

      // I2 开发支出（资本化部分，期末余额代表已资本化金额）
      const capResp = responses.find((r: any) => r.item_id === 'I2-1-audited-total')
      const capAmount = parseNum(capResp?.conclusion)
      if (capAmount !== 0) {
        _rdCapitalized.value = capAmount
        _persistCrossData('N5-cross-i2-capitalized', capAmount)
      }
    } catch {
      // I2未创建或无数据，不阻塞
    }
  }

  /** 拉取A类利润表会计利润 */
  async function _fetchProfitData(pid: string): Promise<void> {
    try {
      // A类利润表编码为 "A" 或利润表底稿
      const wpData: any = await api.get(
        `/api/projects/${pid}/wp-index/by-code/A`,
        { _silent: true } as any,
      )
      const wpId = wpData?.working_paper_id || wpData?.wp_id || wpData?.id
      if (!wpId) return

      const res = await api.get(
        `/api/workpapers/${wpId}/checklist-responses`,
        { _silent: true } as any,
      )
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])

      // A类利润表会计利润总额（利润总额行）
      const profitResp = responses.find((r: any) =>
        r.item_id === 'A-profit-total' || r.item_id === 'A-accounting-profit',
      )
      const profitAmount = parseNum(profitResp?.conclusion)
      if (profitAmount !== 0) {
        _accountingProfit.value = profitAmount
        _persistCrossData('N5-cross-a-profit', profitAmount)
      }
    } catch {
      // A利润表未创建或无数据，不阻塞
    }
  }

  // ─── 7. publishIncomeTaxUpdated — 通知A类利润表勾稽 ─────────────────────

  /**
   * 发布 'income-tax:updated' 事件到 EventBus。
   * 供A类利润表所得税费用行勾稽。
   *
   * 载荷：当期所得税 + 递延所得税 + 合计 + 有效税率
   */
  function publishIncomeTaxUpdated(): void {
    const { current, deferred, total } = adjudicationVsCalc.value
    const rate = effectiveTaxRate.value.rate

    eventBus.emit('income-tax:updated', {
      wpCode: 'N5',
      currentTax: current,
      deferredTax: deferred,
      totalIncomeTax: total,
      effectiveTaxRate: rate,
      timestamp: Date.now(),
    })
  }

  // ─── 8. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** N5 所得税费用 cross_wp_references */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'N1',
      label: 'N1递延所得税资产-本期变动→N5递延税费用核对',
      direction: 'from',
    },
    {
      targetWpCode: 'N3',
      label: 'N3递延所得税负债-本期变动→N5递延税费用核对',
      direction: 'from',
    },
    {
      targetWpCode: 'I6',
      label: 'I6研发费用-费用化研发费用→N5研发加计扣除',
      direction: 'from',
    },
    {
      targetWpCode: 'I2',
      label: 'I2开发支出-资本化研发费用→N5研发加计扣除',
      direction: 'from',
    },
    {
      targetWpCode: 'A',
      label: 'A利润表-会计利润总额→N5当期所得税计算',
      direction: 'from',
    },
  ]

  // ─── Cleanup（组件卸载取消订阅） ──────────────────────────────────────────

  onScopeDispose(() => {
    eventBus.off('deferred-tax:asset-updated', _onDeferredTaxAssetUpdated)
    eventBus.off('deferred-tax:liability-updated', _onDeferredTaxLiabilityUpdated)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsCalc,
    // N1/N3递延核对
    deferredReconcile,
    // I6/I2研发费用
    rdFromI6I2,
    // A利润表会计利润
    profitFromIncomeStatement,
    // 有效税率
    effectiveTaxRate,
    // 跨底稿API拉取
    fetchCrossWorkpaperData,
    // 发布所得税更新
    publishIncomeTaxUpdated,
    // 跨底稿引用
    crossWpReferences,
  }
}

export default useN5CrossSheet
