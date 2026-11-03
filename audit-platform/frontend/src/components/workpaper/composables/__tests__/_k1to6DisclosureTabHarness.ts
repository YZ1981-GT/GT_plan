/**
 * K1~K6 离屏同步等价用例的 Tab 夹具（组 k1，spec note-pull-followup-closure R1）：挂载真实的底稿披露 Tab（onMounted 照常
 * 读回复 / 自动取数），调它自己的 `syncToDisclosureNotes`，截下它发出的**全部**同步载荷（K6 国企一次发 八、12 + 八、43 两条）。
 *
 * el-* 一律桩掉（vitest 不跑组件自动注册，未解析的标签会直接执行作用域插槽），子组件浅挂载；调用方负责 mock 网络模块
 * （Tab 走 `@/utils/http` 或 `@/services/apiProxy`，`post` 传对应的 mock）与 element-plus 的提示。
 */
import { flushPromises, shallowMount } from '@vue/test-utils'
import { expect, type Mock } from 'vitest'

const EL_TAGS = [
  'el-alert', 'el-button', 'el-card', 'el-collapse', 'el-collapse-item', 'el-divider', 'el-empty', 'el-icon',
  'el-input', 'el-input-number', 'el-option', 'el-select', 'el-switch', 'el-table', 'el-table-column', 'el-tag',
  'el-tooltip',
]
export const EL_STUBS: Record<string, true> = Object.fromEntries(EL_TAGS.map((t) => [t, true]))

export const SYNC_URL = '/api/projects/p1/disclosure-notes/sync-from-workpaper'

export interface Resp {
  item_id: string
  remark: string | null
  conclusion: string | null
}

export interface TabSyncResult {
  /** Tab 发出的同步载荷（按发送顺序） */
  payloads: any[]
  /** 挂载 + 同步期间 emit 的保存 `[itemId, value]`（离屏同步不写底稿，这里只用来对照 Tab 自己的行为） */
  saves: Array<[string, unknown]>
}

/** 挂载 Tab（项目 p1，底稿 `wpId`，只给本底稿前缀的回复）→ 调它的同步函数 → 返回它发出的载荷 */
export async function syncPayloadsFromTab(
  Comp: unknown,
  post: Mock,
  opts: { wpId: string; prefix: string; responses: readonly Resp[]; applicableStandards?: string[] },
): Promise<TabSyncResult> {
  const allResponses = new Map(
    opts.responses.filter((r) => r.item_id.startsWith(opts.prefix)).map((r) => [r.item_id, { ...r }]),
  )
  const w = shallowMount(Comp as any, {
    props: {
      wpId: opts.wpId, projectId: 'p1', allResponses, isReadonly: false,
      applicableStandards: opts.applicableStandards ?? [],
    },
    global: { stubs: EL_STUBS },
  })
  await flushPromises()
  const before = post.mock.calls.length
  await (w.vm as any).$.setupState.syncToDisclosureNotes()
  await flushPromises()
  const payloads = post.mock.calls.slice(before).filter(([url]) => url === SYNC_URL).map((c) => c[1])
  const saves = ((w.emitted('save') ?? []) as unknown[][]).map((args) => [String(args[0]), args[1]] as [string, unknown])
  w.unmount()
  expect(payloads.length, 'Tab 没有发出同步请求').toBeGreaterThan(0)
  return { payloads, saves }
}
