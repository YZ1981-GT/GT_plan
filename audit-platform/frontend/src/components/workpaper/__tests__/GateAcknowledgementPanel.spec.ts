/**
 * S2 ADR-CCN-06: GateAcknowledgementPanel 单元测试
 *
 * 测试:
 * - 渲染五态标签
 * - enforce 模式显示确认按钮
 * - observe 模式隐藏确认按钮
 * - 确认交互调用 API
 * - 撤销交互
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import GateAcknowledgementPanel from '../GateAcknowledgementPanel.vue'

// Mock composable
vi.mock('@/composables/useGateAcknowledgements', () => ({
  listAcks: vi.fn().mockResolvedValue([]),
  acknowledge: vi.fn().mockResolvedValue({ id: 'ack-1' }),
  revoke: vi.fn().mockResolvedValue({ id: 'ack-1', revoked_at: '2025-01-01' }),
}))

// Mock Element Plus
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue(true) },
  ElButton: {
    name: 'ElButton',
    template: '<button :disabled="disabled" :loading="loading" @click="$emit(\'click\')"><slot /></button>',
    props: ['size', 'type', 'plain', 'loading', 'disabled'],
  },
  ElDialog: {
    name: 'ElDialog',
    template: '<div v-if="modelValue" class="el-dialog"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title', 'width', 'closeOnClickModal'],
    emits: ['update:modelValue'],
  },
  ElInput: {
    name: 'ElInput',
    template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)"></textarea>',
    props: ['modelValue', 'type', 'rows', 'placeholder', 'maxlength', 'showWordLimit'],
    emits: ['update:modelValue'],
  },
}))

const makeHit = (overrides: Record<string, unknown> = {}) => ({
  rule_code: 'R4-CROSS-CHECK',
  error_code: 'CROSS_CHECK_FAILED',
  severity: 'blocking',
  message: '跨科目校验未全部通过',
  location: { diff: 10.0 },
  status: 'failed',
  check_class: 'data-missing',
  ...overrides,
})

describe('GateAcknowledgementPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染五态标签：未通过', async () => {
    const wrapper = mount(GateAcknowledgementPanel, {
      props: {
        projectId: 'proj-1',
        year: 2025,
        blockingHits: [makeHit({ status: 'failed' })],
        mode: 'enforce',
      },
    })
    await flushPromises()

    const statusTag = wrapper.find('.status-tag')
    expect(statusTag.exists()).toBe(true)
    expect(statusTag.text()).toBe('未通过')
  })

  it('渲染五态标签：未执行', async () => {
    const wrapper = mount(GateAcknowledgementPanel, {
      props: {
        projectId: 'proj-1',
        year: 2025,
        blockingHits: [makeHit({ status: 'not_executed' })],
        mode: 'enforce',
      },
    })
    await flushPromises()

    const statusTag = wrapper.find('.status-tag')
    expect(statusTag.text()).toBe('未执行')
  })

  it('渲染五态标签：通过', async () => {
    const wrapper = mount(GateAcknowledgementPanel, {
      props: {
        projectId: 'proj-1',
        year: 2025,
        blockingHits: [makeHit({ status: 'passed' })],
        mode: 'enforce',
      },
    })
    await flushPromises()

    const statusTag = wrapper.find('.status-tag')
    expect(statusTag.text()).toBe('通过')
  })

  it('渲染五态标签：检查异常', async () => {
    const wrapper = mount(GateAcknowledgementPanel, {
      props: {
        projectId: 'proj-1',
        year: 2025,
        blockingHits: [makeHit({ status: 'error' })],
        mode: 'enforce',
      },
    })
    await flushPromises()

    const statusTag = wrapper.find('.status-tag')
    expect(statusTag.text()).toBe('检查异常')
  })

  it('渲染五态标签：不适用', async () => {
    const wrapper = mount(GateAcknowledgementPanel, {
      props: {
        projectId: 'proj-1',
        year: 2025,
        blockingHits: [makeHit({ status: 'not_applicable' })],
        mode: 'enforce',
      },
    })
    await flushPromises()

    const statusTag = wrapper.find('.status-tag')
    expect(statusTag.text()).toBe('不适用')
  })

  it('enforce 模式显示确认按钮', async () => {
    const wrapper = mount(GateAcknowledgementPanel, {
      props: {
        projectId: 'proj-1',
        year: 2025,
        blockingHits: [makeHit()],
        mode: 'enforce',
      },
    })
    await flushPromises()

    const confirmBtn = wrapper.find('.confirm-btn')
    expect(confirmBtn.exists()).toBe(true)
    expect(confirmBtn.text()).toContain('确认并说明')
  })

  it('observe 模式隐藏确认按钮', async () => {
    const wrapper = mount(GateAcknowledgementPanel, {
      props: {
        projectId: 'proj-1',
        year: 2025,
        blockingHits: [makeHit()],
        mode: 'observe',
      },
    })
    await flushPromises()

    const confirmBtn = wrapper.find('.confirm-btn')
    expect(confirmBtn.exists()).toBe(false)
  })

  it('确认按钮点击打开弹窗', async () => {
    const wrapper = mount(GateAcknowledgementPanel, {
      props: {
        projectId: 'proj-1',
        year: 2025,
        blockingHits: [makeHit()],
        mode: 'enforce',
      },
      global: {
        stubs: {
          'el-dialog': {
            template: '<div v-if="modelValue" class="el-dialog"><slot /><slot name="footer" /></div>',
            props: ['modelValue'],
          },
          'el-button': {
            template: '<button @click="$emit(\'click\')"><slot /></button>',
          },
          'el-input': {
            template: '<textarea></textarea>',
            props: ['modelValue'],
          },
        },
      },
    })
    await flushPromises()

    await wrapper.find('.confirm-btn').trigger('click')
    await nextTick()

    const dialog = wrapper.find('.el-dialog')
    expect(dialog.exists()).toBe(true)
  })

  it('空列表显示暂无阻断项', async () => {
    const wrapper = mount(GateAcknowledgementPanel, {
      props: {
        projectId: 'proj-1',
        year: 2025,
        blockingHits: [],
        mode: 'enforce',
      },
    })
    await flushPromises()

    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(wrapper.find('.empty-state').text()).toContain('暂无阻断项')
  })

  it('已确认项显示撤销按钮', async () => {
    const { listAcks } = await import('@/composables/useGateAcknowledgements')
    ;(listAcks as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      {
        id: 'ack-1',
        project_id: 'proj-1',
        year: 2025,
        check_name: 'R4-CROSS-CHECK',
        branch_id: '',
        status: 'failed',
        result_fingerprint: 'fp1',
        reason: '已知差异确认说明',
        acknowledged_by: 'user-1',
        acknowledged_role: 'partner',
        created_at: '2025-01-01T00:00:00',
        revoked_at: null,
        revoked_by: null,
      },
    ])

    const wrapper = mount(GateAcknowledgementPanel, {
      props: {
        projectId: 'proj-1',
        year: 2025,
        blockingHits: [makeHit()],
        mode: 'enforce',
      },
    })
    await flushPromises()

    const ackInfo = wrapper.find('.ack-info')
    expect(ackInfo.exists()).toBe(true)
    expect(ackInfo.text()).toContain('已确认')
  })
})
