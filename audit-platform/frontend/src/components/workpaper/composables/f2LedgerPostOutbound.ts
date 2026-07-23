/**
 * F2 期后出库取数（复用 useD2Detail 期后回款序时账范式：fetch + Authorization）
 *
 * 审计意义：查次年（资产负债表日之后）序时账存货科目**贷方**发生额 = 期后出库，
 * 按存货名称归集，用于评估期末存货可变现性 / 存货减值信号 / 出库结转成本勾稽。
 *
 * 数据源：GET /api/projects/{pid}/ledger/entries/{accountCode}
 *   ?year={bsYear+1}&date_from={bsYear+1}-01-01&date_to=（次年前 monthsAfter 月末）&limit=1000
 *   贷方 credit_amount = 存货减少（发出 / 领用 / 销售出库）。
 *   取数方式对齐 useD2Detail.importPostPaymentFromLedger：fetch + sessionStorage token。
 *
 * 优雅降级：无 projectId/年度/科目 → error；HTTP 非 2xx / 期后无分录 → empty；异常 → error。
 */

/** 无法归集到具体存货名称时的兜底桶名 */
export const UNMATCHED_NAME = '未匹配存货'

export interface PostPeriodOutboundEntry {
  credit_amount?: number
  credit_qty?: number
  credit_quantity?: number
  summary?: string
  counterpart_account?: string
  aux_name?: string
  [k: string]: unknown
}

/** 单个存货的期后出库归集值：金额 + 数量 */
export interface OutboundAgg {
  amount: number
  qty: number
}

export interface PostPeriodOutboundResult {
  status: 'ok' | 'empty' | 'error'
  /** 原始期后出库分录（贷方） */
  entries: PostPeriodOutboundEntry[]
  /** 按规范化存货名称归集：name → {金额, 数量} 合计 */
  byName: Record<string, OutboundAgg>
  /** 期后出库贷方金额合计 */
  totalAmount: number
  /** 期后出库数量合计 */
  totalQty: number
  /** 归入「未匹配存货」桶的分录数 */
  unmatchedCount: number
  message: string
}

export interface PostOutboundOptions {
  /** 取数窗口月数（默认 6，覆盖典型审计报告日；窗口 = 次年 01-01 至 次年第 monthsAfter 月末） */
  monthsAfter?: number
}

function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 纯函数：存货名称规范化。
 * - 去除首尾/中间空白与全角空格（\u3000）
 * - 转小写
 *
 * 幂等：normalizeInvName(normalizeInvName(x)) === normalizeInvName(x)
 * （规范化后不再含空白/全角空格，二次应用为恒等）。
 */
export function normalizeInvName(name: string): string {
  return String(name ?? '')
    .replace(/[\s\u3000]+/g, '')
    .toLowerCase()
}

/**
 * 从序时账分录解析存货名称（原始，未规范化）。
 * 优先辅助核算名称，其次摘要 / 对方科目。
 */
function resolveInvName(entry: PostPeriodOutboundEntry): string {
  const candidates = [entry?.aux_name, entry?.summary, entry?.counterpart_account]
  for (const c of candidates) {
    const s = String(c ?? '').trim()
    if (s) return s
  }
  return ''
}

/**
 * 纯函数：把序时账分录按规范化存货名称归集贷方金额+数量。
 * - 仅取 credit_amount > 0 的分录（贷方 = 出库）
 * - 无名称的分录归入 UNMATCHED_NAME 桶
 *
 * 不变式（Property 5）：Σ byName[*].amount === 输入全部 credit_amount>0 分录贷方合计 === totalAmount，
 * 故归集金额守恒。
 */
export function aggregateOutboundByName(entries: PostPeriodOutboundEntry[]): {
  byName: Record<string, OutboundAgg>
  totalAmount: number
  totalQty: number
  unmatchedCount: number
} {
  const list = Array.isArray(entries) ? entries : []
  const byName: Record<string, OutboundAgg> = {}
  let totalAmount = 0
  let totalQty = 0
  let unmatchedCount = 0

  for (const e of list) {
    const amount = parseNum(e?.credit_amount)
    if (amount <= 0) continue
    const qty = parseNum(e?.credit_qty ?? e?.credit_quantity)
    const rawName = resolveInvName(e)
    const key = normalizeInvName(rawName) || UNMATCHED_NAME
    if (key === UNMATCHED_NAME) unmatchedCount++
    if (!byName[key]) byName[key] = { amount: 0, qty: 0 }
    byName[key].amount += amount
    byName[key].qty += qty
    totalAmount += amount
    totalQty += qty
  }

  return { byName, totalAmount, totalQty, unmatchedCount }
}

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

/** 次年第 monthsAfter 月末（monthsAfter 归一到 1..12） */
function windowEnd(postYear: number, monthsAfter: number): string {
  const m = Math.min(Math.max(Math.trunc(monthsAfter) || 6, 1), 12)
  const lastDay = new Date(postYear, m, 0).getDate() // 第 m 月最后一天
  return `${postYear}-${pad2(m)}-${pad2(lastDay)}`
}

/**
 * 拉取期后（次年）存货科目贷方发生额并按名称归集。
 *
 * @param projectId 项目 ID
 * @param bsYear 资产负债表年度（取数取 bsYear+1）
 * @param accountCode 存货科目（如 1405 库存商品 / 1411 原材料 等）
 * @param opts 取数窗口（monthsAfter 默认 6）
 */
export async function pullPostPeriodOutbound(
  projectId: string,
  bsYear: number,
  accountCode: string,
  opts: PostOutboundOptions = {},
): Promise<PostPeriodOutboundResult> {
  const empty: PostPeriodOutboundResult = {
    status: 'error',
    entries: [],
    byName: {},
    totalAmount: 0,
    totalQty: 0,
    unmatchedCount: 0,
    message: '',
  }
  if (!projectId) return { ...empty, message: '缺少 projectId' }
  if (!bsYear || !Number.isFinite(Number(bsYear))) return { ...empty, message: '缺少有效资产负债表年度' }
  if (!accountCode) return { ...empty, message: '缺少存货科目' }

  const postYear = Number(bsYear) + 1
  const monthsAfter = opts.monthsAfter ?? 6
  const dateFrom = `${postYear}-01-01`
  const dateTo = windowEnd(postYear, monthsAfter)

  try {
    const token = sessionStorage.getItem('token') || ''
    const url = `/api/projects/${projectId}/ledger/entries/${accountCode}?year=${postYear}`
      + `&date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}&limit=1000`
    const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    if (!resp || !resp.ok) {
      return { ...empty, status: 'empty', message: `期后（${postYear}年）序时账无数据或未导入` }
    }
    const result = await resp.json()
    const payload = result?.data ?? result
    const items: PostPeriodOutboundEntry[] = Array.isArray(payload)
      ? payload
      : Array.isArray(payload?.items)
        ? payload.items
        : Array.isArray(payload?.ledger?.items)
          ? payload.ledger.items
          : []

    if (items.length === 0) {
      return {
        ...empty,
        status: 'empty',
        message: `期后（${dateFrom} 至 ${dateTo}）无 ${accountCode} 出库分录`,
      }
    }

    const { byName, totalAmount, totalQty, unmatchedCount } = aggregateOutboundByName(items)
    return {
      status: 'ok',
      entries: items,
      byName,
      totalAmount,
      totalQty,
      unmatchedCount,
      message: `期后出库归集 ${Object.keys(byName).length} 项，合计贷方 ${totalAmount.toLocaleString('zh-CN')}`,
    }
  } catch (e: any) {
    return { ...empty, status: 'error', message: e?.message || '期后出库取数失败' }
  }
}
