import { describe, it, expect, vi, beforeEach } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { mount, flushPromises } from '@vue/test-utils'
import BatchImportDialog from '../BatchImportDialog.vue'

const api = vi.hoisted(() => ({
  validate: vi.fn(),
  apply: vi.fn(),
  status: vi.fn(),
  template: vi.fn(),
  groupTemplate: vi.fn(),
  selectedTemplate: vi.fn(),
  errors: vi.fn(),
  errorMessage: vi.fn((_error: unknown, fallback: string) => fallback),
}))

vi.mock('@/services/batchProjectImport', () => ({
  validateBatchProjectFile: api.validate,
  applyBatchProjectPlan: api.apply,
  getBatchProjectPlan: api.status,
  downloadBatchTemplate: api.template,
  downloadGroupImportTemplate: api.groupTemplate,
  downloadSelectedProjectTemplate: api.selectedTemplate,
  downloadBatchErrors: api.errors,
  batchErrorMessage: api.errorMessage,
  newBatchIdempotencyKey: () => 'client-operation-0001',
  BATCH_PLAN_STATUS: { validated: 'validated', applying: 'applying', applied: 'applied', failed: 'failed' },
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  }
})

const validation = {
  valid: true,
  total_rows: 2,
  tree_preview: [],
  errors: [],
  warnings: [],
  summary: { create: 2, update: 0, unchanged: 0, skip: 0, auto_root: 1, error: 0 },
  validation_id: '11111111-1111-4111-8111-111111111111',
  file_sha256: 'a'.repeat(64),
  template_version: '2',
  expires_at: '2030-01-01T00:00:00Z',
}
const receipt = {
  success_count: 2, fail_count: 0, failures: [], created_count: 2,
  updated_count: 0, unchanged_count: 0, skipped_count: 0,
  auto_root_count: 1, project_ids: ['p1', 'r1'], root_project_ids: ['r1'],
  idempotent: false,
}

const stubs = {
  'el-dialog': { name: 'ElDialog', template: '<div><slot /><slot name="footer" /></div>', props: ['modelValue'], emits: ['update:modelValue', 'open'] },
  'el-button': { template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>', props: ['disabled', 'loading'], emits: ['click'] },
  'el-upload': { name: 'ElUpload', template: '<div><slot /><slot name="tip" /></div>', props: ['onChange', 'disabled'], methods: { clearFiles: vi.fn() } },
  'el-steps': { name: 'ElSteps', template: '<div><slot /></div>', props: ['active'] },
  'el-step': true,
  'el-table': { template: '<div><slot /></div>' },
  'el-table-column': true,
  'el-alert': true,
  'el-icon': true,
  'el-tree': true,
  'el-tree-v2': true,
  'el-tag': true,
  'el-select': { template: '<div><slot /></div>' },
  'el-option': true,
}

function mountDialog(props: Record<string, unknown> = {}) {
  return mount(BatchImportDialog, {
    props: { modelValue: true, ...props },
    global: { stubs },
  })
}

async function selectFile(wrapper: ReturnType<typeof mountDialog>) {
  const file = new File(['xlsx'], '批量.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  const upload = wrapper.findComponent({ name: 'ElUpload' })
  await (upload.props('onChange') as Function)({ name: file.name, raw: file })
  return file
}

describe('BatchImportDialog', () => {
  beforeEach(() => {
    api.validate.mockReset()
    api.apply.mockReset()
    api.status.mockReset()
    api.template.mockReset()
    api.groupTemplate.mockReset()
    api.selectedTemplate.mockReset()
    api.errors.mockReset()
    api.errorMessage.mockReset()
    api.errorMessage.mockImplementation((_error: unknown, fallback: string) => fallback)
    sessionStorage.clear()
    api.validate.mockResolvedValue(validation)
    api.apply.mockResolvedValue(receipt)
  })

  it('普通与合并场景显示不同的模板入口', () => {
    expect(mountDialog().text()).toContain('下载建项模板')
    expect(mountDialog().text()).not.toContain('导出当前集团树')
    const consolidation = mountDialog({
      mode: 'consolidation',
      consolidationRoots: [{ id: 'root-1', label: '测试集团 · 2025' }],
    })
    expect(consolidation.text()).toContain('调整现有企业树')
    expect(consolidation.text()).toContain('导出当前集团树')
  })

  it('文件只上传校验一次，确认阶段只发送计划 id 与同一幂等键', async () => {
    const wrapper = mountDialog()
    const file = await selectFile(wrapper)
    const validateButton = wrapper.findAll('button').find((item) => item.text().includes('预校验并生成计划'))!
    await validateButton.trigger('click')
    await flushPromises()
    expect(api.validate).toHaveBeenCalledWith(file, 'project', 'client-operation-0001')
    expect(wrapper.text()).toContain('自动合并根')
    expect(wrapper.findComponent({ name: 'ElSteps' }).props('active')).toBe(2)
    expect(sessionStorage.getItem('gt:batch-project-plan:project')).toContain(validation.validation_id)

    const applyButton = wrapper.findAll('button').find((item) => item.text().includes('确认执行'))!
    expect(applyButton.attributes('disabled')).toBeUndefined()
    await applyButton.trigger('click')
    await flushPromises()
    expect(api.apply).toHaveBeenCalledWith(validation.validation_id, 'client-operation-0001')
    expect(api.validate).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('success')?.[0]?.[0]).toEqual(receipt)
    expect(wrapper.findComponent({ name: 'ElSteps' }).props('active')).toBe(4)
    expect(sessionStorage.getItem('gt:batch-project-plan:project')).toBeNull()
    const openRoot = wrapper.findAll('button').find((item) => item.text().includes('进入新建合并项目'))!
    await openRoot.trigger('click')
    expect(wrapper.emitted('open-root')).toEqual([['r1']])
  })

  it('校验请求失败后保留所选文件，可原地重试', async () => {
    api.validate.mockRejectedValueOnce(new Error('temporary'))
    const wrapper = mountDialog()
    const file = await selectFile(wrapper)
    const button = wrapper.findAll('button').find((item) => item.text().includes('预校验并生成计划'))!
    await button.trigger('click')
    await flushPromises()
    await button.trigger('click')
    await flushPromises()
    expect(api.validate).toHaveBeenCalledTimes(2)
    expect(api.validate.mock.calls[1][0]).toBe(file)
  })

  it('网络错误后从计划状态恢复首次回执', async () => {
    api.apply.mockRejectedValueOnce(new Error('network'))
    api.status.mockResolvedValue({ status: 'applied', receipt })
    const wrapper = mountDialog()
    await selectFile(wrapper)
    await wrapper.findAll('button').find((item) => item.text().includes('预校验并生成计划'))!.trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find((item) => item.text().includes('确认执行'))!.trigger('click')
    await flushPromises()
    expect(api.status).toHaveBeenCalledWith(validation.validation_id)
    expect(wrapper.text()).toContain('没有重复创建项目')
  })

  it('重新打开弹窗可从 sessionStorage 恢复未执行计划，无需重新选择文件', async () => {
    sessionStorage.setItem('gt:batch-project-plan:project', JSON.stringify({
      validationId: validation.validation_id,
      idempotencyKey: 'client-operation-0001',
      mode: 'project',
      expiresAt: '2030-01-01T00:00:00Z',
    }))
    api.status.mockResolvedValue({
      validation_id: validation.validation_id,
      mode: 'project',
      status: 'validated',
      valid: true,
      total_rows: 2,
      errors: [],
      summary: validation.summary,
      tree_preview: [],
      warnings: [],
      template_version: '2',
      receipt: null,
      public_error: null,
      expires_at: '2030-01-01T00:00:00Z',
    })
    const wrapper = mountDialog()
    wrapper.findComponent({ name: 'ElDialog' }).vm.$emit('open')
    await flushPromises()
    expect(api.status).toHaveBeenCalledWith(validation.validation_id)
    const applyButton = wrapper.findAll('button').find((item) => item.text().includes('确认执行'))!
    expect(applyButton.attributes('disabled')).toBeUndefined()
  })

  it('弹窗主体限高、操作栏固定且大树不再默认全展开', () => {
    const source = fs.readFileSync(path.resolve(__dirname, '../BatchImportDialog.vue'), 'utf-8')
    expect(source).toContain('max-height: 80vh')
    expect(source).toContain('.el-dialog__footer')
    expect(source).toContain('<el-tree-v2')
    expect(source).toContain(':default-expanded-keys="expandedKeys')
    expect(source).not.toContain('default-expand-all')
  })

  it('关闭按钮仍透传 v-model 事件', async () => {
    const wrapper = mountDialog()
    const close = wrapper.findAll('button').find((item) => item.text() === '关闭')!
    await close.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  })
})


describe('BatchImportDialog 并发恢复保护', () => {
  beforeEach(() => {
    api.validate.mockReset()
    api.apply.mockReset()
    api.status.mockReset()
    api.template.mockReset()
    api.groupTemplate.mockReset()
    api.selectedTemplate.mockReset()
    api.errors.mockReset()
    api.errorMessage.mockReset()
    api.errorMessage.mockImplementation((_error: unknown, fallback: string) => fallback)
    sessionStorage.clear()
    api.validate.mockResolvedValue(validation)
    api.apply.mockResolvedValue(receipt)
  })

  it('延迟恢复响应不会覆盖用户刚选择的新文件', async () => {
    sessionStorage.setItem('gt:batch-project-plan:project', JSON.stringify({
      validationId: validation.validation_id,
      idempotencyKey: 'client-operation-0001',
      mode: 'project',
      expiresAt: '2030-01-01T00:00:00Z',
    }))
    let resolveStatus!: (value: any) => void
    api.status.mockReturnValueOnce(new Promise((resolve) => { resolveStatus = resolve }))
    const wrapper = mountDialog()
    wrapper.findComponent({ name: 'ElDialog' }).vm.$emit('open')
    await selectFile(wrapper)
    resolveStatus({
      validation_id: validation.validation_id,
      mode: 'project',
      status: 'validated',
      valid: true,
      total_rows: validation.total_rows,
      errors: [],
      summary: validation.summary,
      tree_preview: [],
      warnings: [],
      template_version: '2',
      receipt: null,
      public_error: null,
      expires_at: validation.expires_at,
    })
    await flushPromises()

    expect(sessionStorage.getItem('gt:batch-project-plan:project')).toBeNull()
    const applyButton = wrapper.findAll('button').find((item) => item.text().includes('确认执行'))!
    expect(applyButton.attributes('disabled')).toBeDefined()
    expect(api.apply).not.toHaveBeenCalled()
  })

  it('明确的 409 不会被当成网络丢响应而假报状态', async () => {
    api.apply.mockRejectedValueOnce({ response: { status: 409 } })
    const wrapper = mountDialog()
    await selectFile(wrapper)
    await wrapper.findAll('button').find((item) => item.text().includes('预校验并生成计划'))!.trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find((item) => item.text().includes('确认执行'))!.trigger('click')
    await flushPromises()

    expect(api.status).not.toHaveBeenCalled()
  })

  it('普通入口和左栏都会消费新合并根跳转事件', () => {
    const projectView = fs.readFileSync(path.resolve(__dirname, '../../../views/Projects.vue'), 'utf-8')
    const middleList = fs.readFileSync(path.resolve(__dirname, '../../layout/MiddleProjectList.vue'), 'utf-8')
    expect(projectView).toContain('@open-root="openProject"')
    expect(middleList).toContain('@open-root="openRoot"')
    expect(middleList).toContain("name: 'ProjectEntry'")
  })
})


describe('BatchImportDialog 不确定执行结果', () => {
  beforeEach(() => {
    api.validate.mockReset()
    api.apply.mockReset()
    api.status.mockReset()
    api.errorMessage.mockReset()
    api.errorMessage.mockImplementation((_error: unknown, fallback: string) => fallback)
    sessionStorage.clear()
    api.validate.mockResolvedValue(validation)
  })

  it('status 短暂返回 validated 时继续轮询，而不宣称未写入', async () => {
    vi.useFakeTimers()
    try {
      api.apply.mockRejectedValueOnce(new Error('network'))
      api.status.mockResolvedValue({
        validation_id: validation.validation_id,
        mode: 'project',
        status: 'validated',
        valid: true,
        total_rows: validation.total_rows,
        errors: [],
        summary: validation.summary,
        tree_preview: [],
        warnings: [],
        template_version: '2',
        receipt: null,
        public_error: null,
        expires_at: validation.expires_at,
      })
      const wrapper = mountDialog()
      await selectFile(wrapper)
      await wrapper.findAll('button').find((item) => item.text().includes('预校验并生成计划'))!.trigger('click')
      await flushPromises()
      await wrapper.findAll('button').find((item) => item.text().includes('确认执行'))!.trigger('click')
      await flushPromises()
      await vi.runAllTimersAsync()
      await flushPromises()

      expect(api.status).toHaveBeenCalledTimes(4)
    } finally {
      vi.useRealTimers()
    }
  })
})
