/**
 * H2-10 利息资本化（无专门借款）↔ L1 短期借款 借款明细拉取
 *
 * 数据来源（L1 checklist_responses，逐单元格 item_id）：
 * - L1-int-{n}-{field}：L1-5 利息测算表行，field ∈ {bank, contractNo, loanStart,
 *   loanEnd, rate, principal, days, calculatedInterest, bookedInterest ...}。
 *
 * 审计意义：无专门借款情形下，一般借款加权资本化率的本金/利率/账面利息应与
 * L1 短期借款实测数据一致，避免在 H2-10 重复手工录入且口径不一致。短期借款本身
 * 即"一般借款"，故映射进 H2-10 一般借款表语义正确（专门借款判断仍由 H2-11 承担）。
 */
import { api } from '@/services/apiProxy'

/** 从 L1-5 重建的一条借款测算记录 */
export interface L1LoanRow {
  bank: string
  contractNo: string
  principal: number
  /** 年利率（原始口径，可能为小数 0.05 或百分数 5） */
  rate: number
  days: number
  /** 测算利息 */
  calculatedInterest: number
  /** 账载利息 */
  bookedInterest: number
  loanStart: string
  loanEnd: string
}

export interface L1LoanPullResult {
  status: 'ok' | 'wp_missing' | 'empty' | 'error'
  message: string
  l1WpId: string | null
  /** 本金合计 */
  principalTotal: number
  rows: L1LoanRow[]
}

function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
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

async function loadResponses(wpId: string): Promise<any[]> {
  try {
    const res = await api.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
    return Array.isArray(res) ? res : (res?.data ?? [])
  } catch {
    return []
  }
}

/**
 * 纯函数：从 L1 checklist_responses 列表重建 L1-5 利息测算行。
 * 逐单元格 item_id `L1-int-{n}-{field}` 按行号 n 归并。
 */
export function reconstructL1InterestRows(responses: any[]): L1LoanRow[] {
  const pattern = /^L1-int-(\d+)-(\w+)$/
  const byRow = new Map<number, Record<string, string>>()
  for (const r of responses || []) {
    const m = pattern.exec(String(r?.item_id ?? ''))
    if (!m) continue
    const n = Number(m[1])
    const field = m[2]
    const val = r?.remark
    if (val == null || val === '') continue
    if (!byRow.has(n)) byRow.set(n, {})
    byRow.get(n)![field] = String(val)
  }
  const rows: L1LoanRow[] = []
  for (const n of [...byRow.keys()].sort((a, b) => a - b)) {
    const cells = byRow.get(n)!
    const principal = parseNum(cells['principal'])
    const bank = String(cells['bank'] ?? '')
    const contractNo = String(cells['contractNo'] ?? '')
    // 全空行跳过
    if (principal === 0 && !bank && !contractNo) continue
    rows.push({
      bank,
      contractNo,
      principal,
      rate: parseNum(cells['rate']),
      days: parseNum(cells['days']),
      calculatedInterest: parseNum(cells['calculatedInterest']),
      bookedInterest: parseNum(cells['bookedInterest']),
      loanStart: String(cells['loanStart'] ?? ''),
      loanEnd: String(cells['loanEnd'] ?? ''),
    })
  }
  return rows
}

/** 拉取同项目 L1 短期借款测算明细，供 H2-10 一般借款表带入 */
export async function pullL1LoansForH2(projectId: string): Promise<L1LoanPullResult> {
  const base: L1LoanPullResult = {
    status: 'error',
    message: '',
    l1WpId: null,
    principalTotal: 0,
    rows: [],
  }
  if (!projectId) return { ...base, message: '缺少 projectId' }

  const l1WpId = await resolveWpId(projectId, 'L1')
  if (!l1WpId) {
    return { ...base, status: 'wp_missing', message: '项目中未找到 L1 短期借款底稿' }
  }

  try {
    const responses = await loadResponses(l1WpId)

    // 优先从 L1-L1-5-rows JSON 数组读取（L1 利息测算已改为 JSON 存储）
    let rows = reconstructFromJsonKey(responses)
    // 回退：从旧 flat keys L1-int-{n}-{field} 重建
    if (rows.length === 0) {
      rows = reconstructL1InterestRows(responses)
    }
    rows = rows.filter((r) => r.principal > 0)

    if (rows.length === 0) {
      return {
        ...base,
        status: 'empty',
        message: 'L1-5 利息测算暂无借款明细，请先编制 L1 短期借款',
        l1WpId,
      }
    }
    const principalTotal = rows.reduce((s, r) => s + r.principal, 0)
    return {
      status: 'ok',
      message: `已从 L1-5 取借款 ${rows.length} 笔（本金合计 ${principalTotal.toLocaleString('zh-CN')}）`,
      l1WpId,
      principalTotal,
      rows,
    }
  } catch (e: any) {
    return { ...base, status: 'error', message: e?.message || '拉取 L1 失败', l1WpId }
  }
}

/**
 * 从 L1-L1-5-rows JSON 数组重建（L1 改 JSON 存储后的新格式）。
 * checklist_responses 里 item_id='L1-L1-5-rows' 的 remark 字段存 JSON 数组。
 */
function reconstructFromJsonKey(responses: any[]): L1LoanRow[] {
  const entry = responses.find(
    (r: any) => r?.item_id === 'L1-L1-5-rows',
  )
  if (!entry) return []
  const raw = entry.remark ?? entry.conclusion
  if (!raw || typeof raw !== 'string') return []
  try {
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr)) return []
    const rows: L1LoanRow[] = []
    for (const item of arr) {
      if (!item || typeof item !== 'object') continue
      const principal = parseNum(item.principal ?? item.loanAmount)
      const bank = String(item.bank ?? item.lender ?? '')
      const contractNo = String(item.contractNo ?? '')
      if (principal === 0 && !bank && !contractNo) continue
      rows.push({
        bank,
        contractNo,
        principal,
        rate: parseNum(item.rate ?? item.annualRate),
        days: parseNum(item.days ?? item.interestDays),
        calculatedInterest: parseNum(item.calculatedInterest ?? item.expectedInterest),
        bookedInterest: parseNum(item.bookedInterest ?? item.accountedInterest ?? item.actualInterest),
        loanStart: String(item.loanStart ?? item.startDate ?? ''),
        loanEnd: String(item.loanEnd ?? item.endDate ?? ''),
      })
    }
    return rows
  } catch {
    return []
  }
}

/**
 * 纯函数：把 L1 年利率归一化为 H2 LoanItem 口径（百分数）。
 * L1 引擎年利率为小数（0.05=5%）；若已是百分数（>1）则原样返回。
 */
export function normalizeL1RateToPercent(rate: number): number {
  const r = parseNum(rate)
  if (r === 0) return 0
  return r <= 1 ? r * 100 : r
}
