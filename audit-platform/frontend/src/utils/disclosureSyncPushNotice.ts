/**
 * 底稿披露同步的「以试算表审定数为准」提示（spec note-pull-followup-closure R3 / ADR-3）。
 *
 * 公式推送写过的附注主表格（试算表审定数），底稿披露同步写入后保持推送值，后端在响应 `push_kept` 里逐格回报。
 * 披露 Tab 有 90 多个、各自发 `sync-from-workpaper`，提示放在 http 响应拦截器一处做（与 `noteEditRequestGuard` 同一装法）；
 * 请求带 `_silent`（附注页离屏同步自己汇总结果）时不弹。
 */
import type { AxiosInstance, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

export interface PushKeptCell {
  table: string
  row: string
  period: string
  field?: string
  kind?: string
  pushed: unknown
  incoming: unknown
}

export interface PushKeptGroup {
  section: string
  cells: PushKeptCell[]
}

/** 单章节同步、批量同步、HTML 入口三个写附注的同步端点 */
const SYNC_URL = /\/disclosure-notes\/sync-(?:batch-)?from-workpaper(?:\?|$)|\/wp-disclosure-sync\/[^/?]+\/sync-html(?:\?|$)/

export function isDisclosureSyncUrl(url: string | undefined): boolean {
  return !!url && SYNC_URL.test(url)
}

function cellsOf(raw: unknown): PushKeptCell[] {
  return Array.isArray(raw) ? raw.filter((c): c is PushKeptCell => !!c && typeof c === 'object' && 'row' in c) : []
}

/** 响应体（已由 http 拦截器解包）→ 按章节分组的保持推送值的格；批量同步的 `results[]` 逐项读 */
export function pushKeptGroups(data: unknown): PushKeptGroup[] {
  if (!data || typeof data !== 'object') return []
  const d = data as Record<string, unknown>
  const items = Array.isArray(d.results) ? d.results : [d]
  const out: PushKeptGroup[] = []
  for (const item of items) {
    if (!item || typeof item !== 'object') continue
    const cells = cellsOf((item as Record<string, unknown>).push_kept)
    if (cells.length) out.push({ section: String((item as Record<string, unknown>).section_id || ''), cells })
  }
  return out
}

const PERIOD_LABEL: Record<string, string> = { end: '期末', prior: '期初' }

/** 一个章节一句提示；没有保持推送值的格返回 null */
export function pushKeptMessage(group: PushKeptGroup): string | null {
  const cells = group.cells.filter((c) => c.kind !== 'total')
  const named = cells.length ? cells : group.cells
  if (!named.length) return null
  const sample = named.slice(0, 3).map((c) => `「${c.row}」${PERIOD_LABEL[c.period] || c.period}`).join('、')
  const more = named.length > 3 ? ` 等 ${named.length} 格` : ''
  return `附注 ${group.section || ''}：${sample}${more}由公式推送维护，已保持试算表审定数（披露表里的数与之不同，以试算表审定数为准）`
}

/** 装到 http 实例上；返回卸载函数 */
export function installPushKeptNotice(http: AxiosInstance, notify: (msg: string) => void = (msg) => {
  ElMessage({ type: 'warning', message: msg, duration: 6000, showClose: true })
}): () => void {
  const id = http.interceptors.response.use((response: AxiosResponse) => {
    const config = response.config as AxiosResponse['config'] & { _silent?: boolean }
    if (!config?._silent && isDisclosureSyncUrl(config?.url)) {
      for (const group of pushKeptGroups(response.data)) {
        const msg = pushKeptMessage(group)
        if (msg) notify(msg)
      }
    }
    return response
  })
  return () => http.interceptors.response.eject(id)
}
