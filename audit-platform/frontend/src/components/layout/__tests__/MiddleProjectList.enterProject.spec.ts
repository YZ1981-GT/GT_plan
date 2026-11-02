/**
 * MiddleProjectList.enterProject.spec.ts
 *
 * 守卫：点击中间栏项目节点（ProjectTreeNode 的 @select）必须**导航到项目入口页**
 * ProjectEntry，而不是只在右栏换详情面板。
 *
 * 🔴 为什么要这条守卫：改动前 `selectProject` 只做「选中 + emit」，路由仍停在
 *    `/projects` ⇒ 用户点了项目没有「进入」的效果。回归成那样时本文件打红。
 *
 * 同时钉住 `emit('select')` 仍然发出 —— DefaultLayout 用它维护 selectedProject
 * （四栏目录与侧栏隐藏判断都读这个值），顺手删掉会连带破坏四栏模式。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue([
      {
        id: 'proj-1',
        name: '辽宁卫生服务有限公司_2025',
        client_name: '辽宁卫生服务有限公司',
        short_name: '辽宁卫生',
        status: 'planning',
        report_scope: 'standalone',
        parent_project_id: null,
        consol_level: 1,
        audit_year: 2025,
        project_type: 'annual',
        created_at: '2026-11-02T10:20:00',
      },
    ]),
    delete: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/utils/confirm', () => ({
  confirmDelete: vi.fn().mockResolvedValue(undefined),
  confirmBatch: vi.fn().mockResolvedValue(undefined),
}))

import MiddleProjectList from '../MiddleProjectList.vue'

const stubs = {
  'el-button': { template: '<button><slot /></button>' },
  'el-input': { template: '<input />' },
  'el-icon': { template: '<i><slot /></i>' },
  'el-checkbox': { template: '<span><slot /></span>' },
  'el-select': { template: '<span><slot /></span>' },
  'el-option': { template: '<span />' },
  'el-empty': { template: '<div />' },
  'el-tag': { template: '<span><slot /></span>' },
  BatchImportDialog: { template: '<div />' },
}

beforeEach(() => {
  push.mockReset()
})

describe('MiddleProjectList — 点击项目节点进入项目', () => {
  it('点击节点导航到 ProjectEntry 并带上 projectId', async () => {
    const w = mount(MiddleProjectList, { global: { stubs } })
    await flushPromises()

    const node = w.findComponent({ name: 'ProjectTreeNode' })
    expect(node.exists()).toBe(true)

    node.vm.$emit('select', { id: 'proj-1', name: '辽宁卫生服务有限公司_2025' })
    await flushPromises()

    expect(push).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith({ name: 'ProjectEntry', params: { projectId: 'proj-1' } })
  })

  it('仍然向父组件 emit select（DefaultLayout 的 selectedProject 依赖它）', async () => {
    const w = mount(MiddleProjectList, { global: { stubs } })
    await flushPromises()

    const node = w.findComponent({ name: 'ProjectTreeNode' })
    node.vm.$emit('select', { id: 'proj-1' })
    await flushPromises()

    expect(w.emitted('select')?.[0]?.[0]).toMatchObject({ id: 'proj-1' })
  })
})
