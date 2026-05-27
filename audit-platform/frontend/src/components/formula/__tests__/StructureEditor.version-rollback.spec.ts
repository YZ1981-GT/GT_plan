/**
 * StructureEditor — 自定义模板版本回滚 UI（Sprint 3 Task 3.4）
 *
 * Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3 Task 3.4
 * Reqs:   R4.3 验收 36（自定义模板隔离 + 版本回滚）
 *
 * 用例：
 * 1. 打开 dialog → 调用 GET /api/projects/{pid}/note-template/versions
 * 2. 列表显示 + 「回滚」按钮调 POST .../restore?version=N + ElMessageBox 二次确认
 * 3. 回滚成功后刷新版本列表（新增条目应在末尾）
 *
 * **Validates: Requirements R4.3**
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

// ─── Mock apiProxy ─────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

// ─── Mock element-plus ─────────────────────────────────────────────────────

const mockConfirm = vi.fn().mockResolvedValue('confirm')
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
    ElMessageBox: { confirm: (...args: any[]) => mockConfirm(...args) },
  }
})

// ─── Mock commonApi ────────────────────────────────────────────────────────

vi.mock('@/services/commonApi', () => ({
  getExcelHtmlPreview: vi.fn().mockResolvedValue({ html: '', total_rows: 0, sheet_names: [] }),
  saveExcelHtmlEdits: vi.fn().mockResolvedValue({ version: 1 }),
  getModuleHtml: vi.fn().mockResolvedValue({ html: '<div>module</div>' }),
  acquireEditLock: vi.fn().mockResolvedValue(undefined),
  releaseEditLock: vi.fn().mockResolvedValue(undefined),
  refreshEditLock: vi.fn().mockResolvedValue(undefined),
  listFileVersions: vi.fn().mockResolvedValue([]),
  rollbackFileVersion: vi.fn().mockResolvedValue(undefined),
  executeFormulas: vi.fn().mockResolvedValue({ executed: 0, total_formulas: 0, errors: [] }),
}))

vi.mock('@/components/formula/FormulaBar.vue', () => ({
  default: { template: '<div class="mock-formula-bar" />' },
}))
vi.mock('@/components/formula/CellSelector.vue', () => ({
  default: { template: '<div class="mock-cell-selector" />' },
}))

// eslint-disable-next-line import/order
import StructureEditor from '@/components/formula/StructureEditor.vue'

const STUBS = {
  'el-button': { template: '<button :data-test="$attrs[\'data-test\']" @click="$emit(\'click\')"><slot /></button>' },
  'el-button-group': { template: '<div><slot /></div>' },
  'el-divider': true,
  'el-checkbox': true,
  'el-input': true,
  'el-input-number': true,
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div><slot /></div>' },
  'el-select': true,
  'el-option': true,
  'el-dialog': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div v-if="modelValue" :data-test="$attrs[\'data-test\']" class="mock-dialog"><slot /><slot name="footer" /></div>',
  },
  'el-tabs': { template: '<div><slot /></div>' },
  'el-tab-pane': { template: '<div><slot /></div>' },
  'el-table': {
    props: ['data'],
    template: '<table :data-test="$attrs[\'data-test\']"><tbody><tr v-for="(row, i) in data" :key="i" :data-test="\'row-\' + row.version"><slot :row="row" :$index="i" /></tr></tbody></table>',
  },
  'el-table-column': {
    template: '<td><slot :row="$parent.$attrs.data?.[0] || {}" /></td>',
  },
  'el-pagination': true,
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockConfirm.mockReset()
  mockConfirm.mockResolvedValue('confirm')
})

describe('StructureEditor — Sprint 3 Task 3.4: 版本历史回滚', () => {
  function mountSE() {
    // mount 时 loadSelectorData 调 api.get → 静默返回空数组
    mockGet.mockResolvedValue([])
    return mount(StructureEditor, {
      props: {
        projectId: 'proj-A',
        module: 'disclosure_note',
        moduleParams: { note_section: '五、6', year: 2024 },
        year: 2024,
      },
      global: { stubs: STUBS },
    })
  }

  it('用例 1 — 打开版本历史 dialog → GET /api/projects/{pid}/note-template/versions', async () => {
    const wrapper = mountSE()
    await flushPromises()

    // 准备返回值：3 条历史
    const fakeVersions = [
      { version: 1, snapshot_path: 'v1.json', updated_at: '2026-05-25T10:00:00Z' },
      { version: 2, snapshot_path: 'v2.json', updated_at: '2026-05-26T11:00:00Z' },
      { version: 3, snapshot_path: 'v3.json', updated_at: '2026-05-27T12:00:00Z' },
    ]
    mockGet.mockReset()
    mockGet.mockResolvedValue(fakeVersions)

    const vm: any = wrapper.vm
    await vm.onOpenVersions()
    await flushPromises()

    expect(mockGet).toHaveBeenCalledWith('/api/projects/proj-A/note-template/versions')
    expect(vm.versions).toEqual(fakeVersions)
    expect(vm.showVersions).toBe(true)
  })

  it('用例 2 — 「回滚」按钮调 POST .../restore?version=N + ElMessageBox 二次确认', async () => {
    const wrapper = mountSE()
    await flushPromises()

    mockPost.mockResolvedValue({ version: 4, updated_at: '2026-05-28T13:00:00Z', history: [] })
    mockGet.mockResolvedValue([])  // restore 后 list 刷新

    const vm: any = wrapper.vm
    vm.showVersions = true
    await vm.onRollbackCustomTemplate(2)
    await flushPromises()

    // 二次确认
    expect(mockConfirm).toHaveBeenCalled()
    // POST 调用
    expect(mockPost).toHaveBeenCalledWith('/api/projects/proj-A/note-template/restore?version=2')
    // emit custom-template-restored 携带新版本号
    const emitted = wrapper.emitted('custom-template-restored')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({ version: 4 })
  })

  it('用例 3 — 回滚成功后刷新版本列表（GET 再次调用）', async () => {
    const wrapper = mountSE()
    await flushPromises()

    const initialVersions = [
      { version: 1, snapshot_path: 'v1.json', updated_at: '2026-05-25' },
      { version: 2, snapshot_path: 'v2.json', updated_at: '2026-05-26' },
    ]
    const refreshedVersions = [
      ...initialVersions,
      { version: 3, snapshot_path: 'v3.json', updated_at: '2026-05-27' },
    ]
    mockGet.mockReset()
    mockGet.mockResolvedValueOnce(initialVersions)  // onOpenVersions 第一次
    mockPost.mockResolvedValue({ version: 3, updated_at: '2026-05-27', history: [] })
    mockGet.mockResolvedValueOnce(refreshedVersions)  // 回滚后第二次

    const vm: any = wrapper.vm
    await vm.onOpenVersions()
    await flushPromises()
    expect(vm.versions.length).toBe(2)

    await vm.onRollbackCustomTemplate(1)
    await flushPromises()

    // GET 应被调用 2 次：openVersions + 回滚后 refresh
    expect(mockGet).toHaveBeenCalledTimes(2)
    // 列表已更新到 3 条（含末尾新版本）
    expect(vm.versions.length).toBe(3)
    expect(vm.versions[vm.versions.length - 1].version).toBe(3)
  })

  it('用例 4 — 用户取消二次确认 → 不调用 POST', async () => {
    const wrapper = mountSE()
    await flushPromises()

    mockConfirm.mockRejectedValueOnce('cancel')
    const vm: any = wrapper.vm
    await vm.onRollbackCustomTemplate(2)
    await flushPromises()

    expect(mockPost).not.toHaveBeenCalled()
    // 不发出 custom-template-restored
    expect(wrapper.emitted('custom-template-restored')).toBeUndefined()
  })
})
