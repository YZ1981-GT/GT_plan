/**
 * H1-7 「在建工程转入」↔ H2 在建工程「转入固定资产（转固）」跨底稿勾稽
 *
 * 数据来源（H2 checklist_responses）：
 * - H2-2-rows：在建工程明细表，字段 transferAmount=「转入固定资产」，
 *   transferAdj=账项调整，transferDate/transferToH1=竣工结转辅助。
 *
 * 审计意义：H1-7 中「在建工程转入」形成的固定资产增加合计，应与 H2 本期
 * 结转（转固）合计勾稽一致；差异需查明（未达可使用状态误转 / 漏转 / 分期转固）。
 */
import { api } from '@/services/apiProxy'

export interface H2TransferRow {
  name: string
  transferAmount: number
  transferDate: string
}

export interface H2CipTransferPullResult {
  status: 'ok' | 'wp_missing' | 'empty' | 'error'
  message: string
  h2WpId: string | null
  /** H2-2「转入固定资产」合计（审定口径=未审+账项调整） */
  transferToFaTotal: number
  rows: H2TransferRow[]
}

function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function parseRemark(raw: unknown): unknown {
  if (raw == null) return null
  if (typeof raw !== 'string') return raw
  const s = raw.trim()
  if (!s) return null
  try {
    return JSON.parse(s)
  } catch {
    return raw
  }
}

async function resolveWpId(projectId: string, wpCode: string): Promise<string | null> {
  try {
    const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: wpCode },
      _silent: true,
    } as any)
    return (idRes as any)?.wp_id ?? (idRes as any)?.data?.wp_id ?? null
  } catch {
    return null
  }
}

async function loadResponseItem(wpId: string, itemId: string): Promise<any | null> {
  try {
    const res = await api.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    return list.find((r) => r?.item_id === itemId) ?? null
  } catch {
    return null
  }
}

/**
 * 纯函数：从 H2-2 明细行数组提取「转入固定资产」合计与明细。
 * 审定口径 = transferAmount(未审) + transferAdj(账项调整)；兼容旧 decreaseTransfer。
 */
export function extractH2TransferToFa(rowsRaw: unknown): { total: number; rows: H2TransferRow[] } {
  const list = Array.isArray(rowsRaw) ? rowsRaw : []
  const rows: H2TransferRow[] = []
  let total = 0
  for (const r of list) {
    if (!r || r.isSubtotal || r.isTotal) continue
    const amt = parseNum(r.transferAmount ?? r.decreaseTransfer) + parseNum(r.transferAdj)
    if (amt === 0) continue
    total += amt
    rows.push({
      name: String(r.projectName || r.name || r.category || '在建工程项目'),
      transferAmount: amt,
      transferDate: String(r.transferDate || ''),
    })
  }
  return { total, rows }
}

/** 拉取同项目 H2「转入固定资产」合计，供 H1-7 勾稽 */
export async function pullH2CipTransferForH1(projectId: string): Promise<H2CipTransferPullResult> {
  const base: H2CipTransferPullResult = {
    status: 'error',
    message: '',
    h2WpId: null,
    transferToFaTotal: 0,
    rows: [],
  }
  if (!projectId) return { ...base, message: '缺少 projectId' }

  const h2WpId = await resolveWpId(projectId, 'H2')
  if (!h2WpId) {
    return { ...base, status: 'wp_missing', message: '项目中未找到 H2 在建工程底稿' }
  }

  try {
    const item = await loadResponseItem(h2WpId, 'H2-2-rows')
    const { total, rows } = extractH2TransferToFa(parseRemark(item?.remark))
    if (rows.length === 0) {
      return {
        ...base,
        status: 'empty',
        message: 'H2-2 暂无「转入固定资产」明细，请先编制 H2-2',
        h2WpId,
      }
    }
    return {
      status: 'ok',
      message: `已从 H2-2 取转固合计 ${total.toLocaleString('zh-CN')}（${rows.length} 项）`,
      h2WpId,
      transferToFaTotal: total,
      rows,
    }
  } catch (e: any) {
    return { ...base, status: 'error', message: e?.message || '拉取 H2 失败', h2WpId }
  }
}

export interface CipH2Reconcile {
  /** H1-7 在建工程转入增加合计 */
  h1CipTransferIn: number
  /** H2-2 转入固定资产合计 */
  h2TransferToFa: number
  diff: number
  /** |diff| < 容差 视为勾稽一致 */
  matched: boolean
  tolerance: number
}

/** H1 CIP 转入合计 vs H2 转固合计 勾稽（容差默认 1 元） */
export function buildCipH2Reconcile(
  h1CipTransferIn: number,
  h2TransferToFa: number,
  tolerance = 1,
): CipH2Reconcile {
  const diff = parseNum(h1CipTransferIn) - parseNum(h2TransferToFa)
  return {
    h1CipTransferIn: parseNum(h1CipTransferIn),
    h2TransferToFa: parseNum(h2TransferToFa),
    diff,
    matched: Math.abs(diff) < tolerance,
    tolerance,
  }
}
