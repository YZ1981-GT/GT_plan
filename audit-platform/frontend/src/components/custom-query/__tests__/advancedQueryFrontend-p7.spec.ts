/**
 * P7 模板作用域属性测试 — 独立文件避免与其他 describe 块的 mock 交叉污染。
 *
 * Feature: advanced-query-disclosure-integration-hardening, Property P7
 * Validates: Requirements 6.1–6.5
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'

// ─── 独立 mock：每个测试用新鲜模块 ───
const roleHolder = { value: 'auditor' }

vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({ currentRole: { get value() { return roleHolder.value } } }),
}))

vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({
    buildAddressTree: vi.fn(),
    loadCellNodes: vi.fn(),
    resolveIndex: vi.fn(),
    clearCache: vi.fn(),
  }),
}))

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
    ElMessageBox: { confirm: vi.fn(), alert: vi.fn(), prompt: vi.fn() },
  }
})

const apiMocks = { get: vi.fn().mockResolvedValue([]), post: vi.fn().mockResolvedValue({}), delete: vi.fn().mockResolvedValue({}) }
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))

beforeEach(() => {
  vi.clearAllMocks()
  apiMocks.get.mockResolvedValue([])
  apiMocks.post.mockResolvedValue({})
})

describe('Feature: advanced-query-disclosure-integration-hardening, Property P7', () => {
  async function mountTabForScope(role: string) {
    roleHolder.value = role
    const CustomQueryTab = (await import('@/components/template-library/CustomQueryTab.vue')).default
    const wrapper = shallowMount(CustomQueryTab, {
      global: {
        directives: { loading: {} },
        stubs: { 'el-dialog': { template: '<div class="el-dialog-stub" />' } },
      },
    })
    await flushPromises()
    return wrapper
  }

  it('legacy global 只显示为 canonical public/公开', async () => {
    const wrapper = await mountTabForScope('manager')
    expect(wrapper.vm.normalizeTemplateScope('global')).toBe('public')
    expect(wrapper.vm.templateScopeLabel('global')).toBe('公开')
  })

  it('只读角色只能保存私人模板，分享 scope fail-closed', async () => {
    const wrapper = await mountTabForScope('auditor')
    expect(wrapper.vm.canShareTemplates).toBe(false)
    wrapper.vm.saveForm.name = '只读用户模板'
    wrapper.vm.saveForm.scope = 'project'
    wrapper.vm.saveForm.shared_project_ids = ['00000000-0000-0000-0000-000000000001']
    expect(wrapper.vm.canSaveTemplate).toBe(false)
    await wrapper.vm.onConfirmSaveTemplate()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('有模板编辑权限时仅提交去重后的可编辑项目', async () => {
    const wrapper = await mountTabForScope('manager')
    wrapper.vm.projectList = [
      { id: '00000000-0000-0000-0000-000000000001', can_edit: true },
      { id: '00000000-0000-0000-0000-000000000002', can_edit: false },
    ]
    wrapper.vm.formCtx.source = 'tb_detail'
    wrapper.vm.formCtx.project_id = '00000000-0000-0000-0000-000000000001'
    wrapper.vm.saveForm.name = '项目模板'
    wrapper.vm.saveForm.scope = 'project'
    wrapper.vm.saveForm.shared_project_ids = [
      '00000000-0000-0000-0000-000000000001',
      '00000000-0000-0000-0000-000000000001',
    ]
    await wrapper.vm.onConfirmSaveTemplate()
    expect(apiMocks.post).toHaveBeenCalledTimes(1)
    expect(apiMocks.post.mock.calls[0][1].shared_project_ids).toEqual([
      '00000000-0000-0000-0000-000000000001',
    ])
  })
})
