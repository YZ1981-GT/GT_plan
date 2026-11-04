/**
 * 凭证 ↔ 底稿之间的导航地址（spec voucher-workflow-linkage-lineage-closure R3.5 / R3.7，design §5.4~5.5）。
 *
 * - `ledgerRouteOfVoucherKey`：凭证键 + 科目 → 序时账凭证层地址（与序时账页同步地址同一套键，`buildLedgerQuery`）；
 *   底稿待导入提示、抽样增强页等共用。凭证键解析不了或没有科目时返回 null（调用方不显示入口）。
 * - `workpaperRouteFromLedger`：序时账 → 底稿编辑页，带返回地址；从挂凭结果打开时再带 `from=voucher-attach`
 *   （底稿顶部的待导入提示据此默认展开）。
 * - `safeReturnTo`：返回地址只接受本站以 `/projects/` 开头的路径（防开放跳转：协议、`//`、反斜杠都拒绝）。
 */
import type { RouteLocationRaw } from 'vue-router'
import { buildLedgerQuery } from '@/composables/useLedgerUrlSync'

export const FROM_VOUCHER_ATTACH = 'voucher-attach'

/** 解析凭证键规范串（5 元素 JSON 数组）；格式不对返回 null */
export function parseVoucherKeyParts(voucherKey: string | null | undefined): [string, string, string, string, string] | null {
  if (!voucherKey) return null
  try {
    const parts = JSON.parse(voucherKey)
    if (!Array.isArray(parts) || parts.length !== 5 || !parts.every(p => typeof p === 'string')) return null
    const [year, , date, , no] = parts as string[]
    if (!/^\d{4}$/.test(year) || !/^\d{4}-\d{2}-\d{2}$/.test(date) || !no) return null
    return parts as [string, string, string, string, string]
  } catch {
    return null
  }
}

/**
 * 凭证键 → 序时账凭证层地址。必须给科目：序时账页从地址恢复凭证层要求科目（面包屑「科目 序时账」），
 * 没有科目的地址只会落到科目余额表 ⇒ 返回 null，调用方不显示入口。
 */
export function ledgerRouteOfVoucherKey(
  projectId: string,
  voucherKey: string | null | undefined,
  opts: { accountCode?: string | null } = {},
): RouteLocationRaw | null {
  const parts = parseVoucherKeyParts(voucherKey)
  const account = (opts.accountCode ?? '').trim()
  if (!projectId || !parts || !account) return null
  const [year, company, date, type, no] = parts
  return {
    name: 'LedgerPenetration',
    params: { projectId },
    query: buildLedgerQuery({
      level: 'voucher',
      account,
      voucherNo: no,
      voucherDate: date,
      voucherType: type,
      voucherCompany: company,
    }, year),
  }
}

export function workpaperRouteFromLedger(
  projectId: string,
  workpaperId: string,
  opts: { returnTo?: string | null; fromAttach?: boolean } = {},
): RouteLocationRaw {
  const query: Record<string, string> = {}
  const back = safeReturnTo(opts.returnTo)
  if (back) query.returnTo = back
  if (opts.fromAttach) query.from = FROM_VOUCHER_ATTACH
  return { name: 'WorkpaperEditor', params: { projectId, wpId: workpaperId }, query }
}

/**
 * 底稿页「返回」按钮的文字：按返回地址说回哪里（序时账 / 上一张底稿，他稿结论弹层打开底稿时带的是当前底稿页）；
 * 没有安全的返回地址或认不出是哪类页面时只写「返回」。
 */
export function returnLabelOf(raw: unknown): string {
  const back = safeReturnTo(raw)
  const path = back ? back.split(/[?#]/)[0] : ''
  if (/^\/projects\/[^/]+\/ledger\/?$/.test(path)) return '← 返回序时账'
  if (/^\/projects\/[^/]+\/workpapers\/[^/]+\/edit\/?$/.test(path)) return '← 返回上一张底稿'
  return '← 返回'
}

/** 返回地址白名单：本站 `/projects/...` 路径；其余（外站、协议、`//`、反斜杠、控制字符）一律 null */
export function safeReturnTo(raw: unknown): string | null {
  const value = Array.isArray(raw) ? raw[0] : raw
  if (typeof value !== 'string' || !value.startsWith('/projects/')) return null
  if (value.includes('//') || value.includes('\\') || /[\u0000-\u001f]/.test(value)) return null
  return value
}
