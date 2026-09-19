/**
 * useM1CrossSheet — M1 应付股利跨sheet校验引擎 + M6利润分配联动
 *
 * Spec: .kiro/specs/m1-dividends-payable/
 * Task: 3.2
 * Requirements: 2.5, 5.2, 5.6
 *
 * 职责：
 * 1. adjudicationVsDetail — M1-1审定表合计 vs M1-2明细表合计 交叉验证
 * 2. declareVsM6 — M1-5测算宣告 vs M6利润分配（分配股利）一致性校验
 *
 * 联动方向：
 *   M6未分配利润 → 'm6:profit-distributed' → declareVsM6
 *   M1-1审定表合计 ↔ M1-2明细表合计 双向勾稽
 *
 * 科目：2232 应付股利（贷方/负债类！期末=期初+贷方-借方）
 *
 * M1是M股东权益循环中M6利润分配的下游负债：
 * M6宣告分配股利时 → 形成M1应付股利（EventBus订阅验证宣告准确性）。
 */
import { computed, ref, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useM1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = M1-1审定表期末合计 - M1-2明细表期末合计 */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

/** 测算宣告 vs M6利润分配 一致性校验结果 */
export interface DeclareVsM6Result {
  /** 差额 = M1-5测算宣告合计 - M6分配股利 */
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

/** 宣告vs M6一致性阈值（100元，允许多股东分配比例四舍五入误差） */
const DECLARE_CONSISTENCY_THRESHOLD = 100

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
 * M1 跨sheet校验引擎 + M6利润分配联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useM1FormData）
 */
export function useM1CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── EventBus 订阅的M6数据（reactive ref） ────────────────────────────────

  /** M6利润分配-分配股利金额（订阅 'm6:profit-distributed'） */
  const _m6ProfitDistributed = ref(0)

  // ─── EventBus 订阅 handler ──────────────────────────────────────────────

  /**
   * M6未分配利润-分配股利完成
   * 载荷: { wpCode, distributedDividend, distributableProfit, ratio, timestamp }
   * 取 distributedDividend（M6实际分配股利金额）
   */
  function _onM6ProfitDistributed(payload: {
    wpCode?: string
    dividendAmount?: number
    cashDividend?: number
    stockDividend?: number
    distributedDividend?: number
    amount?: number
    timestamp?: number
  }): void {
    _m6ProfitDistributed.value = parseNum(
      payload?.dividendAmount ?? payload?.distributedDividend ?? payload?.amount,
    )
  }

  // ─── 订阅 EventBus ─────────────────────────────────────────────────────────

  eventBus.on('m6:profit-distributed', _onM6ProfitDistributed)

  // ─── 初始化：从 allResponses 读取已持久化的M6数据 ───────────────────────────

  /**
   * 从 checklist_responses 恢复上次保存的M6利润分配数据
   * （EventBus 仅同会话有效，需要从持久化数据恢复）
   */
  function _restoreFromResponses(): void {
    const m6Resp = allResponses.value.get('M1-cross-m6-profit-distributed')
    if (m6Resp?.remark) _m6ProfitDistributed.value = parseNum(m6Resp.remark)
  }

  // 初次恢复
  _restoreFromResponses()

  // ─── 1. adjudicationVsDetail — 审定表M1-1合计 vs 明细表M1-2合计 ──────────

  /**
   * M1-1 审定表期末余额合计 应= M1-2 明细表各股东期末余额之和
   * 差额 = 审定表期末合计 - 明细表期末合计
   *
   * 负债类期末=期初+贷方(宣告)-借方(支付)
   *
   * 数据来源：
   * - M1-1 审定表合计存于 item_id: "M1-M1-1-total-end-balance"（remark=期末余额合计）
   * - M1-2 明细表合计存于 item_id: "M1-M1-2-total-end"（remark=各股东期末合计）
   *   或遍历 "M1-M1-2-row*-end" 模式累加
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：M1-1期末余额合计
    const adjResp = allResponses.value.get('M1-M1-1-total-end-balance')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：优先取汇总行（M1-2合计行）
    const detailTotalResp = allResponses.value.get('M1-M1-2-total-end')
    let detailTotal = parseNum(detailTotalResp?.remark)

    // 降级：如果汇总行无值，遍历明细行期末累加
    if (detailTotal === 0 && !detailTotalResp?.remark) {
      for (const [key, resp] of allResponses.value) {
        if (key.startsWith('M1-M1-2-row') && key.endsWith('-end')) {
          detailTotal += parseNum(resp.remark)
        }
      }
    }

    const diff = parseFloat((adjTotal - detailTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) < MATCH_THRESHOLD,
    }
  })

  // ─── 2. declareVsM6 — M1-5测算宣告 vs M6利润分配 ──────────────────────────

  /**
   * M1-5 测算宣告股利合计 vs M6利润分配的分配股利金额
   * 差额 = M1-5测算宣告合计 - M6分配股利
   *
   * 正差异 = M1测算>M6分配（可能分配比例设定偏高）
   * 负差异 = M6分配>M1测算（可能未入账宣告或比例偏低）
   *
   * 数据来源：
   * - M1-5 测算宣告: item_id "M1-M1-5-declared-total"（remark=测算宣告股利合计）
   * - M6 分配股利: EventBus 'm6:profit-distributed' 或持久化恢复
   */
  const declareVsM6: ComputedRef<DeclareVsM6Result> = computed(() => {
    // M1-5 测算宣告合计
    const declareResp = allResponses.value.get('M1-M1-5-declared-total')
    const declaredTotal = parseNum(declareResp?.remark)

    // M6 利润分配-分配股利
    const m6Distributed = _m6ProfitDistributed.value

    const diff = parseFloat((declaredTotal - m6Distributed).toFixed(2))
    return {
      diff,
      isConsistent: Math.abs(diff) < DECLARE_CONSISTENCY_THRESHOLD,
    }
  })

  // ─── 3. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** M1 应付股利 cross_wp_references（关联 M6 利润分配） */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'M6',
      label: 'M6未分配利润-分配股利→M1应付股利宣告核对',
      direction: 'from',
    },
  ]

  // ─── 持久化M6数据（EventBus收到时保存到checklist_responses） ───────────────

  /**
   * 获取当前M6利润分配金额（供外部持久化用）
   */
  function getM6ProfitDistributed(): number {
    return _m6ProfitDistributed.value
  }

  // ─── Cleanup（组件卸载取消订阅） ──────────────────────────────────────────

  onScopeDispose(() => {
    eventBus.off('m6:profit-distributed', _onM6ProfitDistributed)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    // 宣告vs M6一致性
    declareVsM6,
    // 跨底稿引用
    crossWpReferences,
    // M6数据访问（供外部持久化到 checklist_responses）
    getM6ProfitDistributed,
  }
}

export default useM1CrossSheet
