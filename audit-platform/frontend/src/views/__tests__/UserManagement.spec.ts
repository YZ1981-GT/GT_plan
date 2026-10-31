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
const grantApi = vi.hoisted(() => ({ list: vi.fn(), grant: vi.fn(), revoke: vi.fn() }))
const bindingApi = vi.hoisted(() => ({ list: vi.fn(), bind: vi.fn(), unbind: vi.fn(), search: vi.fn() }))
vi.mock('@/services/commonApi', () => ({ listUsers: api.list, createUser: api.create, updateUser: api.update }))
vi.mock('@/services/staffBindingApi', () => ({
  listStaffBindings: bindingApi.list,
  bindStaffToUser: bindingApi.bind,
  unbindStaffFromUser: bindingApi.unbind,
  searchUnboundStaff: bindingApi.search,
}))
vi.mock('@/services/projectCreationGrantApi', () => ({
  listProjectCreationGrants: grantApi.list,
  grantProjectCreation: grantApi.grant,
  revokeProjectCreationGrant: grantApi.revoke,
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ userId: 'u-admin' }) }))
vi.mock('@/components/common/GtPageHeader.vue', () => ({ default: { name: 'GtPageHeader', template: '<div><slot /></div>' } }))

import UserManagement from '../UserManagement.vue'
import StaffBindingDialog from '@/components/system/StaffBindingDialog.vue'

const USERS = [
  { id: 'u-admin', username: 'admin', email: 'admin@example.com', role: 'admin', is_active: true },
  { id: 'u-a', username: 'auditor_a', email: 'a@example.com', role: 'auditor', is_active: true },
  { id: 'u-m', username: 'manager_m', email: 'm@example.com', role: 'manager', is_active: true },
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
  grantApi.list.mockResolvedValue([])
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
  grantApi.list.mockReset().mockResolvedValue([])
  grantApi.grant.mockReset().mockResolvedValue([])
  grantApi.revoke.mockReset().mockResolvedValue({ revoked: true })
  bindingApi.list.mockReset().mockResolvedValue([])
  bindingApi.bind.mockReset().mockResolvedValue({ changed: true, project_count: 0 })
  bindingApi.unbind.mockReset().mockResolvedValue({ changed: true })
  bindingApi.search.mockReset().mockResolvedValue([])
  vi.spyOn(ElMessage, 'success').mockImplementation((() => undefined) as any)
  vi.spyOn(ElMessage, 'error').mockImplementation((() => undefined) as any)
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


describe('用户管理 — 经理精确 USCC 建项授权', () => {
  it('只列已启用经理，并经二次确认把换行/逗号代码去重后批量授权', async () => {
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValueOnce('confirm' as any)
    const { wrapper, vm } = await mountPage()
    expect(wrapper.text()).toContain('经理建项授权')
    expect(vm.activeManagers.map((item: any) => item.id)).toEqual(['u-m'])
    vm.openGrantDialog()
    vm.grantDialog.managerUserId = 'u-m'
    vm.grantDialog.companyCodes = '91110000300000000G\n91110000400000000U，91110000300000000G'
    vm.grantDialog.reason = '新客户承接审批通过'
    await vm.submitGrant()
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('2 个企业代码'),
      '确认经理建项授权',
      expect.objectContaining({ confirmButtonText: '确认授权' }),
    )
    expect(grantApi.grant).toHaveBeenCalledWith('u-m', {
      company_codes: ['91110000300000000G', '91110000400000000U'],
      valid_until: null,
      reason: '新客户承接审批通过',
    })
    expect(grantApi.list).toHaveBeenCalledTimes(2)
  })

  it('无效代码在前端拦截，不发授权请求', async () => {
    const { vm } = await mountPage()
    vm.openGrantDialog()
    vm.grantDialog.managerUserId = 'u-m'
    vm.grantDialog.companyCodes = 'INVALID'
    vm.grantDialog.reason = '测试授权原因'
    await vm.submitGrant()
    expect(grantApi.grant).not.toHaveBeenCalled()
    expect(ElMessage.error).toHaveBeenCalledWith('请输入有效的18位统一社会信用代码')
  })

  it('撤销要求原因，确认后调用撤销接口并刷新', async () => {
    const { vm } = await mountPage()
    const prompt = vi.spyOn(ElMessageBox, 'prompt').mockResolvedValueOnce({ value: '客户负责人调整' } as any)
    const grant = {
      id: 'g-1', version: 3, manager_username: 'manager_m', company_code: '91110000300000000G',
    }
    await vm.revokeGrant(grant)
    await flushPromises()
    expect(prompt).toHaveBeenCalledWith(
      expect.stringContaining('91110000300000000G'),
      '撤销经理建项授权',
      expect.objectContaining({ confirmButtonText: '撤销' }),
    )
    expect(grantApi.revoke).toHaveBeenCalledWith('g-1', 3, '客户负责人调整')
    expect(grantApi.list).toHaveBeenCalledTimes(2)
  })

  it('读取失败显示错误与重新加载，保留上次成功数据而不是显示暂无授权', async () => {
    const { wrapper, vm } = await mountPage()
    const grant = {
      id: 'g-load', version: 1, manager_username: 'manager_m', company_code: '91110000300000000G',
      valid_until: null, reason: '客户承接', granted_by_username: 'admin', status: 'active',
    }
    grantApi.list.mockResolvedValueOnce([grant])
    await vm.loadGrants()
    await flushPromises()
    grantApi.list.mockRejectedValueOnce(new Error('network'))
    await vm.loadGrants()
    await flushPromises()
    expect(wrapper.text()).toContain('经理建项授权加载失败')
    expect(wrapper.find('.stub-row[data-id="g-load"]').exists()).toBe(true)

    grantApi.list.mockResolvedValueOnce([])
    const retry = wrapper.findAll('button').find((button) => button.text() === '重新加载')!
    await retry.trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('经理建项授权加载失败')
    expect(wrapper.find('.stub-row[data-id="g-load"]').exists()).toBe(false)
  })

  it('账号已停用或不再是经理的授权显示为已暂停', async () => {
    const { wrapper, vm } = await mountPage()
    grantApi.list.mockResolvedValueOnce([{
      id: 'g-suspended', version: 2, manager_username: 'former_manager',
      company_code: '91110000300000000G', valid_until: null, reason: '历史授权',
      granted_by_username: 'admin', status: 'suspended',
    }])
    await vm.loadGrants()
    await flushPromises()
    const row = wrapper.find('.stub-row[data-id="g-suspended"]')
    expect(row.find('[data-label="状态"]').text()).toBe('已暂停')
  })

  it('撤销失败（如版本冲突）后刷新到服务端当前状态', async () => {
    const { vm } = await mountPage()
    vi.spyOn(ElMessageBox, 'prompt').mockResolvedValueOnce({ value: '负责人调整' } as any)
    grantApi.revoke.mockRejectedValueOnce({ response: { status: 409 } })
    await vm.revokeGrant({
      id: 'g-stale', version: 1, manager_username: 'manager_m', company_code: '91110000300000000G',
    })
    await flushPromises()
    expect(grantApi.list).toHaveBeenCalledTimes(2)
  })

  it('启用 / 停用账号后同时刷新用户与建项授权状态', async () => {
    const { vm } = await mountPage()
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValueOnce('confirm' as any)
    await vm.toggleActive(USERS[2])
    await flushPromises()
    expect(api.update).toHaveBeenCalledWith('u-m', { is_active: false })
    expect(api.list).toHaveBeenCalledTimes(2)
    expect(grantApi.list).toHaveBeenCalledTimes(2)
  })
})


describe('用户管理 — 人员档案绑定', () => {
  const BINDING = {
    user_id: 'u-m', staff_id: 's-m', staff_name: '王经理', employee_no: 'A001',
    department: '审计一部', status: 'active',
  }

  it('已绑定显示档案与“解除”，未绑定显示“未绑定”与“绑定”', async () => {
    bindingApi.list.mockResolvedValue([BINDING])
    const { row } = await mountPage()
    const bound = row('u-m').find('[data-label="人员档案"]')
    expect(bound.text()).toContain('王经理（A001）')
    expect(bound.findAll('button').map((b) => b.text())).toEqual(['解除'])
    const unbound = row('u-a').find('[data-label="人员档案"]')
    expect(unbound.text()).toContain('未绑定')
    expect(unbound.findAll('button').map((b) => b.text())).toEqual(['绑定'])
    expect(unbound.find('button').attributes('disabled')).toBeUndefined()
    // 停用的账号不能绑定（后端同样 422）
    expect(row('u-b').find('[data-label="人员档案"]').find('button').attributes('disabled')).toBeDefined()
  })

  it('连续重读时慢的旧响应不覆盖新结果（成功与失败都按最后一次）', async () => {
    const { row, vm } = await mountPage()
    let resolveOld!: (rows: any[]) => void
    bindingApi.list
      .mockReturnValueOnce(new Promise((r) => { resolveOld = r }))
      .mockResolvedValueOnce([])
    const older = vm.loadStaffBindings()
    await vm.loadStaffBindings()
    resolveOld([{ user_id: 'u-a', staff_id: 's-old', staff_name: '旧档案', employee_no: 'OLD', department: null, status: 'active' }])
    await older
    await flushPromises()
    expect(row('u-a').find('[data-label="人员档案"]').text()).toContain('未绑定')

    let rejectOld!: (e: unknown) => void
    bindingApi.list
      .mockReturnValueOnce(new Promise((_r, reject) => { rejectOld = reject }))
      .mockResolvedValueOnce([])
    const failing = vm.loadStaffBindings()
    await vm.loadStaffBindings()
    rejectOld(new Error('late'))
    await failing
    await flushPromises()
    expect(row('u-a').find('[data-label="人员档案"]').text()).not.toContain('加载失败')
  })

  it('弹窗绑定成功（bound）或被拒（stale）都重读绑定列表', async () => {
    const { wrapper } = await mountPage()
    expect(bindingApi.list).toHaveBeenCalledTimes(1)
    const dialog = wrapper.findComponent(StaffBindingDialog)
    dialog.vm.$emit('bound', { user_id: 'u-a', staff_id: 's-a', changed: true })
    await flushPromises()
    expect(bindingApi.list).toHaveBeenCalledTimes(2)
    dialog.vm.$emit('stale')
    await flushPromises()
    expect(bindingApi.list).toHaveBeenCalledTimes(3)
  })

  it('读取绑定失败显示“加载失败”，不误显示为未绑定', async () => {
    bindingApi.list.mockRejectedValue(new Error('network'))
    const { row } = await mountPage()
    const cell = row('u-a').find('[data-label="人员档案"]')
    expect(cell.text()).toContain('加载失败')
    expect(cell.text()).not.toContain('未绑定')
    expect(cell.findAll('button')).toHaveLength(0)
  })

  it('点“绑定”为该账号打开绑定弹窗', async () => {
    const { row, vm } = await mountPage()
    const bindButton = row('u-a').find('[data-label="人员档案"]').findAll('button').find((b) => b.text() === '绑定')!
    await bindButton.trigger('click')
    await flushPromises()
    expect(vm.staffBindingDialog).toEqual({ visible: true, user: { id: 'u-a', username: 'auditor_a' } })
  })

  it('解除绑定须二次确认；确认后按账号与档案调用并刷新，取消不发请求', async () => {
    bindingApi.list.mockResolvedValue([BINDING])
    const { vm } = await mountPage()
    const confirm = vi.spyOn(ElMessageBox, 'confirm')
    confirm.mockRejectedValueOnce('cancel')
    await vm.unbindStaff(USERS[2], BINDING)
    expect(bindingApi.unbind).not.toHaveBeenCalled()

    confirm.mockResolvedValueOnce('confirm' as any)
    await vm.unbindStaff(USERS[2], BINDING)
    await flushPromises()
    expect(confirm).toHaveBeenLastCalledWith(
      expect.stringContaining('王经理（A001）'), '解除人员档案绑定', expect.objectContaining({ confirmButtonText: '解除绑定' }),
    )
    expect(bindingApi.unbind).toHaveBeenCalledWith('u-m', 's-m')
    expect(bindingApi.list).toHaveBeenCalledTimes(2)
  })

  it('解除失败（如仍在项目团队中）也刷新绑定列表', async () => {
    bindingApi.list.mockResolvedValue([BINDING])
    const { vm } = await mountPage()
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValueOnce('confirm' as any)
    bindingApi.unbind.mockRejectedValueOnce({ response: { status: 409 } })
    await vm.unbindStaff(USERS[2], BINDING)
    await flushPromises()
    expect(bindingApi.list).toHaveBeenCalledTimes(2)
    expect(ElMessage.success).not.toHaveBeenCalledWith('已解除人员档案绑定')
  })
})
