/**
 * AttachmentVersionsDialog 组件测试
 *
 * Validates: proposal-remaining-18 §三 AT-3，task 5.3
 *  - 加载并渲染版本列表（version 升序）
 *  - 当前最新版本不显示"回滚"按钮
 *  - 旧版本显示"回滚"按钮，点击调用 rollback 端点
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AttachmentVersionsDialog from '@/components/attachment/AttachmentVersionsDialog.vue'

// 必须 hoist 到 mock 调用之前
const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({
  api: apiMock,
  default: apiMock,
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

// 跳过 ElMessageBox.confirm 二次确认
vi.mock('element-plus', async () => {
  const real = await vi.importActual<any>('element-plus')
  return {
    ...real,
    ElMessageBox: {
      confirm: vi.fn().mockResolvedValue('confirm'),
    },
    ElMessage: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
  }
})

const stubs = {
  'el-dialog': {
    template:
      '<div class="el-dialog" v-if="modelValue !== false"><slot /><slot name="footer" /></div>',
    props: ['modelValue'],
  },
  'el-table': {
    template: `
      <div class="el-table">
        <div v-for="(row, idx) in data" :key="idx" class="el-table__row">
          <ElTableRowProvider :row="row">
            <slot />
          </ElTableRowProvider>
        </div>
      </div>
    `,
    props: ['data'],
    components: {
      ElTableRowProvider: {
        props: ['row'],
        provide(this: any) {
          return { __tableRow: () => this.row }
        },
        template: '<div class="el-table-row-wrap"><slot /></div>',
      },
    },
  },
  'el-table-column': {
    template: `<span class="el-table-column"><slot :row="getRow()" /></span>`,
    props: ['label', 'prop', 'width', 'minWidth'],
    inject: { __tableRow: { default: () => () => ({}) } },
    methods: {
      getRow(this: any): any {
        return this.__tableRow ? this.__tableRow() : {}
      },
    },
  },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-button': {
    template: '<button class="el-button" :data-type="$attrs.type" @click="$emit(\'click\')"><slot /></button>',
    emits: ['click'],
  },
  'el-empty': { template: '<div class="el-empty"><slot /></div>' },
}

const mkVersions = () => [
  {
    id: 'v1-id',
    version: 1,
    previous_version_id: null,
    file_name: '合同.pdf',
    file_size: 1024,
    file_type: 'pdf',
    storage_type: 'local',
    uploaded_by: 'user-aaaaaaa',
    uploaded_at: '2026-01-01T10:00:00',
    is_deleted: false,
  },
  {
    id: 'v2-id',
    version: 2,
    previous_version_id: 'v1-id',
    file_name: '合同.pdf',
    file_size: 2048,
    file_type: 'pdf',
    storage_type: 'local',
    uploaded_by: 'user-aaaaaaa',
    uploaded_at: '2026-01-02T10:00:00',
    is_deleted: false,
  },
  {
    id: 'v3-id',
    version: 3,
    previous_version_id: 'v2-id',
    file_name: '合同.pdf',
    file_size: 4096,
    file_type: 'pdf',
    storage_type: 'local',
    uploaded_by: 'user-bbbbbbb',
    uploaded_at: '2026-01-03T10:00:00',
    is_deleted: false,
  },
]

describe('AttachmentVersionsDialog — AT-3 历史版本列表 + 回滚', () => {
  beforeEach(() => {
    apiMock.get.mockReset()
    apiMock.post.mockReset()
  })

  function factory(props: Record<string, unknown> = {}) {
    return mount(AttachmentVersionsDialog, {
      props: {
        modelValue: true,
        attachmentId: 'v3-id',
        ...props,
      },
      global: { stubs },
    })
  }

  it('loads versions on mount and renders rows', async () => {
    apiMock.get.mockResolvedValueOnce({ versions: mkVersions() })
    const wrapper = factory()
    await flushPromises()

    expect(apiMock.get).toHaveBeenCalledWith('/api/attachments/v3-id/versions')
    const html = wrapper.html()
    expect(html).toContain('v1')
    expect(html).toContain('v2')
    expect(html).toContain('v3')
    // 文件大小渲染
    expect(html).toContain('1.0 KB')
    expect(html).toContain('2.0 KB')
  })

  it('hides rollback button on the latest version row', async () => {
    apiMock.get.mockResolvedValueOnce({ versions: mkVersions() })
    const wrapper = factory()
    await flushPromises()

    // v3 为最新版本，不应出现"回滚到此版本"按钮上
    // 我们计数：rollback 按钮总数应等于 totalVersions - 1 = 2
    const rollbackButtons = wrapper.findAll('button.el-button').filter((btn) =>
      btn.text().includes('回滚到此版本')
    )
    expect(rollbackButtons.length).toBe(2)
  })

  it('calls rollback endpoint with correct version id when clicking rollback', async () => {
    apiMock.get.mockResolvedValueOnce({ versions: mkVersions() })
    apiMock.post.mockResolvedValueOnce({
      id: 'v4-id',
      version: 4,
      previous_version_id: 'v3-id',
      file_name: '合同.pdf',
      file_size: 1024,
    })
    // 第二次 loadVersions（rollback 后刷新）
    apiMock.get.mockResolvedValueOnce({
      versions: [
        ...mkVersions(),
        {
          id: 'v4-id',
          version: 4,
          previous_version_id: 'v3-id',
          file_name: '合同.pdf',
          file_size: 1024,
          file_type: 'pdf',
          storage_type: 'local',
          uploaded_by: null,
          uploaded_at: '2026-01-04T10:00:00',
          is_deleted: false,
        },
      ],
    })

    const wrapper = factory()
    await flushPromises()

    // 点击第一个"回滚到此版本"按钮（应该是 v1）
    const rollbackButtons = wrapper
      .findAll('button.el-button')
      .filter((btn) => btn.text().includes('回滚到此版本'))
    expect(rollbackButtons.length).toBe(2)
    await rollbackButtons[0].trigger('click')
    await flushPromises()

    expect(apiMock.post).toHaveBeenCalled()
    const callArgs = apiMock.post.mock.calls[0]
    // URL 应包含 attachment id 和 v1 版本 id（端点：/versions/{vid}/rollback）
    expect(callArgs[0]).toBe('/api/attachments/v3-id/versions/v1-id/rollback')
  })

  it('emits rolled-back event after successful rollback', async () => {
    apiMock.get.mockResolvedValueOnce({ versions: mkVersions() })
    apiMock.post.mockResolvedValueOnce({ id: 'v4-id', version: 4 })
    apiMock.get.mockResolvedValueOnce({ versions: mkVersions() })

    const wrapper = factory()
    await flushPromises()

    const rollbackButtons = wrapper
      .findAll('button.el-button')
      .filter((btn) => btn.text().includes('回滚到此版本'))
    await rollbackButtons[0].trigger('click')
    await flushPromises()

    expect(wrapper.emitted('rolled-back')).toBeTruthy()
    expect(wrapper.emitted('rolled-back')?.[0]).toEqual([{ newVersion: { id: 'v4-id', version: 4 } }])
  })

  it('emits preview event when preview button clicked', async () => {
    apiMock.get.mockResolvedValueOnce({ versions: mkVersions() })
    const wrapper = factory()
    await flushPromises()

    const previewButtons = wrapper
      .findAll('button.el-button')
      .filter((btn) => btn.text().includes('预览'))
    expect(previewButtons.length).toBe(3)
    await previewButtons[0].trigger('click')
    await flushPromises()

    expect(wrapper.emitted('preview')).toBeTruthy()
    expect(wrapper.emitted('preview')?.[0]?.[0]).toMatchObject({ id: 'v1-id', version: 1 })
  })

  it('renders empty state when no versions', async () => {
    apiMock.get.mockResolvedValueOnce({ versions: [] })
    const wrapper = factory()
    await flushPromises()
    expect(wrapper.html()).toContain('暂无版本记录')
  })
})
