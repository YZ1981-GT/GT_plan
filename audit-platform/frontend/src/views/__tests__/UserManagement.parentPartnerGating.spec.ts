/**
 * UserManagement「上级合伙人」按角色门控守卫
 * Spec: account-field-completion Task 4.3（Requirement 3.4）
 *
 * Requirement 3.4 原文：「Parent_Partner_Resolver SHALL 仅在业务语义上用于
 * manager/auditor 账号（不强制 DB 约束角色，**由前端仅对这两类角色展示该字段**）」。
 *
 * 🔴 执行 Task 4.3 时实测发现 Task 4.1 是**半交付标全绿**（本 spec 第三例，
 * 前两例是 Task 2.1 的 username 校验器与 Task 3.1 的 update_user）：
 * 「所属合伙人」el-form-item **完全没有 v-if 门控**，对 admin / partner / qc / eqcr
 * 同样展示 ⇒ Requirement 3.4 未实现。本次先补实现（`showParentPartner` computed
 * + 角色切换清空）再写本守卫。
 *
 * 被守卫的行为（落在组件真实派生态与真实 DOM 上，不查字符串存在）：
 *  1. `showParentPartner` 对全部 6 个角色逐一判定 —— manager/auditor 为 true，
 *     admin/partner/qc/eqcr 为 false。**双向断言**：只测「manager 下显示」
 *     抓不到「恒显示」这个原始缺陷。
 *  2. DOM 层同样双向：弹窗打开后，该表单项在 manager/auditor 下**存在**、
 *     在 admin/partner/qc/eqcr 下**不存在**。
 *     （computed 正确但模板忘记绑 v-if 时，判据 1 全绿、只有 DOM 判据能抓到 ——
 *      这正是原始缺陷的形态。）
 *  3. 角色从 manager 切到 partner 时，已选的 parent_partner_id 被清空 ——
 *     否则字段虽被隐藏，旧值仍随表单提交，写出「partner 挂着上级合伙人」的越界数据。
 *  4. 角色在 manager ↔ auditor 之间切换时**不得**清空（两者都适用该字段，
 *     清空会让用户白填一次）。
 *
 * 变异检验：把门控条件改成恒 true（`showParentPartner = computed(() => true)`）
 * ⇒ 判据 1 的「非 manager/auditor 时隐藏」与判据 2 的 DOM 侧同时打红。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import UserManagement from '../UserManagement.vue'

vi.mock('@/services/commonApi', () => ({
  listUsers: vi.fn(async () => usersPayload),
  createUser: vi.fn(async () => ({})),
  updateUser: vi.fn(async () => ({})),
  listDepartments: vi.fn(async () => [{ id: 'dept-1', name: '审计一部' }]),
}))

const PARTNER = {
  id: 'p-1', username: 'partner_zhang', full_name: '张合伙人',
  email: 'zhang@example.com', role: 'partner', is_active: true,
  parent_partner_id: null, dept_id: 'dept-1',
}
let usersPayload: any[] = [PARTNER]

/**
 * 全部 7 个角色 → 是否应展示「上级合伙人」。
 * 🔴 单一真源：与 UserManagement.vue 的 ROLE_OPTIONS 逐值对齐（7 个角色一个不少），
 * 下面所有用例一律从本表派生，不在断言里内联角色名。
 * 只测 2 个角色会漏掉「某个角色被错误纳入/排除」。
 *
 * `site_lead`（现场经理）为 true —— spec site-lead-and-field-lead 加入的独立系统角色，
 * 权限等同 manager，同样需要挂靠某个合伙人：该 spec 的「签字合伙人→下属」级联按
 * `parent_partner_id` 筛候选人，若 site_lead 账号无法设置上级合伙人，它就永远
 * 进不了项目经理/现场负责人候选名单（表现为「选不到人」而非报错）。
 */
const ROLE_EXPECTATIONS: ReadonlyArray<readonly [string, boolean]> = [
  ['admin', false],
  ['partner', false],
  ['manager', true],
  ['site_lead', true],
  ['auditor', true],
  ['qc', false],
  ['eqcr', false],
]

// 期望表自身的完整性自检：必须同时含 true 与 false 两侧，
// 否则「恒 true」或「恒 false」的实现都能蒙过全表。
const _hasPositive = ROLE_EXPECTATIONS.some(([, v]) => v)
const _hasNegative = ROLE_EXPECTATIONS.some(([, v]) => !v)

function mountPage() {
  return mount(UserManagement, {
    attachTo: document.body,
    global: {
      plugins: [ElementPlus],
      directives: { permission: {} },
      stubs: { GtPageHeader: { template: '<div><slot /></div>' } },
    },
  })
}

/** 从真实 DOM 找「所属合伙人」表单项（el-dialog append-to-body ⇒ 须查 document）。 */
function findParentPartnerItem(): Element | null {
  const items = Array.from(document.querySelectorAll('.el-form-item'))
  return (
    items.find(el => (el.querySelector('.el-form-item__label')?.textContent || '').includes('所属合伙人')) || null
  )
}

beforeEach(() => {
  setActivePinia(createPinia())
  usersPayload = [PARTNER]
})

afterEach(() => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

describe('UserManagement 上级合伙人角色门控（Task 4.3 / Req 3.4）', () => {
  it('期望表自身覆盖正反两侧（防「恒 true / 恒 false」蒙过全表）', () => {
    expect(ROLE_EXPECTATIONS).toHaveLength(7)
    expect(_hasPositive).toBe(true)
    expect(_hasNegative).toBe(true)
  })

  /**
   * 🔴 期望表必须与组件的 ROLE_OPTIONS **逐值对齐**。
   *
   * 原先本表是手写的 6 项、且不从组件读取 ⇒ 新增第 7 个角色（site_lead）时
   * 全部用例照旧全绿，而那个新角色**一条都没被覆盖** —— 正是「判据的观察粒度
   * 低于缺陷的存在粒度」这类假绿。这条把两侧钉在一起：往 ROLE_OPTIONS 加角色
   * 而忘了补期望值，立刻打红。
   */
  it('期望表与 UserManagement.vue 的 ROLE_OPTIONS 角色集合完全一致', () => {
    const src = readFileSync(resolve(__dirname, '../UserManagement.vue'), 'utf-8')
    const block = src.match(/const ROLE_OPTIONS = \[([\s\S]*?)\] as const/)
    expect(block, 'ROLE_OPTIONS 定义找不到了（组件结构变了）').toBeTruthy()

    const fromComponent = [...block![1].matchAll(/value:\s*'([a-z_]+)'/g)].map(m => m[1])
    expect(fromComponent.length, 'ROLE_OPTIONS 解析为空').toBeGreaterThan(0)

    expect([...fromComponent].sort()).toEqual(
      ROLE_EXPECTATIONS.map(([r]) => r).sort(),
    )
  })

  it.each(ROLE_EXPECTATIONS)(
    'role=%s 时 showParentPartner 应为 %s（派生态双向）',
    async (role, expected) => {
      const wrapper = mountPage()
      await flushPromises()

      const vm = wrapper.vm as any
      vm.form.role = role
      await flushPromises()

      expect(vm.showParentPartner).toBe(expected)
      wrapper.unmount()
    },
  )

  it.each(ROLE_EXPECTATIONS)(
    'role=%s 时「所属合伙人」表单项在真实 DOM 中存在应为 %s',
    async (role, expected) => {
      const wrapper = mountPage()
      await flushPromises()

      const vm = wrapper.vm as any
      vm.showCreate = true
      vm.form.role = role
      await flushPromises()

      // 前置自检：弹窗确实渲染出来了，否则「找不到该表单项」会假通过
      const allItems = document.querySelectorAll('.el-form-item')
      expect(allItems.length).toBeGreaterThan(0)
      // 同一弹窗内的对照项（无门控）必须始终在场 —— 证明查询选择器本身有效
      const roleItem = Array.from(allItems).find(el =>
        (el.querySelector('.el-form-item__label')?.textContent || '').includes('角色'),
      )
      expect(roleItem).toBeTruthy()

      expect(findParentPartnerItem() !== null).toBe(expected)
      wrapper.unmount()
    },
  )

  it('角色从 manager 切到 partner 时清空已选上级合伙人（隐藏字段不得残留提交值）', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.form.role = 'manager'
    await flushPromises()
    vm.form.parent_partner_id = 'p-1'
    await flushPromises()
    expect(vm.form.parent_partner_id).toBe('p-1')

    vm.form.role = 'partner'
    await flushPromises()

    expect(vm.showParentPartner).toBe(false)
    expect(vm.form.parent_partner_id).toBeNull()
    wrapper.unmount()
  })

  it('角色在 manager ↔ auditor 之间切换时保留已选上级合伙人（两者都适用）', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.form.role = 'manager'
    await flushPromises()
    vm.form.parent_partner_id = 'p-1'
    await flushPromises()

    vm.form.role = 'auditor'
    await flushPromises()

    expect(vm.showParentPartner).toBe(true)
    expect(vm.form.parent_partner_id).toBe('p-1')
    wrapper.unmount()
  })
})
