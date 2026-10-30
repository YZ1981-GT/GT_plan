/**
 * noteWorkpaperPull — 附注「刷新」时从底稿取数（spec note-pull-header-formula-closure R2）
 *
 * 1. 后端 `pull-from-workpapers`：按项目准则找到章节对应的底稿，执行公式推送
 *    （试算表审定数 → 底稿披露项 → 附注主表；规则 = 公式管理「📤 公式推送」页），回逐章节结果与底稿 id；
 * 2. 前端离屏同步（`noteHeadlessDisclosure.ts`）：已接入的底稿在附注页按披露 Tab 同一套代码现算披露表并同步。
 *
 * 本文件只放请求与提示文案（纯函数），编排在 `useNoteRefresh`。
 */
import http from '@/utils/http'

/** 章节状态：离屏同步「从未由底稿同步、已有人工填写不覆盖」据此判 */
export interface NotePullSectionState {
  exists: boolean
  synced_before: boolean
  manual_values: number
}

export interface NotePullSection extends NotePullSectionState {
  section: string
  wp_codes: string[]
  wp_ids: Record<string, string>
  push_wp_codes: string[]
  unsupported_wp_codes: string[]
  written: number
  unchanged: number
  kept: number
  skipped: number
  reasons: string[]
}

export type NotePullPhase = 'all' | 'prepare' | 'push'

export interface NotePullResult {
  phase?: NotePullPhase
  synced: number
  skipped: number
  skipped_never_synced: number
  variant: 'soe' | 'listed'
  applicable_standards: string[]
  push: {
    ran: boolean
    error: string | null
    wp_codes: string[]
    written: number
    kept: number
    skipped: number
    run_id: string | null
    warnings: string[]
  }
  sections: NotePullSection[]
  /** 章节 → 状态（取数结果的章节行 + 全部刷新时其余已有章节；一张底稿可写多个章节，spec note-pull-followup-closure R1） */
  section_states?: Record<string, NotePullSectionState>
}

export interface HeadlessSyncOutcome {
  wpCode: string
  section: string
  status: 'synced' | 'skipped' | 'failed'
  rows?: number
  /** 公式推送维护、保持试算表审定数的格数 */
  kept?: number
  message?: string
}

/** 调后端取数；失败不阻断后续刷新，回 `{ result: null, error }`。 */
export async function pullFromWorkpapers(
  projectId: string,
  year: number,
  section: string | null,
  phase: NotePullPhase = 'all',
): Promise<{ result: NotePullResult | null; error: string | null }> {
  try {
    const res: any = await http.post(
      `/api/disclosure-notes/${projectId}/${year}/pull-from-workpapers`,
      null,
      { params: { ...(section ? { note_section: section } : {}), phase }, _silent: true } as any,
    )
    const data = res?.data ?? res
    return { result: data && Array.isArray(data.sections) ? (data as NotePullResult) : null, error: null }
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.response?.data?.message
    const msg = typeof detail === 'string' ? detail : (err?.message || '请求失败')
    return { result: null, error: `从底稿取数失败：${msg}` }
  }
}

/**
 * 刷新提示里「从底稿取数」这一段：推送写入 / 保留人工、离屏同步结果、未接入离屏同步的底稿。
 * 返回 `{ lines, warn }`：warn = 有失败或需要用户去底稿处理的事项。
 */
export function describeWorkpaperPull(
  pull: NotePullResult | null,
  pullError: string | null,
  headless: HeadlessSyncOutcome[],
  options: { pendingWpCodes?: string[] } = {},
): { lines: string[]; warn: boolean } {
  const lines: string[] = []
  let warn = false
  if (pullError) {
    lines.push(pullError)
    warn = true
  }
  if (pull) {
    const p = pull.push
    if (p.error) {
      lines.push(`公式推送未执行：${p.error}`)
      warn = true
    } else if (p.ran) {
      const touched = pull.sections.filter((s) => s.written > 0).map((s) => s.section)
      if (p.written > 0) {
        lines.push(`公式推送按审定数写入 ${p.written} 格（${touched.slice(0, 4).join('、')}${touched.length > 4 ? '等' : ''}）`)
      }
      if (p.kept > 0) lines.push(`保留人工 / 锁定 ${p.kept} 格`)
    }
  }
  const synced = headless.filter((h) => h.status === 'synced')
  const failed = headless.filter((h) => h.status === 'failed')
  const skipped = headless.filter((h) => h.status === 'skipped' && h.message)
  const more = (n: number, shown: number) => (n > shown ? ` 等 ${n} 项` : '')
  if (synced.length) {
    const head = synced.slice(0, 6).map((h) => `${h.wpCode}→${h.section}（${h.rows ?? 0} 行）`).join('、')
    lines.push(`已从底稿披露表同步：${head}${more(synced.length, 6)}`)
  }
  const kept = synced.filter((h) => (h.kept ?? 0) > 0)
  if (kept.length) {
    const total = kept.reduce((n, h) => n + (h.kept ?? 0), 0)
    lines.push(`其中 ${total} 格由公式推送维护，已保持试算表审定数（${kept.slice(0, 4).map((h) => h.section).join('、')}${more(kept.length, 4)}）`)
  }
  for (const h of skipped.slice(0, 3)) lines.push(`${h.wpCode}：${h.message}`)
  if (skipped.length > 3) lines.push(`另有 ${skipped.length - 3} 个章节未写入（原因同上类）`)
  if (failed.length) {
    warn = true
    const head = failed.slice(0, 6).map((h) => `${h.wpCode}→${h.section}（${h.message || '未知原因'}）`).join('、')
    lines.push(`底稿披露表同步失败：${head}${more(failed.length, 6)}`)
  }
  const pending = options.pendingWpCodes ?? []
  if (pending.length) {
    lines.push(`底稿 ${pending.slice(0, 6).join('、')}${pending.length > 6 ? '等' : ''} 的明细表需在底稿附注披露页保存一次后同步`)
  }
  return { lines, warn }
}
