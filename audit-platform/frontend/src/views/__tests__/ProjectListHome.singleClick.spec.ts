/**
 * ProjectListHome.singleClick.spec.ts
 *
 * 守卫：项目卡片**单击**即进入项目。
 *
 * 🔴 回归背景：原实现是「单击选中 / 双击进入」，用户反馈要点两下才能进项目。
 *    改为单击进入后，修改 / 删除挪到卡片上的按钮 —— 这两个按钮必须 `.stop`，
 *    否则点击会冒泡到卡片、先跳进项目，按钮本身形同虚设。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// 🔴 vi.mock 会被提升到文件最顶部，工厂里引用的变量必须走 vi.hoisted，
//    否则工厂执行时这些 const 还没初始化（实测首版即因此整文件报错）。
const { push, del, confirmDelete, PROJECT } = vi.hoisted(() => ({
  push: vi.fn(),
  del: vi.fn(),
  confirmDelete: vi.fn(),
  PROJECT: {
    id: 'proj-1',
    name: '辽宁卫生服务有限公司_2025',
    client_name: '辽宁卫生服务有限公司',
    short_name: '辽宁卫生',
    project_type: 'annual',
    audit_year: 2025,
    created_at: '2026-11-02T10:20:00',
  },
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([PROJECT]), delete: (...a: any[]) => del(...a) },
}))
vi.mock('@/utils/confirm', () => ({ confirmDelete: (...a: any[]) => confirmDelete(...a) }))

import ProjectListHome from '../ProjectListHome.vue'

const stubs = {
  // 按钮 stub 必须透传 click 并保留 .stop 语义：用原生 button + $attrs
  'el-button': { inheritAttrs: true, template: '<button type="button"><slot /></button>' },
  'el-tag': { template: '<span><slot /></span>' },
  'el-empty': { template: '<div><slot /></div>' },
}
const directives = { loading: {} }

async function mountList() {
  const w = mount(ProjectListHome, { global: { stubs, directives } })
  await flushPromises()
  return w
}

beforeEach(() => {
  push.mockReset()
  del.mockReset()
  confirmDelete.mockReset()
})

describe('ProjectListHome — 单击进入项目', () => {
  it('单击卡片一次就导航到 ProjectEntry（不需要双击）', async () => {
    const w = await mountList()
    await w.get('[data-testid="plh-card-proj-1"]').trigger('click')
    expect(push).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith({ name: 'ProjectEntry', params: { projectId: 'proj-1' } })
  })

  it('键盘回车也能进入（卡片可聚焦）', async () => {
    const w = await mountList()
    await w.get('[data-testid="plh-card-proj-1"]').trigger('keydown', { key: 'Enter' })
    expect(push).toHaveBeenCalledWith({ name: 'ProjectEntry', params: { projectId: 'proj-1' } })
  })

  it('点「修改」只去编辑页，不会冒泡成进入项目', async () => {
    const w = await mountList()
    await w.get('[data-testid="plh-edit-proj-1"]').trigger('click')
    expect(push).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith('/projects/new?projectId=proj-1')
  })

  it('点「删除」后取消：不进入项目、不调删除接口', async () => {
    confirmDelete.mockRejectedValueOnce(new Error('cancel'))
    const w = await mountList()
    await w.get('[data-testid="plh-delete-proj-1"]').trigger('click')
    await flushPromises()
    expect(confirmDelete).toHaveBeenCalledTimes(1)
    expect(push).not.toHaveBeenCalled()
    expect(del).not.toHaveBeenCalled()
  })
})
