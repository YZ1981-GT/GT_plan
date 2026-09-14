/**
 * syncHubFromSummary — 函证汇总（*-1）→ ConfirmationHub 投影同步
 *
 * 原则：confirmation-v1 为编制真源；Hub 为项目级发函台账投影。
 * - 仅正向推进 Hub 状态机（pending→sent→returned→matched/discrepancy）
 * - 金额：Hub.book_amount←amount；Hub.confirmed_amount←reply_amount（非可确认金额）
 * - 行上写入 _hub_confirmation_id，下次按 id 精确匹配
 */
import api from '@/utils/http'
import type { ConfirmationRow } from '../confirmationTypes'
import { isConfirmationInFlight } from './emitConfirmationCompleted'

export type HubConfirmType = 'receivable' | 'payable' | 'bank' | 'loan'
export type HubStatus = 'pending' | 'sent' | 'returned' | 'matched' | 'discrepancy'

export interface HubConfirmationItem {
  id: string
  confirm_type: string
  counterparty: string
  status: string
  book_amount: number | null
  confirmed_amount: number | null
  diff_amount: number | null
  diff_note: string | null
  account_code: string | null
  wp_id: string | null
}

const STATUS_RANK: Record<string, number> = {
  pending: 0,
  sent: 1,
  returned: 2,
  matched: 3,
  discrepancy: 3,
}

/** 科目编码前缀 → Hub confirm_type（优先于中文名匹配） */
const ACCOUNT_CODE_TO_HUB_TYPE: Array<[RegExp, HubConfirmType]> = [
  [/^(1001|1002|1012)/, 'bank'],    // 库存现金/银行存款/其他货币资金
  [/^(1501|1502|1503|2501|2502)/, 'loan'], // 短期借款/长期借款/融资租赁
  [/^(2201|2202|2203|2241)/, 'payable'], // 应付票据/应付账款/预收/其他应付
  [/^(1121|1122|1123|1131|1221|1231)/, 'receivable'], // 应收票据/应收账款/预付/其他应收
]

/** 科目大类 → Hub confirm_type（优先用 account_code 前缀，fallback 中文名正则） */
export function accountTypeToHubType(accountType?: string, accountCode?: string): HubConfirmType {
  // 优先：按科目编码前 4 位精确匹配
  if (accountCode) {
    const code = String(accountCode).trim()
    for (const [pattern, hubType] of ACCOUNT_CODE_TO_HUB_TYPE) {
      if (pattern.test(code)) return hubType
    }
  }
  // Fallback：按中文科目名匹配
  const t = String(accountType || '')
  if (/银行|存款|货币资金/.test(t)) return 'bank'
  if (/借款|贷款|融资/.test(t)) return 'loan'
  if (/应付/.test(t)) return 'payable'
  return 'receivable'
}

/** 汇总行 → 期望 Hub 状态 */
export function rowToHubStatus(row: ConfirmationRow): HubStatus {
  if (row.match_status === '相符') return 'matched'
  if (row.match_status === '不符') return 'discrepancy'
  if (row.is_replied || row.reply_date) return 'returned'
  if (row.send_date || row.confirmation_method || row.match_status === '未回函') return 'sent'
  return 'pending'
}

/** pending→…→target 的逐步推进路径 */
export function transitionPath(from: string, to: HubStatus): HubStatus[] {
  if (STATUS_RANK[to] == null || STATUS_RANK[from] == null) return []
  if (STATUS_RANK[to] <= STATUS_RANK[from]) return []
  const path: HubStatus[] = []
  let cur = from
  // matched/discrepancy 都从 returned 进入
  const chain: HubStatus[] =
    to === 'matched' || to === 'discrepancy'
      ? ['sent', 'returned', to]
      : to === 'returned'
        ? ['sent', 'returned']
        : to === 'sent'
          ? ['sent']
          : []
  for (const step of chain) {
    if (STATUS_RANK[step] > STATUS_RANK[cur]) {
      path.push(step)
      cur = step
    }
  }
  return path
}

export interface SyncHubResult {
  created: number
  updated: number
  transitioned: number
  errors: string[]
  /** 写回行上的 _hub_confirmation_id，供调用方持久化 */
  hubIdByRowId: Record<string, string>
}

/**
 * 将汇总表「已进入函证程序」的行 upsert 到 Hub
 */
export async function syncHubFromSummary(options: {
  projectId: string
  wpId?: string
  sourceWpCode?: string
  /** 源函证底稿循环码 D0/F0/G0…（transition 到终态时触发 CONFIRMATION_RECEIVED 下游 stale 路由） */
  wpCode?: string
  /** 审计年度（stale 传播按年度） */
  year?: number
  rows: ConfirmationRow[]
}): Promise<SyncHubResult> {
  const { projectId, wpId, wpCode, year, rows } = options
  const result: SyncHubResult = {
    created: 0,
    updated: 0,
    transitioned: 0,
    errors: [],
    hubIdByRowId: {},
  }
  if (!projectId?.trim()) {
    result.errors.push('缺少 projectId')
    return result
  }

  // P2-1: 当 rows 为空/null 时直接跳过，不捏造不存在的 confirmation_id
  if (!rows || !rows.length) return result

  const candidates = rows.filter(
    (r) => r.entity_name?.trim() && isConfirmationInFlight(r),
  )
  if (!candidates.length) return result

  let hubItems: HubConfirmationItem[] = []
  try {
    const res = await api.get<{ items: HubConfirmationItem[] }>(
      `/api/projects/${projectId}/confirmations`,
      { _silent: true } as any,
    )
    hubItems = (res as any)?.items ?? []
  } catch (e: any) {
    result.errors.push('加载函证中心失败：' + (e?.message || '未知错误'))
    return result
  }

  for (const row of candidates) {
    const name = String(row.entity_name || '').trim()
    const rowId = row._row_id || name
    const confirmType = accountTypeToHubType(row.account_type)
    const targetStatus = rowToHubStatus(row)
    const book = Number(row.amount) || null
    const reply = Number(row.reply_amount) || null
    const diff =
      row.difference != null
        ? Number(row.difference)
        : book != null && reply != null
          ? Math.round((book - reply) * 100) / 100
          : null

    let hub =
      (row._hub_confirmation_id &&
        hubItems.find((h) => h.id === row._hub_confirmation_id)) ||
      hubItems.find(
        (h) =>
          h.counterparty?.trim().toLowerCase() === name.toLowerCase() &&
          h.confirm_type === confirmType,
      )

    try {
      if (!hub) {
        const created = await api.post<HubConfirmationItem>(
          `/api/projects/${projectId}/confirmations`,
          {
            confirm_type: confirmType,
            counterparty: name,
            wp_id: wpId || undefined,
            account_code: row.confirm_index || undefined,
            book_amount: book,
            confirmed_amount: reply,
            diff_amount: diff,
            diff_note: row.remark || undefined,
          },
          { _silent: true } as any,
        )
        hub = created as any
        if (hub?.id) {
          hubItems.push(hub)
          result.created++
          result.hubIdByRowId[rowId] = hub.id
          row._hub_confirmation_id = hub.id
        }
      } else {
        await api.put(
          `/api/projects/${projectId}/confirmations/${hub.id}`,
          {
            book_amount: book,
            confirmed_amount: reply,
            diff_amount: diff,
            wp_id: wpId || hub.wp_id || undefined,
            account_code: row.confirm_index || hub.account_code || undefined,
            diff_note: row.remark || hub.diff_note || undefined,
          },
          { _silent: true } as any,
        )
        result.updated++
        result.hubIdByRowId[rowId] = hub.id
        row._hub_confirmation_id = hub.id
      }

      if (hub?.id) {
        const path = transitionPath(hub.status || 'pending', targetStatus)
        for (const step of path) {
          try {
            const next = await api.post<HubConfirmationItem>(
              `/api/projects/${projectId}/confirmations/${hub.id}/transition`,
              { target_status: step, wp_code: wpCode, year },
              { _silent: true } as any,
            )
            hub = (next as any) || { ...hub, status: step }
            result.transitioned++
          } catch {
            // 状态机不允许则停止后续推进
            break
          }
        }
      }
    } catch (e: any) {
      result.errors.push(`${name}: ${e?.message || '同步失败'}`)
    }
  }

  return result
}

/** Hub 状态 → 汇总行字段补丁（稀疏回写，不覆盖编制细节） */
export function hubStatusToRowPatch(
  status: string,
  amounts?: { book_amount?: number | null; confirmed_amount?: number | null; diff_amount?: number | null },
): Partial<ConfirmationRow> {
  const patch: Partial<ConfirmationRow> = {}
  if (status === 'sent') {
    patch.match_status = '未回函'
  }
  if (status === 'returned' || status === 'matched' || status === 'discrepancy') {
    patch.is_replied = true
  }
  if (status === 'matched') patch.match_status = '相符'
  if (status === 'discrepancy') patch.match_status = '不符'
  if (status === 'returned') patch.match_status = patch.match_status || undefined

  if (amounts?.book_amount != null) patch.amount = Number(amounts.book_amount)
  if (amounts?.confirmed_amount != null) patch.reply_amount = Number(amounts.confirmed_amount)
  if (amounts?.diff_amount != null) patch.difference = Number(amounts.diff_amount)
  return patch
}
