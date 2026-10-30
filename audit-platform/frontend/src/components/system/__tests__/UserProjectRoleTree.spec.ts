/**
 * UserProjectRoleTree.vue 单元测试（project-data-permission-isolation Task 6.4）
 *
 * 判据分五组：
 *   A. 懒加载三段（根层 / 项目层 / 角色层）各自请求正确的端点
 *   B. `has_children=false` 的账号被标成叶子（否则 el-tree 永久转圈）
 *   C. `out_of_scope` 的项目**照常显示**、只加标记（不是过滤掉）
 *   D. 搜索走后端（带 search 参数）而非前端过滤
 *   E. 失败时 resolve 空数组而非悬挂，且按状态码给不同提示
 *
 * 🔴 **判据锚在「发出的请求」与「resolve 的数据」上，不锚 DOM 文本**：
 *    el-tree 的懒加载渲染时序难以稳定断言，而"请求打对了 + 数据结构对了"
 *    才是本组件的真实职责。DOM 层面只验少数关键标记。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// ─── mock API 层 ────────────────────────────────────────────────────────────

const listUserNodes = vi.fn()
const getUserSubtree = vi.fn()

vi.mock('@/services/projectRoleTreeApi', () => ({
  listUserNodes: (...a: any[]) => listUserNodes(...a),
  getUserSubtree: (...a: any[]) => getUserSubtree(...a),
}))

const msgError = vi.fn()
const msgWarning = vi.fn()
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: {
      error: (...a: any[]) => msgError(...a),
      warning: (...a: any[]) => msgWarning(...a),
      success: vi.fn(),
    },
  }
})

import UserProjectRoleTree from '../UserProjectRoleTree.vue'

// ─── 测试数据 ───────────────────────────────────────────────────────────────

const U_WITH = {
  id: 'u-1',
  username: 'zhangsan',
  full_name: '张三',
  email: 'zs@t.com',
  system_role: 'manager',
  is_active: true,
  has_children: true,
}

const U_WITHOUT = {
  id: 'u-2',
  username: 'lisi',
  full_name: null,
  email: 'ls@t.com',
  system_role: 'auditor',
  is_active: false,
  has_children: false,
}

const ROLE_NODE = {
  role: 'manager',
  permission_level: 'edit',
  valid_from: null,
  valid_to: null,
  scope_cycles: 'D,F',
  scope_accounts: null,
}

const SUBTREE = {
  user_id: 'u-1',
  effective_data_scope: 2,
  effective_data_scope_label: '自定义项目',
  projects: [
    {
      project_id: 'p-1',
      name: '可见项目',
      client_name: '甲公司',
      status: 'execution',
      out_of_scope: false,
      role: ROLE_NODE,
    },
    {
      project_id: 'p-2',
      name: '不可见项目',
      client_name: '乙公司',
      status: 'created',
      out_of_scope: true,
      role: { ...ROLE_NODE, role: 'auditor', permission_level: 'readonly' },
    },
  ],
}

function mountTree() {
  return mount(UserProjectRoleTree, {
    global: {
      stubs: {
        // el-tree 的 lazy 渲染在 jsdom 下不稳定，stub 掉但**保留 load 回调可调**。
        // ⚠️ **stub 必须显式带 `name`**：`findComponent({ name: 'el-tree' })`
        //    靠它定位；匿名 stub 会让所有查找返回空 wrapper，
        //    表现为 "Cannot call props on an empty VueWrapper"（实测 15/15 全红）。
        'el-tree': {
          name: 'el-tree',
          props: ['load', 'props', 'nodeKey'],
          template: '<div class="stub-tree" />',
        },
        'el-input': { template: '<input />' },
        'el-button': { template: '<button><slot /></button>' },
        'el-icon': { template: '<i><slot /></i>' },
        'el-tag': { template: '<span><slot /></span>' },
        'el-tooltip': { template: '<span><slot /></span>' },
        'el-pagination': { template: '<div />' },
      },
    },
  })
}

/** 拿到组件传给 el-tree 的 `load` 回调。 */
function loadFn(wrapper: any) {
  return wrapper.findComponent({ name: 'el-tree' }).props('load')
}

beforeEach(() => {
  vi.clearAllMocks()
  listUserNodes.mockResolvedValue({ items: [U_WITH, U_WITHOUT], total: 2 })
  getUserSubtree.mockResolvedValue(SUBTREE)
})

// ===========================================================================
// A. 懒加载三段
// ===========================================================================

describe('懒加载三段', () => {
  it('根层请求 listUserNodes 并带分页参数', async () => {
    const w = mountTree()
    const load = loadFn(w)
    const got: any[] = []
    await load({ level: 0 }, (d: any[]) => got.push(...d))

    expect(listUserNodes).toHaveBeenCalledTimes(1)
    const params = listUserNodes.mock.calls[0][0]
    expect(params.page).toBe(1)
    expect(params.page_size).toBe(50)
    expect(got).toHaveLength(2)
    expect(got[0].kind).toBe('user')
  })

  it('展开账号时用该账号 id 请求子树（不是当前登录者）', async () => {
    const w = mountTree()
    const load = loadFn(w)
    const got: any[] = []
    await load(
      { level: 1, data: { kind: 'user', nodeKey: 'u:u-1', raw: U_WITH } },
      (d: any[]) => got.push(...d),
    )

    expect(getUserSubtree).toHaveBeenCalledWith('u-1')
    expect(got).toHaveLength(2)
    expect(got.map((x) => x.kind)).toEqual(['project', 'project'])
  })

  it('展开项目时不再发请求，直接给出唯一角色节点', async () => {
    const w = mountTree()
    const load = loadFn(w)
    const got: any[] = []
    await load(
      {
        level: 2,
        data: {
          kind: 'project',
          nodeKey: 'p:u-1:p-1',
          raw: SUBTREE.projects[0],
        },
      },
      (d: any[]) => got.push(...d),
    )

    // project_users 对 (project_id, user_id) 有唯一索引 ⇒ 恒一个角色
    expect(got).toHaveLength(1)
    expect(got[0].kind).toBe('role')
    expect(got[0].isLeaf).toBe(true)
    expect(got[0].raw.role).toBe('manager')
    // 角色层不该再打网络请求
    expect(getUserSubtree).not.toHaveBeenCalled()
    expect(listUserNodes).not.toHaveBeenCalled()
  })
})

// ===========================================================================
// B. has_children → isLeaf
// ===========================================================================

describe('has_children 与 isLeaf', () => {
  it('无项目账号必须标成叶子（否则 el-tree 永久转圈）', async () => {
    const w = mountTree()
    const got: any[] = []
    await loadFn(w)({ level: 0 }, (d: any[]) => got.push(...d))

    const withProj = got.find((x) => x.raw.id === 'u-1')
    const withoutProj = got.find((x) => x.raw.id === 'u-2')

    expect(withProj.isLeaf).toBe(false)
    expect(withoutProj.isLeaf).toBe(true)
  })

  it('无项目账号仍出现在根层（不被过滤掉）', async () => {
    const w = mountTree()
    const got: any[] = []
    await loadFn(w)({ level: 0 }, (d: any[]) => got.push(...d))

    expect(got.map((x) => x.raw.username)).toContain('lisi')
  })
})

// ===========================================================================
// C. out_of_scope 是标记不是过滤
// ===========================================================================

describe('out_of_scope 语义', () => {
  it('不可见项目照常出现在项目层（只是带标记）', async () => {
    const w = mountTree()
    const got: any[] = []
    await loadFn(w)(
      { level: 1, data: { kind: 'user', nodeKey: 'u:u-1', raw: U_WITH } },
      (d: any[]) => got.push(...d),
    )

    expect(got).toHaveLength(2)
    const names = got.map((x) => x.raw.name)
    expect(names).toContain('不可见项目')

    const marks = got.map((x) => x.raw.out_of_scope)
    expect(marks).toEqual([false, true])
  })

  it('若把不可见项目过滤掉，管理员就发现不了配置矛盾 —— 故断言数量不减', async () => {
    getUserSubtree.mockResolvedValue({
      ...SUBTREE,
      projects: SUBTREE.projects.map((p) => ({ ...p, out_of_scope: true })),
    })
    const w = mountTree()
    const got: any[] = []
    await loadFn(w)(
      { level: 1, data: { kind: 'user', nodeKey: 'u:u-1', raw: U_WITH } },
      (d: any[]) => got.push(...d),
    )

    expect(got).toHaveLength(2)
    expect(got.every((x) => x.raw.out_of_scope)).toBe(true)
  })
})

// ===========================================================================
// D. 搜索走后端
// ===========================================================================

describe('搜索', () => {
  it('关键字作为 search 参数传给后端', async () => {
    const w = mountTree()
    ;(w.vm as any).keyword = 'zhang'
    const got: any[] = []
    await loadFn(w)({ level: 0 }, (d: any[]) => got.push(...d))

    expect(listUserNodes.mock.calls[0][0].search).toBe('zhang')
  })

  it('空关键字不传 search（而非传空串）', async () => {
    const w = mountTree()
    ;(w.vm as any).keyword = '   '
    await loadFn(w)({ level: 0 }, () => {})

    expect(listUserNodes.mock.calls[0][0].search).toBeUndefined()
  })

  it('total 取后端返回值（不是当前页条数）', async () => {
    listUserNodes.mockResolvedValue({ items: [U_WITH], total: 137 })
    const w = mountTree()
    await loadFn(w)({ level: 0 }, () => {})

    expect((w.vm as any).total).toBe(137)
  })
})

// ===========================================================================
// E. 失败处理
// ===========================================================================

describe('失败处理', () => {
  it('请求失败时 resolve 空数组（不能悬挂，否则节点永久转圈）', async () => {
    listUserNodes.mockRejectedValue(new Error('boom'))
    const w = mountTree()
    const resolve = vi.fn()
    await loadFn(w)({ level: 0 }, resolve)

    expect(resolve).toHaveBeenCalledTimes(1)
    expect(resolve).toHaveBeenCalledWith([])
  })

  it('403 给「仅管理员可用」提示', async () => {
    listUserNodes.mockRejectedValue({ response: { status: 403 } })
    const w = mountTree()
    await loadFn(w)({ level: 0 }, () => {})

    expect(msgError).toHaveBeenCalledWith(
      expect.stringContaining('仅管理员'),
    )
  })

  it('404 给「账号已不存在」提示（用 warning 而非 error）', async () => {
    getUserSubtree.mockRejectedValue({ response: { status: 404 } })
    const w = mountTree()
    await loadFn(w)(
      { level: 1, data: { kind: 'user', nodeKey: 'u:u-1', raw: U_WITH } },
      () => {},
    )

    expect(msgWarning).toHaveBeenCalledWith(
      expect.stringContaining('已不存在'),
    )
    expect(msgError).not.toHaveBeenCalled()
  })
})

// ===========================================================================
// F. 数据权限范围标签
// ===========================================================================

describe('数据权限范围标签', () => {
  it('展开账号后记录其 scope 标签', async () => {
    const w = mountTree()
    await loadFn(w)(
      { level: 1, data: { kind: 'user', nodeKey: 'u:u-1', raw: U_WITH } },
      () => {},
    )

    expect((w.vm as any).scopeLabels['u-1']).toBe('自定义项目')
  })

  it('未展开的账号没有标签（不显示占位，避免误以为"没有范围"）', async () => {
    const w = mountTree()
    await loadFn(w)({ level: 0 }, () => {})

    expect((w.vm as any).scopeLabels['u-1']).toBeUndefined()
  })
})
