/**
 * 离屏披露 Node 执行器入口（spec note-disclosure-pull-regression-and-headless-backend 任务 11~13，design §5.2 / §5.4）。
 *
 * 在 Node 里跑附注页「刷新」的同一套代码，不翻译、不复制：
 *   prepare（`pullFromWorkpapers(..., 'prepare')`）→ `runHeadlessDisclosure`（复用 `HEADLESS_PROVIDERS`，各底稿披露 Tab 的
 *   同一个 composable / builder）→ push（`pullFromWorkpapers(..., 'push')`）→ 后端重算（`refresh-from-workpapers`）。
 * 唯一替换的是 http 客户端（构建别名 `@/utils/http` → `nodeHttp.ts`）；源码不为 Node 改一行。
 */
import { createPinia, setActivePinia } from 'pinia'
import { HEADLESS_PROVIDERS } from '@/components/workpaper/headless/registry'
import type { HeadlessDisclosureContext, HeadlessProviderResult } from '@/components/workpaper/headless/headlessFramework'
import { runHeadlessDisclosure } from '@/views/composables/noteHeadlessDisclosure'
import { pullFromWorkpapers, type NotePullResult } from '@/views/composables/noteWorkpaperPull'
import { disclosureNotes } from '@/services/apiPaths/report'
import http, { configureNodeHttp, PASS, type InterceptedRequest, type NodeHttpConfig } from './nodeHttp'

export { configureNodeHttp, PASS, type InterceptedRequest, type NodeHttpConfig }

let booted = false
/**
 * Node 侧环境注入（任务 10 实跑结论，design §5.3）：
 * - pinia：登录态 store 等模块要一个活动实例（离屏不读它的状态：令牌由 nodeHttp 带）；
 * - `window`：F2 / F3 国企披露 composable 在 setup 里往 window 上挂 / 发底稿间广播事件（`substantive:adjudicated`、
 *   `f2:save-items` …）。给一个只在本进程内转发的 EventTarget，不模拟 DOM / 存储 / 导航；其余 76 个 provider
 *   不碰 window（加不加垫片两次全量实跑结果相同）。
 */
export function bootstrap(): void {
  if (booted) return
  setActivePinia(createPinia())
  const g = globalThis as any
  if (typeof g.window === 'undefined') g.window = new EventTarget()
  booted = true
}

export function providerCodes(): string[] {
  return Object.keys(HEADLESS_PROVIDERS).sort()
}

export interface HeadlessRunScope {
  projectId: string
  year: number
  section?: string | null
}

/**
 * 离屏执行器的写请求名单（design §5.4）：只有取数（prepare / push）、披露同步（单条 / 批量）与后端重算这几个现有端点，
 * 且项目 / 年度 / 章节必须是本次运行的。路径与发请求处同一写法（`pullFromWorkpapers` / `postHeadlessSyncPayload` /
 * `disclosureNotes`）；写法一改、名单没跟上 ⇒ 请求被拒、刷新报失败，不会静默发往别处。
 * 其他写请求（改底稿、改附注正文等）一概不发：不新建写入端点，四层人工保护与推送 ownership 重放都在这几个端点里。
 */
export function headlessWriteAllowlist(scopes: readonly HeadlessRunScope[]): (req: InterceptedRequest) => boolean {
  const allowed = new Set<string>()
  for (const { projectId, year, section } of scopes) {
    allowed.add(`/api/disclosure-notes/${projectId}/${year}/pull-from-workpapers`)
    allowed.add(`/api/projects/${projectId}/disclosure-notes/sync-from-workpaper`)
    allowed.add(`/api/projects/${projectId}/disclosure-notes/sync-batch-from-workpaper`)
    allowed.add(disclosureNotes.refreshFromWorkpapers(projectId, year))
    if (section) allowed.add(disclosureNotes.refreshSectionFromWorkpaper(projectId, year, section))
  }
  return (req) => req.method === 'POST' && allowed.has(String(req.url).split('?')[0])
}

/** 直接跑一个 provider（可移植性实跑 / 逐字节对拍用；ctx 由调用方给） */
export async function runProvider(code: string, ctx: HeadlessDisclosureContext): Promise<HeadlessProviderResult> {
  bootstrap()
  const load = HEADLESS_PROVIDERS[code]
  if (!load) throw new Error(`未接入离屏同步的底稿：${code}`)
  const provider = await load()
  return provider(ctx)
}

export interface RefreshOptions {
  projectId: string
  year: number
  /** 只刷一个章节（null = 全部刷新） */
  section: string | null
  /** 不做 push 与后端重算（干跑：只看离屏同步会发什么） */
  headlessOnly?: boolean
}

/** 与附注页 `_pullFromWorkpapers` + 「全部刷新」同一顺序：prepare → 离屏同步 → push → 后端重算。 */
export async function refreshNotes(opts: RefreshOptions): Promise<Record<string, unknown>> {
  bootstrap()
  const prepared = await pullFromWorkpapers(opts.projectId, opts.year, opts.section, 'prepare')
  if (!prepared.result) return { ok: false, stage: 'prepare', error: prepared.error }
  const { outcomes, pending } = await runHeadlessDisclosure(prepared.result as NotePullResult, {
    projectId: opts.projectId, year: opts.year, allSections: opts.section === null,
  })
  if (opts.headlessOnly) return { ok: true, stage: 'headless', outcomes, pending }
  const pushed = await pullFromWorkpapers(opts.projectId, opts.year, opts.section, 'push')
  let refresh: unknown = null
  if (opts.section === null) {
    const res: any = await http.post(disclosureNotes.refreshFromWorkpapers(opts.projectId, opts.year))
    refresh = res?.data ?? null
  } else {
    const res: any = await http.post(
      disclosureNotes.refreshSectionFromWorkpaper(opts.projectId, opts.year, opts.section))
    refresh = res?.data ?? null
  }
  return {
    ok: !pushed.error, stage: 'done', outcomes, pending,
    push: pushed.result?.push ?? null, push_error: pushed.error, refresh,
  }
}
