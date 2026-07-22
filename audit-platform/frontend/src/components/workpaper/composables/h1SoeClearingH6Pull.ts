/**
 * H1 国企附注「固定资产清理」← H6 跨底稿自动取数
 *
 * 数据来源（H6 checklist_responses）：
 * - H6-1-end-balance-audited → 汇总表清理期末账面价值
 * - H6-1-rows 期初/期末审定（新格式 beginAudited/endAudited，或旧 balance 行）→ 汇总表清理期初
 * - H6-2-rows → (2) 清理明细行（项目/期末/期初/转入原因）
 * - 超 1 年清理进展草稿（由 startDate 判定）
 */
import { api } from '@/services/apiProxy'
import type { H1SoeClearingRow } from './h1SoeDisclosureModel'
import { n, newRowId } from './h1SoeDisclosureModel'

export interface H6ClearingPullResult {
  status: 'ok' | 'wp_missing' | 'empty' | 'error'
  message: string
  h6WpId: string | null
  /** 汇总：期末审定（1606） */
  clearingEnd: number
  /** 汇总：期初（H6-1 期初余额行） */
  clearingBegin: number
  /** 明细行（供附注 (2)） */
  clearingRows: H1SoeClearingRow[]
  /** 超 1 年进展说明草稿（空则不覆盖用户已填） */
  clearingNoteDraft: string
  /** 过渡科目是否已清零 */
  transitZero: boolean
  detailCount: number
  overOneYearCount: number
}

const MS_PER_DAY = 24 * 60 * 60 * 1000
const ONE_YEAR_DAYS = 365

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

async function loadResponses(wpId: string): Promise<Map<string, any>> {
  const map = new Map<string, any>()
  try {
    const res = await api.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    for (const item of list) {
      if (item?.item_id) map.set(item.item_id, item)
    }
  } catch { /* ignore */ }
  return map
}

function remarkNum(map: Map<string, any>, itemId: string): number {
  const item = map.get(itemId)
  if (!item) return 0
  const parsed = parseRemark(item.remark ?? item.conclusion)
  if (typeof parsed === 'number') return n(parsed)
  if (typeof parsed === 'string' || typeof parsed === 'number') return n(parsed)
  return n(item.remark)
}

function daysSince(startDate: string, asOf: Date = new Date()): number | null {
  if (!startDate) return null
  const d = new Date(startDate)
  if (Number.isNaN(d.getTime())) return null
  return Math.floor((asOf.getTime() - d.getTime()) / MS_PER_DAY)
}

/**
 * 从 H6-1-rows 取期初/期末审定余额。
 * 兼容：
 * - 新格式：beginAudited / endAudited（合计行或明细求和）
 * - 旧过程结构：category=balance 的「期初余额」「期末余额」行
 */
export function extractH61Balances(rowsRaw: unknown): { begin: number; end: number } {
  const rows = Array.isArray(rowsRaw) ? rowsRaw : []
  let begin = 0
  let end = 0
  let hasNew = false
  let beginSum = 0
  let endSum = 0

  for (const r of rows) {
    if (!r || r.isSubtotal) continue
    const name = String(r?.name || '')
    const cat = String(r?.category || '')

    // 新格式（Excel 对齐列）
    if (r.beginAudited != null || r.endAudited != null || r.beginUnadjusted != null || r.endUnadjusted != null) {
      hasNew = true
      if (r.isTotal || name === '合计') {
        begin = n(r.beginAudited) || n(r.beginUnadjusted) + n(r.beginAdjustment)
        end = n(r.endAudited) || n(r.endUnadjusted) + n(r.endAdjustment)
      } else {
        beginSum += n(r.beginAudited) || n(r.beginUnadjusted) + n(r.beginAdjustment)
        endSum += n(r.endAudited) || n(r.endUnadjusted) + n(r.endAdjustment)
      }
      continue
    }

    // 旧过程结构
    if (cat !== 'balance' && !/期初|期末|本期/.test(name)) continue
    const audited = n(r?.audited)
    const beginBal = n(r?.beginBalance)
    const endBal = n(r?.endBalance)
    if (name.includes('期初')) {
      begin = audited || beginBal || endBal
    } else if (name.includes('期末')) {
      end = audited || endBal || beginBal
    }
  }

  if (hasNew) {
    if (begin === 0 && end === 0) {
      begin = beginSum
      end = endSum
    }
  }
  return { begin, end }
}

/** H6-2 明细 → 附注清理行；优先「清理中」，若无则保留期末仍有余额的项 */
export function mapH62ToClearingRows(
  detailRaw: unknown,
  opts?: { asOf?: Date },
): { rows: H1SoeClearingRow[]; overOneYearNote: string; overOneYearCount: number } {
  const list = Array.isArray(detailRaw) ? detailRaw : []
  const asOf = opts?.asOf ?? new Date()
  const endOf = (r: any) =>
    n(r?.endAudited) || n(r?.endUnadjusted) || n(r?.netBookValue)
  const beginOf = (r: any) =>
    n(r?.beginAudited) || n(r?.beginUnadjusted) || n(r?.beginCarrying)

  const active = list.filter((r) => {
    const status = String(r?.status || '')
    const endBal = endOf(r)
    if (status === '清理中') return true
    // 已完成/已结转但期末仍有余额：仍需披露
    if (endBal !== 0 && status !== '已结转') return true
    return false
  })
  const source = active.length ? active : list.filter((r) => endOf(r) !== 0)

  const overYearLines: string[] = []
  const rows: H1SoeClearingRow[] = source.map((r: any, i: number) => {
    const start = String(r.startDate || '')
    const days = daysSince(start, asOf)
    const over = days != null && days >= ONE_YEAR_DAYS
    const name = String(r.assetName || `清理项目-${i + 1}`)
    const endCarrying = endOf(r)
    const beginExplicit = beginOf(r)
    // 有余额列则用审定/未审期初；否则超期/清理中用期末近似
    const beginCarrying = beginExplicit !== 0
      ? beginExplicit
      : (over || String(r.status) === '清理中' ? endCarrying : 0)
    if (over) {
      overYearLines.push(
        `${name}（起始 ${start || '未填'}，已 ${days} 天）：状态 ${r.status || '—'}，账面价值 ${endCarrying.toLocaleString('zh-CN')}；进展待补充。`,
      )
    }
    return {
      rowId: String(r.rowId || newRowId('h6clr')),
      name,
      endCarrying,
      beginCarrying,
      reason: String(r.disposalReason || '') + (over ? '（转入清理已超1年）' : ''),
    }
  })

  return {
    rows,
    overOneYearCount: overYearLines.length,
    overOneYearNote: overYearLines.length
      ? `以下固定资产清理起始已超过1年，请说明进展：\n${overYearLines.map((l, i) => `${i + 1}. ${l}`).join('\n')}`
      : '',
  }
}

/**
 * 拉取 H6 清理余额与明细，供 H1 国企附注写入。
 */
export async function pullH6ClearingForH1Soe(projectId: string): Promise<H6ClearingPullResult> {
  const empty: H6ClearingPullResult = {
    status: 'error',
    message: '',
    h6WpId: null,
    clearingEnd: 0,
    clearingBegin: 0,
    clearingRows: [],
    clearingNoteDraft: '',
    transitZero: true,
    detailCount: 0,
    overOneYearCount: 0,
  }

  if (!projectId) {
    return { ...empty, status: 'error', message: '缺少 projectId' }
  }

  const h6WpId = await resolveWpId(projectId, 'H6')
  if (!h6WpId) {
    return { ...empty, status: 'wp_missing', message: '项目中未找到 H6 固定资产清理底稿' }
  }

  try {
    const map = await loadResponses(h6WpId)
    const endFromKey = remarkNum(map, 'H6-1-end-balance-audited')
    const h61 = extractH61Balances(parseRemark(map.get('H6-1-rows')?.remark))
    const clearingEnd = endFromKey || h61.end
    const clearingBegin = h61.begin

    const mapped = mapH62ToClearingRows(parseRemark(map.get('H6-2-rows')?.remark))
    // 明细合计与审定期末不一致时，仍以 H6-1 审定为准写汇总；明细照常带入
    const hasData = clearingEnd !== 0 || clearingBegin !== 0 || mapped.rows.length > 0
    if (!hasData) {
      return {
        ...empty,
        status: 'empty',
        message: 'H6 暂无清理余额/明细，请先编制 H6-1 / H6-2',
        h6WpId,
        transitZero: true,
      }
    }

    return {
      status: 'ok',
      message: `已从 H6 带入期末 ${clearingEnd.toLocaleString('zh-CN')}、明细 ${mapped.rows.length} 项`,
      h6WpId,
      clearingEnd,
      clearingBegin,
      clearingRows: mapped.rows,
      clearingNoteDraft: mapped.overOneYearNote,
      transitZero: Math.abs(clearingEnd) < 0.005,
      detailCount: mapped.rows.length,
      overOneYearCount: mapped.overOneYearCount,
    }
  } catch (e: any) {
    return {
      ...empty,
      status: 'error',
      message: e?.message || '拉取 H6 失败',
      h6WpId,
    }
  }
}

/** 上市附注清理行（期末余额 / 上年年末余额） */
export interface H1ListedClearingFromH6 {
  rowId: string
  name: string
  endBalance: number
  priorBalance: number
  reason: string
}

export interface H6ClearingPullListedResult {
  status: 'ok' | 'wp_missing' | 'empty' | 'error'
  message: string
  h6WpId: string | null
  clearingEnd: number
  clearingPrior: number
  clearingRows: H1ListedClearingFromH6[]
  clearingNoteDraft: string
  transitZero: boolean
  detailCount: number
  overOneYearCount: number
}

/**
 * 拉取 H6 → H1 上市附注「固定资产清理」（字段映射为 endBalance/priorBalance）
 */
export async function pullH6ClearingForH1Listed(projectId: string): Promise<H6ClearingPullListedResult> {
  const soe = await pullH6ClearingForH1Soe(projectId)
  return {
    status: soe.status,
    message: soe.message,
    h6WpId: soe.h6WpId,
    clearingEnd: soe.clearingEnd,
    clearingPrior: soe.clearingBegin,
    clearingRows: soe.clearingRows.map((r) => ({
      rowId: r.rowId,
      name: r.name,
      endBalance: r.endCarrying,
      priorBalance: r.beginCarrying,
      reason: r.reason,
    })),
    clearingNoteDraft: soe.clearingNoteDraft,
    transitZero: soe.transitZero,
    detailCount: soe.detailCount,
    overOneYearCount: soe.overOneYearCount,
  }
}
