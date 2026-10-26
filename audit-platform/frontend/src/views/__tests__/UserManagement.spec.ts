/**
 * 用户管理（spec procedure-chain-followup-closure R1）：
 * - 编辑只发改了的字段（用户名不可改、不带空密码；后端多余字段直接 422）；
 * - 启用 / 停用二次确认，不能停用自己（不给按钮，后端同样拒绝）；
 * - 重置密码只发 password，两次输入须一致；
 * - 角色选项含「只读」（后端 UserRole 有 readonly）。
 * 表单控件用真实 Element Plus（校验走 el-form）；表格 / 弹窗用内联桩，断言看渲染结果。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, inject, provide } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'
import Schema from 'async-validator'

const api = vi.hoisted(() => ({ list: vi.fn(), create: vi.fn(), update: vi.fn() }))
vi.mock('@/services/commonApi', () => ({ listUsers: api.list, createUser: api.create, updateUser: api.update }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ userId: 'u-admin' }) }))
vi.mock('@/components/common/GtPageHeader.vue', () => ({ default: { name: 'GtPageHeader', template: '<div><slot /></div>' } }))

import UserManagement from '../UserManagement.vue'

const USERS = [
  { id: 'u-admin', username: 'admin', email: 'admin@example.com', role: 'admin', is_active: true },
  { id: 'u-a', username: 'auditor_a', email: 'a@example.com', role: 'auditor', is_active: true },
  { id: 'u-b', username: 'reader_b', email: 'b@example.com', role: 'readonly', is_active: false },
]

const RowScope = defineComponent({
  props: { row: { type: Object, required: true } },
  setup(props, { slots }) {
    provide('stubRow', props.row)
    return () => h('div', { class: 'stub-row', 'data-id': (props.row as any).id }, slots.default?.())
  },
})
const STUBS = {
  'el-table': defineComponent({
    props: { data: { type: Array, default: () => [] } },
    setup(props, { slots }) {
      return () => h('div', (props.data as any[]).map((row) => h(RowScope, { row, key: row.id }, { default: () => slots.default?.() })))
    },
  }),
  'el-table-column': defineComponent({
    props: ['label', 'prop'],
    setup(props, { slots }) {
      const row = inject<any>('stubRow', null)
      return () => h('div', { class: 'col', 'data-label': props.label }, row && slots.default ? slots.default({ row }) : [])
    },
  }),
  'el-dialog': { template: '<div v-if="modelValue" class="el-dialog"><slot /><slot name="footer" /></div>', props: ['modelValue'] },
  // 实测：本测试环境里真实 el-form 的 validate 对两次不一致的密码也返回通过（字段停在 validating）⇒
  // 用 Element Plus 同一个校验库（async-validator）按页面的 rules 判
  'el-form': defineComponent({
    props: ['model', 'rules'],
    setup(props, { slots, expose }) {
      expose({ validate: () => new Schema(props.rules || {}).validate({ ...props.model }).then(() => true) })
      return () => h('form', slots.default?.())
    },
  }),
  'el-form-item': { template: '<div class="el-form-item"><slot /></div>' },
}

async function mountPage() {
  api.list.mockResolvedValue(JSON.parse(JSON.stringify(USERS)))
  const wrapper = mount(UserManagement, {
    global: { plugins: [ElementPlus], stubs: STUBS, directives: { permission: {} } },
  })
  await flushPromises()
  const row = (id: string) => wrapper.find(`.stub-row[data-id="${id}"]`)
  const actions = (id: string) => row(id).find('[data-label="操作"]').findAll('button').map((b) => b.text())
  return { wrapper, vm: wrapper.vm as any, row, actions }
}

beforeEach(() => {
  api.list.mockReset()
  api.create.mockReset().mockResolvedValue({})
  api.update.mockReset().mockResolvedValue({})
  vi.spyOn(ElMessage, 'success').mockImplementation((() => undefined) as any)
  vi.spyOn(ElMessage, 'info').mockImplementation((() => undefined) as any)
})

describe('用户管理 — 列表与启用 / 停用', () => {
  it('显示状态与「只读」角色；自己没有停用按钮，停用的账号显示「启用」', async () => {
    const { row, actions } = await mountPage()
    expect(actions('u-admin')).toEqual(['编辑', '重置密码'])
    expect(actions('u-a')).toEqual(['编辑', '重置密码', '停用'])
    expect(actions('u-b')).toEqual(['编辑', '重置密码', '启用'])
    expect(row('u-b').find('[data-label="状态"]').text()).toBe('停用')
    expect(row('u-b').find('[data-label="角色"]').text()).toBe('只读')
  })

  it('停用：确认后只发 is_active 并刷新列表；取消不发请求', async () => {
    const { vm, row } = await mountPage()
    const confirm = vi.spyOn(ElMessageBox, 'confirm')
    confirm.mockRejectedValueOnce('cancel')
    await vm.toggleActive(USERS[1])
    expect(api.update).not.toHaveBeenCalled()

    confirm.mockResolvedValueOnce('confirm' as any)
    const stop = row('u-a').find('[data-label="操作"]').findAll('button').find((b) => b.text() === '停用')!
    await stop.trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenLastCalledWith(expect.stringContaining('停用后该账号不能登录'), '停用账号', expect.anything())
    expect(api.update).toHaveBeenCalledWith('u-a', { is_active: false })
    expect(api.list).toHaveBeenCalledTimes(2)
  })
})

describe('用户管理 — 编辑只发改了的字段', () => {
  it('用户名不可改；改了邮箱只发邮箱（不带用户名、不带空密码）', async () => {
    const { wrapper, vm } = await mountPage()
    vm.editUser(USERS[1])
    await flushPromises()
    expect(wrapper.find('input[placeholder="请输入用户名"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('input[placeholder="请输入密码"]').exists()).toBe(false)
    vm.form.email = 'new@example.com'
    await vm.saveUser()
    await flushPromises()
    expect(api.update).toHaveBeenCalledWith('u-a', { email: 'new@example.com' })
  })

  it('什么都没改 ⇒ 不发请求、提示没有改动', async () => {
    const { vm } = await mountPage()
    vm.editUser(USERS[1])
    await flushPromises()
    await vm.saveUser()
    await flushPromises()
    expect(api.update).not.toHaveBeenCalled()
    expect(ElMessage.info).toHaveBeenCalledWith('没有改动')
  })
})

describe('用户管理 — 重置密码', () => {
  it('两次一致 ⇒ 只发 password', async () => {
    const { vm } = await mountPage()
    vm.openResetPassword(USERS[1])
    await flushPromises()
    vm.resetDialog.password = 'Reset#2026'
    vm.resetDialog.confirm = 'Reset#2026'
    await vm.submitResetPassword()
    await flushPromises()
    expect(api.update).toHaveBeenCalledWith('u-a', { password: 'Reset#2026' })
  })

  it('两次不一致 / 太短 ⇒ 不发请求', async () => {
    const { vm } = await mountPage()
    vm.openResetPassword(USERS[1])
    await flushPromises()
    vm.resetDialog.password = 'Reset#2026'
    vm.resetDialog.confirm = 'Reset#2027'
    await vm.submitResetPassword()
    vm.resetDialog.password = '123'
    vm.resetDialog.confirm = '123'
    await vm.submitResetPassword()
    await flushPromises()
    expect(api.update).not.toHaveBeenCalled()
  })

  it('长度下限与后端 UserUpdate 一致：7 位不发（后端会 422），8 位发', async () => {
    const { vm } = await mountPage()
    vm.openResetPassword(USERS[1])
    await flushPromises()
    vm.resetDialog.password = 'Abc#567'
    vm.resetDialog.confirm = 'Abc#567'
    await vm.submitResetPassword()
    await flushPromises()
    expect(api.update).not.toHaveBeenCalled()
    vm.resetDialog.password = 'Abc#5678'
    vm.resetDialog.confirm = 'Abc#5678'
    await vm.submitResetPassword()
    await flushPromises()
    expect(api.update).toHaveBeenCalledWith('u-a', { password: 'Abc#5678' })
  })
})
