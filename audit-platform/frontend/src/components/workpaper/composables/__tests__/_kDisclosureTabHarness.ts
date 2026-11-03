/**
 * K7~K10 离屏同步等价用例的 Tab 夹具（spec note-pull-followup-closure R1）：挂载真实的底稿披露 Tab（onMounted 照常
 * 读回复 / 自动取数），调它自己的 `syncToDisclosureNotes`，截下它经 `http.post` 发出的同步载荷。
 *
 * el-* 一律桩掉（vitest 不跑组件自动注册，未解析的标签会直接执行作用域插槽），子组件浅挂载；调用方负责
 * mock `@/utils/http` 与 `element-plus` 的提示。
 */
import { flushPromises, shallowMount } from '@vue/test-utils'
import { expect, type Mock } from 'vitest'

const EL_TAGS = [
  'el-alert', 'el-button', 'el-card', 'el-icon', 'el-input', 'el-input-number', 'el-option', 'el-select',
  'el-table', 'el-table-column', 'el-tag', 'el-tooltip',
]
export const EL_STUBS: Record<string, true> = Object.fromEntries(EL_TAGS.map((t) => [t, true]))

export const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'

export interface TabMountResult {
  payload: any
  /** Tab 挂载期间 emit 的保存（item_id 列表；离屏同步不写底稿，这里只用来对照 Tab 自己的行为） */
  saves: string[]
}

/** 挂载 Tab → 调它的同步函数 → 返回它发出的载荷（项目 p1，底稿 `wpId`） */
export async function payloadFromTab(
  Comp: unknown,
  post: Mock,
  opts: { wpId: string; responses: ReadonlyArray<{ item_id: string; remark: unknown; conclusion: unknown }> },
): Promise<TabMountResult> {
  const allResponses = new Map(opts.responses.map((r) => [r.item_id, { ...r }]))
  const w = shallowMount(Comp as any, {
    props: { wpId: opts.wpId, projectId: 'p1', allResponses, isReadonly: false, applicableStandards: [] },
    global: { stubs: EL_STUBS },
  })
  await flushPromises()
  post.mockClear()
  await (w.vm as any).$.setupState.syncToDisclosureNotes()
  const call = post.mock.calls.find(([url]) => url === SYNC_URL)
  const saves = ((w.emitted('save') ?? []) as unknown[][]).map((args) => String(args[0]))
  w.unmount()
  expect(call, 'Tab 没有发出同步请求').toBeTruthy()
  return { payload: call![1], saves }
}
