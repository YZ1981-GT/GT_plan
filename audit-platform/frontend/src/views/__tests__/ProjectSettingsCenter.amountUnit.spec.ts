/**
 * 项目设置中心的项目默认金额单位。
 *
 * Validates: Requirements R4, AC-05, AC-06
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const state = vi.hoisted(() => ({
  canEdit: true,
  getProject: vi.fn(),
  apiGet: vi.fn(),
  apiPut: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'p1' }, query: { tab: 'standard' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/composables/usePermissionMatrix', async () => {
  const { ref } = await import('vue')
  return {
    usePermissionMatrix: () => ({
      can: (operation: string) => operation === 'project:edit' ? state.canEdit : true,
      whyCannot: () => '',
      currentRole: ref('manager'),
    }),
  }
})
vi.mock('@/services/auditPlatformApi', () => ({
  getProject: (...args: unknown[]) => state.getProject(...args),
}))
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: unknown[]) => state.apiGet(...args),
    put: (...args: unknown[]) => state.apiPut(...args),
  },
}))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() } }))

import ProjectSettingsCenter from '../ProjectSettingsCenter.vue'
import { useProjectStore } from '@/stores/project'

const STUBS = {
  GtPageShell: { template: '<div><slot name="context" /><slot /></div>' },
  ProjectContextBar: true,
  AgingConfigDialog: true,
  ProjectAuditPhaseSection: true,
}

const mountCenter = () => mount(ProjectSettingsCenter, {
  global: { plugins: [ElementPlus], stubs: STUBS },
})

function configResponse(amountUnit: 'yuan' | 'qian' | 'wan') {
  return {
    project_id: 'p1',
    amount_unit: amountUnit,
    report_standard: 'soe',
    report_scope: 'standalone',
    note_template_type: 'auto',
    export_preferences: {},
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  state.canEdit = true
  state.getProject.mockReset()
  state.apiGet.mockReset()
  state.apiPut.mockReset()
  state.getProject.mockResolvedValue({ id: 'p1', audit_year: 2025, amount_unit: 'yuan' })
  state.apiGet.mockImplementation((path: string) => {
    if (path === '/api/projects/p1/config') return Promise.resolve(configResponse('yuan'))
    return Promise.resolve({ years: [] })
  })
})

describe('ProjectSettingsCenter 项目默认金额单位', () => {
  it('读取并保存三值配置，成功响应只更新当前同一项目', async () => {
    state.apiPut.mockResolvedValue(configResponse('wan'))
    const wrapper = mountCenter()
    await flushPromises()

    const select = wrapper.getComponent('[data-testid="project-amount-unit-select"]')
    select.vm.$emit('update:modelValue', 'wan')
    await wrapper.vm.$nextTick()
    await wrapper.get('[data-testid="project-amount-unit-save"]').trigger('click')
    await flushPromises()

    expect(state.apiGet).toHaveBeenCalledWith('/api/projects/p1/config', { _silent: true })
    expect(state.apiPut).toHaveBeenCalledWith(
      '/api/projects/p1/config',
      { amount_unit: 'wan' },
      { _silent: true },
    )
    expect(useProjectStore().projectAmountUnit).toBe('wan')
    expect(wrapper.text()).toContain('其他成员在刷新或重新进入项目后生效')
  })

  it('没有 project:edit 权限时不提供可提交的保存按钮', async () => {
    state.canEdit = false
    const wrapper = mountCenter()
    await flushPromises()

    expect(wrapper.getComponent('[data-testid="project-amount-unit-save"]').props('disabled')).toBe(true)
  })

  it('保存请求返回后若当前项目已变化，不写入新项目上下文', async () => {
    let resolve!: (value: ReturnType<typeof configResponse>) => void
    state.apiPut.mockReturnValue(new Promise<ReturnType<typeof configResponse>>((done) => { resolve = done }))
    const wrapper = mountCenter()
    await flushPromises()

    const select = wrapper.getComponent('[data-testid="project-amount-unit-select"]')
    select.vm.$emit('update:modelValue', 'wan')
    await wrapper.vm.$nextTick()
    const saving = wrapper.get('[data-testid="project-amount-unit-save"]').trigger('click')
    const store = useProjectStore()
    store.projectId = 'p2'
    store.projectAmountUnit = 'qian'
    resolve(configResponse('wan'))
    await saving
    await flushPromises()

    expect(store.projectId).toBe('p2')
    expect(store.projectAmountUnit).toBe('qian')
  })
})
