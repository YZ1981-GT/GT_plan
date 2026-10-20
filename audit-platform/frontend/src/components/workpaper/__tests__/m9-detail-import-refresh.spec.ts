/**
 * M9TabDetail — 导入成功后当页按同一口径重载明细行
 * spec: m7-m9-service-modules-and-lazy-import-guard（R5）
 *
 * 修复前：导入成功只 emit('imported')，父组件没有监听 ⇒ 后端已整表替换 M9-2-detail-rows，
 * 界面仍停在导入前、刷新整页才看得到。M7-2 一直是「导入成功 → loadData → 恢复行」。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { shallowMount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
  httpGet: vi.fn(),
  httpPost: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({ api: { get: mocks.apiGet, put: mocks.apiPut, post: vi.fn() } }))
vi.mock('@/utils/http', () => ({ default: { get: mocks.httpGet, post: mocks.httpPost } }))

import M9TabDetail from '../m9/core/M9TabDetail.vue'

/** checklist-responses 读接口只返回整表键（与后端导入写入的形态一致：conclusion 存行数组） */
function serveRows(names: string[]): void {
  const rows = names.map((itemName, i) => ({ key: `k-${i}`, itemName, ociCategory: 'reclass', beginning: i + 1 }))
  mocks.apiGet.mockImplementation(async (url: string) =>
    url.includes('/checklist-responses')
      ? [{ item_id: 'M9-2-detail-rows', conclusion: JSON.stringify(rows), remark: null }]
      : {},
  )
}

/** 页面用到的 Element Plus 标签：注册成不渲染插槽的空组件（不装组件库时，表格列的作用域插槽拿不到行数据） */
const EL_TAGS = [
  'ElButton', 'ElDropdown', 'ElDropdownItem', 'ElDropdownMenu', 'ElIcon', 'ElInput', 'ElInputNumber',
  'ElSegmented', 'ElTable', 'ElTableColumn', 'ElTag', 'ElTooltip', 'ElUpload',
]
const emptyStub = defineComponent({ render: () => null })

function mountDetail() {
  return shallowMount(M9TabDetail, {
    props: { wpId: 'wp-1', projectId: 'p-1', isReadonly: false },
    global: { components: Object.fromEntries(EL_TAGS.map((name) => [name, emptyStub])) },
  })
}

function rowNames(wrapper: ReturnType<typeof mountDetail>): string[] {
  return (wrapper.vm as any).detailRows.map((r: { itemName: string }) => r.itemName)
}

describe('M9TabDetail 导入后重载明细行', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('导入成功：重新拉取并按 M9-2-detail-rows 恢复行，再通知父组件', async () => {
    serveRows(['导入前'])
    const wrapper = mountDetail()
    await flushPromises()
    expect(rowNames(wrapper)).toEqual(['导入前'])

    serveRows(['导入甲', '导入乙'])
    mocks.httpPost.mockResolvedValue({ data: { data: { imported_count: 2, warnings: [] } } })
    await (wrapper.vm as any).onImportFile(new File(['x'], 'm9.xlsx'))
    await flushPromises()

    expect(mocks.httpPost).toHaveBeenCalledWith(
      '/api/m9-other-comprehensive-income/wp-1/import-data',
      expect.any(FormData),
      expect.anything(),
    )
    expect(rowNames(wrapper)).toEqual(['导入甲', '导入乙'])
    expect(wrapper.emitted('imported')).toHaveLength(1)
  })

  it('导入失败：不重载、不通知', async () => {
    serveRows(['导入前'])
    const wrapper = mountDetail()
    await flushPromises()
    const loadsBefore = mocks.apiGet.mock.calls.length

    serveRows(['不该出现'])
    mocks.httpPost.mockRejectedValue({ response: { data: { detail: '缺少列：备注' } } })
    await (wrapper.vm as any).onImportFile(new File(['x'], 'm9.xlsx'))
    await flushPromises()

    expect(mocks.apiGet.mock.calls.length).toBe(loadsBefore)
    expect(rowNames(wrapper)).toEqual(['导入前'])
    expect(wrapper.emitted('imported')).toBeUndefined()
  })
})
