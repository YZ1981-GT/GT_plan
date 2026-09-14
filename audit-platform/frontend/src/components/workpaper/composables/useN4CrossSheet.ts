/**
 * useN4CrossSheet — N4 税金及附加跨sheet引擎 + N2计提对应 + A利润表勾稽
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/
 * Task: 3.2
 * Requirements: 2.5, 2.6, 6.1-6.5
 *
 * 职责：
 * 1. adjudicationVsDetail — N4-1审定表合计 vs N4-2明细表合计 交叉验证
 * 2. n4VsN2Accrual — N4费用确认 vs N2各税种计提额 交叉验证（费用确认=计提）
 * 3. toIncomeStatement — 聚合审定额供A利润表"税金及附加"行勾稽
 *
 * 联动方向：
 *   N2应交税费 → 'tax-accrual:updated' → n4VsN2Accrual 刷新
 *   N4审定 → 'expense:taxes-surcharges-updated' → A利润表
 *   N4-1审定合计 ↔ N4-2明细合计 → adjudicationVsDetail
 *
 * 科目：6403 税金及附加（借方/损益类！取发生额）
 */
import { computed, ref, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import { parseNum } from './useN4FormulaEngine'
import { calcExpenseDiff } from './useN4MultiTaxEngine'

/**
 * 从 `allResponses` 读取某 item 的数值（`remark` 优先，回退 `conclusion`）。
 *
 * 🔴 本函数原先**既未 import 也未定义**却被调用 3 次（`adjudicationVsDetail` ×2、
 * `toIncomeStatement` ×1）→ 一旦走到「无现算数据、回退持久化合计」的分支就
 * `ReferenceError: getResponseNum is not defined`，**整个 N4 页面渲染崩**
 * （实测报「页面渲染出错 getResponseNum is not defined」）。
 * 该分支恰好在 N4-1 尚未编制时触发，即新项目打开 N4 必崩。
 */
function getResponseNum(
  allResponses: Map<string, any> | undefined,
  itemId: string,
): number {
  const item = allResponses?.get(itemId)
  if (!item) return 0
  return parseNum(item.remark ?? item.conclusion ?? item.value ?? item)
}

// ─── 税种常量 ─────────────────────────────────────────────────────────────────

/** N4涵盖的全部税种（10种） */
export const TAX_TYPES = [
  '消费税',
  '城建税',
  '教育费附加',
  '地方教育附加',
  '房产税',
  '土地使用税',
  '车船税',
  '印花税',
  '资源税',
  '其他',
] as const

export type TaxType = (typeof TAX_TYPES)[number]

// ─── Types ───────────────────────────────────────────────────────────────────

/** N4-1审定表 vs N4-2明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差异金额（审定合计 - 明细合计） */
  diff: number
  /** 是否一致（|diff| < 0.01 视为一致） */
  isMatch: boolean
}

/** N4 费用确认 vs N2 计提额 逐税种比对结果 */
export interface N4VsN2AccrualItem {
  /** 税种名称 */
  tax: string
  /** N4本期费用确认额（税金及附加发生额） */
  expense: number
  /** N2本期计提额（应交税费计提额） */
  accrual: number
  /** 差异 = expense - accrual */
  diff: number
}

/** 供A利润表勾稽的聚合金额 */
export interface ToIncomeStatementResult {
  /** 税金及附加审定合计金额（供A利润表该行取数） */
  amount: number
}

/** EventBus 'tax-accrual:updated' 载荷（来自N2） */
export interface TaxAccrualUpdatedPayload {
  /** 各税种计提数据 */
  items: { tax: string; accrual: number }[]
  /** 来源底稿编码 */
  wpCode: string
  /** 时间戳 */
  timestamp: number
}

/** 跨底稿引用定义 */
export interface CrossWpReference {
  targetWpCode: string
  label: string
  direction: 'from' | 'to'
}

/** useN4CrossSheet 选项 */
export interface UseN4CrossSheetOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * N4 跨sheet引擎 + N2计提对应 + A利润表勾稽
 *
 * @param allResponses - 全部 checklist_responses（来自 useN4FormData）
 * @param options - wpId / projectId 用于跨底稿API调用
 */
export function useN4CrossSheet(
  allResponses: Ref<Map<string, any>>,
  options?: UseN4CrossSheetOptions,
) {
  // ─── N2计提数据（EventBus订阅 + 持久化恢复） ───────────────────────────────

  /** N2各税种计提额（key=税种名称, value=计提金额） */
  const _n2AccrualMap = ref<Map<string, number>>(new Map())

  // ─── EventBus handlers ──────────────────────────────────────────────────────

  /**
   * 处理 N2 计提额更新事件
   * 载荷: { items: [{ tax, accrual }], wpCode, timestamp }
   */
  function _onTaxAccrualUpdated(payload: any): void {
    // 🔴 N2 发布载荷字段为 accruals/items，项形状 {tax, amount|accrual}，此处兼容读取 + 归一化税种名。
    const items: any[] = payload?.items ?? payload?.accruals ?? []
    for (const item of items) {
      if (item?.tax === undefined) continue
      const accrual = item.accrual ?? item.amount
      if (accrual === undefined) continue
      _n2AccrualMap.value.set(_normalizeTaxName(String(item.tax)), parseNum(accrual))
    }
    // 持久化到 checklist_responses 避免会话丢失
    _persistN2AccrualData()
  }

  /**
   * 持久化N2计提数据到 checklist_responses
   * 铁律：EventBus跨表值必须持久化到checklist_responses + render策略回读seed
   */
  async function _persistN2AccrualData(): Promise<void> {
    if (!options?.wpId?.value) return
    try {
      const serialized = JSON.stringify(Object.fromEntries(_n2AccrualMap.value))
      await api.put(`/api/workpapers/${options.wpId.value}/checklist-responses`, {
        project_id: options.projectId?.value,
        items: [{ item_id: 'N4-cross-n2-accrual', conclusion: serialized, remark: null }],
      })
    } catch {
      // 持久化失败不阻塞UI
    }
  }

  // ─── 订阅 EventBus ─────────────────────────────────────────────────────────

  eventBus.on('tax-accrual:updated', _onTaxAccrualUpdated)

  // ─── 初始化：从 allResponses 恢复已持久化的跨底稿数据 ─────────────────────

  function _restoreFromResponses(): void {
    const accrualResp = allResponses.value.get('N4-cross-n2-accrual')
    if (accrualResp?.conclusion) {
      try {
        const parsed = JSON.parse(accrualResp.conclusion)
        if (parsed && typeof parsed === 'object') {
          _n2AccrualMap.value = new Map(Object.entries(parsed).map(([k, v]) => [_normalizeTaxName(k), parseNum(v)]))
        }
      } catch { /* 解析失败忽略 */ }
    }
  }

  // 初次恢复
  _restoreFromResponses()

  // ─── Helper: 从allResponses取数 ───────────────────────────────────────────

  /**
   * 税种名称归一化。消除各底稿命名分歧（城建税/城市维护建设税、土地使用税/城镇土地使用税、
   * 车船税/车船使用税/车船牌照税、所得税/企业所得税、增值税/未交增值税），使跨表按名匹配可靠。
   */
  function _normalizeTaxName(name: string): string {
    const s = String(name ?? '').trim()
    if (s === '城建税' || s === '城市维护建设税') return '城市维护建设税'
    if (s === '土地使用税' || s === '城镇土地使用税') return '土地使用税'
    if (s === '车船税' || s === '车船使用税' || s === '车船牌照税') return '车船税'
    if (s === '所得税' || s === '企业所得税') return '企业所得税'
    if (s === '增值税' || s === '未交增值税') return '增值税'
    return s
  }

  function _parseRows(itemId: string): any[] {
    const resp = allResponses.value.get(itemId)
    const raw = resp?.remark ?? resp?.conclusion
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  /**
   * N4-1 审定表各税种审定发生额映射（key=归一化税种名）。
   * 🔴 useN4Adjudication 存储整行数组于 "N4-1-rows"（不写 per-tax "N4-1-{tax}-audited"），
   *    审定数=未审+AJE+RJE，须从行数组现算，否则读 per-tax 键恒 0。
   */
  const _adjudicationMap: ComputedRef<Map<string, number>> = computed(() => {
    const map = new Map<string, number>()
    for (const row of _parseRows('N4-1-rows')) {
      const key = _normalizeTaxName(row.taxType)
      if (!key) continue
      const audited = parseNum(row.unadjusted) + parseNum(row.aje) + parseNum(row.rje)
      map.set(key, (map.get(key) ?? 0) + audited)
    }
    return map
  })

  /**
   * N4-2 明细表各税种本期发生额映射（key=归一化税种名）。
   * useN4Detail 存储 "N4-2-detail-rows"，本期税额=计税依据×税率。
   */
  const _detailMap: ComputedRef<Map<string, number>> = computed(() => {
    const map = new Map<string, number>()
    for (const row of _parseRows('N4-2-detail-rows')) {
      const key = _normalizeTaxName(row.taxType)
      if (!key) continue
      const amount = parseNum(row.taxBasis) * parseNum(row.taxRate)
      map.set(key, (map.get(key) ?? 0) + amount)
    }
    return map
  })

  /** 获取N4-1审定表某税种的审定发生额（从 N4-1-rows 现算，归一化匹配） */
  function _getAdjudicationAmount(taxType: string): number {
    return _adjudicationMap.value.get(_normalizeTaxName(taxType)) ?? 0
  }

  /** 获取N4-2明细表某税种的本期发生额（从 N4-2-detail-rows 现算，归一化匹配） */
  function _getDetailAmount(taxType: string): number {
    return _detailMap.value.get(_normalizeTaxName(taxType)) ?? 0
  }

  // ─── 1. adjudicationVsDetail — N4-1审定表合计 vs N4-2明细表合计 ─────────────

  /**
   * N4-1审定表各税种合计 vs N4-2明细表各税种合计
   * 两表应完全一致（同源数据，不同展现维度）
   *
   * 数据来源：
   * - N4-1: "N4-1-{taxType}-audited"
   * - N4-2: "N4-2-{taxType}-amount"
   * - 也读取合计行: "N4-1-total-audited" / "N4-2-total-amount"
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：优先从 N4-1-rows 现算（审定=未审+AJE+RJE），回退持久化的 N4-1-audited-total。
    let adjTotal = 0
    if (_adjudicationMap.value.size > 0) {
      for (const v of _adjudicationMap.value.values()) adjTotal += v
    } else {
      adjTotal = getResponseNum(allResponses.value, 'N4-1-audited-total')
    }

    // 明细表合计：优先从 N4-2-detail-rows 现算，回退持久化的 N4-2-subtotal。
    // 🔴 useN4Detail 存储键为 "N4-2-subtotal"（非 "N4-2-total-amount"）。
    let detailTotal = 0
    if (_detailMap.value.size > 0) {
      for (const v of _detailMap.value.values()) detailTotal += v
    } else {
      detailTotal = getResponseNum(allResponses.value, 'N4-2-subtotal')
    }

    const diff = parseFloat((adjTotal - detailTotal).toFixed(2))
    const isMatch = Math.abs(diff) < 0.01

    return { diff, isMatch }
  })

  // ─── 2. n4VsN2Accrual — N4费用确认 vs N2各税种计提额 ──────────────────────

  /**
   * N4各税种费用确认 vs N2各税种计提额 逐项比对
   *
   * 核心勾稽关系（ADR-3）：
   *   N4税金及附加费用确认（损益发生额）=== N2应交税费本期计提额（负债贷方发生）
   *   差异≠0 → 红色高亮 → 审计关注
   *
   * N4费用来源: "N4-1-{taxType}-audited"（审定表审定数=本期费用确认额）
   * N2计提来源: EventBus 'tax-accrual:updated' → _n2AccrualMap
   */
  const n4VsN2Accrual: ComputedRef<N4VsN2AccrualItem[]> = computed(() => {
    return TAX_TYPES.map((tax) => {
      const expense = _getAdjudicationAmount(tax)
      const accrual = _n2AccrualMap.value.get(_normalizeTaxName(tax)) ?? 0
      const diff = calcExpenseDiff(expense, accrual)
      return { tax, expense, accrual, diff }
    })
  })

  // ─── 3. toIncomeStatement — 供A利润表勾稽 ─────────────────────────────────

  /**
   * 税金及附加审定合计金额
   * 供A利润表"税金及附加"行取数勾稽
   *
   * 取自N4-1审定表合计行（优先），或逐税种审定额累加
   */
  const toIncomeStatement: ComputedRef<ToIncomeStatementResult> = computed(() => {
    // 🔴 审定合计持久化键为 "N4-1-audited-total"（非 "N4-1-total-audited"）；优先从 N4-1-rows 现算。
    let amount = 0
    if (_adjudicationMap.value.size > 0) {
      for (const v of _adjudicationMap.value.values()) amount += v
    } else {
      amount = getResponseNum(allResponses.value, 'N4-1-audited-total')
    }
    return { amount: parseFloat(amount.toFixed(2)) }
  })

  // ─── 4. 逐税种差异追踪（供N4-2明细表红色高亮） ────────────────────────────

  /**
   * 各税种是否有差异（供N4-2明细表渲染使用）
   * diff≠0 → 红色高亮该行
   */
  const taxDiffHighlights: ComputedRef<Map<string, boolean>> = computed(() => {
    const map = new Map<string, boolean>()
    for (const item of n4VsN2Accrual.value) {
      map.set(item.tax, Math.abs(item.diff) >= 0.01)
    }
    return map
  })

  // ─── 5. refreshN2AccrualData — 手动刷新N2计提数据 ─────────────────────────

  /**
   * 手动拉取N2应交税费各税种计提额（初始化或用户主动刷新时调用）
   *
   * 通过 wp-index/by-code 查找N2底稿wpId，再读取其 checklist_responses。
   * 失败不阻塞：黄色提示"N2未编制"。
   */
  async function refreshN2AccrualData(): Promise<void> {
    if (!options?.projectId?.value) return

    const pid = options.projectId.value

    try {
      const wpData: any = await api.get(
        `/api/projects/${pid}/wp-index/by-code/N2`,
        { _silent: true } as any,
      )
      const wpId = wpData?.working_paper_id || wpData?.wp_id || wpData?.id
      if (!wpId) return

      const res = await api.get(
        `/api/workpapers/${wpId}/checklist-responses`,
        { _silent: true } as any,
      )
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])

      // 🔴 N2各税种本期计提额 = 应交税费本期贷方发生额(creditAmount)，存于整行数组 "N2-1-adjudication-rows"
      //    （useN2Adjudication 不写 per-tax "N2-1-{tax}-accrual"），须从行数组现算 + 归一化税种名。
      const rowsResp = responses.find((r: any) => r.item_id === 'N2-1-adjudication-rows')
      if (rowsResp) {
        const raw = rowsResp.remark ?? rowsResp.conclusion
        let n2Rows: any[] = []
        if (raw) {
          try {
            const parsed = JSON.parse(raw)
            if (Array.isArray(parsed)) n2Rows = parsed
          } catch { /* 忽略 */ }
        }
        for (const row of n2Rows) {
          const key = _normalizeTaxName(String(row.taxType ?? ''))
          if (key) _n2AccrualMap.value.set(key, parseNum(row.creditAmount))
        }
      }

      // 持久化
      _persistN2AccrualData()
    } catch {
      // N2未创建或无数据，不阻塞
    }
  }

  // ─── 6. publishTaxesSurchargesUpdated — 通知A利润表勾稽 ────────────────────

  /**
   * 发布 'expense:taxes-surcharges-updated' 事件到 EventBus
   * 供A类利润表"税金及附加"行勾稽
   *
   * 载荷：审定合计金额 + 各税种明细
   */
  function publishTaxesSurchargesUpdated(): void {
    const { amount } = toIncomeStatement.value
    const details = n4VsN2Accrual.value.map(({ tax, expense }) => ({ tax, amount: expense }))

    eventBus.emit('expense:taxes-surcharges-updated', {
      wpCode: 'N4',
      amount,
      details,
      timestamp: Date.now(),
    })
  }

  // ─── 7. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** N4 税金及附加 cross_wp_references */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'N2',
      label: 'N2应交税费-各税种计提额→N4费用确认交叉验证',
      direction: 'from',
    },
    {
      targetWpCode: 'A',
      label: 'N4税金及附加审定合计→A利润表"税金及附加"行',
      direction: 'to',
    },
  ]

  // ─── Cleanup（组件卸载取消订阅） ──────────────────────────────────────────

  onScopeDispose(() => {
    eventBus.off('tax-accrual:updated', _onTaxAccrualUpdated)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    n4VsN2Accrual,
    toIncomeStatement,
    // 逐税种差异高亮
    taxDiffHighlights,
    // 手动刷新N2数据
    refreshN2AccrualData,
    // 发布A利润表勾稽事件
    publishTaxesSurchargesUpdated,
    // 跨底稿引用
    crossWpReferences,
    // 税种常量（供外部使用）
    TAX_TYPES,
  }
}

export default useN4CrossSheet
