/**
 * useM5AccrualTest — M5-4 计提检查表 composable
 *
 * Spec: .kiro/specs/m5-surplus-reserve/
 * Task: 3.4
 * Requirements: 4.1-4.7
 *
 * 职责：
 * - 法定10%计提测试
 * - 接收M6净利润(EventBus 'm6:net-profit')
 * - 计提基数=净利润-弥补以前年度亏损
 * - 应计提=基数×10% (引用 useM5AccrualEngine)
 * - 差异=应计提-账面计提
 * - 50%上限判断 (isAccrualCeilingReached)
 * - 3列: 法定/任意/合计
 * - 42×9结构，14公式
 *
 * 科目：4101 盈余公积（**贷方/权益类！**）
 * 法定盈余公积按净利润（弥补以前年度亏损后）10%计提
 * 累计法定盈余公积达注册资本50%时可不再计提
 */
import { computed, ref, onMounted, onUnmounted, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcStatutoryAccrual,
  calcAccrualDiff,
  isAccrualCeilingReached,
} from './useM5AccrualEngine'
import { calcSubtotal } from './useM5FormulaEngine'
import type { useM5FormData } from './useM5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 计提测试列类型 */
export type AccrualColumn = 'statutory' | 'discretionary' | 'total'

/** M6净利润事件数据 */
export interface M6NetProfitPayload {
  /** 本期净利润 */
  netProfit: number
  /** 弥补以前年度亏损金额（正数） */
  priorLossOffset: number
  /** 时间戳 */
  timestamp?: number
}

/** 计提测试行数据（按列结构） */
export interface M5AccrualTestData {
  // ─── 来源数据（M6净利润输入） ───
  /** 本期净利润（来自M6未分配利润） */
  netProfit: number
  /** 弥补以前年度亏损（正数） */
  priorLossOffset: number
  /** 计提基数=净利润-弥补以前年度亏损 */
  accrualBase: number

  // ─── 法定盈余公积 ───
  /** 法定计提比例（默认10%） */
  statutoryRate: number
  /** 法定应计提=基数×10% */
  statutoryEstimated: number
  /** 法定账面计提（从M5-2明细表或TB获取） */
  statutoryBooked: number
  /** 法定计提差异=应计提-账面 */
  statutoryDiff: number

  // ─── 任意盈余公积 ───
  /** 任意计提比例（股东会决议） */
  discretionaryRate: number
  /** 任意应计提=基数×任意比例 */
  discretionaryEstimated: number
  /** 任意账面计提 */
  discretionaryBooked: number
  /** 任意计提差异 */
  discretionaryDiff: number

  // ─── 合计 ───
  /** 合计应计提 */
  totalEstimated: number
  /** 合计账面计提 */
  totalBooked: number
  /** 合计差异 */
  totalDiff: number

  // ─── 50%上限判断 ───
  /** 累计法定盈余公积余额 */
  accumulatedStatutory: number
  /** 注册资本 */
  registeredCapital: number
  /** 是否达到注册资本50%上限 */
  ceilingReached: boolean
}

/** 差异阈值配置 */
export interface AccrualThreshold {
  /** 绝对值阈值（默认100元） */
  absolute: number
  /** 相对值阈值（默认1%） */
  relative: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEFAULT_STATUTORY_RATE = 0.1  // 法定10%
const DEFAULT_THRESHOLD: AccrualThreshold = {
  absolute: 100,
  relative: 0.01,
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M5-4 计提检查表业务逻辑（法定10%+任意+50%上限+M6联动）
 *
 * @param formData 由调用方传入的 useM5FormData 实例
 * @param options 配置项
 */
export function useM5AccrualTest(
  formData: ReturnType<typeof useM5FormData>,
  options?: {
    threshold?: AccrualThreshold
  },
) {
  const { debouncedSave, saveField } = formData
  const threshold = options?.threshold || DEFAULT_THRESHOLD

  // ─── 1. 响应式状态 ────────────────────────────────────────────────────

  /** M6净利润（EventBus接收） */
  const netProfit = ref(0)
  /** 弥补以前年度亏损 */
  const priorLossOffset = ref(0)
  /** 法定计提比例 */
  const statutoryRate = ref(DEFAULT_STATUTORY_RATE)
  /** 任意计提比例（股东会决议） */
  const discretionaryRate = ref(0)
  /** 法定账面计提 */
  const statutoryBooked = ref(0)
  /** 任意账面计提 */
  const discretionaryBooked = ref(0)
  /** 累计法定盈余公积余额（含前期） */
  const accumulatedStatutory = ref(0)
  /** 注册资本 */
  const registeredCapital = ref(0)
  /** M6数据是否已就绪 */
  const m6DataReady = ref(false)

  // ─── 2. 计算属性：14公式全部前端实时计算 ──────────────────────────────

  /** 计提基数=净利润-弥补以前年度亏损 */
  const accrualBase: ComputedRef<number> = computed(() => {
    return netProfit.value - priorLossOffset.value
  })

  /** 法定应计提=基数×10% */
  const statutoryEstimated: ComputedRef<number> = computed(() => {
    return calcStatutoryAccrual(accrualBase.value, statutoryRate.value)
  })

  /** 法定计提差异=应计提-账面 */
  const statutoryDiff: ComputedRef<number> = computed(() => {
    return calcAccrualDiff(statutoryEstimated.value, statutoryBooked.value)
  })

  /** 任意应计提=基数×任意比例 */
  const discretionaryEstimated: ComputedRef<number> = computed(() => {
    return calcStatutoryAccrual(accrualBase.value, discretionaryRate.value)
  })

  /** 任意计提差异 */
  const discretionaryDiff: ComputedRef<number> = computed(() => {
    return calcAccrualDiff(discretionaryEstimated.value, discretionaryBooked.value)
  })

  /** 合计应计提 */
  const totalEstimated: ComputedRef<number> = computed(() => {
    return calcSubtotal([statutoryEstimated.value, discretionaryEstimated.value])
  })

  /** 合计账面计提 */
  const totalBooked: ComputedRef<number> = computed(() => {
    return calcSubtotal([statutoryBooked.value, discretionaryBooked.value])
  })

  /** 合计差异 */
  const totalDiff: ComputedRef<number> = computed(() => {
    return calcAccrualDiff(totalEstimated.value, totalBooked.value)
  })

  /** 50%上限判断 */
  const ceilingReached: ComputedRef<boolean> = computed(() => {
    return isAccrualCeilingReached(accumulatedStatutory.value, registeredCapital.value)
  })

  // ─── 3. 聚合数据（供Vue组件渲染） ────────────────────────────────────

  /** 完整计提测试数据 */
  const testData: ComputedRef<M5AccrualTestData> = computed(() => ({
    netProfit: netProfit.value,
    priorLossOffset: priorLossOffset.value,
    accrualBase: accrualBase.value,
    statutoryRate: statutoryRate.value,
    statutoryEstimated: statutoryEstimated.value,
    statutoryBooked: statutoryBooked.value,
    statutoryDiff: statutoryDiff.value,
    discretionaryRate: discretionaryRate.value,
    discretionaryEstimated: discretionaryEstimated.value,
    discretionaryBooked: discretionaryBooked.value,
    discretionaryDiff: discretionaryDiff.value,
    totalEstimated: totalEstimated.value,
    totalBooked: totalBooked.value,
    totalDiff: totalDiff.value,
    accumulatedStatutory: accumulatedStatutory.value,
    registeredCapital: registeredCapital.value,
    ceilingReached: ceilingReached.value,
  }))

  // ─── 4. 差异高亮判断 ──────────────────────────────────────────────────

  /**
   * 判断差异是否超阈值（红色高亮）
   * |差异| > absolute 且 相对差异 > relative
   */
  function isDiffExceedThreshold(diff: number, estimated: number): boolean {
    if (Math.abs(diff) <= threshold.absolute) return false
    if (estimated === 0) return Math.abs(diff) > threshold.absolute
    return Math.abs(diff / estimated) > threshold.relative
  }

  /** 法定计提差异是否超阈值 */
  const statutoryDiffHighlight: ComputedRef<boolean> = computed(() => {
    return isDiffExceedThreshold(statutoryDiff.value, statutoryEstimated.value)
  })

  /** 任意计提差异是否超阈值 */
  const discretionaryDiffHighlight: ComputedRef<boolean> = computed(() => {
    return isDiffExceedThreshold(discretionaryDiff.value, discretionaryEstimated.value)
  })

  // ─── 5. EventBus 订阅M6净利润 ────────────────────────────────────────

  let _unsubM6: (() => void) | null = null

  /**
   * 订阅M6未分配利润的净利润/计提基数事件
   * 事件名: 'm6:net-profit'
   */
  function subscribeM6(): void {
    const handler = (payload: {
      netProfit?: number
      priorLossOffset?: number
      accrualBase?: number
      amount?: number
      timestamp?: number
    }) => {
      netProfit.value = payload.netProfit ?? payload.accrualBase ?? payload.amount ?? 0
      priorLossOffset.value = payload.priorLossOffset ?? 0
      m6DataReady.value = true
    }
    eventBus.on('m6:net-profit', handler)
    _unsubM6 = () => eventBus.off('m6:net-profit', handler)
  }

  function unsubscribeM6(): void {
    if (_unsubM6) {
      _unsubM6()
      _unsubM6 = null
    }
  }

  // ─── 6. 字段更新 ──────────────────────────────────────────────────────

  /** 手动设置净利润（当M6未发布事件时可手工输入） */
  function setNetProfit(val: number): void {
    netProfit.value = val
    m6DataReady.value = true
    _persistField('net-profit', val)
  }

  /** 设置弥补以前年度亏损 */
  function setPriorLossOffset(val: number): void {
    priorLossOffset.value = val
    _persistField('prior-loss-offset', val)
  }

  /** 设置任意计提比例 */
  function setDiscretionaryRate(val: number): void {
    discretionaryRate.value = val
    _persistField('discretionary-rate', val)
  }

  /** 设置法定账面计提 */
  function setStatutoryBooked(val: number): void {
    statutoryBooked.value = val
    _persistField('statutory-booked', val)
  }

  /** 设置任意账面计提 */
  function setDiscretionaryBooked(val: number): void {
    discretionaryBooked.value = val
    _persistField('discretionary-booked', val)
  }

  /** 设置累计法定盈余公积 */
  function setAccumulatedStatutory(val: number): void {
    accumulatedStatutory.value = val
    _persistField('accumulated-statutory', val)
  }

  /** 设置注册资本 */
  function setRegisteredCapital(val: number): void {
    registeredCapital.value = val
    _persistField('registered-capital', val)
  }

  function _persistField(field: string, value: number): void {
    debouncedSave(`M5-4-${field}`, { remark: String(value) })
  }

  // ─── 7. 保存计提检查结果 + 发布M5→M6 ──────────────────────────────────────

  /** 保存完整计提检查结果并发布M5→M6计提金额 */
  async function saveTestResult(): Promise<void> {
    await saveField('M5-4-test-result', {
      remark: JSON.stringify(testData.value),
    })

    // 发布M5→M6（ADR-3: M5计提盈余公积→M6可供分配利润）
    eventBus.emit('m5:surplus-accrual', {
      wpCode: 'M5',
      statutoryAccrual: statutoryEstimated.value,
      discretionaryAccrual: discretionaryEstimated.value,
      totalAccrual: totalEstimated.value,
      timestamp: Date.now(),
    })
  }

  // ─── 8. 后端拉取M6净利润（主动拉取，补充EventBus被动推送） ────────────

  /**
   * 从后端拉取M6净利润/计提基数（复盘铁律②：附注自动从审定表/明细表抓数,EventBus不够需主动拉取）
   * 调用 GET /api/m5-surplus-reserve/{wpId}/m6-net-profit?project_id=xxx
   */
  async function fetchM6NetProfit(wpId: string, projectId: string): Promise<void> {
    try {
      const { api } = await import('@/services/apiProxy')
      const res = await api.get(
        `/api/m5-surplus-reserve/${wpId}/m6-net-profit?project_id=${projectId}`,
        { _silent: true } as any,
      )
      const data = res?.data ?? res
      if (data?.ready) {
        netProfit.value = data.net_profit ?? 0
        priorLossOffset.value = data.prior_loss_offset ?? 0
        m6DataReady.value = true
      }
    } catch {
      // 静默失败：后端 M6 数据暂不可用不阻塞
    }
  }

  // ─── 9. 生命周期 ──────────────────────────────────────────────────────

  onMounted(() => {
    subscribeM6()
  })

  onUnmounted(() => {
    unsubscribeM6()
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // M6数据状态
    m6DataReady,
    netProfit,
    priorLossOffset,

    // 计提参数
    statutoryRate,
    discretionaryRate,
    accumulatedStatutory,
    registeredCapital,

    // 账面数据
    statutoryBooked,
    discretionaryBooked,

    // 计算属性（14公式）
    accrualBase,
    statutoryEstimated,
    statutoryDiff,
    discretionaryEstimated,
    discretionaryDiff,
    totalEstimated,
    totalBooked,
    totalDiff,
    ceilingReached,

    // 聚合数据
    testData,

    // 差异高亮
    statutoryDiffHighlight,
    discretionaryDiffHighlight,
    isDiffExceedThreshold,

    // 字段更新
    setNetProfit,
    setPriorLossOffset,
    setDiscretionaryRate,
    setStatutoryBooked,
    setDiscretionaryBooked,
    setAccumulatedStatutory,
    setRegisteredCapital,

    // 保存
    saveTestResult,

    // 后端拉取M6
    fetchM6NetProfit,

    // EventBus
    subscribeM6,
    unsubscribeM6,
  }
}

export default useM5AccrualTest
