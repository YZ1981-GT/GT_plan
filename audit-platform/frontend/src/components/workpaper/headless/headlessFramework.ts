/**
 * 底稿披露表离屏同步框架（附注页「刷新」用；spec note-pull-followup-closure R1 / ADR-1）。
 *
 * 披露表口径只有前端一份：各底稿披露 Tab 的 composable / 快照函数 + `buildXSyncPayload(s)`。离屏同步**调同一套函数**
 * （不复制逻辑）现算载荷，经同一个 `sync-from-workpaper` 写入，不必打开底稿。一个 provider 用 `defineHeadlessProvider`
 * 声明：
 *
 * - `prefix`：本底稿 checklist 响应的条目前缀（与底稿主入口同口径，只取本底稿的条目）；
 * - `needs`：`aging` 先预取项目账龄配置（`useAgingConfig` 离屏只套用缓存）、`renderConfig` 取底稿渲染配置（预填 / 跨表）；
 * - `setup`：在 `effectScope` 里实例化 Tab 同一个 composable（不挂载组件、不 inject 外壳；保存回调置空 —— 离屏不改底稿）；
 * - `prepare`：组件 onMounted 里的初始化（离屏版：不弹提示、不写底稿）；
 * - `build`：Tab 同一个 builder 产出的载荷（单个 / 数组 / null = 本口径没有章节）；
 * - `post`：逐条发送的自定义（缺省 `postHeadlessSyncPayload`；批量端点等）。
 *
 * 离屏没有界面：provider 模块不许 import element-plus、不调 Tab 的 `syncTo…` 同步函数（里面有提示 / 确认框）、不触发受限
 * 资产段与 AI（守卫 `noteHeadlessProviders.spec.ts`）。每条载荷发送前过 `ctx.sectionGuard`（附注页按取数结果判「从未由底稿
 * 同步、已有人工填写」不覆盖），逐章节回报。
 */
import { effectScope, nextTick } from 'vue'
import http from '@/utils/http'
import { primeAgingConfig } from '@/composables/useAgingConfig'
import type { ChecklistResponse } from '@/components/workpaper/composables/useD2FormData'

export interface HeadlessDisclosureContext {
  projectId: string
  year: number
  variant: 'soe' | 'listed'
  wpId: string
  wpCode: string
  applicableStandards: string[]
  /** 项目附注模板类型；未提供时 provider 可从 render-config 的 project_context 读取。 */
  templateType?: string
  /** standalone|consolidated；未提供时 provider 可从 render-config 读取。 */
  reportScope?: string
  /**
   * 章节写入前的判定：`null` = 写；字符串 = 不写（非空写进提示，空串 = 不在本次刷新范围、静默跳过）。
   * 缺省全写（单测 / 直接调用）。
   */
  sectionGuard?: (section: string) => string | null
}

export interface HeadlessSectionResult {
  section: string
  rows: number
  /** 公式推送维护、本次保持试算表审定数的格数（R3 `push_kept`） */
  kept?: number
  /** 没写的原因（空串 = 静默跳过） */
  skipped?: string
  /** 这一章节发送失败的原因（其他章节照常） */
  error?: string
}

export interface HeadlessProviderResult {
  sections: HeadlessSectionResult[]
}

export type HeadlessDisclosureProvider = (ctx: HeadlessDisclosureContext) => Promise<HeadlessProviderResult>

/** 注册表里的懒加载入口（附注页只在用到时才加载底稿代码） */
export type HeadlessProviderLoader = () => Promise<HeadlessDisclosureProvider>

/** `sync-from-workpaper` 请求体（builder 产出；只约束框架要读的字段，其余原样发送） */
export interface HeadlessSyncPayload {
  section_id: string
}

export interface HeadlessProviderInput {
  ctx: HeadlessDisclosureContext
  /** 本底稿前缀的 checklist 响应 */
  responses: Map<string, ChecklistResponse>
  /** `GET /api/workpapers/{wpId}/render-config` 的业务数据（`needs.renderConfig` 时；取不到为 null） */
  renderConfig: any | null
}

export interface HeadlessProviderSpec<T> {
  prefix: string | readonly string[]
  needs?: { aging?: boolean; renderConfig?: boolean }
  setup: (input: HeadlessProviderInput) => T
  prepare?: (instance: T, input: HeadlessProviderInput) => unknown | Promise<unknown>
  build: (instance: T, input: HeadlessProviderInput) =>
    HeadlessSyncPayload | readonly HeadlessSyncPayload[] | null | undefined
    | Promise<HeadlessSyncPayload | readonly HeadlessSyncPayload[] | null | undefined>
  post?: (instance: T, payload: HeadlessSyncPayload, input: HeadlessProviderInput) => Promise<HeadlessSectionResult>
  /**
   * 通过一个原子批量请求发送所有已通过 sectionGuard 的章节。失败时框架把同一错误
   * 回报到批内每个章节；不得与 `post` 同时声明。
   */
  postAll?: (
    instance: T, payloads: readonly HeadlessSyncPayload[], input: HeadlessProviderInput,
  ) => Promise<readonly HeadlessSectionResult[]>
}

/** 底稿的 checklist 响应（只取本底稿前缀的条目，与底稿主入口同口径）。 */
export async function loadWorkpaperResponses(
  wpId: string,
  prefix: string | readonly string[],
): Promise<Map<string, ChecklistResponse>> {
  const prefixes = typeof prefix === 'string' ? [prefix] : [...prefix]
  const res: any = await http.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
  const list: any[] = Array.isArray(res) ? res : (Array.isArray(res?.data) ? res.data : [])
  const out = new Map<string, ChecklistResponse>()
  for (const item of list) {
    const id = String(item?.item_id ?? '')
    if (prefixes.some((p) => id.startsWith(p))) {
      out.set(id, { item_id: id, conclusion: item.conclusion ?? null, remark: item.remark ?? null })
    }
  }
  return out
}

/** 底稿渲染配置（预填 / 跨表数据从这里来）；取不到回 null，由 provider 按 Tab 加载失败的同一兜底处理。 */
export async function loadRenderConfig(wpId: string): Promise<any | null> {
  try {
    const res: any = await http.get(`/api/workpapers/${wpId}/render-config`, { _silent: true } as any)
    const data = res?.data ?? res
    return data && typeof data === 'object' ? data : null
  } catch {
    return null
  }
}

const SKIP_REASON: Record<string, string> = {
  section_not_applicable_to_report_scope: '章节不适用于本项目口径（单体项目的合并专属章节等），未写入',
}

/** 经 `sync-from-workpaper` 发一条载荷（静默：离屏同步自己汇总提示）。 */
export async function postHeadlessSyncPayload(projectId: string, payload: HeadlessSyncPayload): Promise<HeadlessSectionResult> {
  const res: any = await http.post(
    `/api/projects/${projectId}/disclosure-notes/sync-from-workpaper`,
    payload,
    { _silent: true } as any,
  )
  const data = res?.data ?? res
  const section = String(data?.section_id || payload.section_id)
  const unresolved = Array.isArray(data?.row_scope_unresolved)
    ? data.row_scope_unresolved.map((name: unknown) => String(name)).filter(Boolean)
    : []
  if (unresolved.length > 0) {
    const reasons = data?.row_scope_unresolved_reasons && typeof data.row_scope_unresolved_reasons === 'object'
      ? data.row_scope_unresolved_reasons as Record<string, string>
      : {}
    const detail = unresolved.map((name: string) => reasons[name] ? `${name}（${reasons[name]}）` : name).join('、')
    return { section, rows: 0, error: `附注分段同步未写入：${detail}` }
  }
  if (data?.skipped) return { section, rows: 0, skipped: SKIP_REASON[data.reason] || `章节未写入：${data.reason || '不适用'}` }
  if (data?.blocked_by_manual_override) return { section, rows: 0, skipped: `附注 ${section} 标记了整节人工覆盖，未写入` }
  return {
    section,
    rows: Number(data?.rows_synced ?? 0),
    kept: Array.isArray(data?.push_kept) ? data.push_kept.length : 0,
  }
}

export function headlessErrorMessage(err: any): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail.message === 'string') return detail.message
  return err?.message || '未知原因'
}

function payloadList(built: unknown): HeadlessSyncPayload[] {
  const list = Array.isArray(built) ? built : built ? [built] : []
  return list.filter((p): p is HeadlessSyncPayload => !!p && typeof p === 'object')
}

/** 声明一个离屏 provider（见文件头）。 */
export function defineHeadlessProvider<T>(spec: HeadlessProviderSpec<T>): HeadlessDisclosureProvider {
  return async (ctx) => {
    const [responses, renderConfig] = await Promise.all([
      loadWorkpaperResponses(ctx.wpId, spec.prefix),
      spec.needs?.renderConfig ? loadRenderConfig(ctx.wpId) : Promise.resolve(null),
      spec.needs?.aging ? primeAgingConfig(ctx.projectId) : Promise.resolve(),
    ])
    const input: HeadlessProviderInput = { ctx, responses, renderConfig }
    const scope = effectScope(true)
    try {
      const instance = scope.run(() => spec.setup(input))
      if (instance === undefined || instance === null) throw new Error(`${ctx.wpCode} 披露表离屏实例化失败`)
      await nextTick()
      if (spec.prepare) await spec.prepare(instance, input)
      await nextTick()
      const payloads = payloadList(await spec.build(instance, input))
      if (spec.post && spec.postAll) throw new Error(`${ctx.wpCode} provider 不能同时声明 post 与 postAll`)
      const sections: Array<HeadlessSectionResult | null> = payloads.map(() => null)
      const allowed: Array<{ payload: HeadlessSyncPayload; index: number }> = []
      payloads.forEach((payload, index) => {
        const section = String(payload.section_id ?? '')
        const why = ctx.sectionGuard ? ctx.sectionGuard(section) : null
        if (why !== null) {
          sections[index] = { section, rows: 0, skipped: why }
        } else {
          allowed.push({ payload, index })
        }
      })

      if (spec.postAll && allowed.length > 0) {
        try {
          const posted = [...await spec.postAll(instance, allowed.map(item => item.payload), input)]
          if (posted.length !== allowed.length) {
            throw new Error(
              `${ctx.wpCode} 批量同步回执数 ${posted.length} 与请求章节数 ${allowed.length} 不一致`,
            )
          }
          allowed.forEach((item, resultIndex) => {
            sections[item.index] = posted[resultIndex]
          })
        } catch (err: any) {
          const message = headlessErrorMessage(err)
          allowed.forEach(({ payload, index }) => {
            sections[index] = { section: String(payload.section_id ?? ''), rows: 0, error: message }
          })
        }
      } else {
        for (const { payload, index } of allowed) {
          const section = String(payload.section_id ?? '')
          try {
            sections[index] = await (
              spec.post ? spec.post(instance, payload, input) : postHeadlessSyncPayload(ctx.projectId, payload)
            )
          } catch (err: any) {
            sections[index] = { section, rows: 0, error: headlessErrorMessage(err) }
          }
        }
      }
      return { sections: sections.filter((item): item is HeadlessSectionResult => item !== null) }
    } finally {
      scope.stop()
    }
  }
}
