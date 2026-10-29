import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { ref } from 'vue'

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { post: mocks.post } }))
vi.mock('element-plus', () => ({
  ElMessage: { success: mocks.success, error: mocks.error },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))

import N2TabDetail from '../../n2/core/N2TabDetail.vue'
import { useN2ImportExport } from '../useN2ImportExport'

function mountDetail() {
  return shallowMount(N2TabDetail, {
    props: {
      wpId: 'wp-1',
      projectId: 'project-1',
      allResponses: new Map(),
    },
    global: {
      stubs: {
        'el-alert': true,
        'el-button': true,
        'el-card': true,
        'el-dropdown': true,
        'el-dropdown-item': true,
        'el-dropdown-menu': true,
        'el-icon': true,
        'el-input': true,
        'el-input-number': true,
        'el-tag': true,
        'el-table': { template: '<div><slot /></div>' },
        'el-table-column': { template: '<div />' },
      },
    },
  })
}

describe('N2 导入请求契约', () => {
  beforeEach(() => {
    mocks.post.mockReset()
    mocks.success.mockReset()
    mocks.error.mockReset()
    mocks.post.mockResolvedValue({ data: { imported_count: 1, warnings: [] } })
  })

  it('sheet 走 query 参数，multipart 只携带文件', async () => {
    const api = useN2ImportExport({ wpId: ref('wp-1'), projectId: ref('project-1') })
    const file = new File(['xlsx'], 'n2.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })

    const result = await api.importData(file, 'N2-2')

    expect(result).toMatchObject({ success: true, rowCount: 1 })
    expect(mocks.post).toHaveBeenCalledOnce()
    const [url, body, config] = mocks.post.mock.calls[0]
    expect(url).toBe('/api/n2-taxes-payable/wp-1/import-data')
    expect(config.params).toEqual({ sheet: 'N2-2' })
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('file')).toBe(file)
    expect(body.get('sheet')).toBeNull()
  })

  it('warnings 数组逐条显示并保留在回执中', async () => {
    mocks.post.mockResolvedValue({
      data: { imported_count: 2, warnings: ['超过 500 行，已截断', '忽略空白行'] },
    })
    const api = useN2ImportExport({ wpId: ref('wp-1'), projectId: ref('project-1') })
    const result = await api.importData(new File(['xlsx'], 'n2.xlsx'), 'N2-2')

    expect(result.warnings).toEqual(['超过 500 行，已截断', '忽略空白行'])
    expect(mocks.success).toHaveBeenCalledWith(
      '成功导入 2 行数据（超过 500 行，已截断；忽略空白行）',
    )
  })

  it('详情页仅在导入成功后发 imported，交由宿主读回唯一快照', async () => {
    const wrapper = mountDetail()
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [new File(['xlsx'], 'n2.xlsx')],
    })

    await input.trigger('change')
    await flushPromises()

    expect(wrapper.emitted('imported')).toHaveLength(1)
    wrapper.unmount()
  })

  it('详情页导入失败时不发 imported', async () => {
    mocks.post.mockRejectedValueOnce(new Error('导入失败'))
    const wrapper = mountDetail()
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [new File(['bad'], 'n2.xlsx')],
    })

    await input.trigger('change')
    await flushPromises()

    expect(wrapper.emitted('imported')).toBeUndefined()
    wrapper.unmount()
  })
})
