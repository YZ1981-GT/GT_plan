/**
 * M1~M3 离屏同步等价用例的 Tab 夹具（spec note-pull-followup-closure R1）：挂载真实的底稿披露 Tab（宿主不传回复，
 * Tab 自己经 `useMxFormData` → `api.get` 取本底稿回复，onMounted 读回表格），调它自己的同步函数，截下它经
 * `http.post` 发出的同步载荷。
 *
 * el-* 一律桩掉（vitest 不跑组件自动注册，未解析的标签会直接执行作用域插槽），子组件浅挂载；调用方负责
 * mock `@/utils/http`、`@/services/apiProxy` 与 `element-plus` 的提示。
 */
import { flushPromises, shallowMount } from '@vue/test-utils'
import { expect, type Mock } from 'vitest'

const EL_TAGS = [
  'el-button', 'el-card', 'el-icon', 'el-input', 'el-table', 'el-table-column', 'el-tag', 'el-tooltip',
]
export const M_TAB_STUBS: Record<string, true> = {
  ...Object.fromEntries(EL_TAGS.map((t) => [t, true])),
  MagicStick: true,
  WpAmountInput: true,
}

export const M_SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'

export type MResponseFixture = ReadonlyArray<{ item_id: string; remark: string | null; conclusion: string | null }>

/** 挂载 Tab（项目 p1，底稿 `wpId`）→ 调它的同步函数 → 返回它发出的载荷 */
export async function payloadFromMTab(
  Comp: unknown,
  mocks: { apiGet: Mock; post: Mock },
  opts: { wpId: string; responses: MResponseFixture },
): Promise<any> {
  mocks.apiGet.mockImplementation(async (url: string) => (
    url === `/api/workpapers/${opts.wpId}/checklist-responses` ? opts.responses.map((r) => ({ ...r })) : {}
  ))
  const w = shallowMount(Comp as any, {
    props: { wpId: opts.wpId, projectId: 'p1', isReadonly: false, applicableStandards: [] },
    global: { stubs: M_TAB_STUBS },
  })
  await flushPromises()
  mocks.post.mockClear()
  await (w.vm as any).$.setupState.syncToDisclosureNotes()
  const call = mocks.post.mock.calls.find(([url]) => url === M_SYNC_URL)
  w.unmount()
  expect(call, 'Tab 没有发出同步请求').toBeTruthy()
  return call![1]
}
