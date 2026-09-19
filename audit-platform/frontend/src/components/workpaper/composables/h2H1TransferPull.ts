/**
 * H2-5 转固时点检查 ↔ H1 固定资产「在建工程转入」 反向勾稽拉取
 *
 * 方向：H2-5 拉 H1（与 h1CipH2Pull 的 H1 拉 H2 互补，闭合双向环）。
 *
 * 数据来源（H1 checklist_responses）：
 * - H1-7-rows：固定资产增加检查表，additionMethod 命中「在建工程转入」的行，
 *   originalCost = H1 实际入账原值，name/assetCategory/voucherNo 供匹配与追溯。
 *
 * 审计意义：H2-5「本期已转固」各工程的转固金额应与 H1 实际入账原值一致；
 * 差异需查明（分期入账 / 金额录入错误 / 漏入账 / 误转），并在 H2-5 差异列高亮。
 */
import { api } from '@/services/apiProxy'

/** 从 H1 提取的一条 CIP 转入固定资产记录 */
export interface H1CipAddition {
  name: string
  /** H1 实际入账原值 */
  recordedAmount: number
  assetCategory: string
  voucherNo: string
}

export interface H1CipAdditionPullResult {
  status: 'ok' | 'wp_missing' | 'empty' | 'error'
  message: string
  h1WpId: string | null
  /** H1「在建工程转入」入账原值合计 */
  recordedTotal: number
  rows: H1CipAddition[]
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

/** 判断增加方式是否为「在建工程转入」（与 useH1AdditionCheck.isCipTransferMethod 口径一致） */
export function isCipTransferMethod(method: unknown): boolean {
  const m = String(method || '').trim()
  return m === '在建工程转入' || m === 'cip' || m === '在建转入' || m.includes('在建')
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
 * 纯函数：从 H1-7 增加检查行数组提取「在建工程转入」入账记录。
 */
export function extractH1CipAdditions(rowsRaw: unknown): { total: number; rows: H1CipAddition[] } {
  const list = Array.isArray(rowsRaw) ? rowsRaw : []
  const rows: H1CipAddition[] = []
  let total = 0
  for (const r of list) {
    if (!r || r.isSubtotal || r.isTotal) continue
    if (!isCipTransferMethod(r.additionMethod)) continue
    const amt = parseNum(r.originalCost ?? r.amount)
    if (amt === 0) continue
    total += amt
    rows.push({
      name: String(r.name || r.assetName || r.projectName || '固定资产'),
      recordedAmount: amt,
      assetCategory: String(r.assetCategory || r.category || ''),
      voucherNo: String(r.voucherNo || r.voucher_no || ''),
    })
  }
  return { total, rows }
}

function _normName(s: unknown): string {
  return String(s || '').replace(/\s+/g, '').toLowerCase()
}

/**
 * 纯函数：按工程/资产名称匹配 H1 入账记录（精确 → 双向包含），返回命中记录或 null。
 */
export function matchH1AmountByName(
  targetName: string,
  h1Rows: H1CipAddition[],
): H1CipAddition | null {
  const t = _normName(targetName)
  if (!t) return null
  let hit = h1Rows.find((r) => _normName(r.name) === t)
  if (hit) return hit
  hit = h1Rows.find((r) => {
    const n = _normName(r.name)
    return n.includes(t) || t.includes(n)
  })
  return hit ?? null
}

/** 拉取同项目 H1「在建工程转入」入账记录，供 H2-5 反向勾稽 */
export async function pullH1CipAdditionsForH2(projectId: string): Promise<H1CipAdditionPullResult> {
  const base: H1CipAdditionPullResult = {
    status: 'error',
    message: '',
    h1WpId: null,
    recordedTotal: 0,
    rows: [],
  }
  if (!projectId) return { ...base, message: '缺少 projectId' }

  const h1WpId = await resolveWpId(projectId, 'H1')
  if (!h1WpId) {
    return { ...base, status: 'wp_missing', message: '项目中未找到 H1 固定资产底稿' }
  }

  try {
    const item = await loadResponseItem(h1WpId, 'H1-7-rows')
    const { total, rows } = extractH1CipAdditions(parseRemark(item?.remark))
    if (rows.length === 0) {
      return {
        ...base,
        status: 'empty',
        message: 'H1-7 暂无「在建工程转入」入账记录，请先编制 H1-7 增加检查',
        h1WpId,
      }
    }
    return {
      status: 'ok',
      message: `已从 H1-7 取转入固定资产入账合计 ${total.toLocaleString('zh-CN')}（${rows.length} 项）`,
      h1WpId,
      recordedTotal: total,
      rows,
    }
  } catch (e: any) {
    return { ...base, status: 'error', message: e?.message || '拉取 H1 失败', h1WpId }
  }
}

export interface H2H1TransferReconcile {
  /** H2-5 本期转固金额合计 */
  h2TransferTotal: number
  /** H1「在建工程转入」入账原值合计 */
  h1RecordedTotal: number
  diff: number
  matched: boolean
  tolerance: number
}

/** H2-5 转固合计 vs H1 入账合计 勾稽（容差默认 1 元） */
export function buildH2H1TransferReconcile(
  h2TransferTotal: number,
  h1RecordedTotal: number,
  tolerance = 1,
): H2H1TransferReconcile {
  const diff = parseNum(h2TransferTotal) - parseNum(h1RecordedTotal)
  return {
    h2TransferTotal: parseNum(h2TransferTotal),
    h1RecordedTotal: parseNum(h1RecordedTotal),
    diff,
    matched: Math.abs(diff) < tolerance,
    tolerance,
  }
}
