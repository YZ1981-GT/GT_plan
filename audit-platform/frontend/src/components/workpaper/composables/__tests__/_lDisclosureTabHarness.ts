/**
 * L 循环离屏同步等价用例的 Tab 夹具（组 l，spec note-pull-followup-closure R1）：挂载真实的底稿披露 Tab（onMounted /
 * 外壳注入照常），调它自己的 `syncToDisclosureNotes`，截下它发出的同步请求（按 URL 过滤，L3 国企走批量端点）。
 *
 * el-* 一律桩掉（vitest 不跑组件自动注册，未解析的标签会直接执行作用域插槽），子组件浅挂载；调用方负责 mock 网络模块
 * （Tab 走 `@/utils/http` 或 `@/services/apiProxy`，`post` 传对应的 mock）与 element-plus 的提示。
 */
import { flushPromises, shallowMount } from '@vue/test-utils'
import { expect, type Mock } from 'vitest'

const EL_TAGS = [
  'el-alert', 'el-button', 'el-card', 'el-empty', 'el-icon', 'el-input', 'el-input-number', 'el-option',
  'el-select', 'el-table', 'el-table-column', 'el-tag', 'el-tooltip',
]
export const EL_STUBS: Record<string, true> = Object.fromEntries(EL_TAGS.map((t) => [t, true]))

export const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'
export const BATCH_URL = '/api/projects/p1/disclosure-notes/sync-batch-from-workpaper'

export interface Resp {
  item_id: string
  remark: string | null
  conclusion: string | null
}

/** 只留本底稿前缀的回复（与外壳 / 框架加载口径一致） */
export function ownResponses(prefix: string, list: readonly Resp[]): Resp[] {
  return list.filter((r) => r.item_id.startsWith(prefix))
}

/**
 * 挂载 Tab（项目 p1）→（可选）挂载后再做一步，如外壳在 Tab 挂上之后才加载完表单 → 调它的同步函数 → 返回它发出的同步请求
 * （按发送顺序）
 */
export async function syncRequestsFromTab(
  Comp: unknown,
  post: Mock,
  opts: { wpId: string; provide?: Record<string | symbol, unknown>; afterMount?: () => Promise<unknown> },
): Promise<Array<{ url: string; body: any }>> {
  const w = shallowMount(Comp as any, {
    props: { wpId: opts.wpId, projectId: 'p1', isReadonly: false, applicableStandards: [] },
    global: { stubs: EL_STUBS, provide: opts.provide ?? {} },
  })
  await flushPromises()
  if (opts.afterMount) {
    await opts.afterMount()
    await flushPromises()
  }
  const before = post.mock.calls.length
  await (w.vm as any).$.setupState.syncToDisclosureNotes()
  await flushPromises()
  const sent = post.mock.calls.slice(before)
    .filter(([url]) => url === SYNC_URL || url === BATCH_URL)
    .map(([url, body]) => ({ url: String(url), body }))
  w.unmount()
  expect(sent.length, 'Tab 没有发出同步请求').toBeGreaterThan(0)
  return sent
}
