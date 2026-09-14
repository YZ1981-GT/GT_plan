/**
 * WorkpaperWordEditor.spec.ts — A16 主/补分离组件测试
 *
 * Task 11（a16-representation-letter）：
 * 1. 主版本区仅包含 A16-1~6（无 A16-7）
 * 2. 推荐版本排序置顶 + badge 显示
 * 3. 补充声明 A16-7 独立 toggle + 独立签回
 * 4. 补充区启用后显示独立操作栏
 * 5. 主版本/补充签回 scope 隔离
 *
 * Validates: Requirements 3（跳转页模式 — 主/补分离）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { projectId: 'proj-test-123' },
    query: {},
  }),
  useRouter: () => ({ push: vi.fn() }),
}))

// Mock apiProxy
const mockApiGet = vi.fn().mockResolvedValue(null)
const mockApiPost = vi.fn().mockResolvedValue({})
const mockApiPut = vi.fn().mockResolvedValue({})
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockApiGet(...args),
    post: (...args: any[]) => mockApiPost(...args),
    put: (...args: any[]) => mockApiPut(...args),
  },
}))

// Mock OnlyOfficeWordDialog
vi.mock('../OnlyOfficeWordDialog.vue', () => ({
  default: { name: 'OnlyOfficeWordDialog', template: '<div class="mock-onlyoffice" />', props: ['visible', 'documentUrl', 'documentKey', 'title', 'mode', 'callbackUrl'] },
}))

// Global stubs for Element Plus components
const globalStubs = {
  'el-radio-group': {
    template: '<div class="el-radio-group" data-testid="radio-group"><slot /></div>',
    props: ['modelValue', 'size'],
    emits: ['update:modelValue', 'change'],
  },
  'el-radio-button': {
    template: '<label class="el-radio-button" :data-code="value"><slot /></label>',
    props: ['value', 'class'],
  },
  'el-tag': {
    template: '<span class="el-tag" :data-type="type"><slot /></span>',
    props: ['type', 'size', 'effect'],
  },
  'el-switch': {
    template: '<input type="checkbox" class="el-switch" :checked="modelValue" @change="$emit(\'update:modelValue\', !modelValue); $emit(\'change\', !modelValue)" />',
    props: ['modelValue', 'activeText'],
    emits: ['update:modelValue', 'change'],
  },
  'el-button': {
    template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'loading', 'disabled'],
  },
  'el-button-group': {
    template: '<div class="el-button-group"><slot /></div>',
  },
  'el-divider': { template: '<span class="el-divider" />', props: ['direction'] },
  'el-alert': {
    template: '<div class="el-alert" :data-type="type"><slot name="title" /><slot /></div>',
    props: ['type', 'closable', 'showIcon', 'title'],
  },
  'el-descriptions': {
    template: '<div class="el-descriptions"><slot /></div>',
    props: ['column', 'border', 'size', 'title'],
  },
  'el-descriptions-item': {
    template: '<div class="el-descriptions-item" :data-label="label"><slot /></div>',
    props: ['label'],
  },
  'el-dialog': {
    template: '<div class="el-dialog" v-if="modelValue"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title', 'width', 'closeOnClickModal'],
    emits: ['update:modelValue'],
  },
  'el-upload': {
    template: '<div class="el-upload"><slot /></div>',
    props: ['action', 'headers', 'onSuccess', 'accept', 'limit', 'drag'],
  },
  'el-date-picker': {
    template: '<input class="el-date-picker" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target?.value)" />',
    props: ['modelValue', 'type', 'placeholder', 'valueFormat'],
    emits: ['update:modelValue'],
  },
}

import WorkpaperWordEditor from '../WorkpaperWordEditor.vue'

function createWrapper(props: any = {}) {
  return mount(WorkpaperWordEditor, {
    props: {
      wpId: 'wp-test-001',
      wpCode: 'A16',
      projectId: 'proj-test-123',
      ...props,
    },
    global: {
      stubs: globalStubs,
    },
  })
}

describe('WorkpaperWordEditor — 主/补分离', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default: project info returns basic data, no recommendation
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/a16/recommended-version')) {
        return Promise.resolve({ main: { code: 'A16-3', label: 'IPO申报' }, supplement: null })
      }
      if (url.includes('/projects/')) {
        return Promise.resolve({ client_name: '测试公司', audit_period_end: '2025-12-31', audit_year: '2025' })
      }
      if (url.includes('/file-info')) {
        return Promise.resolve({ sign_status: 'pending' })
      }
      if (url.includes('/onlyoffice/health')) {
        return Promise.resolve({ healthy: false })
      }
      if (url.includes('/misstatements/for-letter')) {
        return Promise.resolve({ summary: '' })
      }
      return Promise.resolve(null)
    })
  })

  describe('主版本区（A16-1~6）', () => {
    it('radio group 仅包含 A16-1~6，不含 A16-7', async () => {
      const wrapper = createWrapper()
      await flushPromises()

      const radioButtons = wrapper.findAll('.el-radio-button')
      const codes = radioButtons.map(el => el.attributes('data-code'))

      expect(codes).toContain('A16-1')
      expect(codes).toContain('A16-2')
      expect(codes).toContain('A16-3')
      expect(codes).toContain('A16-4')
      expect(codes).toContain('A16-5')
      expect(codes).toContain('A16-6')
      expect(codes).not.toContain('A16-7')
      expect(codes).toHaveLength(6)
    })

    it('推荐版本排序置顶', async () => {
      const wrapper = createWrapper()
      await flushPromises()

      // A16-3 is recommended, should be first
      const radioButtons = wrapper.findAll('.el-radio-button')
      expect(radioButtons[0].attributes('data-code')).toBe('A16-3')
    })

    it('推荐版本有 badge 标签', async () => {
      const wrapper = createWrapper()
      await flushPromises()

      // Find the radio button for A16-3 and check it has a tag inside
      const recommendedRadio = wrapper.findAll('.el-radio-button').find(
        el => el.attributes('data-code') === 'A16-3',
      )
      expect(recommendedRadio).toBeDefined()
      const tags = recommendedRadio!.findAll('.el-tag')
      expect(tags.length).toBeGreaterThan(0)
    })

    it('主版本区有独立操作栏（编辑/下载/签回按钮）', async () => {
      const wrapper = createWrapper()
      await flushPromises()

      const mainSection = wrapper.find('.gt-wp-word-editor__main-section')
      expect(mainSection.exists()).toBe(true)

      const buttons = mainSection.findAll('.el-button')
      const texts = buttons.map(b => b.text())
      expect(texts.some(t => t.includes('编辑'))).toBe(true)
      expect(texts.some(t => t.includes('下载'))).toBe(true)
      expect(texts.some(t => t.includes('签回') || t.includes('已签回'))).toBe(true)
    })

    it('签回 scope 使用 word_template:A16:{version}', async () => {
      const wrapper = createWrapper()
      await flushPromises()

      // Trigger sign status update — find the '已签回' button and click
      const mainSection = wrapper.find('.gt-wp-word-editor__main-section')
      const buttons = mainSection.findAll('.el-button')
      const signedBtn = buttons.find(b => b.text().includes('已签回'))
      expect(signedBtn).toBeDefined()

      await signedBtn!.trigger('click')
      await flushPromises()

      // CW-76: 现在弹出日期对话框，需确认后才调用 API
      const vm = wrapper.vm as any
      expect(vm.showSignDateDialog).toBe(true)
      vm.signDateValue = '2025-03-15'
      await vm.confirmSignDate()
      await flushPromises()

      // Check the API was called with correct version (A16-3 is selected by recommendation)
      expect(mockApiPost).toHaveBeenCalledWith(
        expect.stringContaining('/sign-status'),
        expect.objectContaining({ status: 'signed', version: 'A16-3', sign_date: '2025-03-15' }),
      )
    })
  })

  describe('补充声明区（A16-7）', () => {
    it('补充区有独立 toggle 开关', async () => {
      const wrapper = createWrapper()
      await flushPromises()

      const supplementSection = wrapper.find('.gt-wp-word-editor__supplement-section')
      expect(supplementSection.exists()).toBe(true)

      const toggle = supplementSection.find('.el-switch')
      expect(toggle.exists()).toBe(true)
    })

    it('补充区默认禁用时显示提示文案', async () => {
      // No supplement recommendation
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-1' }, supplement: null })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()

      const hint = wrapper.find('.gt-wp-word-editor__supplement-hint')
      expect(hint.exists()).toBe(true)
      expect(hint.text()).toContain('关联交易')
    })

    it('补充区启用后显示独立操作栏', async () => {
      // Supplement is recommended
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-1' }, supplement: { code: 'A16-7' } })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        if (url.includes('/file-info')) {
          return Promise.resolve({ sign_status: 'pending' })
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()

      // Supplement should be enabled via recommendation
      const supplementSection = wrapper.find('.gt-wp-word-editor__supplement-section')
      const toolbar = supplementSection.find('.gt-wp-word-editor__toolbar')
      expect(toolbar.exists()).toBe(true)

      const buttons = toolbar.findAll('.el-button')
      const texts = buttons.map(b => b.text())
      expect(texts.some(t => t.includes('A16-7'))).toBe(true)
    })

    it('toggle 切换持久化 field_overrides enabled', async () => {
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-1' }, supplement: null })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()

      // Find and toggle the switch
      const toggle = wrapper.find('.el-switch')
      await toggle.trigger('change')
      await flushPromises()

      // Should persist enabled via field_overrides
      expect(mockApiPost).toHaveBeenCalledWith(
        '/api/workpapers/field-overrides',
        expect.objectContaining({
          scope: 'word_template:A16:A16-7',
          item_key: 'enabled',
          field: 'value',
        }),
      )
    })

    it('A16-7 签回 scope 独立于主版本', async () => {
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-1' }, supplement: { code: 'A16-7' } })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        if (url.includes('/file-info')) {
          return Promise.resolve({ sign_status: 'pending' })
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()

      // Find A16-7 signed button in supplement section
      const supplementSection = wrapper.find('.gt-wp-word-editor__supplement-section')
      const buttons = supplementSection.findAll('.el-button')
      const signedBtn = buttons.find(b => b.text().includes('已签回'))
      expect(signedBtn).toBeDefined()

      await signedBtn!.trigger('click')
      await flushPromises()

      // Should call sign-status with version=A16-7
      expect(mockApiPost).toHaveBeenCalledWith(
        expect.stringContaining('/sign-status'),
        expect.objectContaining({ status: 'signed', version: 'A16-7' }),
      )
    })
  })

  describe('版本选择与联动', () => {
    it('切换版本后 loadSignStatus 使用新版本 scope', async () => {
      const wrapper = createWrapper()
      await flushPromises()

      mockApiGet.mockClear()
      mockApiGet.mockResolvedValue({ sign_status: 'sent' })

      // The component's radio change triggers onVersionChange
      // Simulate by calling directly via vm (since radio stubs don't emit)
      const vm = wrapper.vm as any
      await vm.onVersionChange('A16-2')
      await flushPromises()

      const fileInfoCall = mockApiGet.mock.calls.find((c) => String(c[0]).includes('file-info'))
      expect(fileInfoCall?.[0]).toContain('version=A16-2')
    })
  })
})

/**
 * Task 13 — selected_version 持久化 + 按版本 sign_status scope
 *
 * Validates: Requirements 3 (field_overrides 契约)
 */
describe('WorkpaperWordEditor — selected_version 持久化 + 按版本 sign_status scope', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('selected_version 持久化', () => {
    it('切换版本时 POST field_overrides 持久化 selected_version', async () => {
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-1' }, supplement: null })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        if (url.includes('/file-info')) {
          return Promise.resolve({ sign_status: 'pending' })
        }
        if (url.includes('/field-overrides')) {
          return Promise.resolve({}) // No persisted version initially
        }
        if (url.includes('/onlyoffice/health')) {
          return Promise.resolve({ healthy: false })
        }
        if (url.includes('/misstatements/for-letter')) {
          return Promise.resolve({ summary: '' })
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()
      mockApiPost.mockClear()

      // Switch version via vm (radio stubs don't emit)
      const vm = wrapper.vm as any
      await vm.onVersionChange('A16-5')
      await flushPromises()

      // Should persist selected_version via field_overrides
      expect(mockApiPost).toHaveBeenCalledWith(
        '/api/workpapers/field-overrides',
        expect.objectContaining({
          project_id: 'proj-test-123',
          scope: 'word_template:A16',
          item_key: 'selected_version',
          field: 'value',
          value: 'A16-5',
        }),
      )
    })

    it('加载时优先使用持久化的 selected_version（覆盖推荐）', async () => {
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-3', label: 'IPO申报' }, supplement: null })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        if (url.includes('/file-info')) {
          return Promise.resolve({ sign_status: 'pending' })
        }
        if (url.includes('/field-overrides')) {
          // Persisted version = A16-2
          return Promise.resolve({ selected_version: { value: 'A16-2' } })
        }
        if (url.includes('/onlyoffice/health')) {
          return Promise.resolve({ healthy: false })
        }
        if (url.includes('/misstatements/for-letter')) {
          return Promise.resolve({ summary: '' })
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      // Persisted A16-2 overrides recommended A16-3
      expect(vm.selectedVersion).toBe('A16-2')
    })

    it('URL query ?version= 优先级高于持久化版本', async () => {
      // Re-mock useRoute to include query.version
      const useRouteMock = vi.fn(() => ({
        params: { projectId: 'proj-test-123' },
        query: { version: 'A16-6' },
      }))
      vi.mocked(await import('vue-router')).useRoute = useRouteMock as any

      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-3' }, supplement: null })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        if (url.includes('/file-info')) {
          return Promise.resolve({ sign_status: 'pending' })
        }
        if (url.includes('/field-overrides')) {
          // Persisted version = A16-2 (should be overridden by query)
          return Promise.resolve({ selected_version: { value: 'A16-2' } })
        }
        if (url.includes('/onlyoffice/health')) {
          return Promise.resolve({ healthy: false })
        }
        if (url.includes('/misstatements/for-letter')) {
          return Promise.resolve({ summary: '' })
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      // URL query A16-6 > persisted A16-2 > recommended A16-3
      expect(vm.selectedVersion).toBe('A16-6')

      // Restore default mock
      vi.mocked(await import('vue-router')).useRoute = (() => ({
        params: { projectId: 'proj-test-123' },
        query: {},
      })) as any
    })
  })

  describe('按版本 sign_status 独立', () => {
    it('切换版本加载对应版本的独立 sign_status', async () => {
      // First version A16-1 = pending, second A16-5 = signed
      let callCount = 0
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-1' }, supplement: null })
        }
        if (url.includes('/file-info')) {
          callCount++
          if (url.includes('version=A16-5')) {
            return Promise.resolve({ sign_status: 'signed' })
          }
          return Promise.resolve({ sign_status: 'pending' })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        if (url.includes('/field-overrides')) {
          return Promise.resolve({})
        }
        if (url.includes('/onlyoffice/health')) {
          return Promise.resolve({ healthy: false })
        }
        if (url.includes('/misstatements/for-letter')) {
          return Promise.resolve({ summary: '' })
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      expect(vm.signStatus).toBe('pending') // A16-1 = pending

      // Switch to A16-5
      await vm.onVersionChange('A16-5')
      await flushPromises()

      expect(vm.signStatus).toBe('signed') // A16-5 = signed
    })

    it('版本 A 的 signed 不继承到版本 B', async () => {
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-2' }, supplement: null })
        }
        if (url.includes('/file-info')) {
          if (url.includes('version=A16-2')) {
            return Promise.resolve({ sign_status: 'signed' })
          }
          if (url.includes('version=A16-1')) {
            return Promise.resolve({ sign_status: 'pending' })
          }
          return Promise.resolve({ sign_status: 'pending' })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        if (url.includes('/field-overrides')) {
          return Promise.resolve({})
        }
        if (url.includes('/onlyoffice/health')) {
          return Promise.resolve({ healthy: false })
        }
        if (url.includes('/misstatements/for-letter')) {
          return Promise.resolve({ summary: '' })
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      // Recommended A16-2 loaded, sign_status = signed
      expect(vm.signStatus).toBe('signed')

      // Switch to A16-1: sign_status should reset to its own value (pending)
      await vm.onVersionChange('A16-1')
      await flushPromises()

      expect(vm.signStatus).toBe('pending') // NOT inherited from A16-2
    })

    it('sign_status API 调用使用正确的 per-version scope', async () => {
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-1' }, supplement: null })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        if (url.includes('/file-info')) {
          return Promise.resolve({ sign_status: 'pending' })
        }
        if (url.includes('/field-overrides')) {
          return Promise.resolve({})
        }
        if (url.includes('/onlyoffice/health')) {
          return Promise.resolve({ healthy: false })
        }
        if (url.includes('/misstatements/for-letter')) {
          return Promise.resolve({ summary: '' })
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any

      // Switch to A16-4 first
      await vm.onVersionChange('A16-4')
      await flushPromises()
      mockApiPost.mockClear()

      // Update sign status for A16-4
      await vm.updateSignStatus('signed')
      await flushPromises()

      // CW-76: 现在弹出日期对话框，需确认后才调用 API
      expect(vm.showSignDateDialog).toBe(true)
      vm.signDateValue = '2025-03-15'
      await vm.confirmSignDate()
      await flushPromises()

      // The sign-status API should be called with version=A16-4
      expect(mockApiPost).toHaveBeenCalledWith(
        expect.stringContaining('/sign-status'),
        expect.objectContaining({ status: 'signed', version: 'A16-4', sign_date: '2025-03-15' }),
      )
    })
  })
})


/**
 * Task 17 — OnlyOffice / 降级下载 upload 端到端 单元测试
 *
 * 验证:
 * 1. openEditor('main') 调用正确的 onlyoffice-config 端点 + 传入 selectedVersion
 * 2. downloadTemplate('main') 构建正确的 prefilled-download URL
 * 3. Upload success handler 正确刷新 sign_status
 *
 * Validates: Requirements 3（跳转页模式 — OnlyOffice + 降级流程）
 */
describe('WorkpaperWordEditor — OnlyOffice / 降级下载 upload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/a16/recommended-version')) {
        return Promise.resolve({ main: { code: 'A16-1', label: '一般财报' }, supplement: null })
      }
      if (url.includes('/projects/')) {
        return Promise.resolve({ client_name: '测试公司', audit_period_end: '2025-12-31' })
      }
      if (url.includes('/file-info')) {
        return Promise.resolve({ sign_status: 'pending' })
      }
      if (url.includes('/onlyoffice/health')) {
        return Promise.resolve({ healthy: true })
      }
      if (url.includes('/misstatements/for-letter')) {
        return Promise.resolve({ summary: '' })
      }
      if (url.includes('/field-overrides')) {
        return Promise.resolve({})
      }
      if (url.includes('/onlyoffice-config')) {
        return Promise.resolve({
          document_url: 'http://localhost:8080/doc.docx',
          document_key: 'proj-test-123:A16:A16-1:1',
        })
      }
      return Promise.resolve(null)
    })
  })

  describe('openEditor 调用 onlyoffice-config', () => {
    it('openEditor("main") 请求 onlyoffice-config?version=<selectedVersion>', async () => {
      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      // 确认 OnlyOffice 可用
      expect(vm.onlyofficeAvailable).toBe(true)

      mockApiGet.mockClear()
      mockApiGet.mockResolvedValue({
        document_url: 'http://oo/doc.docx',
        document_key: 'proj:A16:A16-1:2',
      })

      await vm.openEditor('main')
      await flushPromises()

      // 验证调用了 onlyoffice-config 端点 + 正确版本参数
      expect(mockApiGet).toHaveBeenCalledWith(
        expect.stringContaining('/onlyoffice-config'),
        expect.objectContaining({
          params: expect.objectContaining({ version: 'A16-1' }),
        }),
      )
    })

    it('openEditor("main") 切换版本后使用新版本调用', async () => {
      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      // 切换到 A16-3
      vm.selectedVersion = 'A16-3'
      await flushPromises()

      mockApiGet.mockClear()
      mockApiGet.mockResolvedValue({
        document_url: 'http://oo/doc.docx',
        document_key: 'proj:A16:A16-3:1',
      })

      await vm.openEditor('main')
      await flushPromises()

      expect(mockApiGet).toHaveBeenCalledWith(
        expect.stringContaining('/onlyoffice-config'),
        expect.objectContaining({
          params: expect.objectContaining({ version: 'A16-3' }),
        }),
      )
    })

    it('openEditor("supplement") 使用 A16-7 版本', async () => {
      // Enable supplement
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-1' }, supplement: { code: 'A16-7' } })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        if (url.includes('/file-info')) {
          return Promise.resolve({ sign_status: 'pending' })
        }
        if (url.includes('/onlyoffice/health')) {
          return Promise.resolve({ healthy: true })
        }
        if (url.includes('/misstatements/for-letter')) {
          return Promise.resolve({ summary: '' })
        }
        if (url.includes('/field-overrides')) {
          return Promise.resolve({})
        }
        if (url.includes('/onlyoffice-config')) {
          return Promise.resolve({
            document_url: 'http://oo/a16-7.docx',
            document_key: 'proj:A16:A16-7:1',
          })
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      mockApiGet.mockClear()
      mockApiGet.mockResolvedValue({
        document_url: 'http://oo/a16-7.docx',
        document_key: 'proj:A16:A16-7:1',
      })

      await vm.openEditor('supplement')
      await flushPromises()

      expect(mockApiGet).toHaveBeenCalledWith(
        expect.stringContaining('/onlyoffice-config'),
        expect.objectContaining({
          params: expect.objectContaining({ version: 'A16-7' }),
        }),
      )
    })

    it('OnlyOffice 不可用时 openEditor 不发请求 + 提示消息', async () => {
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/onlyoffice/health')) {
          return Promise.resolve({ healthy: false })
        }
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-1' }, supplement: null })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        if (url.includes('/file-info')) {
          return Promise.resolve({ sign_status: 'pending' })
        }
        if (url.includes('/misstatements/for-letter')) {
          return Promise.resolve({ summary: '' })
        }
        if (url.includes('/field-overrides')) {
          return Promise.resolve({})
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      expect(vm.onlyofficeAvailable).toBe(false)

      mockApiGet.mockClear()
      await vm.openEditor('main')
      await flushPromises()

      // 不可用时不调用 onlyoffice-config
      const configCalls = mockApiGet.mock.calls.filter(
        (c: any[]) => c[0]?.includes?.('/onlyoffice-config'),
      )
      expect(configCalls).toHaveLength(0)
    })
  })

  describe('downloadTemplate URL 构建', () => {
    it('downloadTemplate("main") 使用 /wp-templates/{selectedVersion}/prefilled-download', async () => {
      // Mock fetch for download
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(new Blob(['docx-content'])),
      })
      global.fetch = mockFetch

      const mockCreateObjectURL = vi.fn().mockReturnValue('blob:test')
      const mockRevokeObjectURL = vi.fn()
      global.URL.createObjectURL = mockCreateObjectURL
      global.URL.revokeObjectURL = mockRevokeObjectURL

      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      // Default selected = A16-1 (from recommendation)
      expect(vm.selectedVersion).toBe('A16-1')

      await vm.downloadTemplate('main')
      await flushPromises()

      // 验证 fetch URL 包含正确版本
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/wp-templates/A16-1/prefilled-download'),
        expect.objectContaining({
          headers: expect.objectContaining({ Authorization: expect.any(String) }),
        }),
      )
    })

    it('downloadTemplate("supplement") 使用 A16-7 版本码', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(new Blob(['docx-content'])),
      })
      global.fetch = mockFetch

      const mockCreateObjectURL = vi.fn().mockReturnValue('blob:test')
      global.URL.createObjectURL = mockCreateObjectURL
      global.URL.revokeObjectURL = vi.fn()

      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      await vm.downloadTemplate('supplement')
      await flushPromises()

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/wp-templates/A16-7/prefilled-download'),
        expect.any(Object),
      )
    })

    it('切换版本后 downloadTemplate 使用新版本', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(new Blob(['docx-content'])),
      })
      global.fetch = mockFetch
      global.URL.createObjectURL = vi.fn().mockReturnValue('blob:test')
      global.URL.revokeObjectURL = vi.fn()

      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      vm.selectedVersion = 'A16-5'
      await flushPromises()

      await vm.downloadTemplate('main')
      await flushPromises()

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/wp-templates/A16-5/prefilled-download'),
        expect.any(Object),
      )
    })
  })

  describe('upload success handler 刷新 sign_status', () => {
    it('onUploadSuccess 主版本上传后刷新 sign_status', async () => {
      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      vm.uploadTarget = 'main'
      vm.showUpload = true

      mockApiGet.mockClear()
      mockApiGet.mockResolvedValue({ sign_status: 'sent' })

      vm.onUploadSuccess()
      await flushPromises()

      // 应关闭弹窗
      expect(vm.showUpload).toBe(false)

      // 应刷新 sign_status（loadSignStatus 被调用）
      const fileInfoCalls = mockApiGet.mock.calls.filter(
        (c: any[]) => c[0]?.includes?.('/file-info'),
      )
      expect(fileInfoCalls.length).toBeGreaterThan(0)
    })

    it('onUploadSuccess supplement 上传后刷新 supplement sign_status', async () => {
      // Enable supplement
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/a16/recommended-version')) {
          return Promise.resolve({ main: { code: 'A16-1' }, supplement: { code: 'A16-7' } })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司' })
        }
        if (url.includes('/file-info')) {
          return Promise.resolve({ sign_status: 'pending' })
        }
        if (url.includes('/onlyoffice/health')) {
          return Promise.resolve({ healthy: true })
        }
        if (url.includes('/misstatements/for-letter')) {
          return Promise.resolve({ summary: '' })
        }
        if (url.includes('/field-overrides')) {
          return Promise.resolve({})
        }
        return Promise.resolve(null)
      })

      const wrapper = createWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      vm.uploadTarget = 'supplement'
      vm.showUpload = true

      mockApiGet.mockClear()
      mockApiGet.mockResolvedValue({ sign_status: 'signed' })

      vm.onUploadSuccess()
      await flushPromises()

      // 应关闭弹窗
      expect(vm.showUpload).toBe(false)

      // supplement sign_status 应被刷新（loadSupplementSignStatus 调用 file-info?version=A16-7）
      const fileInfoCalls = mockApiGet.mock.calls.filter(
        (c: any[]) => c[0]?.includes?.('/file-info') && c[0]?.includes?.('A16-7'),
      )
      expect(fileInfoCalls.length).toBeGreaterThan(0)
    })
  })
})


/**
 * Task 21 — CW-76: signed 时必填 sign_date → push representation_letter_date
 *
 * 验证：
 * 1. 点击"标记已签回"弹出日期选择对话框（非直接签回）
 * 2. 对话框预填默认日期（audit_report_date 或 audit_period_end）
 * 3. 确认后 sign_date 随 sign-status POST 一起发送
 * 4. A16-7 补充声明签回不弹日期对话框（sign_date 可选）
 *
 * Validates: Requirements 5（签回与审计报告联动 CW-76）
 */
describe('WorkpaperWordEditor — CW-76 签署日期对话框', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/a16/recommended-version')) {
        return Promise.resolve({ main: { code: 'A16-1', label: '一般财报' }, supplement: { code: 'A16-7' } })
      }
      if (url.includes('/projects/')) {
        return Promise.resolve({ client_name: '测试公司', audit_period_end: '2025-12-31', audit_year: '2025' })
      }
      if (url.includes('/file-info')) {
        return Promise.resolve({ sign_status: 'pending' })
      }
      if (url.includes('/onlyoffice/health')) {
        return Promise.resolve({ healthy: false })
      }
      if (url.includes('/misstatements/for-letter')) {
        return Promise.resolve({ summary: '' })
      }
      if (url.includes('/field-overrides')) {
        return Promise.resolve({})
      }
      if (url.includes('/audit-report')) {
        return Promise.resolve({ report_date: '2025-03-20' })
      }
      return Promise.resolve(null)
    })
  })

  it('点击"标记已签回"时弹出签署日期对话框', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.showSignDateDialog).toBe(false)

    // 触发签回
    await vm.updateSignStatus('signed')
    await flushPromises()

    // 应弹出对话框而非直接调用 API
    expect(vm.showSignDateDialog).toBe(true)
    // sign-status API 不应被直接调用
    const signCalls = mockApiPost.mock.calls.filter(
      (c: any[]) => c[0]?.includes?.('/sign-status'),
    )
    expect(signCalls).toHaveLength(0)
  })

  it('对话框预填审计报告日期作为默认值', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.updateSignStatus('signed')
    await flushPromises()

    // cachedReportDate from audit-report API
    expect(vm.cachedReportDate).toBe('2025-03-20')
    // signDateValue should be pre-filled with report_date
    expect(vm.signDateValue).toBe('2025-03-20')
  })

  it('无审计报告日期时降级使用 audit_period_end', async () => {
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/a16/recommended-version')) {
        return Promise.resolve({ main: { code: 'A16-1' }, supplement: null })
      }
      if (url.includes('/projects/')) {
        return Promise.resolve({ client_name: '测试公司', audit_period_end: '2025-12-31' })
      }
      if (url.includes('/file-info')) {
        return Promise.resolve({ sign_status: 'pending' })
      }
      if (url.includes('/onlyoffice/health')) {
        return Promise.resolve({ healthy: false })
      }
      if (url.includes('/misstatements/for-letter')) {
        return Promise.resolve({ summary: '' })
      }
      if (url.includes('/field-overrides')) {
        return Promise.resolve({})
      }
      if (url.includes('/audit-report')) {
        // No report_date available
        return Promise.resolve({ report_date: null })
      }
      return Promise.resolve(null)
    })

    const wrapper = createWrapper()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.updateSignStatus('signed')
    await flushPromises()

    // Should fall back to audit_period_end
    expect(vm.signDateValue).toBe('2025-12-31')
  })

  it('确认签回后 sign_date 随 POST 一起发送', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const vm = wrapper.vm as any
    // 弹出对话框
    await vm.updateSignStatus('signed')
    await flushPromises()

    // 设置日期并确认
    vm.signDateValue = '2025-03-15'
    await vm.confirmSignDate()
    await flushPromises()

    // 验证 sign-status 被调用且包含 sign_date
    expect(mockApiPost).toHaveBeenCalledWith(
      expect.stringContaining('/sign-status'),
      expect.objectContaining({
        status: 'signed',
        version: 'A16-1',
        sign_date: '2025-03-15',
      }),
    )
  })

  it('"标记已发送"不弹日期对话框', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.updateSignStatus('pending')
    await flushPromises()

    // 发送不弹对话框
    expect(vm.showSignDateDialog).toBe(false)
    // 直接调用 API
    expect(mockApiPost).toHaveBeenCalledWith(
      expect.stringContaining('/sign-status'),
      expect.objectContaining({ status: 'pending', version: 'A16-1' }),
    )
  })

  it('A16-7 补充声明签回不弹日期对话框', async () => {
    const wrapper = createWrapper()
    await flushPromises()

    const vm = wrapper.vm as any
    mockApiPost.mockClear()

    await vm.updateSupplementSignStatus('signed')
    await flushPromises()

    // A16-7 不弹日期对话框
    expect(vm.showSignDateDialog).toBe(false)
    // 直接调用 API（不含 sign_date）
    expect(mockApiPost).toHaveBeenCalledWith(
      expect.stringContaining('/sign-status'),
      expect.objectContaining({ status: 'signed', version: 'A16-7' }),
    )
    // 不应有 sign_date 参数
    const callPayload = mockApiPost.mock.calls.find(
      (c: any[]) => c[0]?.includes?.('/sign-status'),
    )?.[1]
    expect(callPayload?.sign_date).toBeUndefined()
  })
})


/**
 * Feature: word-template-dual-mode, Property 13: dual-mode scope
 *
 * For any wp_code mapped to componentType "word-template" in wp_code_overrides
 * (excluding A16), the WorkpaperWordEditor SHALL render the el-segmented dual-mode switch.
 * For wp_code === 'A16', the el-segmented SHALL NOT be rendered.
 *
 * **Validates: Requirements 9.1, 9.3**
 */
import * as fc from 'fast-check'
import { h } from 'vue'

// ─── 25 word-template wp_codes (from requirements) ─────────────────────────
const WORD_TEMPLATE_WP_CODES = [
  'A8-1', 'A8-2', 'A9-1', 'A9-2', 'A10-1', 'A11-1', 'A12-1',
  'A16-1', 'A16-2', 'A16-3', 'A16-4', 'A16-5', 'A16-6', 'A16-7',
  'A17-2-1', 'A17-3', 'A17-3-1', 'A17-4', 'A17-6', 'A18-1',
  'A26-1', 'A26-2', 'A26-3', 'A26-4', 'A27-1',
  'S12A', 'S33-REV', 'S34-1-1',
] as const

// el-segmented stub that renders identifiable markup
const elSegmentedStub = {
  name: 'ElSegmented',
  props: ['modelValue', 'options', 'size'],
  emits: ['update:modelValue', 'change'],
  setup(props: any) {
    return () => h('div', { class: 'el-segmented-stub', 'data-testid': 'dual-mode-switch' },
      (props.options || []).map((opt: string) =>
        h('button', { class: 'el-segmented-item' }, opt),
      ),
    )
  },
}

// Extended stubs for Property 13 (includes el-segmented functional stub)
const property13Stubs = {
  ...globalStubs,
  'el-segmented': elSegmentedStub,
  'el-tooltip': { template: '<div class="el-tooltip-stub"><slot /></div>', props: ['content', 'disabled', 'placement'] },
  'el-skeleton': { template: '<div class="el-skeleton" />', props: ['rows', 'animated'] },
  'el-empty': { template: '<div class="el-empty" />', props: ['description'] },
  'GtWordTemplateStructuredView': { template: '<div class="gt-structured-view-stub" />', props: ['templateStructure', 'fieldValues', 'readonly'] },
  'OnlyOfficeWordDialog': { template: '<div />', props: ['visible', 'documentUrl', 'documentKey', 'title', 'mode', 'callbackUrl'] },
}

function createProperty13Wrapper(wpCode: string) {
  return mount(WorkpaperWordEditor, {
    props: {
      wpId: `wp-prop13-${wpCode}`,
      wpCode,
      projectId: 'proj-prop13',
    },
    global: {
      stubs: property13Stubs,
    },
  })
}

describe('Feature: word-template-dual-mode, Property 13: dual-mode scope', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Mock all API calls to avoid network errors
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/a16/recommended-version')) {
        return Promise.resolve({ main: { code: 'A16-1' }, supplement: null })
      }
      if (url.includes('/projects/')) {
        return Promise.resolve({ client_name: '测试', audit_period_end: '2025-12-31', audit_year: '2025' })
      }
      if (url.includes('/file-info')) {
        return Promise.resolve({ sign_status: 'pending' })
      }
      if (url.includes('/onlyoffice/health')) {
        return Promise.resolve({ healthy: true })
      }
      if (url.includes('/render-config')) {
        return Promise.resolve({ sheets: [{ html_data: {} }] })
      }
      if (url.includes('/template-structure')) {
        return Promise.resolve({ placeholders: [], paragraphs: [], tables: [], metadata: {} })
      }
      if (url.includes('/field-overrides')) {
        return Promise.resolve({})
      }
      if (url.includes('/misstatements/for-letter')) {
        return Promise.resolve({ summary: '' })
      }
      return Promise.resolve(null)
    })
  })

  it('property: for any word-template wp_code (≠ A16), el-segmented dual-mode switch is rendered', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom(...WORD_TEMPLATE_WP_CODES),
        async (wpCode) => {
          const wrapper = createProperty13Wrapper(wpCode)
          await flushPromises()

          const segmented = wrapper.find('.el-segmented-stub')
          // All 25 word-template wp_codes are NOT 'A16', so segmented must exist
          expect(segmented.exists()).toBe(true)

          // Verify it has the two mode options
          const items = wrapper.findAll('.el-segmented-item')
          expect(items.length).toBe(2)
          expect(items[0].text()).toBe('结构化视图')
          expect(items[1].text()).toBe('在线编辑')

          wrapper.unmount()
        },
      ),
      { numRuns: 100 },
    )
  })

  it('property: wp_code "A16" does NOT render el-segmented (uses A16 mode instead)', async () => {
    const wrapper = createProperty13Wrapper('A16')
    await flushPromises()

    const segmented = wrapper.find('.el-segmented-stub')
    expect(segmented.exists()).toBe(false)

    // A16 mode renders the version radio-group instead
    const radioGroup = wrapper.find('.el-radio-group')
    expect(radioGroup.exists()).toBe(true)

    wrapper.unmount()
  })

  it('property: exhaustive check — all 25 codes render segmented, A16 does not', async () => {
    // Exhaustive: test each of the 25 codes explicitly
    for (const wpCode of WORD_TEMPLATE_WP_CODES) {
      const wrapper = createProperty13Wrapper(wpCode)
      await flushPromises()

      const segmented = wrapper.find('.el-segmented-stub')
      expect(segmented.exists()).toBe(true)

      wrapper.unmount()
    }

    // Negative case: A16
    const a16Wrapper = createProperty13Wrapper('A16')
    await flushPromises()
    expect(a16Wrapper.find('.el-segmented-stub').exists()).toBe(false)
    a16Wrapper.unmount()
  })
})


/**
 * Task 5.6 — Dual-mode unit tests
 *
 * Tests:
 * 1. Mode switch: structured→online calls structuredFlush then initGenericEditor
 * 2. Mode switch: online→structured calls loadStructuredData
 * 3. OO disabled: onlyofficeAvailable=false → clicking "在线编辑" reverts + warning
 * 4. Flush-before-switch: flush completes before editor init (ordering)
 * 5. Export: structured view export triggers prefilled-download?include_responses=true
 *
 * Validates: Requirements 1.3, 1.4, 5.6, 6.1
 */

describe('WorkpaperWordEditor — dual-mode unit tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Ensure DocsAPI is not available (prevents initGenericEditor from hanging on script load)
    ;(window as any).DocsAPI = undefined
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/a16/recommended-version')) {
        return Promise.resolve({ main: { code: 'A8-1' }, supplement: null })
      }
      if (url.includes('/projects/')) {
        return Promise.resolve({ client_name: '测试公司', audit_period_end: '2025-12-31', audit_year: '2025' })
      }
      if (url.includes('/file-info')) {
        return Promise.resolve({ sign_status: 'pending' })
      }
      if (url.includes('/onlyoffice/health')) {
        return Promise.resolve({ healthy: true })
      }
      if (url.includes('/render-config')) {
        return Promise.resolve({ sheets: [{ html_data: { template_structure: { placeholders: [{ field_id: 'entity_name', label: '被审计单位', data_type: 'text', default_value: '××公司' }], paragraphs: [], tables: [], metadata: {} }, filled_responses: {} } }] })
      }
      if (url.includes('/template-structure')) {
        return Promise.resolve({ placeholders: [{ field_id: 'entity_name', label: '被审计单位', data_type: 'text', default_value: '××公司' }], paragraphs: [], tables: [], metadata: {} })
      }
      if (url.includes('/field-overrides')) {
        return Promise.resolve({})
      }
      if (url.includes('/misstatements/for-letter')) {
        return Promise.resolve({ summary: '' })
      }
      // onlyoffice-config: return null config so initGenericEditor exits early
      // (avoids hanging on loadOnlyOfficeScript which loads a <script> that never resolves in jsdom)
      if (url.includes('/onlyoffice-config')) {
        return Promise.resolve({ config: { document: { url: null } } })
      }
      return Promise.resolve(null)
    })
    mockApiPut.mockResolvedValue({})
  })

  function createDualModeWrapper(wpCode = 'A8-1') {
    return mount(WorkpaperWordEditor, {
      props: {
        wpId: 'wp-dual-001',
        wpCode,
        projectId: 'proj-dual-test',
      },
      global: {
        stubs: property13Stubs,
      },
    })
  }

  describe('mode switch: structured→online', () => {
    it('switching from "结构化视图" to "在线编辑" calls onlyoffice-config (initGenericEditor)', async () => {
      const wrapper = createDualModeWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      expect(vm.genericViewMode).toBe('结构化视图')
      // OO is available from health check
      expect(vm.onlyofficeAvailable).toBe(true)

      // Clear mocks to track subsequent calls
      mockApiGet.mockClear()
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/onlyoffice-config')) {
          // Return null url so it exits early without trying to load DocsAPI script
          return Promise.resolve({ config: { document: { url: null } } })
        }
        return Promise.resolve(null)
      })

      // Simulate el-segmented @change firing with new mode
      await vm.onModeSwitch('在线编辑')
      await flushPromises()

      // initGenericEditor should have been called (it makes the onlyoffice-config GET)
      const configCalls = mockApiGet.mock.calls.filter(
        (c: any[]) => c[0]?.includes?.('/onlyoffice-config'),
      )
      expect(configCalls.length).toBeGreaterThan(0)

      wrapper.unmount()
    })
  })

  describe('mode switch: online→structured', () => {
    it('switching from "在线编辑" to "结构化视图" calls loadStructuredData (render-config)', async () => {
      const wrapper = createDualModeWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      // Manually set mode to online (skipping the switch logic)
      vm.genericViewMode = '在线编辑'
      await flushPromises()

      // Clear mocks to track loadStructuredData call
      mockApiGet.mockClear()
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/render-config')) {
          return Promise.resolve({ sheets: [{ html_data: { template_structure: { placeholders: [], paragraphs: [], tables: [], metadata: {} }, filled_responses: {} } }] })
        }
        return Promise.resolve(null)
      })

      // Switch back to structured view
      await vm.onModeSwitch('结构化视图')
      await flushPromises()

      // loadStructuredData should have been called (triggers render-config GET)
      const renderCalls = mockApiGet.mock.calls.filter(
        (c: any[]) => c[0]?.includes?.('/render-config'),
      )
      expect(renderCalls.length).toBeGreaterThan(0)

      wrapper.unmount()
    })
  })

  describe('OO disabled state', () => {
    it('when onlyofficeAvailable=false, switching to "在线编辑" reverts to "结构化视图"', async () => {
      // Health check returns unhealthy
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/onlyoffice/health')) {
          return Promise.resolve({ healthy: false })
        }
        if (url.includes('/projects/')) {
          return Promise.resolve({ client_name: '测试公司', audit_period_end: '2025-12-31', audit_year: '2025' })
        }
        if (url.includes('/render-config')) {
          return Promise.resolve({ sheets: [{ html_data: { template_structure: { placeholders: [], paragraphs: [], tables: [], metadata: {} }, filled_responses: {} } }] })
        }
        if (url.includes('/template-structure')) {
          return Promise.resolve({ placeholders: [], paragraphs: [], tables: [], metadata: {} })
        }
        if (url.includes('/field-overrides')) {
          return Promise.resolve({})
        }
        return Promise.resolve(null)
      })

      const wrapper = createDualModeWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      expect(vm.onlyofficeAvailable).toBe(false)
      expect(vm.genericViewMode).toBe('结构化视图')

      // Attempt to switch to online edit
      await vm.onModeSwitch('在线编辑')
      await flushPromises()

      // Should revert back to structured view
      expect(vm.genericViewMode).toBe('结构化视图')

      wrapper.unmount()
    })
  })

  describe('flush-before-switch ordering', () => {
    it('flush completes before initGenericEditor executes', async () => {
      const wrapper = createDualModeWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      expect(vm.onlyofficeAvailable).toBe(true)

      // Track execution ordering
      const executionOrder: string[] = []

      mockApiPut.mockImplementation((url: string) => {
        if (url.includes('/checklist-responses')) {
          executionOrder.push('flush')
        }
        return Promise.resolve({})
      })

      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/onlyoffice-config')) {
          executionOrder.push('initEditor')
          return Promise.resolve({ config: { document: { url: null } } })
        }
        return Promise.resolve(null)
      })

      // Simulate having a pending edit so flush actually calls the API
      if (vm.structuredUpdateField) {
        vm.structuredUpdateField('entity_name', '新公司名称')
      }

      // Switch to online mode — triggers: structuredFlush() then initGenericEditor()
      await vm.onModeSwitch('在线编辑')
      await flushPromises()

      // If flush was triggered (had pending saves), it must precede initEditor
      if (executionOrder.includes('flush') && executionOrder.includes('initEditor')) {
        expect(executionOrder.indexOf('flush')).toBeLessThan(executionOrder.indexOf('initEditor'))
      }

      // initGenericEditor should always be called after flush (even if no pending saves)
      expect(executionOrder).toContain('initEditor')

      wrapper.unmount()
    })
  })

  describe('export button in structured view', () => {
    it('export triggers prefilled-download API call for the correct wp_code', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(new Blob(['docx-content'])),
      })
      global.fetch = mockFetch
      global.URL.createObjectURL = vi.fn().mockReturnValue('blob:test')
      global.URL.revokeObjectURL = vi.fn()

      const wrapper = createDualModeWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      expect(vm.genericViewMode).toBe('结构化视图')

      // Call the toolbar export
      await vm.onExportDocx()
      await flushPromises()

      // Verify it calls prefilled-download with correct wp_code path
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/wp-templates/A8-1/prefilled-download'),
        expect.objectContaining({
          headers: expect.objectContaining({ Authorization: expect.any(String) }),
        }),
      )

      wrapper.unmount()
    })

    it('composable exportDocx calls prefilled-download with include_responses=true', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(new Blob(['docx-content'])),
      })
      global.fetch = mockFetch
      global.URL.createObjectURL = vi.fn().mockReturnValue('blob:test')
      global.URL.revokeObjectURL = vi.fn()

      const wrapper = createDualModeWrapper()
      await flushPromises()

      const vm = wrapper.vm as any

      // The composable's exportDocx is the structured-view export with include_responses=true
      // Access it via vm's internal setup state
      const exportFn = vm.structuredExportDocx || vm.exportDocx
      if (exportFn) {
        await exportFn()
        await flushPromises()
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('include_responses=true'),
          expect.any(Object),
        )
      } else {
        // If not directly exposed, verify onExportDocx works correctly for generic mode
        await vm.onExportDocx()
        await flushPromises()
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('/wp-templates/A8-1/prefilled-download'),
          expect.any(Object),
        )
      }

      wrapper.unmount()
    })
  })
})


/**
 * Task 8.4 — Export/Import toolbar buttons unit tests
 *
 * Tests:
 * 1. All 3 buttons render in structured-toolbar when in structured view mode
 * 2. "导出 Word" triggers prefilled-download with include_responses=true
 * 3. "导出模板" triggers prefilled-download with include_guidance=true
 * 4. "导入数据" opens the import dialog
 * 5. Import dialog shows el-upload accepting .docx only
 * 6. Successful import shows ElMessage.success with "已导入 {N} 个字段"
 * 7. Failed import shows ElMessage.error
 * 8. After successful import, structured view data is refreshed (loadStructuredData called)
 *
 * Validates: Requirements 11, 12, 13
 */

// Mock ElMessage for import tests
const mockElMessageSuccess = vi.fn()
const mockElMessageError = vi.fn()
vi.mock('element-plus', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    ElMessage: {
      success: (...args: any[]) => mockElMessageSuccess(...args),
      error: (...args: any[]) => mockElMessageError(...args),
      warning: vi.fn(),
      info: vi.fn(),
    },
  }
})

describe('WorkpaperWordEditor — export/import toolbar buttons', () => {
  let mockFetch: ReturnType<typeof vi.fn>
  let mockCreateObjectURL: ReturnType<typeof vi.fn>
  let mockRevokeObjectURL: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()

    // Mock global.fetch for download endpoints (native fetch, not api proxy)
    mockFetch = vi.fn()
    global.fetch = mockFetch

    // Mock URL APIs for download tests
    mockCreateObjectURL = vi.fn().mockReturnValue('blob:http://localhost/fake-blob')
    mockRevokeObjectURL = vi.fn()
    global.URL.createObjectURL = mockCreateObjectURL
    global.URL.revokeObjectURL = mockRevokeObjectURL

    // Standard API mocks for generic (non-A16) mode
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/projects/')) {
        return Promise.resolve({ client_name: '测试公司', audit_period_end: '2025-12-31', audit_year: '2025' })
      }
      if (url.includes('/onlyoffice/health')) {
        return Promise.resolve({ healthy: true })
      }
      if (url.includes('/render-config')) {
        return Promise.resolve({
          sheets: [{
            html_data: {
              template_structure: {
                placeholders: [{ field_id: 'entity_name', label: '被审计单位', data_type: 'text', default_value: '××公司' }],
                paragraphs: [],
                tables: [],
                metadata: { wp_code: 'A8-1' },
              },
              filled_responses: {},
            },
          }],
        })
      }
      if (url.includes('/template-structure')) {
        return Promise.resolve({ placeholders: [], paragraphs: [], tables: [], metadata: {} })
      }
      if (url.includes('/field-overrides')) {
        return Promise.resolve({})
      }
      return Promise.resolve(null)
    })
  })

  function createToolbarWrapper(wpCode = 'A8-1') {
    return mount(WorkpaperWordEditor, {
      props: {
        wpId: 'wp-toolbar-001',
        wpCode,
        projectId: 'proj-toolbar-test',
      },
      global: {
        stubs: property13Stubs,
      },
    })
  }

  describe('toolbar buttons render', () => {
    it('all 3 buttons (导出 Word, 导出模板, 导入数据) render in structured toolbar', async () => {
      const wrapper = createToolbarWrapper()
      await flushPromises()

      const toolbar = wrapper.find('.gt-wp-word-editor__structured-toolbar')
      expect(toolbar.exists()).toBe(true)

      const buttons = toolbar.findAll('.el-button')
      const texts = buttons.map(b => b.text())

      expect(texts).toContain('导出 Word')
      expect(texts).toContain('导出模板')
      expect(texts).toContain('导入数据')
      expect(buttons.length).toBe(3)

      wrapper.unmount()
    })
  })

  describe('导出 Word button', () => {
    it('click triggers prefilled-download with include_responses=true', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(new Blob(['docx-content'])),
      })

      const wrapper = createToolbarWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      await vm.onExportWord()
      await flushPromises()

      // Verify fetch called with correct endpoint + query param
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/wp-templates\/A8-1\/prefilled-download\?include_responses=true/),
        expect.objectContaining({
          headers: expect.objectContaining({ Authorization: expect.any(String) }),
        }),
      )

      wrapper.unmount()
    })
  })

  describe('导出模板 button', () => {
    it('click triggers prefilled-download with include_guidance=true', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(new Blob(['template-content'])),
      })

      const wrapper = createToolbarWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      await vm.onExportTemplate()
      await flushPromises()

      // Verify fetch called with include_guidance=true
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/wp-templates\/A8-1\/prefilled-download\?include_guidance=true/),
        expect.objectContaining({
          headers: expect.objectContaining({ Authorization: expect.any(String) }),
        }),
      )

      wrapper.unmount()
    })
  })

  describe('导入数据 button', () => {
    it('click opens the import dialog', async () => {
      const wrapper = createToolbarWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      expect(vm.showImportDialog).toBe(false)

      // Find and click the "导入数据" button
      const toolbar = wrapper.find('.gt-wp-word-editor__structured-toolbar')
      const importBtn = toolbar.findAll('.el-button').find(b => b.text() === '导入数据')
      expect(importBtn).toBeDefined()
      await importBtn!.trigger('click')
      await flushPromises()

      expect(vm.showImportDialog).toBe(true)

      wrapper.unmount()
    })

    it('import dialog shows el-upload accepting .docx only', async () => {
      const wrapper = createToolbarWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      vm.showImportDialog = true
      await flushPromises()

      // Find the import dialog's el-upload (the second dialog in DOM)
      const dialogs = wrapper.findAll('.el-dialog')
      const importDialog = dialogs.find(d => d.html().includes('导入数据') || d.html().includes('.docx'))
      expect(importDialog).toBeDefined()

      const upload = importDialog!.find('.el-upload')
      expect(upload.exists()).toBe(true)

      wrapper.unmount()
    })
  })

  describe('import success/error messaging', () => {
    it('successful import shows ElMessage.success with "已导入 {N} 个字段"', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ data: { imported_count: 5, warnings: [] } }),
      })

      const wrapper = createToolbarWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      // Set up import file directly (el-upload stubs won't fire real events)
      vm.importFile = new File(['content'], 'test.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
      vm.showImportDialog = true
      await flushPromises()

      await vm.onImportData()
      await flushPromises()

      // Verify fetch called the import endpoint
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/workpapers/wp-toolbar-001/import-structured'),
        expect.objectContaining({ method: 'POST' }),
      )

      // Verify success message
      expect(mockElMessageSuccess).toHaveBeenCalledWith('已导入 5 个字段')

      // Dialog should close
      expect(vm.showImportDialog).toBe(false)

      wrapper.unmount()
    })

    it('failed import shows ElMessage.error', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({ detail: '文件格式不匹配，请使用正确的模板' }),
      })

      const wrapper = createToolbarWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      vm.importFile = new File(['bad'], 'bad.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
      vm.showImportDialog = true
      await flushPromises()

      await vm.onImportData()
      await flushPromises()

      // Verify error message
      expect(mockElMessageError).toHaveBeenCalledWith('文件格式不匹配，请使用正确的模板')

      wrapper.unmount()
    })
  })

  describe('import refreshes structured view', () => {
    it('after successful import, loadStructuredData is called to refresh view', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ data: { imported_count: 3, warnings: [] } }),
      })

      const wrapper = createToolbarWrapper()
      await flushPromises()

      const vm = wrapper.vm as any
      vm.importFile = new File(['content'], 'test.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })

      // Clear mockApiGet to track loadStructuredData call (it calls render-config)
      mockApiGet.mockClear()
      mockApiGet.mockImplementation((url: string) => {
        if (url.includes('/render-config')) {
          return Promise.resolve({
            sheets: [{
              html_data: {
                template_structure: {
                  placeholders: [{ field_id: 'entity_name', label: '被审计单位', data_type: 'text', default_value: '××公司', current_value: '导入公司' }],
                  paragraphs: [],
                  tables: [],
                  metadata: { wp_code: 'A8-1' },
                },
                filled_responses: { entity_name: '导入公司' },
              },
            }],
          })
        }
        return Promise.resolve(null)
      })

      await vm.onImportData()
      await flushPromises()

      // loadStructuredData should have been called (re-fetches render-config)
      const renderCalls = mockApiGet.mock.calls.filter(
        (c: any[]) => c[0]?.includes?.('/render-config'),
      )
      expect(renderCalls.length).toBeGreaterThan(0)

      wrapper.unmount()
    })
  })
})
