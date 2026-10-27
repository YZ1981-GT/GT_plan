/**
 * P7 模板作用域属性测试 — 独立文件避免与其他 describe 块的 mock 交叉污染。
 *
 * Feature: advanced-query-disclosure-integration-hardening, Property P7
 * Validates: Requirements 6.1–6.5
 */
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { shallowMount, flushPromises, type VueWrapper } from '@vue/test-utils'
// 被测组件在文件顶层静态导入（advanced-query-linkage-closure 任务 1，AQ-32）：原先在第 1 例里
// `await import(CustomQueryTab.vue)`，组件整棵依赖（含 `vi.importActual('element-plus')`）的首次加载耗时
// 算进第 1 例的 15 s 超时——磁盘缓存是冷的或并行负载重时超过 15 s，「legacy global」一例即超时（热缓存时同一例约 2 s）。
// 静态导入让加载发生在收集阶段、不计入任何一例；vi.mock 仍先于它生效（vitest 提升），各例照旧在挂载时读 roleHolder。
// 超时只在冷缓存下复现，所以守卫不靠计时：末尾一例断言重量级依赖是在收集阶段加载的（见 loadPhase）。
import CustomQueryTab from '@/components/template-library/CustomQueryTab.vue'

// ─── 独立 mock ───
const roleHolder = { value: 'auditor' }

/** element-plus（组件的重量级依赖）在哪个阶段第一次加载：收集阶段，还是某个用例里（后者即耗时计入该例超时）。 */
const loadPhase = vi.hoisted(() => ({ testsStarted: false, elementPlus: 'not-loaded' as 'not-loaded' | 'collect' | 'test' }))

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
  loadPhase.elementPlus = loadPhase.testsStarted ? 'test' : 'collect'
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
    ElMessageBox: { confirm: vi.fn(), alert: vi.fn(), prompt: vi.fn() },
  }
})

const apiMocks = vi.hoisted(() => ({
  get: vi.fn().mockResolvedValue([]),
  post: vi.fn().mockResolvedValue({}),
  delete: vi.fn().mockResolvedValue({}),
}))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))

beforeAll(() => {
  loadPhase.testsStarted = true
})

beforeEach(() => {
  vi.clearAllMocks()
  apiMocks.get.mockResolvedValue([])
  apiMocks.post.mockResolvedValue({})
})

describe('Feature: advanced-query-disclosure-integration-hardening, Property P7', () => {
  async function mountTabForScope(role: string) {
    roleHolder.value = role
    const wrapper = shallowMount(CustomQueryTab, {
      global: {
        directives: { loading: {} },
        stubs: { 'el-dialog': { template: '<div class="el-dialog-stub" />' } },
      },
    })
    await flushPromises()
    // 用例直接读写组件内部状态（<script setup> 没有 defineExpose），类型上按 any 处理
    return wrapper as unknown as VueWrapper<any>
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

  it('被测组件的重量级依赖在收集阶段加载，不计入任何一例的超时（AQ-32）', () => {
    // 改回「用例里 await import(组件)」时这里得到 'test'（或该例先跑时得到 'not-loaded'）
    expect(loadPhase.elementPlus).toBe('collect')
  })
})
