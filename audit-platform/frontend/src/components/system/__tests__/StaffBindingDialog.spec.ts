/**
 * 人员档案绑定弹窗（spec batch-project-authorization-and-lock-hardening R6）：
 * - 打开即按空关键字列出未绑定档案；慢请求的旧结果不覆盖新关键字；
 * - 选中后再搜索换掉候选，仍按选中的档案绑定；
 * - 二次确认后才发请求；成功发 bound 并关闭，失败发 stale 并重取候选。
 * el-dialog / el-select 用真实 Element Plus。弹窗内容经 Teleport 挂到 body，VTU 的 teleport 桩
 * 不渲染 ElTeleport 传入的子节点 ⇒ 不桩 teleport，按组件树查找（findComponent 能穿过 Teleport）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElButton, ElMessage, ElMessageBox, ElSelect } from 'element-plus'

const api = vi.hoisted(() => ({ bind: vi.fn(), search: vi.fn() }))
vi.mock('@/services/staffBindingApi', () => ({
  bindStaffToUser: api.bind,
  searchUnboundStaff: api.search,
}))

import StaffBindingDialog from '../StaffBindingDialog.vue'

const USER = { id: 'u-m', username: 'manager_m' }
const WANG = { id: 's-wang', name: '王经理', employee_no: 'A001', department: '审计一部', status: 'active' }
const LI = { id: 's-li', name: '李经理', employee_no: null, department: null, status: 'active' }

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

enableAutoUnmount(afterEach)

async function mountOpened() {
  const wrapper = mount(StaffBindingDialog, {
    props: { modelValue: false, user: USER },
    global: { plugins: [ElementPlus] },
  })
  // 与用户管理页一致：先挂载关闭态，再打开（el-dialog 只在打开时发 open）。
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  return { wrapper, vm: wrapper.vm as any }
}

function confirmButton(wrapper: any) {
  return wrapper.findAllComponents(ElButton).find((b: any) => b.text() === '确认绑定')!
}

beforeEach(() => {
  api.bind.mockReset().mockResolvedValue({ user_id: 'u-m', staff_id: 's-wang', changed: true, project_count: 2 })
  api.search.mockReset().mockResolvedValue([WANG, LI])
  vi.spyOn(ElMessage, 'success').mockImplementation((() => undefined) as any)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('人员档案绑定弹窗', () => {
  it('打开即按空关键字取候选；输入关键字走同一个搜索', async () => {
    const { wrapper, vm } = await mountOpened()
    expect(api.search).toHaveBeenCalledWith('')
    expect(vm.options.map((item: any) => item.id)).toEqual(['s-wang', 's-li'])

    const remoteMethod = wrapper.findComponent(ElSelect).props('remoteMethod') as (q: string) => Promise<void>
    api.search.mockResolvedValueOnce([LI])
    await remoteMethod('李')
    expect(api.search).toHaveBeenLastCalledWith('李')
    expect(vm.options.map((item: any) => item.id)).toEqual(['s-li'])
  })

  it('慢请求的旧结果不覆盖后输入关键字的结果', async () => {
    const { vm } = await mountOpened()
    const slow = deferred<any[]>()
    api.search.mockReturnValueOnce(slow.promise).mockResolvedValueOnce([LI])
    const first = vm.search('王')
    await vm.search('李')
    slow.resolve([WANG])
    await first
    expect(vm.options.map((item: any) => item.id)).toEqual(['s-li'])
    expect(vm.searching).toBe(false)
  })

  it('未选档案时不能确认；选中后再搜索换掉候选，仍按选中的档案绑定', async () => {
    const { wrapper } = await mountOpened()
    expect(confirmButton(wrapper).attributes('disabled')).toBeDefined()

    wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', 's-wang')
    await flushPromises()
    expect(confirmButton(wrapper).attributes('disabled')).toBeUndefined()

    api.search.mockResolvedValueOnce([LI])
    await (wrapper.findComponent(ElSelect).props('remoteMethod') as (q: string) => Promise<void>)('李')
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    await confirmButton(wrapper).trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('王经理（A001 · 审计一部）'), '确认绑定人员档案', expect.anything(),
    )
    expect(api.bind).toHaveBeenCalledWith('u-m', 's-wang')
    expect(ElMessage.success).toHaveBeenCalledWith('已绑定，该人员在 2 个项目的委派已生效')
    expect(wrapper.emitted('bound')?.[0]?.[0]).toMatchObject({ staff_id: 's-wang', project_count: 2 })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('取消二次确认不发请求、不关闭', async () => {
    const { wrapper } = await mountOpened()
    wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', 's-li')
    await flushPromises()
    vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
    await confirmButton(wrapper).trigger('click')
    await flushPromises()
    expect(api.bind).not.toHaveBeenCalled()
    expect(wrapper.emitted('bound')).toBeUndefined()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('绑定被拒：不关闭，清空选择、重取候选并通知页面重读绑定', async () => {
    const { wrapper, vm } = await mountOpened()
    wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', 's-wang')
    await flushPromises()
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    api.bind.mockRejectedValueOnce({ response: { status: 409 } })
    api.search.mockClear().mockResolvedValueOnce([LI])
    await confirmButton(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.emitted('stale')).toHaveLength(1)
    expect(wrapper.emitted('bound')).toBeUndefined()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(api.search).toHaveBeenCalledWith('')
    expect(vm.selectedStaff).toBeNull()
    expect(vm.options.map((item: any) => item.id)).toEqual(['s-li'])
    expect(vm.saving).toBe(false)
  })

  it('重新打开不带上一次的选择', async () => {
    const { wrapper, vm } = await mountOpened()
    wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', 's-wang')
    await flushPromises()
    await wrapper.setProps({ modelValue: false })
    await flushPromises()
    await wrapper.setProps({ modelValue: true, user: { id: 'u-n', username: 'manager_n' } })
    await flushPromises()
    expect(vm.selectedStaff).toBeNull()
    expect(confirmButton(wrapper).attributes('disabled')).toBeDefined()
    expect(api.search).toHaveBeenCalledTimes(2)
  })
})
