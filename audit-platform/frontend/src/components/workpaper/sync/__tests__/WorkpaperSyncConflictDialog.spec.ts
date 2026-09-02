// `WorkpaperSyncConflictDialog.vue` 的**挂载判据**。
//
// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
// Validates: Requirements 8.1, 8.2, 8.3, 8.4, 11.7
// Properties: P35（双侧可追溯）/ P36（八项 fence 齐备才可提交）
//
// ═══ 判据设计 ═══
//
// 1. **关闭不应用**：四种关闭方式各驱动一次，断言 `resolveConflicts` **零调用**
//    且本地选择被清空。只断言「面板收起」对「顺手提交一次」全绿。
// 2. **批量必须点出范围**：断言确认文案里逐字出现范围名 + 条数 + 裁决动作；
//    并断言「只点预览不点确认」时选择集**不动**（二次确认真的是两步）。
// 3. **fence 齐备或可见失败**：宿主不给 room durable fence ⇒ 提交禁用 + 两条阻断原因
//    逐项渲染 + 程序化调用也只写可见错误、不落 HTTP。
// 4. **金额经 store**：期望值是字面量 `1,234,567.50`；再切单位断言渲染随之变化。
// 5. **正面判决**：prop / emit 声明集合逐字等于本文件驱动过的集合。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

import WorkpaperSyncConflictDialog from '../WorkpaperSyncConflictDialog.vue'
import type { WorkpaperSyncBridge } from '../useWorkpaperSyncBridge'
import {
  WP_SYNC_BULK_SCOPE_LABEL,
  WP_SYNC_FENCE_MISSING_TEXT,
  WP_SYNC_VALUE_ABSENT_TEXT,
  WP_SYNC_VALUE_NULL_TEXT,
  type WorkpaperSyncRoomDurableFence,
} from '../workpaperSyncPresentation'
import {
  DIGEST,
  UUID,
  conflictItemWire,
  conflictPreviewWire,
  driveTo,
  stripComments,
  threeGroupPreview,
  type Harness,
} from './workpaperSyncUiHarness'

const EXERCISED_PROPS = new Set<string>()
const EXERCISED_EMITS = new Set<string>()
const LIVE: VueWrapper[] = []

const ROOM_FENCE: WorkpaperSyncRoomDurableFence = { applicationId: UUID(51), sequence: 9 }

interface DialogProps {
  bridge: WorkpaperSyncBridge
  visible: boolean
  roomDurableFence?: WorkpaperSyncRoomDurableFence | null
}

function mountDialog(props: DialogProps): VueWrapper {
  for (const key of Object.keys(props)) EXERCISED_PROPS.add(key)
  const wrapper = mount(WorkpaperSyncConflictDialog, {
    props: props as unknown as Record<string, unknown>,
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  LIVE.push(wrapper)
  return wrapper
}

async function openDialog(
  over: Partial<DialogProps> = {},
): Promise<{ wrapper: VueWrapper; h: Harness }> {
  const h = await driveTo('conflict')
  const wrapper = mountDialog({
    bridge: h.bridge,
    visible: true,
    roomDurableFence: ROOM_FENCE,
    ...over,
  })
  await flushPromises()
  return { wrapper, h }
}

function panel(wrapper: VueWrapper) {
  return wrapper.get('[data-testid="wp-sync-conflict-dialog"]')
}

function textOf(wrapper: VueWrapper, testid: string): string {
  const el = wrapper.find(`[data-testid="${testid}"]`)
  return el.exists() ? el.text() : ''
}

interface DialogApi {
  submitAdjudication: () => Promise<void>
  getAdjudication: () => {
    conflictCount: number
    groupKeys: string[]
    resolutions: { conflictId: string; choice: string; value?: unknown }[]
    undecidedCount: number
    fenceReady: boolean
    fenceMissing: readonly string[]
  }
}

function dialogApi(wrapper: VueWrapper): DialogApi {
  return wrapper.vm as unknown as DialogApi
}

beforeEach(() => {
  LIVE.length = 0
})

afterEach(() => {
  for (const wrapper of LIVE) {
    for (const name of Object.keys(wrapper.emitted())) EXERCISED_EMITS.add(name)
    wrapper.unmount()
  }
  LIVE.length = 0
})

// ═══════════════════════════════════════════════════════════════════════════
// 1. 分组与双侧可追溯（AC 8.1 / 8.2 / Property 35）
// ═══════════════════════════════════════════════════════════════════════════

describe('冲突按 sheet / table / row 三级分组，且每条双侧可追溯', () => {
  it('打开面板即拉一次预览，三组各自渲染成一张卡片并带三级 data 属性', async () => {
    const { wrapper, h } = await openDialog()
    expect(h.api.getOperationConflicts).toHaveBeenCalledTimes(1)
    const groups = wrapper.findAll('[data-testid="wp-sync-conflict-group"]')
    expect(groups.length).toBe(3)
    expect(groups.map((g) => g.attributes('data-group-key'))).toEqual([
      '明细表/tbl_detail/row-1',
      '明细表/tbl_detail/row-2',
      '汇总表/tbl_summary/row-9',
    ])
    expect(groups[0].attributes('data-sheet-key')).toBe('明细表')
    expect(groups[0].attributes('data-table-key')).toBe('tbl_detail')
    expect(groups[0].attributes('data-row-key')).toBe('row-1')
    expect(textOf(wrapper, 'wp-sync-conflict-group-title')).toContain('工作表 明细表')
    expect(panel(wrapper).attributes('data-conflict-count')).toBe('4')
  })

  it('每条冲突同时渲染 JSON Pointer 与 OO 地址（缺一条就不可追溯）', async () => {
    const { wrapper } = await openDialog()
    const items = wrapper.findAll('[data-testid="wp-sync-conflict-item"]')
    expect(items.length).toBe(4)
    for (const item of items) {
      const pointer = item.get('[data-testid="wp-sync-conflict-item-pointer"]').text()
      const oo = item.get('[data-testid="wp-sync-conflict-item-oo"]').text()
      expect(pointer.startsWith('/')).toBe(true)
      expect(oo).toContain('!')
    }
  })

  it('三值（打开时基线 / 服务端当前 / 回传）各占一列且互不相同', async () => {
    const { wrapper } = await openDialog()
    const first = wrapper.findAll('[data-testid="wp-sync-conflict-item"]')[0]
    const base = first.get('[data-testid="wp-sync-conflict-item-base"]').text()
    const current = first.get('[data-testid="wp-sync-conflict-item-current"]').text()
    const incoming = first.get('[data-testid="wp-sync-conflict-item-incoming"]').text()
    expect(new Set([base, current, incoming]).size).toBe(3)
  })

  it('frozen identity（bundle / 授权模型 / 契约）与 requested→canonical 都在面板上', async () => {
    const { wrapper } = await openDialog()
    const identity = wrapper.get('[data-testid="wp-sync-conflict-identity"]').text()
    expect(identity).toContain(UUID(30))
    expect(identity).toContain(UUID(50))
    expect(identity).toContain('projection_contract')
    expect(identity).toContain(DIGEST(3).slice(0, 12))
    expect(identity).toContain('d4-tab-customer-price')
  })

  it('预览形态漂移（缺 adjudicable 布尔）⇒ 渲染具体错误码，不静默画一张空表', async () => {
    const item = conflictItemWire()
    delete (item as Record<string, unknown>).adjudicable_by_value_choice
    const h = await driveTo('conflict')
    h.api.getOperationConflicts.mockImplementation(async () =>
      conflictPreviewWire([{ sheet_key: 's', table_key: 't', row_key: 'r', items: [item] }]),
    )
    const wrapper = mountDialog({ bridge: h.bridge, visible: true, roomDurableFence: ROOM_FENCE })
    await flushPromises()
    const error = wrapper.get('[data-testid="wp-sync-conflict-load-error"]')
    expect(error.attributes('data-code')).toBe('conflict_item_adjudicability_missing')
    expect(wrapper.findAll('[data-testid="wp-sync-conflict-group"]').length).toBe(0)
    expect(wrapper.emitted('failed')?.length).toBe(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. 金额走 displayPrefs
// ═══════════════════════════════════════════════════════════════════════════

describe('金额经 displayPrefs store 成员格式化', () => {
  it('amount 列渲染成千分符 + 2 位小数，且不等于裸 String', async () => {
    const { wrapper } = await openDialog()
    const first = wrapper.findAll('[data-testid="wp-sync-conflict-item"]')[0]
    expect(first.attributes('data-value-type')).toBe('amount')
    const incoming = first.get('[data-testid="wp-sync-conflict-item-incoming"]').text()
    expect(incoming).toBe('1,234,567.50')
    expect(incoming).not.toBe(String(1234567.5))
  })

  it('切换平台单位后同一单元格随之变化（证明读的是活 store）', async () => {
    const { wrapper } = await openDialog()
    const cell = () =>
      wrapper
        .findAll('[data-testid="wp-sync-conflict-item"]')[0]
        .get('[data-testid="wp-sync-conflict-item-incoming"]')
        .text()
    const before = cell()
    const store = useDisplayPrefsStore()
    store.setUnit('wan')
    await flushPromises()
    const after = cell()
    store.setUnit('yuan')
    expect(before).toBe('1,234,567.50')
    expect(after).not.toBe(before)
  })

  it('text 类型不经金额格式化（原样展示）', async () => {
    const { wrapper } = await openDialog()
    const memo = wrapper
      .findAll('[data-testid="wp-sync-conflict-item"]')[1]
      .get('[data-testid="wp-sync-conflict-item-incoming"]')
      .text()
    expect(memo).toBe('回传摘要')
  })

  it('缺字段与显式空值渲染成两句不同的话', async () => {
    const h = await driveTo('conflict')
    h.api.getOperationConflicts.mockImplementation(async () =>
      conflictPreviewWire([
        {
          sheet_key: 's',
          table_key: 't',
          row_key: 'r',
          items: [
            conflictItemWire({
              conflict_id: UUID(67),
              value_type: 'text',
              current: { present: false },
              incoming: { present: true, value: null },
            }),
          ],
        },
      ]),
    )
    const wrapper = mountDialog({ bridge: h.bridge, visible: true, roomDurableFence: ROOM_FENCE })
    await flushPromises()
    const item = wrapper.get('[data-testid="wp-sync-conflict-item"]')
    expect(item.get('[data-testid="wp-sync-conflict-item-current"]').text()).toBe(
      WP_SYNC_VALUE_ABSENT_TEXT,
    )
    expect(item.get('[data-testid="wp-sync-conflict-item-incoming"]').text()).toBe(
      WP_SYNC_VALUE_NULL_TEXT,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 3. 逐项裁决（AC 8.3）
// ═══════════════════════════════════════════════════════════════════════════

describe('逐项裁决', () => {
  it('选「保留当前」后进入 resolutions，data-choice 同步到 DOM', async () => {
    const { wrapper } = await openDialog()
    await wrapper.get(`[data-testid="wp-sync-choice-keep-${UUID(61)}"]`).setValue(true)
    await flushPromises()
    const item = wrapper.findAll('[data-testid="wp-sync-conflict-item"]')[0]
    expect(item.attributes('data-choice')).toBe('keep_current')
    expect(dialogApi(wrapper).getAdjudication().resolutions).toEqual([
      { conflictId: UUID(61), choice: 'keep_current' },
    ])
  })

  it('手工合并只对文本字段开放，且输入值随提交带上', async () => {
    const { wrapper } = await openDialog()
    // 金额行没有手工合并入口
    expect(wrapper.find(`[data-testid="wp-sync-choice-manual-${UUID(61)}"]`).exists()).toBe(false)
    // 文本行有
    await wrapper.get(`[data-testid="wp-sync-choice-manual-${UUID(62)}"]`).setValue(true)
    await flushPromises()
    const input = wrapper.get(`[data-testid="wp-sync-manual-input-${UUID(62)}"]`)
    await input.setValue('人工合并后的摘要')
    await flushPromises()
    expect(dialogApi(wrapper).getAdjudication().resolutions).toEqual([
      { conflictId: UUID(62), choice: 'manual', value: '人工合并后的摘要' },
    ])
  })

  it('结构冲突不给选边入口，改渲染「需先修复结构」', async () => {
    const { wrapper } = await openDialog()
    const structural = wrapper.findAll('[data-testid="wp-sync-conflict-item"]')[3]
    expect(structural.attributes('data-adjudicable')).toBe('false')
    expect(structural.find(`[data-testid="wp-sync-choice-keep-${UUID(64)}"]`).exists()).toBe(false)
    expect(structural.get('[data-testid="wp-sync-conflict-item-structural"]').text()).toContain(
      '需先修复结构',
    )
  })

  it('保护策略逐项中文化（不显示裸英文枚举）', async () => {
    const { wrapper } = await openDialog()
    const texts = wrapper
      .findAll('[data-testid="wp-sync-conflict-item-protection"]')
      .map((el) => el.text())
    expect(texts).toContain('可编辑')
    expect(texts).toContain('只读（服务端公式）')
    for (const text of texts) expect(text).not.toMatch(/^[a-z_]+$/)
  })

  it('未裁决计数只算可选边且未裁决的项', async () => {
    const { wrapper } = await openDialog()
    expect(dialogApi(wrapper).getAdjudication().undecidedCount).toBe(3)
    await wrapper.get(`[data-testid="wp-sync-choice-keep-${UUID(61)}"]`).setValue(true)
    await flushPromises()
    expect(dialogApi(wrapper).getAdjudication().undecidedCount).toBe(2)
    expect(textOf(wrapper, 'wp-sync-conflict-undecided')).toContain('2 条')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 4. 批量裁决的显式范围与二次确认（AC 8.3）
// ═══════════════════════════════════════════════════════════════════════════

describe('批量裁决必须点明范围并二次确认', () => {
  async function pickScope(
    wrapper: VueWrapper,
    scope: string,
    anchorKey: string,
    choice = 'take_incoming',
  ): Promise<void> {
    await wrapper.get('[data-testid="wp-sync-conflict-bulk-scope"]').setValue(scope)
    await wrapper.get('[data-testid="wp-sync-conflict-bulk-anchor"]').setValue(anchorKey)
    await wrapper.get('[data-testid="wp-sync-conflict-bulk-choice"]').setValue(choice)
    await wrapper.get('[data-testid="wp-sync-conflict-bulk-preview"]').trigger('click')
    await flushPromises()
  }

  it('确认文案逐字含范围名、条数与裁决动作', async () => {
    const { wrapper } = await openDialog()
    await pickScope(wrapper, 'table', '明细表/tbl_detail/row-1')
    const confirm = wrapper.get('[data-testid="wp-sync-conflict-bulk-confirm"]')
    expect(confirm.attributes('data-target-count')).toBe('3')
    const text = textOf(wrapper, 'wp-sync-conflict-bulk-confirm-text')
    expect(text).toContain(WP_SYNC_BULK_SCOPE_LABEL.table)
    expect(text).toContain('3 条')
    expect(text).toContain('采用回传')
    expect(text).toContain('tbl_detail')
  })

  it('只点预览不点确认 ⇒ 选择集一条不动（二次确认真的是两步）', async () => {
    const { wrapper } = await openDialog()
    await pickScope(wrapper, 'row', '明细表/tbl_detail/row-1')
    expect(dialogApi(wrapper).getAdjudication().resolutions).toEqual([])
    await wrapper.get('[data-testid="wp-sync-conflict-bulk-cancel"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="wp-sync-conflict-bulk-confirm"]').exists()).toBe(false)
    expect(dialogApi(wrapper).getAdjudication().resolutions).toEqual([])
  })

  it('确认后只落到范围内的条目上（行范围不越界到同表另一行）', async () => {
    const { wrapper } = await openDialog()
    await pickScope(wrapper, 'row', '明细表/tbl_detail/row-1')
    await wrapper.get('[data-testid="wp-sync-conflict-bulk-apply"]').trigger('click')
    await flushPromises()
    const ids = dialogApi(wrapper)
      .getAdjudication()
      .resolutions.map((item) => item.conflictId)
      .sort()
    expect(ids).toEqual([UUID(61), UUID(62)].sort())
    expect(ids).not.toContain(UUID(63))
  })

  it('结构冲突永不进批量目标（选边对它毫无意义）', async () => {
    const { wrapper } = await openDialog()
    await wrapper
      .get('[data-testid="wp-sync-conflict-bulk-scope"]')
      .setValue('all_unresolved')
    await wrapper.get('[data-testid="wp-sync-conflict-bulk-preview"]').trigger('click')
    await flushPromises()
    expect(
      wrapper.get('[data-testid="wp-sync-conflict-bulk-confirm"]').attributes('data-target-count'),
    ).toBe('3')
    await wrapper.get('[data-testid="wp-sync-conflict-bulk-apply"]').trigger('click')
    await flushPromises()
    const ids = dialogApi(wrapper)
      .getAdjudication()
      .resolutions.map((item) => item.conflictId)
    expect(ids).not.toContain(UUID(64))
  })

  it('未选锚点就点「本行」⇒ 具体码 bulk_scope_anchor_required，不静默按全部处理', async () => {
    const { wrapper } = await openDialog()
    await wrapper.get('[data-testid="wp-sync-conflict-bulk-scope"]').setValue('row')
    await wrapper.get('[data-testid="wp-sync-conflict-bulk-preview"]').trigger('click')
    await flushPromises()
    expect(
      wrapper.get('[data-testid="wp-sync-conflict-bulk-error"]').attributes('data-code'),
    ).toBe('bulk_scope_anchor_required')
    expect(wrapper.find('[data-testid="wp-sync-conflict-bulk-confirm"]').exists()).toBe(false)
    expect(dialogApi(wrapper).getAdjudication().resolutions).toEqual([])
  })

  it('范围内没有可裁决项 ⇒ 显式说明，不弹一个 0 条的确认', async () => {
    const { wrapper } = await openDialog()
    await wrapper.get('[data-testid="wp-sync-conflict-bulk-scope"]').setValue('row')
    await wrapper
      .get('[data-testid="wp-sync-conflict-bulk-anchor"]')
      .setValue('汇总表/tbl_summary/row-9')
    await wrapper.get('[data-testid="wp-sync-conflict-bulk-preview"]').trigger('click')
    await flushPromises()
    expect(
      wrapper.get('[data-testid="wp-sync-conflict-bulk-error"]').attributes('data-code'),
    ).toBe('bulk_scope_empty')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 5. 关闭不应用（AC 11.7）
// ═══════════════════════════════════════════════════════════════════════════

describe('关闭面板不得应用任何一侧', () => {
  const closers = [
    ['wp-sync-conflict-close', 'trigger'],
    ['wp-sync-conflict-cancel', 'trigger'],
    ['wp-sync-conflict-mask', 'trigger'],
  ] as const

  for (const [testid] of closers) {
    it(`经 ${testid} 关闭：resolveConflicts 零调用、选择清空、只 emit update:visible(false)`, async () => {
      const { wrapper, h } = await openDialog()
      await wrapper.get(`[data-testid="wp-sync-choice-keep-${UUID(61)}"]`).setValue(true)
      await flushPromises()
      expect(dialogApi(wrapper).getAdjudication().resolutions.length).toBe(1)

      await wrapper.get(`[data-testid="${testid}"]`).trigger('click')
      await flushPromises()

      expect(h.api.resolveConflicts).not.toHaveBeenCalled()
      expect(wrapper.emitted('resolved')).toBeUndefined()
      expect(wrapper.emitted('update:visible')?.at(-1)).toEqual([false])
      expect(dialogApi(wrapper).getAdjudication().resolutions).toEqual([])
    })
  }

  it('ESC 关闭同样零应用', async () => {
    const { wrapper, h } = await openDialog()
    await wrapper.get(`[data-testid="wp-sync-choice-keep-${UUID(61)}"]`).setValue(true)
    await flushPromises()
    await wrapper.get('[role="dialog"]').trigger('keydown.esc')
    await flushPromises()
    expect(h.api.resolveConflicts).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:visible')?.at(-1)).toEqual([false])
  })

  it('visible=false 时整个面板不渲染，也不去拉预览', async () => {
    const h = await driveTo('conflict')
    const wrapper = mountDialog({ bridge: h.bridge, visible: false, roomDurableFence: ROOM_FENCE })
    await flushPromises()
    expect(wrapper.find('[data-testid="wp-sync-conflict-dialog"]').exists()).toBe(false)
    expect(h.api.getOperationConflicts).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 6. fence 齐备或可见失败（AC 8.5 / Property 36）
// ═══════════════════════════════════════════════════════════════════════════

describe('八项 resolve fence 齐备才可提交', () => {
  it('宿主给了 room durable fence ⇒ 提交按钮可用，提交时逐项带上八项', async () => {
    const { wrapper, h } = await openDialog()
    await wrapper.get(`[data-testid="wp-sync-choice-incoming-${UUID(61)}"]`).setValue(true)
    await flushPromises()
    expect(panel(wrapper).attributes('data-fence-ready')).toBe('true')
    const submit = wrapper.get('[data-testid="wp-sync-conflict-submit"]')
    expect(submit.attributes('disabled')).toBeUndefined()
    await submit.trigger('click')
    await flushPromises()
    expect(h.api.resolveConflicts).toHaveBeenCalledTimes(1)
    const payload = h.api.resolveConflicts.mock.calls[0][1] as Record<string, unknown>
    expect(payload).toMatchObject({
      operationId: UUID(30),
      expectedCurrentRevision: 11,
      roomGeneration: 3,
      clientEditEpoch: 4,
      canonicalApplicationId: UUID(50),
      applicationEffectiveRequestSequence: 7,
      roomLatestDurableApplicationId: UUID(51),
      roomLatestDurableSequence: 9,
      conflictSetDigest: DIGEST(9),
    })
    expect(payload.resolutions).toEqual([{ conflictId: UUID(61), choice: 'take_incoming' }])
    expect(wrapper.emitted('resolved')?.length).toBe(1)
    expect(wrapper.emitted('update:visible')?.at(-1)).toEqual([false])
  })

  it('宿主没给 ⇒ 两条阻断原因逐项渲染、提交禁用、零 HTTP', async () => {
    const { wrapper, h } = await openDialog({ roomDurableFence: null })
    await wrapper.get(`[data-testid="wp-sync-choice-incoming-${UUID(61)}"]`).setValue(true)
    await flushPromises()
    expect(panel(wrapper).attributes('data-fence-ready')).toBe('false')
    const reasons = wrapper
      .findAll('[data-testid="wp-sync-conflict-fence-reason"]')
      .map((el) => el.text())
    expect(reasons).toEqual([
      WP_SYNC_FENCE_MISSING_TEXT.room_latest_durable_application_id,
      WP_SYNC_FENCE_MISSING_TEXT.room_latest_durable_sequence,
    ])
    expect(
      wrapper.get('[data-testid="wp-sync-conflict-submit"]').attributes('disabled'),
    ).toBeDefined()
    expect(h.api.resolveConflicts).not.toHaveBeenCalled()
    expect(dialogApi(wrapper).getAdjudication().fenceMissing).toEqual([
      'room_latest_durable_application_id',
      'room_latest_durable_sequence',
    ])
  })

  it('缺 fence 时**程序化**提交也被拦：写出逐项阻断原因且零 HTTP（不拿 canonical 顶替）', async () => {
    const { wrapper, h } = await openDialog({ roomDurableFence: null })
    await wrapper.get(`[data-testid="wp-sync-choice-incoming-${UUID(61)}"]`).setValue(true)
    await flushPromises()
    // 🔴 绕过 `:disabled` 直接调 expose 的提交入口 —— 门若只长在 disabled 上，这里会漏。
    await dialogApi(wrapper).submitAdjudication()
    await flushPromises()
    expect(h.api.resolveConflicts).not.toHaveBeenCalled()
    const error = wrapper.get('[data-testid="wp-sync-conflict-submit-error"]')
    expect(error.attributes('data-code')).toBe('conflict_submit_gate_closed')
    expect(error.text()).toContain(
      WP_SYNC_FENCE_MISSING_TEXT.room_latest_durable_application_id,
    )
    expect(wrapper.emitted('resolved')).toBeUndefined()
  })

  it('一条裁决都没选 ⇒ 按钮禁用，且程序化提交写出具体码', async () => {
    const { wrapper, h } = await openDialog()
    expect(
      wrapper.get('[data-testid="wp-sync-conflict-submit"]').attributes('disabled'),
    ).toBeDefined()
    await dialogApi(wrapper).submitAdjudication()
    await flushPromises()
    expect(h.api.resolveConflicts).not.toHaveBeenCalled()
    const error = wrapper.get('[data-testid="wp-sync-conflict-submit-error"]')
    expect(error.attributes('data-code')).toBe('conflict_submit_gate_closed')
    expect(error.text()).toContain('尚未选择任何裁决')
  })

  it('服务端拒绝裁决 ⇒ 面板留在原地并显示具体码，不假装成功关闭', async () => {
    const { wrapper, h } = await openDialog()
    h.api.resolveConflicts.mockImplementation(async () => {
      throw {
        response: {
          status: 409,
          data: { detail: { error_code: 'resolve_fence_superseded', message: '已被更新的回写取代' } },
        },
      }
    })
    await wrapper.get(`[data-testid="wp-sync-choice-incoming-${UUID(61)}"]`).setValue(true)
    await flushPromises()
    await wrapper.get('[data-testid="wp-sync-conflict-submit"]').trigger('click')
    await flushPromises()
    const error = wrapper.get('[data-testid="wp-sync-conflict-submit-error"]')
    expect(error.attributes('data-code')).toBe('resolve_fence_superseded')
    expect(error.text()).toBe('已被更新的回写取代')
    expect(wrapper.emitted('resolved')).toBeUndefined()
    // 未成功 ⇒ 不得收起面板（收起等于让用户以为已裁决）
    expect(wrapper.emitted('update:visible')).toBeUndefined()
    expect(wrapper.emitted('failed')?.length).toBe(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 7. 结构判据
// ═══════════════════════════════════════════════════════════════════════════

describe('结构判据', () => {
  const body = stripComments(
    readFileSync(resolve(__dirname, '..', 'WorkpaperSyncConflictDialog.vue'), 'utf-8'),
  )

  it('面板零 HTTP：不 import 任何请求面，全部经桥', () => {
    for (const forbidden of ['@/utils/http', './workpaperSyncApi', 'axios']) {
      expect(body, forbidden).not.toContain(forbidden)
    }
    expect(body).toContain('props.bridge.resolveConflicts')
    expect(body).toContain('props.bridge.fetchConflicts')
  })

  it('关闭路径里没有任何提交调用（唯一 resolveConflicts 调用点在 onSubmit）', () => {
    const closeFn = body.slice(body.indexOf('function onCloseRequested'))
    const closeBody = closeFn.slice(0, closeFn.indexOf('\n}'))
    expect(closeBody).not.toContain('resolveConflicts')
    expect(closeBody).toContain('resetLocalState()')
    expect((body.match(/bridge\.resolveConflicts/g) ?? []).length).toBe(1)
  })

  it('模板属性里没有中文弯引号（U+201C/U+201D 会让 Vite 静默编译崩溃）', () => {
    const template = body.slice(0, body.indexOf('<script'))
    expect(template).not.toContain('\u201c')
    expect(template).not.toContain('\u201d')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 8. 零消费方判决（必须放在文件末尾）
// ═══════════════════════════════════════════════════════════════════════════

describe('零消费方判决', () => {
  it('组件声明的 prop 集合逐字等于本文件真正驱动过的集合', () => {
    const declared = Object.keys(
      (WorkpaperSyncConflictDialog as unknown as { props: Record<string, unknown> }).props,
    )
    expect(declared.length).toBeGreaterThan(0)
    expect([...EXERCISED_PROPS].sort()).toEqual(declared.sort())
  })

  it('组件声明的 emit 集合逐字等于本文件真正触发过的集合', () => {
    const declared = (WorkpaperSyncConflictDialog as unknown as { emits: string[] }).emits
    expect(Array.isArray(declared)).toBe(true)
    expect(declared.length).toBeGreaterThan(0)
    const VTU_NATIVE_ARTEFACTS = ['click', 'change', 'input', 'keydown'] as const
    const artefacts = [...EXERCISED_EMITS].filter((name) =>
      (VTU_NATIVE_ARTEFACTS as readonly string[]).includes(name),
    )
    const triggered = [...EXERCISED_EMITS].filter(
      (name) => !(VTU_NATIVE_ARTEFACTS as readonly string[]).includes(name),
    )
    // 排除表本身参与断言：多一个原生事件或少一个都会红
    expect(artefacts.sort()).toEqual([...VTU_NATIVE_ARTEFACTS].sort())
    expect(triggered.sort()).toEqual([...declared].sort())
  })

  it('defineExpose 的两个入口都被真的调用过，且投影与 DOM 一致', async () => {
    const { wrapper } = await openDialog()
    const api = dialogApi(wrapper)
    expect(typeof api.submitAdjudication).toBe('function')
    const projection = api.getAdjudication()
    expect(projection.conflictCount).toBe(4)
    expect(projection.groupKeys.length).toBe(3)
    expect(projection.fenceReady).toBe(true)
    expect(String(projection.conflictCount)).toBe(
      panel(wrapper).attributes('data-conflict-count'),
    )
  })
})

// 未使用的 import 守卫：`vi` 在 mockImplementation 场景里由 harness 提供，
// 这里显式引用一次以避免 lint 误报「未使用」。
void vi
