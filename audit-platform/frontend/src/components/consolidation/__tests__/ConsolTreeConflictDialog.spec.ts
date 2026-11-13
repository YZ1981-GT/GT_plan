import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConsolTreeDiagnostic } from '@/services/consolidationApi'

const routerPush = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}))

import ConsolTreeConflictDialog from '../ConsolTreeConflictDialog.vue'

function diagnostic(overrides: Partial<ConsolTreeDiagnostic> = {}): ConsolTreeDiagnostic {
  return {
    code: 'duplicate_project',
    message: '企业代码存在重复项目，企业树按已选项目取值',
    company_code: '911100002000000005',
    node_key: null,
    project_ids: ['project-1', 'project-2'],
    level: 'warning',
    ...overrides,
  }
}

const dialogStub = defineComponent({
  props: { modelValue: { type: Boolean, default: false } },
  emits: ['update:modelValue'],
  template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>',
})

const buttonStub = defineComponent({
  emits: ['click'],
  template: '<button @click="$emit(\'click\')"><slot /></button>',
})

describe('ConsolTreeConflictDialog', () => {
  beforeEach(() => {
    routerPush.mockReset()
  })

  it('展示诊断和每个涉及项目的去修改入口，确认后发出 acknowledged', async () => {
    const acknowledged = vi.fn()
    const wrapper = mount(ConsolTreeConflictDialog, {
      props: {
        modelValue: true,
        diagnostics: [diagnostic()],
        onAcknowledged: acknowledged,
      },
      global: {
        stubs: {
          'el-dialog': dialogStub,
          'el-alert': true,
          'el-button': buttonStub,
        },
      },
    })

    expect(wrapper.text()).toContain('企业代码存在重复项目')
    expect(wrapper.text()).toContain('去修改（project-1）')
    expect(wrapper.text()).toContain('去修改（project-2）')

    await wrapper.get('[data-testid="consol-tree-conflict-ack"]').trigger('click')

    expect(acknowledged).toHaveBeenCalledOnce()
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  })

  it('点击去修改进入项目基本信息页并编码项目 id', async () => {
    const wrapper = mount(ConsolTreeConflictDialog, {
      props: { modelValue: true, diagnostics: [diagnostic()] },
      global: {
        stubs: {
          'el-dialog': dialogStub,
          'el-alert': true,
          'el-button': buttonStub,
        },
      },
    })

    await wrapper.get('button').trigger('click')

    expect(routerPush).toHaveBeenCalledWith('/projects/new?projectId=project-1')
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  })
})
