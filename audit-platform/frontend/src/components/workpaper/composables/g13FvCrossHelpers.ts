/**
 * G13 公允测试差异跨底稿推送 + G13-2/G13-3 调整数勾稽
 *
 * - G1-6 / G10-5 → G13-3：按指纹幂等写入 6101↔对方科目分录对
 * - G13-2 明细「调整数」按所属科目汇总 vs G13-3 账项回写净额
 */
import { api } from '@/services/apiProxy'
import { parseNum } from './useG13FormulaEngine'
import {
  aggregateG13AdjustmentByBelong,
  type G13AdjustmentEntryLike,
  type G13AdjustmentWritebackMap,
} from './g13AdjStorage'
import { G13_ACCOUNT_CODE, G13_BELONG_ACCOUNT_LABELS, G13_BELONG_ACCOUNTS } from './g13Constants'

export const G13_AJE_ITEM_ID = 'G13-aje-rows'
export const G13_FV_DIFF_THRESHOLD = 0.01
export const G13_FV_PUSH_EVENT = 'g13:fv-diff-pushed'

export type G13FvBelong = 'G1' | 'G8' | 'G9' | 'G10' | 'H3' | 'other'
export type G13FvPushSource = 'G1-6' | 'G10-5' | string

export interface G13FvPushItem {
  /** 调整事项说明 */
  description: string
  /**
   * 差异金额符号约定：
   * - G1（资产）：测试值−账面 >0 → 资产升值 → 贷 6101
   * - G10（负债）：审定−未审 >0 → 负债增加 → 借 6101
   */
  amount: number
  belongAccount: G13FvBelong
  indexRef?: string
  remark?: string
  /** 证券/负债名称，用于指纹 */
  nameKey?: string
}

export interface G13AdjWritebackMismatch {
  belong: string
  label: string
  detailAdj: number
  g13Net: number
  diff: number
}

function genRowId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function buildG13FvAdjFingerprint(
  nameKey: string,
  amount: number,
  source: G13FvPushSource,
): string {
  const key = String(nameKey || 'unnamed').trim().toLowerCase().replace(/\s+/g, '')
  return `fvfp:${source}:${key}:${Math.round(Math.abs(parseNum(amount)) * 100)}`
}

function rowHasFvFingerprint(row: Record<string, unknown>, fp: string): boolean {
  return String(row.remark || '').includes(fp)
}

/** 资产侧（G1）：正差贷 6101 / 借 1501；负债侧（G10）：正差借 6101 / 贷 2101 */
function counterAccountForBelong(belong: G13FvBelong): { code: string; name: string } {
  if (belong === 'G10') return { code: '2101', name: '交易性金融负债' }
  if (belong === 'G8') return { code: '1504', name: '其他非流动金融资产' }
  if (belong === 'G9') return { code: '1501', name: '衍生工具' }
  if (belong === 'H3') return { code: '1521', name: '投资性房地产' }
  return { code: '1501', name: '交易性金融资产' }
}

function isLiabilityBelong(belong: G13FvBelong): boolean {
  return belong === 'G10'
}

/**
 * 将公允差异合并进 G13-3 行数组（纯函数，指纹去重后追加借贷对）。
 * @returns addedCount = 推送的「差异笔数」（每笔 2 行分录）
 */
export function mergeFvDiffIntoG13AdjRows(
  existing: Record<string, unknown>[],
  items: G13FvPushItem[],
  source: G13FvPushSource,
): { rows: Record<string, unknown>[]; addedCount: number } {
  const material = items.filter((it) => Math.abs(parseNum(it.amount)) >= G13_FV_DIFF_THRESHOLD)
  if (!material.length) return { rows: existing, addedCount: 0 }

  const fingerprints = material.map((it) =>
    buildG13FvAdjFingerprint(it.nameKey || it.description, it.amount, source),
  )

  let next = existing.filter((r) => !fingerprints.some((fp) => rowHasFvFingerprint(r, fp)))
  const added: Record<string, unknown>[] = []
  const today = new Date().toISOString().slice(0, 10)

  material.forEach((it, i) => {
    const amt = Math.abs(parseNum(it.amount))
    const signed = parseNum(it.amount)
    const fp = fingerprints[i]
    const belong = (it.belongAccount || 'other') as G13FvBelong
    const counter = counterAccountForBelong(belong)
    const liability = isLiabilityBelong(belong)
    // 负债正差：借 6101；资产正差：贷 6101
    const plDebit = liability ? (signed > 0 ? amt : 0) : (signed > 0 ? 0 : amt)
    const plCredit = liability ? (signed > 0 ? 0 : amt) : (signed > 0 ? amt : 0)

    const baseRemark = `${it.remark || `来源 ${source}`}|${fp}`
    const desc = it.description || `${source} 公允测试差异`

    added.push({
      rowId: genRowId('g13fv'),
      description: desc,
      category: '账项调整',
      reportItem: '公允价值变动收益',
      accountName: '公允价值变动收益',
      accountCode: G13_ACCOUNT_CODE,
      noteItem: '',
      debitAmount: plDebit,
      creditAmount: plCredit,
      indexRef: it.indexRef || source,
      remark: baseRemark,
      belongAccount: belong,
      entryType: 'AJE',
      date: today,
      preparedBy: '',
    })
    added.push({
      rowId: genRowId('g13fv'),
      description: `${desc}（对方科目）`,
      category: '账项调整',
      reportItem: counter.name,
      accountName: counter.name,
      accountCode: counter.code,
      noteItem: '',
      debitAmount: plCredit,
      creditAmount: plDebit,
      indexRef: it.indexRef || source,
      remark: baseRemark,
      belongAccount: belong,
      entryType: 'AJE',
      date: today,
      preparedBy: '',
    })
  })

  return { rows: [...next, ...added], addedCount: material.length }
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

async function loadG13AdjRows(wpId: string): Promise<Record<string, unknown>[]> {
  try {
    const res = await api.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const item = list.find((r) => r.item_id === G13_AJE_ITEM_ID)
    if (!item?.remark) return []
    const parsed = JSON.parse(item.remark)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

async function saveG13AdjRows(
  wpId: string,
  projectId: string,
  rows: Record<string, unknown>[],
): Promise<boolean> {
  try {
    await api.put(`/api/workpapers/${wpId}/checklist-responses`, {
      project_id: projectId,
      items: [{
        item_id: G13_AJE_ITEM_ID,
        conclusion: null,
        remark: JSON.stringify(rows),
      }],
    }, { _silent: true } as any)
    return true
  } catch {
    return false
  }
}

/**
 * 跨底稿：将 G1-6 / G10-5 公允差异推送到同项目 G13-3。
 * 指纹去重；成功后派发 g13:fv-diff-pushed。
 */
export async function pushSourceFvDiffToG13(opts: {
  projectId: string
  items: G13FvPushItem[]
  source: G13FvPushSource
}): Promise<{ ok: boolean; count: number; message: string }> {
  const { projectId, items, source } = opts
  if (!projectId) return { ok: false, count: 0, message: '缺少项目 ID' }
  if (!items.length) return { ok: false, count: 0, message: '无可推送差异' }

  const wpId = await resolveWpId(projectId, 'G13')
  if (!wpId) return { ok: false, count: 0, message: '未找到本项目 G13 底稿' }

  const existing = await loadG13AdjRows(wpId)
  const { rows, addedCount } = mergeFvDiffIntoG13AdjRows(existing, items, source)
  if (!addedCount) return { ok: false, count: 0, message: '无超阈值差异可推送' }

  const saved = await saveG13AdjRows(wpId, projectId, rows)
  if (!saved) return { ok: false, count: 0, message: '写入 G13-3 失败' }

  try {
    window.dispatchEvent(new CustomEvent(G13_FV_PUSH_EVENT, {
      detail: { source, count: addedCount, belongAccounts: [...new Set(items.map((i) => i.belongAccount))] },
    }))
  } catch { /* silent */ }

  return { ok: true, count: addedCount, message: `已推送 ${addedCount} 笔差异至 G13-3` }
}

/** 按所属科目汇总 G13-2 明细调整数 */
export function aggregateDetailAdjustmentByBelong(
  detailRows: Array<{ belongAccount?: string; adjustment?: number }>,
): G13AdjustmentWritebackMap {
  const byBelong: G13AdjustmentWritebackMap = { other: 0 }
  for (const acct of G13_BELONG_ACCOUNTS) byBelong[acct] = 0
  for (const r of detailRows) {
    const raw = String(r.belongAccount || '').trim()
    const key = (G13_BELONG_ACCOUNTS as readonly string[]).includes(raw) ? raw : 'other'
    byBelong[key] = (byBelong[key] ?? 0) + parseNum(r.adjustment)
  }
  return byBelong
}

/**
 * 对比 G13-2 明细调整数 vs G13-3 应回写净额（按所属科目）。
 * |diff| > 0.01 视为不符。
 */
export function findG13AdjustmentWritebackMismatches(
  detailRows: Array<{ belongAccount?: string; adjustment?: number }>,
  adjRows: G13AdjustmentEntryLike[],
  tolerance = 0.01,
): G13AdjWritebackMismatch[] {
  const detailBy = aggregateDetailAdjustmentByBelong(detailRows)
  const g13By = aggregateG13AdjustmentByBelong(adjRows)
  const keys = new Set([...Object.keys(detailBy), ...Object.keys(g13By)])
  const out: G13AdjWritebackMismatch[] = []
  for (const belong of keys) {
    const detailAdj = parseNum(detailBy[belong])
    const g13Net = parseNum(g13By[belong])
    const diff = detailAdj - g13Net
    if (Math.abs(diff) <= tolerance) continue
    // 两边都为 0 已跳过；仅一边非零也报
    if (Math.abs(detailAdj) <= tolerance && Math.abs(g13Net) <= tolerance) continue
    out.push({
      belong,
      label: belong === 'other' ? '其他' : (G13_BELONG_ACCOUNT_LABELS[belong] ?? belong),
      detailAdj,
      g13Net,
      diff,
    })
  }
  return out
}

export function formatG13AdjWritebackMismatchMessage(
  mismatches: G13AdjWritebackMismatch[],
): string {
  if (!mismatches.length) return ''
  return mismatches
    .map((m) => `${m.label}：明细调整 ${m.detailAdj.toFixed(2)} ≠ G13-3 回写 ${m.g13Net.toFixed(2)}（差 ${m.diff.toFixed(2)}）`)
    .join('；')
}
