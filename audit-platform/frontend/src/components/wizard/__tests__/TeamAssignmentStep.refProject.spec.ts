/**
 * 团队分配「参照其他项目」的项目列表（spec procedure-trim-generation-delegation-chain 任务 22 类型检查发现）：
 * 原先 `api.get(P_proj.list())` 把路径字符串当函数调，抛 TypeError 被 catch 吞掉 ⇒ 弹窗里的项目列表恒为空，
 * 「从参照项目复制委派」这条路一直走不通。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('@/services/staffApi', () => ({
  listStaff: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createStaff: vi.fn(),
  listAssignments: vi.fn().mockResolvedValue([]),
  saveAssignments: vi.fn(),
}))
vi.mock('@/stores/wizard', () => ({ useWizardStore: () => ({ projectId: '', stepData: {}, saveStep: vi.fn() }) }))
vi.mock('@/services/apiProxy', () => ({ api: { get: mocks.apiGet } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

import TeamAssignmentStep from '../TeamAssignmentStep.vue'

beforeEach(() => {
  vi.clearAllMocks()
  mocks.apiGet.mockReset()
})

describe('TeamAssignmentStep 参照其他项目', () => {
  it('打开弹窗 ⇒ 按项目列表接口取项目，排除本项目', async () => {
    mocks.apiGet.mockImplementation(async (url: string) => (url === '/api/projects'
      ? [
          { id: 'p1', name: '本项目', audit_year: 2025 },
          { id: 'p0', name: '【测试】上年项目', audit_year: 2024 },
        ]
      : []))
    localStorage.setItem('gt_team_guide_dismissed', '1')
    const w = shallowMount(TeamAssignmentStep, {
      props: { projectId: 'p1' },
      global: { stubs: { 'el-table-column': { template: '<i />' }, ElTableColumn: { template: '<i />' } } },
    })
    await flushPromises()
    const vm = w.vm as any
    vm.showRefProjectDialog = true
    await flushPromises()
    expect(mocks.apiGet).toHaveBeenCalledWith('/api/projects')
    expect(vm.refProjects).toEqual([{ id: 'p0', name: '【测试】上年项目', audit_year: 2024, member_count: '—' }])
    expect(vm.refProjectsLoading).toBe(false)
    w.unmount()
  })
})
