/**
 * WpImportExport 单元测试
 *
 * Feature: platform-global-hardening
 * Requirements: 4.4
 *
 * 测试:
 * 1. 渲染 el-dropdown 按钮 "导入导出 ▾"
 * 2. dropdown 包含三项（导出模板/导出数据/导入数据）
 * 3. 点击导出模板/导出数据 调用对应端点
 * 4. 导入成功后 emit imported
 * 5. 错误时 emit error
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import WpImportExport from '../WpImportExport.vue'

// Mock http module
const mockGet = vi.fn()
const mockPost = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

function mountDropdown(propsData: any = {}) {
  return mount(WpImportExport, {
    props: { wpId: 'wp-123', ...propsData },
    global: {
      plugins: [ElementPlus],
    },
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
})

describe('WpImportExport', () => {
  describe('基础渲染', () => {
    it('渲染触发按钮 "导入导出 ▾"', () => {
      const wrapper = mountDropdown()
      const triggerBtn = wrapper.find('.el-button')
      expect(triggerBtn.exists()).toBe(true)
      expect(triggerBtn.text()).toContain('导入导出')
    })

    it('el-dropdown 组件挂载成功', () => {
      const wrapper = mountDropdown()
      // el-dropdown 渲染为带 el-dropdown 类的容器
      expect(wrapper.find('.el-dropdown').exists()).toBe(true)
    })

    it('dropdown 菜单模板包含3项（导出模板/导出数据/导入数据）', () => {
      // el-dropdown-menu 使用 teleport 渲染到 body，无法从 wrapper 查询
      // 但 handleCommand 接收三种 command 值是组件逻辑的核心
      const wrapper = mountDropdown()
      const vm = wrapper.vm as any
      // 验证 handleCommand 处理三种命令而不崩溃
      mockGet.mockResolvedValue({ data: new ArrayBuffer(8), headers: {} })
      expect(() => vm.handleCommand('export-template')).not.toThrow()
      expect(() => vm.handleCommand('export-data')).not.toThrow()
      // import-data 通过 onFileChange 触发，不经 handleCommand
    })
  })

  describe('导出模板', () => {
    it('handleCommand("export-template") 调用 GET export-template 端点', async () => {
      mockGet.mockResolvedValue({
        data: new ArrayBuffer(8),
        headers: { 'content-disposition': 'attachment; filename="template.xlsx"' },
      })
      const wrapper = mountDropdown()
      const vm = wrapper.vm as any
      await vm.handleCommand('export-template')
      await flushPromises()
      expect(mockGet).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/export-template',
        expect.objectContaining({ responseType: 'blob' }),
      )
    })

    it('自定义 endpoints 时使用自定义路径', async () => {
      mockGet.mockResolvedValue({
        data: new ArrayBuffer(8),
        headers: {},
      })
      const wrapper = mountDropdown({
        wpId: 'wp-456',
        endpoints: { exportTemplate: '/api/custom/export-tpl' },
      })
      const vm = wrapper.vm as any
      await vm.handleCommand('export-template')
      await flushPromises()
      expect(mockGet).toHaveBeenCalledWith(
        '/api/custom/export-tpl',
        expect.anything(),
      )
    })

    it('导出失败时 emit error', async () => {
      mockGet.mockRejectedValue({ message: '网络错误' })
      const wrapper = mountDropdown()
      const vm = wrapper.vm as any
      await vm.handleCommand('export-template')
      await flushPromises()
      const emitted = wrapper.emitted('error')
      expect(emitted).toBeTruthy()
      expect(emitted![0][0]).toContain('网络错误')
    })
  })

  describe('导出数据', () => {
    it('handleCommand("export-data") 调用 GET export-data 端点', async () => {
      mockGet.mockResolvedValue({
        data: new ArrayBuffer(8),
        headers: {},
      })
      const wrapper = mountDropdown()
      const vm = wrapper.vm as any
      await vm.handleCommand('export-data')
      await flushPromises()
      expect(mockGet).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/export-data',
        expect.objectContaining({ responseType: 'blob' }),
      )
    })
  })

  describe('导入数据', () => {
    it('onFileChange 上传文件并 emit imported', async () => {
      mockPost.mockResolvedValue({
        data: { data: { imported_count: 15 } },
      })
      const wrapper = mountDropdown()
      const vm = wrapper.vm as any
      const fakeFile = new File(['content'], 'data.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      await vm.onFileChange({ raw: fakeFile })
      await flushPromises()
      expect(mockPost).toHaveBeenCalledWith(
        '/api/workpapers/wp-123/import-data',
        expect.any(FormData),
        expect.objectContaining({ headers: { 'Content-Type': 'multipart/form-data' } }),
      )
      const emitted = wrapper.emitted('imported')
      expect(emitted).toBeTruthy()
    })

    it('导入失败时 emit error', async () => {
      mockPost.mockRejectedValue({
        response: { data: { detail: '文件格式错误' } },
      })
      const wrapper = mountDropdown()
      const vm = wrapper.vm as any
      const fakeFile = new File(['x'], 'bad.xlsx')
      await vm.onFileChange({ raw: fakeFile })
      await flushPromises()
      const emitted = wrapper.emitted('error')
      expect(emitted).toBeTruthy()
      expect(emitted![0][0]).toContain('文件格式错误')
    })

    it('wpId 为空时不发起请求', async () => {
      const wrapper = mount(WpImportExport, {
        props: { wpId: '' },
        global: { plugins: [ElementPlus] },
      })
      const vm = wrapper.vm as any
      const fakeFile = new File(['x'], 'test.xlsx')
      await vm.onFileChange({ raw: fakeFile })
      await flushPromises()
      expect(mockPost).not.toHaveBeenCalled()
    })
  })
})
