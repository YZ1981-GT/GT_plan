/**
 * UserManagement 人员档案隔离适配守卫
 * Spec: project-role-visibility Task 5.1（Requirement 4.2）
 *
 * 被守卫的行为（落在真实请求次数与组件真实派生态上，不查字符串存在）：
 *  1. 页面每次加载只对 `/api/users/` 发 **一次** 请求。
 *     —— 曾因 loadUsers() 与 loadPartnerUsers() 并发打同一 URL，被 utils/http.ts 的
 *     GET 去重逻辑互杀（先发的被 abort），loadUsers 落入 catch ⇒ 用户表恒为空。
 *  2. 页面不做按 parent_partner_id 的前端二次过滤：接口返回几行就渲染几行，
 *     后端 V153 隔离的结果原样呈现（不与后端叠加成双重过滤、不把本人过滤掉）。
 *  3. 「所属合伙人」下拉候选从返回行集派生；partner 视角下候选集缩到
 *     「本人 + 下属」时，本人（role=partner）仍在候选中，下拉不为空。
 *  4. 待编辑用户的 parent_partner_id 不在候选集内时，不把裸 UUID 显示给用户。
 *
 * 变异检验（4 条，均已实跑打红，见 spec Notes）：
 *  1. 恢复 loadPartnerUsers() 的第二次 listUsers() ⇒ 用例 1 打红（请求 2 次）。
 *  2. loadUsers 后补一句按 parent_partner_id 的前端过滤 ⇒ 用例 2 打红（行数缩水）。
 *  3. partnerOptions 改回直接返回 partnerUsers ⇒ 用例 4 打红（裸 UUID 泄漏）。
 *  4. partnerUsers 的 role 过滤改成 'admin' ⇒ 用例 3 打红（候选空、本人选不到）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import UserManagement from '../UserManagement.vue'

// 记录对 /api/users/ 的真实请求次数
let userListCalls = 0
let usersPayload: any[] = []

vi.mock('@/services/commonApi', () => ({
  listUsers: vi.fn(async () => {
    userListCalls++
    return usersPayload
  }),
  createUser: vi.fn(async () => ({})),
  updateUser: vi.fn(async () => ({})),
  listDepartments: vi.fn(async () => [{ id: 'dept-1', name: '审计一部' }]),
}))

const PARTNER = {
  id: 'p-1', username: 'partner_zhang', full_name: '张合伙人',
  email: 'zhang@example.com', role: 'partner', is_active: true,
  parent_partner_id: null, dept_id: 'dept-1',
}
const SUB_A = {
  id: 'u-1', username: 'auditor_li', full_name: '李审计',
  email: 'li@example.com', role: 'auditor', is_active: true,
  parent_partner_id: 'p-1', dept_id: 'dept-1',
}
const SUB_B = {
  id: 'u-2', username: 'manager_wang', full_name: '王经理',
  email: 'wang@example.com', role: 'manager', is_active: true,
  parent_partner_id: 'p-1', dept_id: 'dept-1',
}

function mountPage() {
  return mount(UserManagement, {
    global: {
      plugins: [ElementPlus],
      directives: { permission: {} },
      stubs: { GtPageHeader: { template: '<div><slot /></div>' } },
    },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  userListCalls = 0
  usersPayload = []
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('UserManagement 人员档案隔离适配（Task 5.1 / Req 4.2）', () => {
  it('每次加载只对 /api/users/ 发一次请求（防 GET 去重互杀）', async () => {
    usersPayload = [PARTNER, SUB_A, SUB_B]
    const wrapper = mountPage()
    await flushPromises()

    expect(userListCalls).toBe(1)
    wrapper.unmount()
  })

  it('不做前端二次过滤：接口返回的隔离行集原样渲染，本人不被过滤掉', async () => {
    // 模拟 partner 视角下后端已隔离的返回：本人 + 2 名下属
    usersPayload = [PARTNER, SUB_A, SUB_B]
    const wrapper = mountPage()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.filteredUsers).toHaveLength(3)
    const names = vm.filteredUsers.map((u: any) => u.username).sort()
    expect(names).toEqual(['auditor_li', 'manager_wang', 'partner_zhang'])
    // 本人未被过滤掉 —— 双重过滤最典型的受害者
    expect(names).toContain('partner_zhang')
    wrapper.unmount()
  })

  it('合伙人候选从返回行集派生，partner 视角下本人可选且候选非空', async () => {
    usersPayload = [PARTNER, SUB_A, SUB_B]
    const wrapper = mountPage()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.partnerUsers).toHaveLength(1)
    expect(vm.partnerUsers[0].id).toBe('p-1')
    expect(vm.partnerOptions.length).toBeGreaterThan(0)
    expect(vm.partnerOptions.some((o: any) => o.id === 'p-1')).toBe(true)
    wrapper.unmount()
  })

  it('parent_partner_id 不在候选集内时不暴露裸 UUID', async () => {
    usersPayload = [PARTNER, SUB_A]
    const wrapper = mountPage()
    await flushPromises()

    const vm = wrapper.vm as any
    // 该下属挂在一个当前不可见的合伙人下（已停用，或不在本账号隔离范围内）
    vm.editUser({ ...SUB_B, parent_partner_id: 'p-invisible-uuid' })
    await flushPromises()

    const opt = vm.partnerOptions.find((o: any) => o.id === 'p-invisible-uuid')
    expect(opt).toBeTruthy()
    // label 必须是人类可读文案，绝不能是裸 ID
    expect(opt.username).not.toBe('p-invisible-uuid')
    expect(opt.username).toContain('不可见')
    wrapper.unmount()
  })
})
