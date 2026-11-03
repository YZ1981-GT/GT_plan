/**
 * CustomQueryTabCountToken.spec.ts — 业务视图翻页复用 COUNT 凭证（platform-performance-user-experience-closure 任务 10）
 *
 * - 第 1 页不带凭证，响应里的 `count_token` 记下；翻页时带上（后端据此跳过重复 COUNT）。
 * - 点「执行查询」= 新查询：回到第 1 页、不带凭证（要的是现算的行数）。
 *   判据走真实模板接线：从按钮发出 click，而不是直调 onExecute —— 模板若写成 `@click="onExecute"`，
 *   点击事件对象会被当成 keepPage（真值），既不回第 1 页也不清凭证，直调函数的用例照样全绿。
 * - 翻页 / 改每页行数同理走真实接线：分页条探针发出 el-pagination 的 current-change / size-change，
 *   经共用的 QueryResultPager（v-model:page / v-model:page-size + change）回到宿主重新查询
 *   （2026-10-30 同步：远端把页面版分页改成 QueryResultPager，原先直调的 onPageChange / onPageSizeChange 已不存在）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'

vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({ buildAddressTree: vi.fn(), loadCellNodes: vi.fn(), resolveIndex: vi.fn(), clearCache: vi.fn() }),
}))
const httpMocks = vi.hoisted(() => ({ get: vi.fn().mockResolvedValue({ headers: {} }), post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: httpMocks }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
    ElMessageBox: { confirm: vi.fn(), alert: vi.fn(), prompt: vi.fn() },
  }
})
vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({ currentRole: { value: 'admin' } }),
}))
const apiMocks = vi.hoisted(() => ({
  get: vi.fn().mockResolvedValue([]),
  post: vi.fn().mockResolvedValue({}),
  delete: vi.fn().mockResolvedValue({}),
}))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))

import CustomQueryTab from '@/components/template-library/CustomQueryTab.vue'

const PROJECT = { id: 'p-2025', name: '【测试】计数凭证_2025', audit_year: 2025, can_edit: true }

function executeBodies(): any[] {
  return apiMocks.post.mock.calls
    .filter(([url]: any[]) => String(url).includes('/api/custom-query/execute'))
    .map(([, body]: any[]) => body)
}

async function mountTab() {
  apiMocks.get.mockImplementation((url: string) =>
    Promise.resolve(String(url).includes('/api/projects') ? [PROJECT] : []))
  const wrapper = shallowMount(CustomQueryTab, {
    global: {
      directives: { loading: {} },
      stubs: {
        'el-dialog': { template: '<div class="el-dialog-stub" />' },
        'el-table': { template: '<div class="el-table-stub" />' },
        'el-table-column': { template: '<div class="el-table-column-stub" />' },
        // 带插槽的按钮探针：模板上的 @click 透传到根 <button>，点击时监听器收到原生 MouseEvent（与 ElButton 发出
        // click 的实参一致），模板写法决定 onExecute 收到什么
        'el-button': { name: 'ButtonProbe', template: '<button class="btn-probe"><slot /></button>' },
        // 分页条渲染真实的 QueryResultPager，只把其中的 el-pagination 换成能发事件的探针
        QueryResultPager: false,
        'el-pagination': { name: 'PaginationProbe', emits: ['current-change', 'size-change'],
          template: '<div class="pagination-probe" />' },
      },
    },
  })
  await flushPromises()
  const vm: any = wrapper.vm
  vm.onProjectChange(PROJECT.id)
  vm.formCtx.project_id = PROJECT.id
  vm.formCtx.source = 'aux_ledger'
  expect(vm.formCtx.year, '反向自检：项目年度未带出，「执行查询」会置灰').toBe(PROJECT.audit_year)
  return wrapper
}

async function clickExecute(wrapper: any) {
  const button = wrapper.findAll('button.btn-probe').find((b: any) => b.text().includes('执行查询'))
  expect(button, '反向自检：没找到「执行查询」按钮，判据不可靠').toBeTruthy()
  await button.trigger('click')
  await flushPromises()
}
/** 分页条事件：探针 → QueryResultPager（更新页码 / 每页行数后发 change）→ 宿主按 offset 重新查询 */
async function paginate(wrapper: any, event: 'current-change' | 'size-change', value: number) {
  const probe = wrapper.findComponent({ name: 'PaginationProbe' })
  expect(probe.exists(), '反向自检：没找到分页条，判据不可靠').toBe(true)
  probe.vm.$emit(event, value)
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMocks.post.mockImplementation((url: string, body: any) => {
    if (!String(url).includes('/api/custom-query/execute')) return Promise.resolve({})
    const page = Math.floor((body.offset || 0) / 100) + 1
    return Promise.resolve({
      rows: [{ id: `r-${page}` }], columns: ['id'], total: 348780,
      count_token: `tok-${page}`, count_reused: Boolean(body.count_token),
    })
  })
})

describe('CustomQueryTab — 翻页复用 COUNT 凭证', () => {
  it('第 1 页不带凭证；翻页带上一页返回的凭证；点「执行查询」回到第 1 页且不带凭证', async () => {
    const wrapper = await mountTab()
    const vm: any = wrapper.vm

    await clickExecute(wrapper)
    await paginate(wrapper, 'current-change', 3)
    await paginate(wrapper, 'current-change', 4)
    await clickExecute(wrapper)

    const sent = executeBodies().map((b) => ({ offset: b.offset ?? 0, token: b.count_token ?? null }))
    expect(sent).toEqual([
      { offset: 0, token: null },
      { offset: 200, token: 'tok-1' },
      { offset: 300, token: 'tok-3' },
      { offset: 0, token: null },
    ])
    expect(vm.page).toBe(1)
  })

  it('新查询请求在途时立即清空旧凭证，不等响应覆盖状态', async () => {
    const wrapper = await mountTab()
    const vm: any = wrapper.vm
    vm.page = 7
    vm.countToken = 'stale-token'

    let resolveRequest!: (value: any) => void
    apiMocks.post.mockImplementation((url: string) => {
      if (!String(url).includes('/api/custom-query/execute')) return Promise.resolve({})
      return new Promise((resolve) => { resolveRequest = resolve })
    })
    const button = wrapper.findAll('button.btn-probe').find((b: any) => b.text().includes('执行查询'))
    expect(button, '反向自检：没找到「执行查询」按钮，判据不可靠').toBeTruthy()
    const click = button!.trigger('click')
    await Promise.resolve()

    expect(vm.page).toBe(1)
    expect(vm.countToken).toBe('')
    expect(executeBodies().at(-1)).not.toHaveProperty('count_token')

    resolveRequest({ rows: [], columns: [], total: 0, count_token: 'fresh-token', count_reused: false })
    await click
    await flushPromises()
    expect(vm.countToken).toBe('fresh-token')
  })

  it('改每页行数仍是同一查询：带凭证从第 1 页重取（行数不变，不必重数）', async () => {
    const wrapper = await mountTab()
    const vm: any = wrapper.vm
    await clickExecute(wrapper)
    await paginate(wrapper, 'size-change', 200)
    const last = executeBodies().at(-1)
    expect({ offset: last.offset ?? 0, limit: last.limit, token: last.count_token }).toEqual({
      offset: 0, limit: 200, token: 'tok-1',
    })
  })
})
