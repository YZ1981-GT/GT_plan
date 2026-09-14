/**
 * useH6CrossSheet — H6 固定资产清理跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('H6-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射：
 * - H6-1 审定表合计 vs H6-2 明细表合计（Req 2.5）
 * - 过渡科目期末余额（1606）：isZero 判定清理是否完成（Req 2.7）
 * - H6 清理净损益 vs H10 资产处置损益对应金额（Req 3.7）
 * - H6-3 调整分录 → H6-1 AJE/RJE（1606 账项/报表净额）
 *
 * 科目：1606固定资产清理（借方/资产类，过渡科目）
 * 公式：期末=期初+借方-贷方；过渡科目期末应为0
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 * Task: 3.2
 * Requirements: 2.5, 2.7, 3.7
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 跨sheet校验结果 */
export interface CrossSheetCheck {
  /** 差额（来源A - 来源B） */
  diff: number
  /** 是否匹配（|diff| < 0.01） */
  isMatch: boolean
}

/** 过渡科目状态 */
export interface TransitAccountStatus {
  /** 期末余额是否为零（清理完毕） */
  isZero: boolean
  /** 当前期末余额 */
  balance: number
}

/** H6-3 → H6-1 调整净额摘要 */
export interface H63AdjustmentSync {
  rowCount: number
  /** 科目 1606 账项净额（借−贷） */
  clearingAjeNet: number
  /** 科目 1606 报表净额（借−贷） */
  clearingRjeNet: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全提取数值，NaN/null/undefined → 0
 */
function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

/**
 * 从 allResponses 获取指定 item_id 的数值（存储在 remark 字段）
 */
function _getResponseNum(allResponses: Map<string, any>, itemId: string): number {
  const resp = allResponses.get(itemId)
  return _getNum(resp?.remark)
}

/**
 * 判断差额是否匹配（精度阈值0.01）
 */
function _checkMatch(diff: number): CrossSheetCheck {
  return {
    diff,
    isMatch: Math.abs(diff) < 0.01,
  }
}

function _isClearingAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1606' || c.startsWith('1606')
}

function _parseRows(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}

function _isRjeRow(r: any): boolean {
  const cat = String(r.category || '')
  const et = String(r.entryType || r.adjustType || '').toUpperCase()
  return cat === '报表调整' || et === 'RJE' || cat.includes('报表') || cat.includes('重分类')
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH6CrossSheet(allResponses: Ref<Map<string, any>>) {
  // ═══════════════════════════════════════════════════════════════════════════
  // 1. adjudicationVsDetail — H6-1审定表合计 vs H6-2明细表合计（Req 2.5）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * H6-1 审定表清理净损益 与 H6-2 明细表净损益合计 的交叉验证。
   * 两者应一致（diff=0），不一致时显示黄色警告。
   *
   * 数据来源：
   * - H6-1: allResponses.get('H6-1-disposal-gain-loss')?.remark → 清理净损益
   * - H6-2: allResponses.get('H6-2-subtotal-gain-loss')?.remark → 明细净损益合计
   *
   * 公式：diff = H6-1清理净损益 - H6-2明细净损益合计
   * isMatch: |diff| < 0.01
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheck> = computed(() => {
    const adjGainLoss = _getResponseNum(allResponses.value, 'H6-1-disposal-gain-loss')
    const detailGainLoss = _getResponseNum(allResponses.value, 'H6-2-subtotal-gain-loss')
    return _checkMatch(adjGainLoss - detailGainLoss)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. transitAccountStatus — 过渡科目期末余额（1606）（Req 2.7）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * 1606固定资产清理是过渡科目，正常情况下期末余额应为0。
   * 期末不为零说明存在未完成清理项目，需红色提醒。
   *
   * 数据来源：
   * - allResponses.get('H6-1-end-balance-audited')?.remark → 期末余额审定数
   *
   * isZero: |balance| < 0.01（考虑浮点精度）
   */
  const transitAccountStatus: ComputedRef<TransitAccountStatus> = computed(() => {
    const balance = _getResponseNum(allResponses.value, 'H6-1-end-balance-audited')
    return {
      isZero: Math.abs(balance) < 0.01,
      balance,
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. disposalGainLossVsH10 — H6清理净损益 vs H10资产处置损益（Req 3.7）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * H6 清理净损益 与 H10 资产处置损益对应金额 的交叉验证。
   * H6清理完毕结转H10，两者金额应一致。
   *
   * 数据来源：
   * - H6: allResponses.get('H6-1-disposal-gain-loss')?.remark → 清理净损益
   * - H10: allResponses.get('H10-disposal-income')?.remark → H10资产处置损益
   *   （通过 EventBus subscription 或跨底稿查询写入 allResponses）
   *
   * 公式：diff = H6清理净损益 - H10资产处置损益
   * isMatch: |diff| < 0.01
   */
  const disposalGainLossVsH10: ComputedRef<CrossSheetCheck> = computed(() => {
    const h6GainLoss = _getResponseNum(allResponses.value, 'H6-1-disposal-gain-loss')
    const h10Income = _getResponseNum(allResponses.value, 'H10-disposal-income')
    return _checkMatch(h6GainLoss - h10Income)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. h63AdjustmentSync — H6-3 调整分录 → H6-1 AJE/RJE（1606）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * 从 H6-3 调整分录汇总读取 1606 账项/报表净额，供 H6-1 回写。
   * 兼容 Excel「类别=账项调整/报表调整/其他」与旧存档 AJE/RJE、debit/credit。
   * 优先读 H6-3-rows；若无行则回退 H6-3-aje-net / H6-3-rje-net。
   */
  const h63AdjustmentSync: ComputedRef<H63AdjustmentSync> = computed(() => {
    const resp = allResponses.value.get('H6-3-rows')
    const rows = _parseRows(resp?.remark ?? resp?.conclusion)
    if (rows.length > 0) {
      let clearingAjeNet = 0
      let clearingRjeNet = 0
      for (const r of rows) {
        if (!_isClearingAccount(String(r.accountCode || ''))) continue
        const debit = _getNum(r.debitAmount ?? r.debit)
        const credit = _getNum(r.creditAmount ?? r.credit)
        const net = debit - credit
        if (_isRjeRow(r)) clearingRjeNet += net
        else clearingAjeNet += net
      }
      return { rowCount: rows.length, clearingAjeNet, clearingRjeNet }
    }
    return {
      rowCount: 0,
      clearingAjeNet: _getResponseNum(allResponses.value, 'H6-3-aje-net'),
      clearingRjeNet: _getResponseNum(allResponses.value, 'H6-3-rje-net'),
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Return
  // ═══════════════════════════════════════════════════════════════════════════

  return {
    // H6-1审定表合计 vs H6-2明细表合计（Req 2.5）
    adjudicationVsDetail,
    // 过渡科目期末余额状态（Req 2.7）
    transitAccountStatus,
    // H6清理净损益 vs H10资产处置损益（Req 3.7）
    disposalGainLossVsH10,
    // H6-3 → H6-1
    h63AdjustmentSync,
  }
}

export default useH6CrossSheet
