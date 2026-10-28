/**
 * 跟函 / 对象核实 / 差异调节的行级附件（spec attachment-confirmation-evidence-loop 需求 4，变异 M11）
 *
 * 位置：表页 = 本循环对应表编码（跟函 X0-3 / 对象核实 X0-2 / 差异调节 X0-4，按 wpCode 取），单元格 = `row:{行 id}`；
 * 只读只能查看。ItemAttachment 的 `cellRef` 优先于 `itemIndex`（列表按该位置从共享链接仓取）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import ElementPlus from 'element-plus'

const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...a: any[]) => mockGet(...a), post: vi.fn(), delete: vi.fn() },
  downloadFile: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'P-route' }, query: {} }),
  useRouter: () => ({ push: vi.fn(), resolve: vi.fn(() => ({ href: '' })) }),
}))
vi.mock('@/components/attachment/AttachmentEyeButton.vue', () => ({
  default: defineComponent({ name: 'EyeStub', props: ['attachmentId'], setup: (p: any) => () => h('i', { class: 'eye', 'data-id': p.attachmentId }) }),
}))
vi.mock('@/components/attachment/RowEvidenceEye.vue', () => ({
  default: defineComponent({
    name: 'RowEyeStub',
    props: ['wpId', 'sheetKey', 'cellRef', 'projectId'],
    setup: (p: any) => () => h('i', { class: 'row-eye', 'data-sheet': p.sheetKey, 'data-cell': p.cellRef }),
  }),
}))

import ItemAttachment from '../../ItemAttachment.vue'
import FollowupDetail from '../followup/FollowupDetail.vue'
import EntityVerifyDetail from '../entityVerify/EntityVerifyDetail.vue'
import DiffReconcileMaster from '../diffReconcile/DiffReconcileMaster.vue'
import GtConfirmationFollowup from '../followup/GtConfirmationFollowup.vue'
import { resetWpEvidenceLinksForTest } from '@/composables/useWpEvidenceLinks'

const axiosLike = (data: unknown) => Promise.resolve({ data, status: 200 })
const ItemStub = defineComponent({
  name: 'ItemAttachment',
  props: ['projectId', 'wpId', 'sheetKey', 'cellRef', 'itemIndex', 'evidenceType', 'readonly'],
  setup: (p: any) => () => h('div', { class: 'item-stub', 'data-cell': p.cellRef, 'data-sheet': p.sheetKey, 'data-type': p.evidenceType, 'data-ro': String(!!p.readonly) }),
})
const ctx = { wpId: 'W1', projectId: 'P1' }

beforeEach(() => {
  mockGet.mockReset()
  resetWpEvidenceLinksForTest()
})

describe('ItemAttachment 的行位置', () => {
  it('给了 cellRef 就按它列出本行附件（不再落到 item:0）', async () => {
    mockGet.mockImplementation(() => axiosLike([
      { id: 'L1', wp_id: 'W1', sheet_name: 'D0-3', cell_ref: 'row:f1', attachment_id: 'A1',
        attachment: { id: 'A1', file_name: '跟函照片.jpg', file_size: 20, file_type: 'image', ocr_status: 'pending' } },
      { id: 'L2', wp_id: 'W1', sheet_name: 'D0-3', cell_ref: 'item:0', attachment_id: 'A2',
        attachment: { id: 'A2', file_name: '别的槽位.pdf', file_size: 20, file_type: 'pdf', ocr_status: 'pending' } },
    ]))
    const w = mount(ItemAttachment, {
      props: { ...ctx, sheetKey: 'D0-3', cellRef: 'row:f1', readonly: true },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    expect(w.text()).toContain('跟函照片.jpg')
    expect(w.text()).not.toContain('别的槽位.pdf')
    expect(w.find('.el-upload').exists()).toBe(false) // 只读不能上传
  })
})

describe('详情区的行级附件', () => {
  it('跟函：表页 + row:{行 id}、类型「审计证据」，只读透传', () => {
    const w = mount(FollowupDetail, {
      props: { row: { _row_id: 'f1', scenario: 'immediate' }, readonly: true, ...ctx, sheetKey: 'D0-3' },
      global: { plugins: [ElementPlus], stubs: { ItemAttachment: ItemStub } },
    })
    const item = w.find('.item-stub')
    expect([item.attributes('data-sheet'), item.attributes('data-cell'), item.attributes('data-type'), item.attributes('data-ro')])
      .toEqual(['D0-3', 'row:f1', 'evidence', 'true'])
  })

  it('跟函：没有底稿上下文时不显示附件区', () => {
    const w = mount(FollowupDetail, {
      props: { row: { _row_id: 'f1' }, readonly: false },
      global: { plugins: [ElementPlus], stubs: { ItemAttachment: ItemStub } },
    })
    expect(w.find('.item-stub').exists()).toBe(false)
  })

  it('对象核实：类型「支持文件」', () => {
    const w = mount(EntityVerifyDetail, {
      props: { row: { _row_id: 'e1' } as any, readonly: false, dictData: {}, ...ctx, sheetKey: 'K0-2' },
      global: { plugins: [ElementPlus], stubs: { ItemAttachment: ItemStub } },
    })
    const item = w.find('.item-stub')
    expect([item.attributes('data-sheet'), item.attributes('data-cell'), item.attributes('data-type')]).toEqual(['K0-2', 'row:e1', 'support'])
  })

  it('跟函宿主按 wpCode 取本循环跟函表编码（K0 → K0-3），项目缺省取路由', async () => {
    const w = mount(GtConfirmationFollowup, {
      props: { wpId: 'W1', wpCode: 'K0', htmlData: { _format: 'confirmation-followup-v1', rows: [] }, readonly: false },
      global: {
        plugins: [ElementPlus],
        stubs: { FollowupDashboard: true, FollowupMaster: true, FollowupMemoPreview: true, FollowupDetail: { name: 'FollowupDetail', props: ['sheetKey', 'projectId', 'wpId'], template: '<i class="fd" :data-sheet="sheetKey" :data-pid="projectId" />' } },
      },
    })
    await flushPromises()
    const fd = w.find('.fd')
    expect([fd.attributes('data-sheet'), fd.attributes('data-pid')]).toEqual(['K0-3', 'P-route'])
  })
})

describe('差异调节网格的附件列', () => {
  const base = {
    rows: [{ _row_id: 'd1', entity_name: '甲', difference: 10 }], isDirty: false,
    subjectOptions: [], diffTypeOptions: [], subjectSummary: [], isOverMateriality: () => false,
    ...ctx, evidenceSheet: 'D0-4',
  }

  it('只读：小眼睛在、没有 📎', async () => {
    const w = mount(DiffReconcileMaster, { props: { ...base, readonly: true }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    const eye = w.find('.row-eye')
    expect([eye.attributes('data-sheet'), eye.attributes('data-cell')]).toEqual(['D0-4', 'row:d1'])
    expect(w.find('[data-testid="diff-row-attach"]').exists()).toBe(false)
  })

  it('编辑态：多一个 📎（弹出本行附件清单）', async () => {
    const w = mount(DiffReconcileMaster, { props: { ...base, readonly: false }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.find('[data-testid="diff-row-attach"]').exists()).toBe(true)
  })
})
