/**
 * useH6Disclosure — H6 附注披露取数与勾稽
 *
 * - 从 H6-1 / H6-2 自动填充清理汇总与明细
 * - 可选从 H1 跨底稿带入固定资产汇总行（合计数详见 H1-1）
 * - 过渡科目 / 明细 vs 审定勾稽
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import {
  clearingVsAdjudication,
  pullClearingFromH6Responses,
  type H6ClearingRow,
  type H6DisclosureState,
  n,
} from './h6DisclosureModel'

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

function parseJson(raw: unknown): unknown {
  if (raw == null) return null
  if (typeof raw !== 'string') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}

/** 从 H1 上市 summary / 国企 carrying 层取固定资产行 */
function extractFaFromH1Map(map: Map<string, any>, variant: 'listed' | 'soe'): { faEnd: number; faPrior: number } | null {
  if (variant === 'listed') {
    const summaryRaw = parseJson(map.get('H1-listed-summary')?.remark)
    if (Array.isArray(summaryRaw)) {
      const fa = summaryRaw.find((r: any) => r?.key === 'fixed_assets' || r?.label === '固定资产')
      if (fa) return { faEnd: n(fa.endBalance), faPrior: n(fa.priorBalance) }
    }
    // H1-1 审定净值兜底
    const end = n(map.get('H1-1-end-net-audited')?.remark ?? map.get('H1-1-carrying-end')?.remark)
    const begin = n(map.get('H1-1-begin-net-audited')?.remark ?? map.get('H1-1-carrying-begin')?.remark)
    if (end !== 0 || begin !== 0) return { faEnd: end, faPrior: begin }
    return null
  }

  // 国企：账面价值层合计 = 固定资产行
  const movement =
    parseJson(map.get('H1-soe-movement')?.remark)
    ?? parseJson(map.get('H1-disc-soe-movement')?.remark)
  if (Array.isArray(movement)) {
    const carrying = movement.find((l: any) => l?.layer === 'carrying')
    if (carrying) {
      const cats = Array.isArray(carrying.categories) ? carrying.categories : []
      const end = cats.reduce((s: number, c: any) => s + n(c?.end ?? c?.amounts?.end), 0) || n(carrying.end)
      const begin = cats.reduce((s: number, c: any) => s + n(c?.begin ?? c?.amounts?.begin), 0) || n(carrying.begin)
      // 兼容 total / amounts 结构
      const tot = carrying.total || carrying.amounts
      const faEnd = n(tot?.end) || end
      const faPrior = n(tot?.begin) || begin
      if (faEnd !== 0 || faPrior !== 0) return { faEnd, faPrior }
    }
  }
  const end = n(map.get('H1-1-end-net-audited')?.remark ?? map.get('H1-1-carrying-end')?.remark)
  const begin = n(map.get('H1-1-begin-net-audited')?.remark ?? map.get('H1-1-carrying-begin')?.remark)
  if (end !== 0 || begin !== 0) return { faEnd: end, faPrior: begin }
  return null
}

export interface H6PullResult {
  status: 'ok' | 'empty' | 'error'
  message: string
  clearingRows: H6ClearingRow[]
  clearingEnd: number
  clearingPrior: number
  clearingNoteDraft: string
  overOneYearCount: number
  transitZero: boolean
  detailCount: number
}

export function useH6Disclosure(allResponses: Ref<Map<string, any>> | ComputedRef<Map<string, any>>) {
  const autoFill = computed(() => pullClearingFromH6Responses(allResponses.value))

  function crossWarnings(state: H6DisclosureState): string[] {
    const warns: string[] = []
    const chk = clearingVsAdjudication(state.clearingRows, allResponses.value)
    if (state.clearingRows.length && !chk.isMatch) {
      warns.push(
        `清理明细期末合计 ${chk.detailEnd.toLocaleString('zh-CN')} ≠ H6-1 审定 ${chk.auditedEnd.toLocaleString('zh-CN')}（差 ${chk.diff.toLocaleString('zh-CN')}）`,
      )
    }
    if (!autoFill.value.transitZero) {
      warns.push(
        `过渡科目 1606 期末未清零（审定 ${autoFill.value.clearingEnd.toLocaleString('zh-CN')}），附注需披露清理项目及超1年进展。`,
      )
    }
    if (autoFill.value.overOneYearCount > 0 && !state.clearingNote.trim()) {
      warns.push(`存在 ${autoFill.value.overOneYearCount} 项转入清理已超1年，请补充进展说明。`)
    }
    return warns
  }

  /** 从本底稿 H6-1/H6-2 取数 */
  function pullFromLocalSources(opts?: { overwriteNote?: boolean; existingNote?: string }): H6PullResult {
    const r = pullClearingFromH6Responses(allResponses.value)
    const hasData = r.clearingRows.length > 0 || r.clearingEnd !== 0 || r.clearingPrior !== 0
    if (!hasData) {
      return {
        status: 'empty',
        message: 'H6-1/H6-2 暂无清理余额或明细，请先编制审定表与明细表',
        clearingRows: [],
        clearingEnd: 0,
        clearingPrior: 0,
        clearingNoteDraft: '',
        overOneYearCount: 0,
        transitZero: true,
        detailCount: 0,
      }
    }
    const note =
      opts?.overwriteNote || !(opts?.existingNote || '').trim()
        ? r.clearingNoteDraft
        : ''
    return {
      status: 'ok',
      message: `已从 H6-1/H6-2 带入明细 ${r.detailCount} 项、期末 ${r.clearingEnd.toLocaleString('zh-CN')}`,
      clearingRows: r.clearingRows,
      clearingEnd: r.clearingEnd,
      clearingPrior: r.clearingPrior,
      clearingNoteDraft: note || r.clearingNoteDraft,
      overOneYearCount: r.overOneYearCount,
      transitZero: r.transitZero,
      detailCount: r.detailCount,
    }
  }

  /** 跨底稿从 H1 取固定资产汇总行（可选） */
  async function pullFaFromH1(
    projectId: string,
    variant: 'listed' | 'soe',
  ): Promise<{ status: 'ok' | 'wp_missing' | 'empty' | 'error'; message: string; faEnd: number; faPrior: number }> {
    if (!projectId) {
      return { status: 'error', message: '缺少 projectId', faEnd: 0, faPrior: 0 }
    }
    const h1WpId = await resolveWpId(projectId, 'H1')
    if (!h1WpId) {
      return { status: 'wp_missing', message: '项目中未找到 H1 固定资产底稿', faEnd: 0, faPrior: 0 }
    }
    try {
      const map = await loadResponses(h1WpId)
      const fa = extractFaFromH1Map(map, variant)
      if (!fa || (fa.faEnd === 0 && fa.faPrior === 0)) {
        return { status: 'empty', message: 'H1 暂无固定资产汇总金额，请先编制 H1 附注或审定表', faEnd: 0, faPrior: 0 }
      }
      return {
        status: 'ok',
        message: `已从 H1 带入固定资产期末 ${fa.faEnd.toLocaleString('zh-CN')}`,
        faEnd: fa.faEnd,
        faPrior: fa.faPrior,
      }
    } catch (e: any) {
      return { status: 'error', message: e?.message || '拉取 H1 失败', faEnd: 0, faPrior: 0 }
    }
  }

  return {
    autoFill,
    crossWarnings,
    pullFromLocalSources,
    pullFaFromH1,
  }
}

export default useH6Disclosure
