/**
 * assetLedgerMovementPull — 资产类底稿从序时账按科目取本期增减变动
 *
 * 用途：H1-2/H2-2/H4-2 明细表「从序时账取数」按钮
 * 取 /api/projects/{pid}/ledger/entries/{code} 全期→按 account_name 聚合借方(增加)/贷方(减少)
 *
 * 资产类科目方向铁律：借方=增加、贷方=减少
 * 纯前端游标分页聚合，不新增后端 resolver
 */
import http from '@/utils/http'

export interface AssetMovementRow {
  /** 明细科目名称 */
  name: string
  /** 本期增加 = Σ debit_amount（资产借方=增加） */
  increase: number
  /** 本期减少 = Σ credit_amount（资产贷方=减少） */
  decrease: number
}

export interface AssetMovementPullResult {
  ok: boolean
  message: string
  rows: AssetMovementRow[]
  /** 全部科目合计增加 */
  totalIncrease: number
  /** 全部科目合计减少 */
  totalDecrease: number
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 从序时账拉取某科目全年分录，按 account_name 聚合借方(增加)/贷方(减少)
 *
 * @param projectId 项目 ID
 * @param year 审计年度
 * @param accountCode 科目编码（H1=1601, H2=1604, H4=1605）
 * @param opts.pageSize 每页条数（默认 2000）
 * @param opts.maxPages 安全上限页数（默认 50）
 */
export async function pullAssetMovementFromLedger(
  projectId: string,
  year: number,
  accountCode: string,
  opts?: { pageSize?: number; maxPages?: number },
): Promise<AssetMovementPullResult> {
  if (!projectId || !year || !accountCode) {
    return { ok: false, message: '缺少项目/年度/科目参数', rows: [], totalIncrease: 0, totalDecrease: 0 }
  }

  const pageSize = opts?.pageSize ?? 2000
  const maxPages = opts?.maxPages ?? 50

  const byName = new Map<string, { increase: number; decrease: number }>()
  let totalIncrease = 0
  let totalDecrease = 0

  try {
    let page = 1
    let hasMore = true

    while (hasMore && page <= maxPages) {
      const res = await http.get(
        `/api/projects/${projectId}/ledger/entries/${encodeURIComponent(accountCode)}`,
        { params: { year, page, page_size: pageSize }, _silent: true } as any,
      )

      // 兼容信封解包：http 拦截器解包 {code,data} → res.data 即 payload
      const payload = res.data?.data ?? res.data ?? {}
      const items: any[] = Array.isArray(payload.items)
        ? payload.items
        : Array.isArray(payload)
          ? payload
          : []

      for (const it of items) {
        const name = String(it.account_name ?? it.accountName ?? '').trim() || '未命名'
        const debit = num(it.debit_amount ?? it.debit)
        const credit = num(it.credit_amount ?? it.credit)

        if (!byName.has(name)) byName.set(name, { increase: 0, decrease: 0 })
        const acc = byName.get(name)!
        acc.increase += debit
        acc.decrease += credit
        totalIncrease += debit
        totalDecrease += credit
      }

      // 判断是否还有更多
      if (items.length < pageSize) {
        hasMore = false
      } else {
        page += 1
      }
    }
  } catch (e: any) {
    return {
      ok: false,
      message: e?.response?.data?.detail || e?.message || '序时账取数失败',
      rows: [],
      totalIncrease: 0,
      totalDecrease: 0,
    }
  }

  // 过滤掉增减都为 0 的空科目
  const rows: AssetMovementRow[] = [...byName.entries()]
    .map(([name, { increase, decrease }]) => ({ name, increase, decrease }))
    .filter((r) => Math.abs(r.increase) > 0.005 || Math.abs(r.decrease) > 0.005)

  if (!rows.length) {
    return {
      ok: false,
      message: `未从序时账取到科目 ${accountCode} 的 ${year} 年度增减变动`,
      rows: [],
      totalIncrease: 0,
      totalDecrease: 0,
    }
  }

  return {
    ok: true,
    message: `已从序时账聚合 ${rows.length} 个明细科目的增减变动`,
    rows,
    totalIncrease,
    totalDecrease,
  }
}
