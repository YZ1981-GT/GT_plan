import { describe, test, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import { ref, computed } from 'vue'
import { EDITOR_CONTEXT_KEY, createMockEditorContext } from '@/composables/useEditorContext'

// ─── Mock child components ───────────────────────────────────────────────────
vi.mock('@/components/workpaper/WorkpaperAuditNav.vue', () => ({
  default: { name: 'WorkpaperAuditNav', template: '<div class="stub-audit-nav" />' },
}))

// ─── Import component ────────────────────────────────────────────────────────
import AuditNavDialog from '@/views/workpaper-editor/AuditNavDialog.vue'

describe('AuditNavDialog', () => {
  function mountComponent(props: Partial<InstanceType<typeof AuditNavDialog>['$props']> = {}) {
    const ctx = createMockEditorContext()
    return shallowMount(AuditNavDialog, {
      props: {
        projectId: 'proj-1',
        wpId: 'wp-1',
        wpCode: 'D2-1',
        visible: false,
        ...props,
      },
      global: {
        provide: { [EDITOR_CONTEXT_KEY as symbol]: ctx },
        stubs: {
          ElDialog: {
            template: '<div class="el-dialog-stub"><slot /><slot name="header" /><slot name="footer" /></div>',
            props: ['modelValue', 'fullscreen', 'width', 'showClose'],
            emits: ['update:modelValue'],
          },
          ElButton: {
            template: '<button @click="$emit(\'click\')"><slot /></button>',
          },
        },
      },
    })
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('默认渲染：dialog 组件正常渲染', async () => {
    const wrapper = mountComponent({ visible: true })
    await flushPromises()

    // dialog 应渲染
    expect(wrapper.find('.el-dialog-stub').exists()).toBe(true)
    // 标题区域应包含"审计导航图"
    expect(wrapper.text()).toContain('审计导航图')
    // wpCode 应显示
    expect(wrapper.text()).toContain('D2-1')
  })

  test('v-model:visible 切换：关闭按钮 emit update:visible', async () => {
    const wrapper = mountComponent({ visible: true })
    await flushPromises()

    // 找到关闭按钮（✕）并点击
    const buttons = wrapper.findAll('button')
    const closeBtn = buttons.find((b) => b.text().includes('✕'))
    expect(closeBtn).toBeDefined()

    await closeBtn!.trigger('click')

    // 应 emit update:visible = false
    const emitted = wrapper.emitted('update:visible')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual([false])
  })
})
