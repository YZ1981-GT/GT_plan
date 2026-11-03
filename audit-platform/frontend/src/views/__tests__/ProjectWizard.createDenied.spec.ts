/**
 * 建项向导被拒（spec batch-project-authorization-and-lock-hardening 6.2 真实验收发现）：
 * 原先经理建项授权被撤销后点「确认创建」，提示只有通用的「权限不足」，接口错误还冒泡到外层错误边界，
 * 整页换成「页面渲染出错」、已填内容丢失。现在：403 显示后端原因、保留表单；其他接口错误同样保留表单；
 * 非接口错误（程序错误）照常冒泡，不被吞掉。
 * http 换成桩，按 http.ts 拦截器的行为在 403 时调用请求级 `_forbiddenHandler`。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, onErrorCaptured } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'

const mocks = vi.hoisted(() => ({
  http: { post: vi.fn(), get: vi.fn(), put: vi.fn() },
  push: vi.fn(),
  stepValidate: vi.fn(),
  query: {} as Record<string, string>,
  msgboxConfirm: vi.fn().mockRejectedValue('cancel'),
}))
vi.mock('@/utils/http', () => ({ default: mocks.http }))
vi.mock('@/services/projectListQuery', () => ({ invalidateProjectListQuery: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: mocks.query }), useRouter: () => ({ push: mocks.push }) }))
vi.mock('@/composables/useWorkflowGuide', () => ({
  showGuide: vi.fn().mockResolvedValue(true),
  showWorkflowGuide: vi.fn().mockResolvedValue(true),
}))
vi.mock('@/components/wizard/ConsolScopeConfigDialog.vue', () => ({
  default: { name: 'ConsolScopeConfigDialog', render: () => null },
}))
vi.mock('@/components/wizard/BasicInfoStep.vue', async () => {
  const vue = await import('vue')
  return {
    default: vue.defineComponent({
      name: 'BasicInfoStep',
      setup(_, { expose }) {
        expose({ validate: () => mocks.stepValidate(), formRef: { validate: () => Promise.resolve(true) } })
        return () => vue.h('div', { class: 'basic-info-stub' }, '基本信息表单')
      },
    }),
  }
})

import ProjectWizard from '../ProjectWizard.vue'
import { useWizardStore } from '@/stores/wizard'

const FORM = { client_name: '【测试】甲', short_name: '甲', audit_year: 2096, company_code: '91110000BPAH62011M' }
const DENIED = { error_code: 'COMPANY_CREATION_NOT_AUTHORIZED', message: '有 1 个企业代码暂无建项授权，请联系管理员授权' }

/** 与 http.ts 一致：403 且请求带 _forbiddenHandler ⇒ 先调钩子（不弹通用提示），再把错误抛给调用方 */
function rejectAsInterceptor(status: number, data: unknown) {
  return (_url: string, _body: unknown, config?: any) => {
    const error = { isAxiosError: true, config, response: { status, data } }
    if (status === 403 && typeof config?._forbiddenHandler === 'function') config._forbiddenHandler(error)
    return Promise.reject(error)
  }
}

let captured: unknown[] = []
function mountWizard() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const Host = defineComponent({
    setup() {
      onErrorCaptured((err) => { captured.push(err); return false })
      return () => h(ProjectWizard)
    },
  })
  const wrapper = mount(Host, { global: { plugins: [pinia, ElementPlus] } })
  const confirm = () => wrapper.findAll('button').find((b) => b.text() === '确认创建')!
  return { wrapper, confirm }
}

beforeEach(() => {
  captured = []
  mocks.query = {}
  mocks.http.post.mockReset()
  mocks.http.get.mockReset()
  mocks.http.put.mockReset()
  mocks.push.mockReset()
  mocks.stepValidate.mockReset().mockResolvedValue({ ...FORM })
  vi.spyOn(ElMessage, 'error').mockImplementation((() => undefined) as any)
  vi.spyOn(ElMessage, 'success').mockImplementation((() => undefined) as any)
  vi.spyOn(ElMessage, 'info').mockImplementation((() => undefined) as any)
  // ElMessageBox.confirm 必须用 spyOn 在同一个对象上改——组件拿到的就是这个对象
  if (typeof ElMessageBox.confirm !== 'function' || !(ElMessageBox.confirm as any).mockRejectedValue) {
    vi.spyOn(ElMessageBox as any, 'confirm')
  }
  ;(ElMessageBox.confirm as any).mockRejectedValue('cancel')
})

describe('建项向导：建项被拒', () => {
  it('403：显示后端原因，留在本页、表单还在，错误不冒泡到错误边界', async () => {
    mocks.http.post.mockImplementation(rejectAsInterceptor(403, { code: 403, message: DENIED, detail: DENIED }))
    const { wrapper, confirm } = mountWizard()
    await confirm().trigger('click')
    await flushPromises()

    expect(mocks.http.post).toHaveBeenCalledTimes(1)
    expect(mocks.http.post.mock.calls[0][0]).toBe('/api/projects')
    expect(ElMessage.error).toHaveBeenCalledWith('有 1 个企业代码暂无建项授权，请联系管理员授权')
    expect(captured).toEqual([])
    expect(mocks.push).not.toHaveBeenCalled()
    expect(wrapper.find('.basic-info-stub').exists()).toBe(true)
    expect(useWizardStore().projectId).toBeNull()
    // 改了授权后可直接重试，按钮没有卡在提交中
    expect(confirm().attributes('disabled')).toBeUndefined()
  })

  it('其他接口错误（如 409 重复）同样留在本页，不冒泡；原因由拦截器提示', async () => {
    mocks.http.post.mockImplementation(rejectAsInterceptor(409, { code: 409, message: '项目已存在' }))
    const { wrapper, confirm } = mountWizard()
    await confirm().trigger('click')
    await flushPromises()
    expect(captured).toEqual([])
    expect(ElMessage.error).not.toHaveBeenCalled()
    expect(mocks.push).not.toHaveBeenCalled()
    expect(wrapper.find('.basic-info-stub').exists()).toBe(true)
  })

  it('程序错误不吞：照常冒泡到错误边界', async () => {
    mocks.stepValidate.mockRejectedValue(new TypeError('boom'))
    const { confirm } = mountWizard()
    await confirm().trigger('click')
    await flushPromises()
    expect(captured).toHaveLength(1)
    expect(String(captured[0])).toContain('boom')
    expect(mocks.http.post).not.toHaveBeenCalled()
  })

  it('已有项目点「保存」被拒同样留在本页，不冒泡', async () => {
    mocks.query = { projectId: 'p-1' }
    mocks.http.get.mockResolvedValue({
      status: 200,
      data: {
        project_id: 'p-1', current_step: 'basic_info',
        steps: { basic_info: { data: { ...FORM }, completed: true } },
      },
    })
    mocks.http.put.mockImplementation(rejectAsInterceptor(409, { code: 409, message: '项目年度已变化，请刷新后重试' }))
    const { wrapper } = mountWizard()
    await flushPromises()
    const save = wrapper.findAll('button').find((b) => b.text() === '保存')!
    await save.trigger('click')
    await flushPromises()
    expect(mocks.http.put).toHaveBeenCalledWith('/api/projects/p-1/wizard/basic_info', expect.objectContaining(FORM))
    expect(captured).toEqual([])
    expect(mocks.push).not.toHaveBeenCalled()
    expect(wrapper.find('.basic-info-stub').exists()).toBe(true)
  })

  it('成功路径：建项 → 引导 → 公式订阅「稍后」→ 确认 planning → 回项目列表', async () => {
    mocks.http.post.mockImplementation(async (url: string) => (
      url === '/api/projects' ? { data: { id: 'p-1', notices: [] } } : { data: { id: 'p-1', status: 'planning' } }
    ))
    const { confirm } = mountWizard()
    await confirm().trigger('click')
    await flushPromises()
    expect(mocks.http.post.mock.calls.map((call) => call[0])).toEqual(['/api/projects', '/api/projects/p-1/wizard/confirm'])
    expect(ElMessage.success).toHaveBeenCalledWith('项目创建成功')
    expect(mocks.push).toHaveBeenCalledWith('/projects')
    expect(captured).toEqual([])
  })
})

describe('建项向导：新建分支恢复（R10）', () => {
  it('引导取消 → 项目已创建（created），提示并回项目列表', async () => {
    mocks.http.post.mockResolvedValue({ data: { id: 'p-cancel', notices: [] } })
    const { showGuide } = await import('@/composables/useWorkflowGuide')
    ;(showGuide as any).mockResolvedValueOnce(false) // 用户关闭引导
    const { confirm } = mountWizard()
    await confirm().trigger('click')
    await flushPromises()
    // createProject 已调用（项目已落库），但 confirmProject 不会被调用
    expect(mocks.http.post.mock.calls.map((c: any[]) => c[0])).toEqual(['/api/projects'])
    expect(ElMessage.info).toHaveBeenCalledWith('项目已创建，可在项目列表中继续完善')
    expect(mocks.push).toHaveBeenCalledWith('/projects')
    expect(useWizardStore().projectId).toBeNull() // reset 清掉了
  })

  it('引导通过 + 公式订阅「去订阅」→ 先确认再跳设置页', async () => {
    mocks.http.post.mockImplementation(async (url: string) => (
      url === '/api/projects' ? { data: { id: 'p-sub', notices: [] } } : { data: { id: 'p-sub', status: 'planning' } }
    ))
    ;(ElMessageBox.confirm as any).mockResolvedValueOnce('confirm') // 公式订阅选「去订阅」
    const { confirm } = mountWizard()
    await confirm().trigger('click')
    await flushPromises()
    const urls = mocks.http.post.mock.calls.map((c: any[]) => c[0])
    expect(urls).toContain('/api/projects')
    expect(urls).toContain('/api/projects/p-sub/wizard/confirm')
    expect(mocks.push).toHaveBeenCalledWith('/settings/formula-global?tab=templates')
  })
})
