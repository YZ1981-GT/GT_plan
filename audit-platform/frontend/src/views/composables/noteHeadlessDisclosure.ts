/**
 * noteHeadlessDisclosure — 附注页离屏同步底稿披露表（spec note-pull-header-formula-closure R2.3 / note-pull-followup-closure R1）
 *
 * 底稿披露表的口径只有前端一份：各底稿披露 Tab 的 composable / 快照函数 + `buildXSyncPayload(s)`。原先只有打开披露 Tab
 * 并保存才会推附注；这里在附注页「刷新」时**调用同一套函数**（不复制逻辑）现算披露表并经同一个 `sync-from-workpaper`
 * 写入，不必打开底稿。provider 的写法见 `components/workpaper/headless/headlessFramework.ts`，登记在
 * `components/workpaper/headless/registry.ts`（按组一份文件）。
 *
 * 逐底稿接入：未接入的底稿冻结在 `noteHeadlessDisclosureCoverage.spec.ts`（只许变短，逐码写明原因），刷新提示里点名
 * 「需在底稿附注披露页保存一次」。
 */
import {
  headlessErrorMessage,
  type HeadlessProviderLoader,
} from '@/components/workpaper/headless/headlessFramework'
import { HEADLESS_PROVIDERS } from '@/components/workpaper/headless/registry'
import type { HeadlessSyncOutcome, NotePullResult, NotePullSection, NotePullSectionState } from './noteWorkpaperPull'

export {
  loadWorkpaperResponses,
  type HeadlessDisclosureContext,
  type HeadlessDisclosureProvider,
} from '@/components/workpaper/headless/headlessFramework'

const PROVIDERS: Readonly<Record<string, HeadlessProviderLoader>> = HEADLESS_PROVIDERS

/** 已接入离屏同步的底稿编码 */
export function headlessDisclosureWpCodes(): string[] {
  return Object.keys(PROVIDERS)
}

function manualSkipMessage(section: string, state: NotePullSectionState): string | null {
  if (state.synced_before || !(state.manual_values > 0)) return null
  return `附注 ${section} 已有 ${state.manual_values} 格人工填写，未用底稿披露表覆盖（如需改用底稿数据，请在底稿附注披露页同步）`
}

/**
 * 按后端取数结果逐底稿离屏同步，结果逐章节回报。
 *
 * - 没接入的底稿：章节从未由底稿同步过 ⇒ 记入 `pending`（提示用户去底稿保存一次）；
 * - 本项目没有该底稿 ⇒ 跳过并说明；
 * - 章节从未由底稿同步、但附注里已有人工填写 ⇒ 不覆盖（同步后编辑器改显示披露表，人工填的表格会被盖住）。一张底稿可写
 *   多个章节：取数结果的章节行之外的章节按 `section_states`（全部刷新时后端给全部已有章节）判；单章节刷新时不在本次范围的
 *   章节不写；
 * - 单张底稿 / 单个章节失败不影响其他底稿与后续刷新。
 */
export async function runHeadlessDisclosure(
  pull: NotePullResult,
  ctx: {
    projectId: string
    year: number
    allSections?: boolean
    templateType?: string
    reportScope?: string
  },
): Promise<{ outcomes: HeadlessSyncOutcome[]; pending: string[] }> {
  const outcomes: HeadlessSyncOutcome[] = []
  const pending: string[] = []
  const rows = new Map<string, NotePullSection>((pull.sections || []).map((s) => [s.section, s]))
  const states = pull.section_states || {}
  const byCode = new Map<string, { sections: NotePullSection[]; wpId: string | null }>()
  for (const sec of pull.sections || []) {
    for (const code of sec.wp_codes || []) {
      const entry = byCode.get(code) ?? { sections: [], wpId: null }
      entry.sections.push(sec)
      entry.wpId = entry.wpId || sec.wp_ids?.[code] || null
      byCode.set(code, entry)
    }
  }
  const sectionGuard = (section: string): string | null => {
    const row = rows.get(section)
    if (row) return manualSkipMessage(section, row)
    if (!ctx.allSections) return ''
    const state = states[section]
    return state ? manualSkipMessage(section, state) : null
  }
  for (const [code, { sections, wpId }] of byCode) {
    const load = PROVIDERS[code]
    const first = sections[0].section
    if (!load) {
      if (wpId && sections.some((s) => !s.synced_before)) pending.push(code)
      continue
    }
    if (!wpId) {
      outcomes.push({ wpCode: code, section: first, status: 'skipped', message: `本项目没有 ${code} 底稿` })
      continue
    }
    try {
      const provider = await load()
      const res = await provider({
        projectId: ctx.projectId, year: ctx.year, variant: pull.variant, wpId, wpCode: code,
        applicableStandards: pull.applicable_standards || [], sectionGuard,
        templateType: ctx.templateType,
        reportScope: ctx.reportScope,
      })
      if (!res.sections.length) {
        outcomes.push({ wpCode: code, section: first, status: 'skipped', message: '本项目口径没有这张底稿的披露表' })
      }
      for (const s of res.sections) {
        if (s.error != null) outcomes.push({ wpCode: code, section: s.section, status: 'failed', message: s.error })
        else if (s.skipped === '') continue
        else if (s.skipped != null) outcomes.push({ wpCode: code, section: s.section, status: 'skipped', message: s.skipped })
        else outcomes.push({ wpCode: code, section: s.section, status: 'synced', rows: s.rows, kept: s.kept ?? 0 })
      }
    } catch (err: any) {
      outcomes.push({ wpCode: code, section: first, status: 'failed', message: headlessErrorMessage(err) })
    }
  }
  return { outcomes, pending }
}
