/**
 * emitConfirmationCompleted — 函证完成回写科目底稿
 *
 * 消费者（window CustomEvent，历史约定）：
 * - useF1Detail / useD3Detail：detail.customerName → isConfirmed='Y'
 * - useD2Detail：detail.customerName → isConfirmation=true
 * - useD2Adjudication：detail.sentCount/receivedCount/... → 函证汇总 JSON
 * - useD7Detail：detail.wpCode==='D7' 或 accountType=其他应收款 → isConfirmed='Y'
 *
 * 同时写入 eventBus（新代码可订阅 typed 事件）。
 */
import { eventBus } from '@/utils/eventBus'

export interface ConfirmationCompletedPayload {
  /** 被询证单位（科目明细匹配键） */
  customerName: string
  /** 函证索引号 */
  confirmIndex?: string
  /** 科目大类 */
  accountType?: string
  /**
   * 科目底稿提示码（D7 严格过滤 wpCode==='D7'）
   * 由 accountType 推导，也可调用方覆盖
   */
  wpCode?: string
  projectId?: string
  /** 来源汇总底稿编码，如 F0-1 */
  sourceWpCode?: string
  /** D2 审定表汇总字段 */
  sentCount?: number
  receivedCount?: number
  responseRate?: number
  confirmedAmount?: number
  differenceAmount?: number
}

/** 科目大类 → 科目底稿提示码 */
export function accountTypeToWpHint(accountType?: string): string | undefined {
  const t = String(accountType || '').trim()
  if (!t) return undefined
  if (t.includes('其他应收')) return 'D7'
  if (t.includes('应收票据')) return 'D1'
  if (t === '应收账款' || t.includes('应收账')) return 'D2'
  if (t.includes('合同负债') || t.includes('预收')) return 'D5'
  if (t.includes('预付')) return 'F1'
  if (t.includes('应付账')) return 'F4'
  if (t.includes('银行') || t.includes('存款') || t.includes('货币资金')) return 'E1'
  if (t.includes('其他应付')) return 'K'
  return undefined
}

/** 行是否视为「已进入函证程序」（发函或已有回函结果） */
export function isConfirmationInFlight(row: {
  send_date?: string
  is_replied?: boolean
  match_status?: string
  confirmation_method?: string
}): boolean {
  if (row.send_date) return true
  if (row.is_replied) return true
  if (row.match_status && ['相符', '不符', '未回函'].includes(row.match_status)) return true
  if (row.confirmation_method) return true
  return false
}

export function emitConfirmationCompleted(payload: ConfirmationCompletedPayload): void {
  const name = String(payload.customerName || '').trim()
  if (!name) return

  const detail: ConfirmationCompletedPayload = {
    ...payload,
    customerName: name,
    wpCode: payload.wpCode || accountTypeToWpHint(payload.accountType),
  }

  try {
    eventBus.emit('confirmation:completed', detail)
  } catch {
    /* ignore */
  }

  try {
    window.dispatchEvent(new CustomEvent('confirmation:completed', { detail }))
  } catch {
    /* ignore */
  }
}

/**
 * 从汇总表行批量回写：每个进入函证程序的对象 emit 一次；
 * 另补一条汇总 metrics（customerName 用空跳过明细匹配，仅带汇总字段）——
 * 因 D2 adjudication 不依赖 customerName，需单独 emit 汇总。
 */
export function emitConfirmationCompletedFromSummary(options: {
  projectId?: string
  sourceWpCode?: string
  rows: Array<{
    entity_name?: string
    confirm_index?: string
    account_type?: string
    send_date?: string
    is_replied?: boolean
    match_status?: string
    confirmation_method?: string
    amount?: number
    reply_amount?: number
    confirmed_amount?: number
    difference?: number
  }>
}): number {
  const { projectId, sourceWpCode, rows } = options
  let emitted = 0

  const inFlight = rows.filter(isConfirmationInFlight)
  for (const row of inFlight) {
    const customerName = String(row.entity_name || '').trim()
    if (!customerName) continue
    emitConfirmationCompleted({
      customerName,
      confirmIndex: row.confirm_index,
      accountType: row.account_type,
      projectId,
      sourceWpCode,
    })
    emitted++
  }

  // 汇总指标（供 D2-1 函证汇总块），customerName 用「__summary__」避免误标明细户
  const sentCount = inFlight.length
  const receivedCount = rows.filter(r => r.is_replied || r.match_status === '相符' || r.match_status === '不符').length
  const confirmedAmount = rows.reduce((s, r) => s + (Number(r.confirmed_amount) || 0), 0)
  const differenceAmount = rows.reduce((s, r) => s + (Number(r.difference) || 0), 0)
  if (sentCount > 0) {
    emitConfirmationCompleted({
      customerName: '__summary__',
      projectId,
      sourceWpCode,
      sentCount,
      receivedCount,
      responseRate: sentCount > 0 ? (receivedCount / sentCount) * 100 : 0,
      confirmedAmount,
      differenceAmount,
    })
  }

  return emitted
}
