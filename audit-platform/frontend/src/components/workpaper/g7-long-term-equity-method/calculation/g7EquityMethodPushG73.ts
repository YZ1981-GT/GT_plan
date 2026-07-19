/**
 * G7-14 → G7-3：解析主表底稿并写入建议调整分录（含 if_match 并发保护）
 */
import { listWorkpapers, getWorkpaper } from '@/services/workpaperApi'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import {
  isG7MainWorkpaper,
  mergeSuggestedIntoG73,
  toG73Entries,
  type SuggestedAdjustmentLine,
} from './g7EquityMethodCalcModel'

const G73_ROWS_KEY = 'G7-3-rows'

function parseStoredEntries(raw: unknown): Record<string, any>[] {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}

async function assertMainWorkpaper(
  projectId: string,
  wpId: string,
): Promise<{ ok: true } | { ok: false; message: string }> {
  try {
    const detail = await getWorkpaper(projectId, wpId)
    if (!isG7MainWorkpaper(detail as any)) {
      return {
        ok: false,
        message: `解析到的底稿不是 G7 主表（wp_id=${wpId}），已取消写入`,
      }
    }
    return { ok: true }
  } catch {
    return { ok: false, message: `无法校验目标底稿（wp_id=${wpId}），已取消写入` }
  }
}

/** 在项目内查找含 G7-3 的主表底稿 id */
export async function resolveG7MainWorkpaperId(
  projectId: string,
  currentWpId?: string,
): Promise<string | null> {
  if (!projectId) return null

  for (const sheetCode of ['G7-3', 'G7-1', 'G7']) {
    try {
      const { data } = await http.get('/api/acnr/resolve-instance', {
        params: { project_id: projectId, parent: 'G7', sheet_code: sheetCode },
        _silent: true,
      } as any)
      const resolved = data?.data?.wp_id ?? data?.wp_id
      if (!resolved) continue
      const check = await assertMainWorkpaper(projectId, String(resolved))
      if (check.ok) return String(resolved)
    } catch {
      /* try next */
    }
  }

  if (currentWpId) {
    try {
      const detail = await getWorkpaper(projectId, currentWpId)
      if (isG7MainWorkpaper(detail as any)) return currentWpId
    } catch {
      /* continue */
    }
  }

  try {
    const list = await listWorkpapers(projectId)
    const hit = list.find((wp) => isG7MainWorkpaper(wp as any))
    if (hit?.id) return String(hit.id)
    const g7 = list.find((wp) => {
      const code = String((wp as any).wp_code ?? (wp as any).code ?? '').toUpperCase()
      const name = String((wp as any).wp_name ?? (wp as any).name ?? '')
      return code === 'G7' && !name.includes('权益法') && !name.includes('子公司')
    })
    return g7?.id ? String(g7.id) : null
  } catch {
    return null
  }
}

export interface PushG73Result {
  ok: boolean
  mainWpId: string | null
  written: number
  message: string
  conflict?: boolean
}

/** 将建议分录合并写入主表 G7-3-rows（仅替换同源建议草稿；带 if_match） */
export async function pushSuggestedAdjustmentsToG73(opts: {
  projectId: string
  currentWpId?: string
  lines: SuggestedAdjustmentLine[]
}): Promise<PushG73Result> {
  const suggested = toG73Entries(opts.lines)
  if (!suggested.length) {
    return { ok: false, mainWpId: null, written: 0, message: '无建议分录可推送' }
  }

  const mainWpId = await resolveG7MainWorkpaperId(opts.projectId, opts.currentWpId)
  if (!mainWpId) {
    return {
      ok: false,
      mainWpId: null,
      written: 0,
      message: '未找到 G7 主表底稿（含 G7-3），请确认项目已生成长期股权投资主表',
    }
  }

  const check = await assertMainWorkpaper(opts.projectId, mainWpId)
  if (!check.ok) {
    return { ok: false, mainWpId, written: 0, message: check.message }
  }

  let existing: Record<string, any>[] = []
  let ifMatch: string | undefined
  try {
    const res: any = await http.get(`/api/workpapers/${mainWpId}/checklist-responses`, {
      _silent: true,
    } as any)
    const items = Array.isArray(res) ? res : res?.data || []
    const rowItem = items.find((it: any) => it?.item_id === G73_ROWS_KEY)
    existing = parseStoredEntries(rowItem?.conclusion || rowItem?.remark)
    ifMatch = String(rowItem?.version || rowItem?.updated_at || '').trim() || undefined
  } catch {
    return {
      ok: false,
      mainWpId,
      written: 0,
      message: '读取 G7-3 现有分录失败，已取消写入以避免覆盖丢失',
    }
  }

  const merged = mergeSuggestedIntoG73(existing, suggested)
  const json = JSON.stringify(merged)
  try {
    await http.put(
      `/api/workpapers/${mainWpId}/checklist-responses`,
      {
        project_id: opts.projectId || undefined,
        items: [{
          item_id: G73_ROWS_KEY,
          conclusion: json,
          remark: json,
          ...(ifMatch ? { if_match: ifMatch } : {}),
        }],
      },
      { _silent: true } as any,
    )
  } catch (err: any) {
    const status = err?.response?.status
    const detail = err?.response?.data?.detail
    if (status === 409 || detail?.code === 'version_conflict') {
      return {
        ok: false,
        mainWpId,
        written: 0,
        conflict: true,
        message: 'G7-3 已被他人修改（版本冲突），请刷新主表后再推送',
      }
    }
    return {
      ok: false,
      mainWpId,
      written: 0,
      message: '写入 G7-3 失败，请稍后重试',
    }
  }

  try {
    eventBus.emit('adjustment:updated')
    window.dispatchEvent(
      new CustomEvent('g7:adjustment-pushed', {
        detail: { source: 'G7-14', mainWpId, count: suggested.length, timestamp: Date.now() },
      }),
    )
  } catch {
    /* ignore */
  }

  return {
    ok: true,
    mainWpId,
    written: suggested.length,
    message: `已写入 G7-3 共 ${suggested.length} 行（仅替换同源建议草稿）`,
  }
}
