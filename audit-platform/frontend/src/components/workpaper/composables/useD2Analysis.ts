/**
 * useD2Analysis — 分析程序D2-5核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 8.1
 *
 * 职责：
 * - AnalysisIndicators 类型定义（周转率/周转天数/坏账率/前五大集中度/账龄分布）
 * - indicators computed（从 allResponses auto-data 或手动输入计算）
 * - turnoverDaysWarning computed（变动>30%警告）
 * - dataSource/remark 手动输入字段 + debounce保存
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import {
  parseNum,
  calculateTurnoverRate,
  calculateTurnoverDays,
} from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AgingDistributionItem {
  band: string        // 账龄段（如 '1年以内', '1-2年', '2-3年', '3年以上'）
  amount: number      // 金额
  ratio: number       // 占比
}

export interface AnalysisIndicators {
  turnoverRate: number          // 应收账款周转率
  turnoverDays: number          // 应收账款周转天数
  priorTurnoverDays: number     // 上期周转天数
  turnoverDaysChange: number    // 周转天数变动率
  badDebtRate: number           // 坏账准备计提比率
  top5Concentration: number     // 前五大客户集中度
  agingDistribution: AgingDistributionItem[]  // 账龄分布
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** allResponses key 前缀 */
const PREFIX = 'D2-analysis'

/** 周转天数变动警告阈值 (30%) */
const TURNOVER_DAYS_WARNING_THRESHOLD = 0.3

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseAgingDistribution(jsonStr: string | null | undefined): AgingDistributionItem[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((item: any) => ({
      band: item.band || '',
      amount: parseNum(item.amount),
      ratio: parseNum(item.ratio),
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2Analysis(options: UseD2BaseOptions) {
  const { allResponses, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const dataSource = ref<string>('')   // 数据来源说明
  const remark = ref<string>('')       // 备注
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Helpers ───────────────────────────────────────────────────────────

  function getVal(itemId: string): string | null {
    const resp = allResponses.value.get(itemId)
    return resp?.remark ?? null
  }

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadData(): void {
    dataSource.value = getVal(`${PREFIX}-dataSource`) || ''
    remark.value = getVal(`${PREFIX}-remark`) || ''
  }

  watch(
    () => allResponses.value.get(`${PREFIX}-dataSource`)?.remark,
    () => {
      if (!dataSource.value) {
        loadData()
      }
    },
    { immediate: true }
  )

  // ─── Indicators Computed ───────────────────────────────────────────────

  /**
   * 分析程序核心指标
   *
   * 数据来源优先级：
   * 1. auto_data_source resolver 自动取数（存储在 D2-analysis-auto-* keys）
   * 2. 手动录入值（存储在 D2-analysis-manual-* keys）
   */
  const indicators: ComputedRef<AnalysisIndicators> = computed(() => {
    // 营业收入 & 平均应收
    const revenue = parseNum(getVal(`${PREFIX}-auto-revenue`) ?? getVal(`${PREFIX}-manual-revenue`))
    const avgReceivable = parseNum(getVal(`${PREFIX}-auto-avgReceivable`) ?? getVal(`${PREFIX}-manual-avgReceivable`))

    // 周转率 & 周转天数
    const turnoverRate = calculateTurnoverRate(revenue, avgReceivable)
    const turnoverDays = calculateTurnoverDays(turnoverRate)

    // 上期周转天数
    const priorTurnoverDays = parseNum(getVal(`${PREFIX}-auto-priorTurnoverDays`) ?? getVal(`${PREFIX}-manual-priorTurnoverDays`))

    // 周转天数变动率
    let turnoverDaysChange = 0
    if (priorTurnoverDays !== 0) {
      turnoverDaysChange = (turnoverDays - priorTurnoverDays) / priorTurnoverDays
    }

    // 坏账率
    const badDebtBalance = parseNum(getVal(`${PREFIX}-auto-badDebtBalance`) ?? getVal(`${PREFIX}-manual-badDebtBalance`))
    const totalReceivable = parseNum(getVal(`${PREFIX}-auto-totalReceivable`) ?? getVal(`${PREFIX}-manual-totalReceivable`))
    const badDebtRate = totalReceivable === 0 ? 0 : badDebtBalance / totalReceivable

    // 前五大集中度
    const top5Concentration = parseNum(getVal(`${PREFIX}-auto-top5Concentration`) ?? getVal(`${PREFIX}-manual-top5Concentration`))

    // 账龄分布
    const agingDistribution = parseAgingDistribution(
      getVal(`${PREFIX}-auto-agingDistribution`) ?? getVal(`${PREFIX}-manual-agingDistribution`)
    )

    return {
      turnoverRate,
      turnoverDays,
      priorTurnoverDays,
      turnoverDaysChange,
      badDebtRate,
      top5Concentration,
      agingDistribution,
    }
  })

  // ─── Warnings ──────────────────────────────────────────────────────────

  /**
   * 周转天数变动>30% 时发出警告
   */
  const turnoverDaysWarning: ComputedRef<string | null> = computed(() => {
    const change = indicators.value.turnoverDaysChange
    if (Math.abs(change) > TURNOVER_DAYS_WARNING_THRESHOLD) {
      const pct = (change * 100).toFixed(1)
      return `应收账款周转天数变动${pct}%，超过30%阈值，需关注原因`
    }
    return null
  })

  // ─── Update Manual Fields ──────────────────────────────────────────────

  /**
   * 更新手动输入字段
   */
  function updateManualField(field: string, value: string | number): void {
    if (isReadonly.value) return

    const itemId = `${PREFIX}-manual-${field}`
    const strValue = typeof value === 'number' ? String(value) : value
    allResponses.value.set(itemId, {
      item_id: itemId,
      conclusion: null,
      remark: strValue,
    })
    debounceSave()
  }

  /**
   * 更新 dataSource / remark 字段
   */
  function updateMetaField(field: 'dataSource' | 'remark', value: string): void {
    if (isReadonly.value) return

    if (field === 'dataSource') {
      dataSource.value = value
    } else {
      remark.value = value
    }

    const itemId = `${PREFIX}-${field}`
    allResponses.value.set(itemId, {
      item_id: itemId,
      conclusion: null,
      remark: value,
    })
    debounceSave()
  }

  // ─── Save Logic ────────────────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    const items: Array<{ item_id: string; conclusion: null; remark: string }> = []
    for (const [key, val] of allResponses.value.entries()) {
      if (key.startsWith(PREFIX)) {
        items.push({ item_id: key, conclusion: null, remark: val?.remark || '' })
      }
    }
    if (items.length > 0) {
      dispatchSaveEvent(items)
    }
  }

  function dispatchSaveEvent(items: any[]): void {
    try {
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  // ─── Significant Change Event Publishing (Task 46.1) ─────────────────

  /**
   * Watch indicators 变化，周转天数变动率>30%时发布 EventBus 事件
   * payload: { wpCode: 'D2', indicator, changeRate, currentValue, priorValue }
   */
  let _lastPublishedTurnoverWarning = false

  watch(
    () => indicators.value.turnoverDaysChange,
    (change) => {
      const shouldWarn = Math.abs(change) > TURNOVER_DAYS_WARNING_THRESHOLD
      // 仅在状态变化时发布（避免重复）
      if (shouldWarn && !_lastPublishedTurnoverWarning) {
        try {
          window.dispatchEvent(new CustomEvent('analytical:significant-change', {
            detail: {
              wpCode: 'D2',
              indicator: 'turnover_days',
              changeRate: change,
              currentValue: indicators.value.turnoverDays,
              priorValue: indicators.value.priorTurnoverDays,
            }
          }))
        } catch {
          // silent
        }
      }
      _lastPublishedTurnoverWarning = shouldWarn
    },
    { immediate: false }
  )

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 核心指标
    indicators,
    turnoverDaysWarning,

    // 元数据字段
    dataSource,
    remark,

    // 操作
    updateManualField,
    updateMetaField,
  }
}

export default useD2Analysis
