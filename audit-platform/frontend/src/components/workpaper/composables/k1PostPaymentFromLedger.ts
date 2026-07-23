/**
 * K1 期后回款 — 从序时账 1221 贷方取数并按债务人名称归集
 *
 * 对齐 D2 importPostPaymentFromLedger 范式：科目改为 1221，窗口自 bs_date 起 N 个月。
 */
import { ElMessage, ElMessageBox } from 'element-plus'

export interface K1PostPaymentTargetRow {
  id: string
  name: string
}

export interface K1PostPaymentFetchResult {
  matched: number
  filledAmount: number
  unmatchedCount: number
  unmatchedAmount: number
  /** rowId → 归集金额 */
  amounts: Map<string, number>
  cancelled: boolean
}

function normalizeName(s: string): string {
  return String(s || '')
    .replace(/\s+/g, '')
    .replace(/[（）()·.•]/g, '')
    .toLowerCase()
}

function fmtAmt(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/**
 * 拉取 1221 期后贷方收款并按债务人名归集。
 * 弹出确认框；用户取消时 cancelled=true、amounts 为空。
 */
export async function fetchK1PostPaymentFromLedger(opts: {
  projectId: string
  bsDate: string
  rows: K1PostPaymentTargetRow[]
  monthsAfter?: number
  confirm?: boolean
}): Promise<K1PostPaymentFetchResult> {
  const empty: K1PostPaymentFetchResult = {
    matched: 0,
    filledAmount: 0,
    unmatchedCount: 0,
    unmatchedAmount: 0,
    amounts: new Map(),
    cancelled: false,
  }

  if (!opts.rows.length) {
    ElMessage.info('请先录入或导入明细债务人后再取期后回款')
    return empty
  }
  if (!opts.projectId) {
    ElMessage.warning('缺少项目信息，无法取数')
    return empty
  }

  let bs = (opts.bsDate || '').trim()
  if (!/^\d{4}-\d{2}-\d{2}$/.test(bs)) {
    ElMessage.warning('资产负债表日无效，无法确定期后回款窗口')
    return empty
  }

  const monthsAfter = opts.monthsAfter ?? 6
  const start = new Date(`${bs}T00:00:00`)
  start.setDate(start.getDate() + 1)
  const end = new Date(start)
  end.setMonth(end.getMonth() + monthsAfter)
  const dateFrom = fmtDate(start)
  const dateTo = fmtDate(end)
  const postYear = start.getFullYear()

  try {
    const token = sessionStorage.getItem('token') || ''
    const url =
      `/api/projects/${opts.projectId}/ledger/entries/1221?year=${postYear}` +
      `&date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}&limit=1000`
    const resp = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!resp.ok) {
      ElMessage.info(`期后（${postYear}年）序时账无数据或未导入`)
      return empty
    }
    const result = await resp.json()
    const payload = result?.data ?? result
    const items: any[] = Array.isArray(payload)
      ? payload
      : Array.isArray(payload?.items)
        ? payload.items
        : Array.isArray(payload?.ledger?.items)
          ? payload.ledger.items
          : []

    if (items.length === 0) {
      ElMessage.info(`期后（${dateFrom} 至 ${dateTo}）无 1221 收款分录`)
      return empty
    }

    const rowSums = new Map<string, number>()
    let unmatchedCount = 0
    let unmatchedAmount = 0

    for (const it of items) {
      const credit = Number(it.credit_amount) || 0
      if (credit <= 0) continue
      const text = normalizeName(
        `${it.summary ?? ''} ${it.counterpart_account ?? ''} ${it.aux_name ?? ''}`,
      )
      let hit: K1PostPaymentTargetRow | null = null
      for (const row of opts.rows) {
        const name = normalizeName(row.name)
        if (name.length >= 2 && text.includes(name)) {
          hit = row
          break
        }
      }
      if (hit) {
        rowSums.set(hit.id, (rowSums.get(hit.id) || 0) + credit)
      } else {
        unmatchedCount++
        unmatchedAmount += credit
      }
    }

    const matched = rowSums.size
    const filledAmount = Array.from(rowSums.values()).reduce((s, v) => s + v, 0)

    if (matched === 0 && unmatchedCount === 0) {
      ElMessage.info('期后窗口内无收款分录')
      return empty
    }

    if (opts.confirm !== false) {
      try {
        await ElMessageBox.confirm(
          `期后窗口 ${dateFrom} 至 ${dateTo}（${postYear}年）：\n` +
            `可归集 ${matched} 户，合计回款 ${fmtAmt(filledAmount)} 元；\n` +
            `未匹配 ${unmatchedCount} 笔，合计 ${fmtAmt(unmatchedAmount)} 元（需手工分配）。\n` +
            `确认后将按债务人填入「期后收款」列，是否继续？`,
          '期后回款取数确认',
          {
            confirmButtonText: '填入',
            cancelButtonText: '取消',
            type: 'warning',
          },
        )
      } catch {
        return { ...empty, cancelled: true }
      }
    }

    ElMessage.success(
      `期后回款取数完成：填入 ${matched} 户，合计 ${fmtAmt(filledAmount)} 元`,
    )
    return {
      matched,
      filledAmount,
      unmatchedCount,
      unmatchedAmount,
      amounts: rowSums,
      cancelled: false,
    }
  } catch {
    ElMessage.error('期后回款取数失败，请稍后重试')
    return empty
  }
}

/** 从 year / bsDate 解析资产负债表日 */
export function resolveK1BsDate(bsDate?: string | null, year?: number | string | null): string {
  const direct = String(bsDate || '').trim()
  if (/^\d{4}-\d{2}-\d{2}$/.test(direct)) return direct
  const y = Number(year)
  if (Number.isFinite(y) && y >= 2000 && y <= 2100) return `${y}-12-31`
  return ''
}
