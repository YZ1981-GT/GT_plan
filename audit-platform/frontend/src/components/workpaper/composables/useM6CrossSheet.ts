/**
 * useM6CrossSheet — M6 未分配利润跨sheet校验引擎 + M5/M1联动枢纽
 *
 * Spec: .kiro/specs/m6-retained-earnings/
 * Task: 3.2
 * Requirements: 2.5, 4.1-4.7
 *
 * 职责：
 * 1. adjudicationVsDetail — M6-1审定表年末 vs M6-2明细表年末 交叉验证
 * 2. surplusVsM5 — M6记录的提取盈余公积 vs M5实际计提 一致性校验
 * 3. dividendVsM1 — M6记录的分配股利 vs M1实际宣告 一致性校验
 * 4. EventBus订阅 'm5:surplus-accrual' / 'm1:declared-confirmed'
 * 5. EventBus发布 'm6:net-profit' / 'm6:profit-distributed'
 * 6. cross_wp_references 关联 M5、M1、本年利润来源
 *
 * 联动方向：
 *   M6-1审定表期末 ↔ M6-2明细表期末 双向勾稽
 *   M5盈余公积 → 'm5:surplus-accrual' → surplusVsM5（M6记录vs M5计提）
 *   M1应付股利 → 'm1:declared-confirmed' → dividendVsM1（M6记录vs M1宣告）
 *   M6 → 'm6:net-profit' → M5/M1（驱动下游计提/分配）
 *   M6 → 'm6:profit-distributed' → M1（股利分配通知）
 *
 * 科目：4104 利润分配-未分配利润（**贷方/权益类！期末=期初+贷方-借方**）
 *
 * ADR-3: 双向联动核对防止分配不一致
 *   M6发布净利润/分配额给M5/M1，同时接收M5实际计提、M1实际宣告做反向核对，
 *   形成闭环验证。任何一环差异都会红色高亮，确保利润分配全链一致。
 */
import { computed, ref, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcLinkageDiff } from './useM6DistributionEngine'
import type { ChecklistResponse } from './useM6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = M6-1审定表期末 - M6-2明细表期末（结转后未分配利润） */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

/** M6提取盈余公积 vs M5实际计提 一致性校验结果 */
export interface SurplusVsM5Result {
  /** 差额 = M6记录的提取盈余公积 - M5实际计提合计 */
  diff: number
  /** |diff| < 阈值视为一致 */
  isConsistent: boolean
}

/** M6分配股利 vs M1实际宣告 一致性校验结果 */
export interface DividendVsM1Result {
  /** 差额 = M6记录的分配股利 - M1实际宣告股利 */
  diff: number
  /** |diff| < 阈值视为一致 */
  isConsistent: boolean
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

// ─── Constants ───────────────────────────────────────────────────────────────

/** 审定-明细勾稽匹配阈值（1元内） */
const MATCH_THRESHOLD = 1

/** M5/M1联动差异一致性阈值（0.01元，会计精度） */
export const DIFF_THRESHOLD = 0.01

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析数字，NaN/null/undefined → 0
 */
function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M6 跨sheet校验引擎 + M5盈余公积/M1股利联动枢纽
 *
 * @param allResponses - 全部 checklist_responses（来自 useM6FormData）
 */
export function useM6CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── EventBus 订阅的联动数据（reactive refs） ──────────────────────────────

  /** M5实际计提盈余公积合计（订阅 'm5:surplus-accrual'） */
  const _m5AccrualConfirmed = ref(0)
  /** M1实际宣告股利合计（订阅 'm1:declared-confirmed'） */
  const _m1DeclaredConfirmed = ref(0)

  // ─── EventBus 订阅 handlers ─────────────────────────────────────────────

  /**
   * M5盈余公积计提确认
   * 载荷: { wpCode, statutoryAccrual, discretionaryAccrual, totalAccrual, timestamp }
   * 取 totalAccrual（法定+任意盈余公积计提合计）
   *
   * 接收后自动持久化到 checklist_responses，防止刷新丢失（复盘铁律②）
   */
  function _onM5AccrualConfirmed(payload: {
    wpCode?: string
    statutoryAccrual?: number
    discretionaryAccrual?: number
    totalAccrual?: number
    amount?: number
    timestamp?: number
  }): void {
    const value = parseNum(
      payload?.totalAccrual
      ?? ((payload?.statutoryAccrual ?? 0) + (payload?.discretionaryAccrual ?? 0) || undefined)
      ?? payload?.amount,
    )
    _m5AccrualConfirmed.value = value
    // 持久化到 checklist_responses（下次 selfLoad 可恢复，不依赖同会话事件）
    const persistItem: ChecklistResponse = {
      item_id: 'M6-cross-m5-accrual-confirmed',
      conclusion: null,
      remark: String(value),
    }
    allResponses.value.set(persistItem.item_id, persistItem)
  }

  /**
   * M1应付股利宣告确认
   * 载荷: { wpCode, declaredAmount, cashDividend, stockDividend, timestamp }
   * 取 declaredAmount（应付股利宣告合计=现金股利+转增股本）
   *
   * 接收后自动持久化到 checklist_responses，防止刷新丢失（复盘铁律②）
   */
  function _onM1DeclaredConfirmed(payload: {
    wpCode?: string
    declaredAmount?: number
    amount?: number
    timestamp?: number
  }): void {
    const value = parseNum(payload?.declaredAmount ?? payload?.amount)
    _m1DeclaredConfirmed.value = value
    // 持久化到 checklist_responses
    const persistItem: ChecklistResponse = {
      item_id: 'M6-cross-m1-declared-confirmed',
      conclusion: null,
      remark: String(value),
    }
    allResponses.value.set(persistItem.item_id, persistItem)
  }

  // ─── 订阅 EventBus ─────────────────────────────────────────────────────────

  eventBus.on('m5:surplus-accrual', _onM5AccrualConfirmed)
  eventBus.on('m1:declared-confirmed', _onM1DeclaredConfirmed)

  // ─── 初始化：从 allResponses 读取已持久化的联动数据 ─────────────────────────

  /**
   * 从 checklist_responses 恢复上次保存的联动数据
   * （EventBus 仅同会话有效，需要从持久化数据恢复）
   */
  function _restoreFromResponses(): void {
    const m5Resp = allResponses.value.get('M6-cross-m5-accrual-confirmed')
    if (m5Resp?.remark) _m5AccrualConfirmed.value = parseNum(m5Resp.remark)

    const m1Resp = allResponses.value.get('M6-cross-m1-declared-confirmed')
    if (m1Resp?.remark) _m1DeclaredConfirmed.value = parseNum(m1Resp.remark)
  }

  // 初次恢复
  _restoreFromResponses()

  // ─── 1. adjudicationVsDetail — M6-1审定表年末 vs M6-2明细表年末 ─────────

  /**
   * M6-1 审定表期末审定数 应= M6-2 明细表期末未分配利润（结转后）
   * 差额 = 审定表期末 - 明细表期末
   *
   * 权益类贷方：期末=期初+贷方(净利润转入)-借方(分配)
   *
   * 数据来源：
   * - M6-1 审定表期末审定数存于 item_id: "M6-M6-1-end-audited"（remark=期末审定余额）
   * - M6-2 明细表期末未分配利润存于 item_id: "M6-M6-2-retained-end"（remark=结转后期末余额）
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表期末：M6-1期末审定余额
    const adjResp = allResponses.value.get('M6-M6-1-end-audited')
    const adjEnd = parseNum(adjResp?.remark)

    // 明细表期末：M6-2结转后期末未分配利润
    const detailResp = allResponses.value.get('M6-M6-2-retained-end')
    const detailEnd = parseNum(detailResp?.remark)

    const diff = parseFloat(calcLinkageDiff(adjEnd, detailEnd).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) < MATCH_THRESHOLD,
    }
  })

  // ─── 2. surplusVsM5 — M6记录的提取盈余公积 vs M5实际计提 ─────────────────

  /**
   * M6明细表（M6-2）中"提取盈余公积"行 应= M5实际计提合计
   * 差额 = M6记录的提取盈余公积 - M5实际计提
   *
   * 数据来源：
   * - M6记录的提取盈余公积：item_id "M6-M6-2-surplus-accrual"（remark=法定+任意盈余公积合计）
   * - M5实际计提：EventBus 'm5:surplus-accrual' 或持久化 "M6-cross-m5-accrual-confirmed"
   */
  const surplusVsM5: ComputedRef<SurplusVsM5Result> = computed(() => {
    // M6-2中记录的提取盈余公积
    const m6SurplusResp = allResponses.value.get('M6-M6-2-surplus-accrual')
    const m6Surplus = parseNum(m6SurplusResp?.remark)

    // M5实际计提
    const m5Amount = _m5AccrualConfirmed.value

    const diff = parseFloat(calcLinkageDiff(m6Surplus, m5Amount).toFixed(2))
    return {
      diff,
      isConsistent: Math.abs(diff) <= DIFF_THRESHOLD,
    }
  })

  // ─── 3. dividendVsM1 — M6记录的分配股利 vs M1实际宣告 ────────────────────

  /**
   * M6明细表（M6-2）中"分配股利"行 应= M1实际宣告股利
   * 差额 = M6记录的分配股利 - M1实际宣告
   *
   * 数据来源：
   * - M6记录的分配股利：item_id "M6-M6-2-dividend"（remark=应付普通股股利合计）
   * - M1实际宣告：EventBus 'm1:declared-confirmed' 或持久化 "M6-cross-m1-declared-confirmed"
   */
  const dividendVsM1: ComputedRef<DividendVsM1Result> = computed(() => {
    // M6-2中记录的分配股利
    const m6DividendResp = allResponses.value.get('M6-M6-2-dividend')
    const m6Dividend = parseNum(m6DividendResp?.remark)

    // M1实际宣告
    const m1Amount = _m1DeclaredConfirmed.value

    const diff = parseFloat(calcLinkageDiff(m6Dividend, m1Amount).toFixed(2))
    return {
      diff,
      isConsistent: Math.abs(diff) <= DIFF_THRESHOLD,
    }
  })

  // ─── 4. M6→M5/M1 发布：净利润+分配股利 → 驱动下游 ────────────────────────

  /**
   * 发布本年净利润/计提基数 → M5盈余公积计提
   *
   * ADR-3: M6是利润分配结转枢纽，发布净利润驱动M5按法定10%计提盈余公积。
   * 事件名: 'm6:net-profit'
   * 载荷: { wpCode, netProfit, accrualBase, timestamp }
   */
  function publishNetProfitToM5(netProfit: number, accrualBase?: number): void {
    const payload = {
      wpCode: 'M6',
      netProfit,
      accrualBase: accrualBase ?? netProfit,
      timestamp: Date.now(),
    }
    eventBus.emit('m6:net-profit', payload)
  }

  /**
   * 发布分配股利 → M1应付股利
   *
   * ADR-3: M6发布分配股利通知M1进行实际宣告处理。
   * 事件名: 'm6:profit-distributed'
   * 载荷: { wpCode, dividendAmount, cashDividend, stockDividend, timestamp }
   */
  function publishDividendToM1(
    dividendAmount: number,
    cashDividend?: number,
    stockDividend?: number,
  ): void {
    const payload = {
      wpCode: 'M6',
      dividendAmount,
      cashDividend: cashDividend ?? dividendAmount,
      stockDividend: stockDividend ?? 0,
      timestamp: Date.now(),
    }
    eventBus.emit('m6:profit-distributed', payload)
  }

  // ─── 5. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** M6 未分配利润 cross_wp_references（枢纽：接收本年利润+输出到M5/M1） */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'M5',
      label: 'M6本年净利润→M5盈余公积计提基数',
      direction: 'to',
    },
    {
      targetWpCode: 'M5',
      label: 'M5实际计提盈余公积→M6核对',
      direction: 'from',
    },
    {
      targetWpCode: 'M1',
      label: 'M6分配股利→M1应付股利宣告',
      direction: 'to',
    },
    {
      targetWpCode: 'M1',
      label: 'M1实际宣告股利→M6核对',
      direction: 'from',
    },
    {
      targetWpCode: 'A',
      label: '本年利润(利润表结转)→M6未分配利润',
      direction: 'from',
    },
  ]

  // ─── 6. Cleanup — 组件卸载时取消 EventBus 订阅 ─────────────────────────────

  onScopeDispose(() => {
    eventBus.off('m5:surplus-accrual', _onM5AccrualConfirmed)
    eventBus.off('m1:declared-confirmed', _onM1DeclaredConfirmed)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    // M5盈余公积联动
    surplusVsM5,
    // M1股利联动
    dividendVsM1,
    // M6→M5/M1 发布
    publishNetProfitToM5,
    publishDividendToM1,
    // 跨底稿引用
    crossWpReferences,
    // 内部状态（供调试/测试）
    _m5AccrualConfirmed,
    _m1DeclaredConfirmed,
  }
}

export default useM6CrossSheet
