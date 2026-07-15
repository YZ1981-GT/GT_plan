/**
 * GtRefreshScopeDialog.spec.ts — Task 16 验证
 *
 * 覆盖：
 *  1. production host 传 project_id/year
 *  2. contract 字段解析（parseDraftRefreshResponse 各状态）
 *  3. failed 响应不弹 success toast
 *  4. partial_success 列出失败目标
 *  5. success 触发 refresh-complete emit
 *  6. 空勾选阻断（P23 保留）
 *
 * Spec: formula-runtime-convergence Task 16
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, ref, nextTick, type Ref } from 'vue'

// ─── ResizeObserver polyfill ────────────────────────────────────────────────────
if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// ─── Hoisted mocks ─────────────────────────────────────────────────────────────
const {
  mockGet,
  mockPost,
  mockMsgError,
  mockMsgSuccess,
  mockMsgWarning,
  roleHolder,
  checkedKeysHolder,
} = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockMsgError: vi.fn(),
  mockMsgSuccess: vi.fn(),
  mockMsgWarning: vi.fn(),
  roleHolder: { role: 'partner' as string },
  checkedKeysHolder: { keys: [] as string[] },
}))

vi.mock('@/utils/http', () => ({
  default: { get: mockGet, post: mockPost },
}))

vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({
    currentRole: { get value() { return roleHolder.role } } as unknown as Ref<string>,
  }),
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: {
      error: mockMsgError,
      success: mockMsgSuccess,
      warning: mockMsgWarning,
      info: vi.fn(),
    },
  }
})

import ElementPlus from 'element-plus'
import GtRefreshScopeDialog from '../GtRefreshScopeDialog.vue'
import {
  parseDraftRefreshResponse,
  isSuccess,
  isPartialSuccess,
  isFailed,
  isIdempotentHit,
} from '../formulaRuntimeContract'

// ─── Stubs ────────────────────────────────────────────────────────────────────
const ElDialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false }, title: { type: String, default: '' } },
  template: '<div class="el-dialog-stub"><slot /><slot name="footer" /></div>',
})

const ElTreeStub = defineComponent({
  name: 'ElTree',
  props: { data: { type: Array as () => any[], default: () => [] } },
  emits: ['check'],
  methods: {
    getCheckedKeys() {
      return checkedKeysHolder.keys
    },
  },
  template: `
    <div class="el-tree-stub">
      <div v-for="n in data" :key="n.key" class="tree-node" :data-key="n.key">
        <span class="tree-label">{{ n.label }}</span>
        <div v-if="n.children" class="tree-children">
          <div v-for="c in n.children" :key="c.key" class="tree-node child" :data-key="c.key">
            <span class="tree-label">{{ c.label }}</span>
          </div>
        </div>
      </div>
    </div>
  `,
})

const STUBS = { ElDialog: ElDialogStub, ElTree: ElTreeStub } as const

const SCOPE_ITEMS = [
  { key: 'report', label: '报表', group: 'report' },
  { key: 'note', label: '附注', group: 'note' },
  { key: 'workpaper:D', label: 'D 类循环底稿', group: 'workpaper', cycle: 'D' },
]

function mountDialog(props: Record<string, unknown> = {}): VueWrapper {
  return mount(GtRefreshScopeDialog, {
    props: { projectId: 'proj-abc', year: 2025, ...props },
    global: { plugins: [ElementPlus], stubs: STUBS },
  })
}

async function openDialog(wrapper: VueWrapper) {
  await (wrapper.vm as any).openDialog()
  await flushPromises()
  await nextTick()
}

// ══════════════════════════════════════════════════════════════════════════════
describe('GtRefreshScopeDialog — Task 16 production host + contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    roleHolder.role = 'partner'
    checkedKeysHolder.keys = []
    mockGet.mockResolvedValue({ data: { data: { items: SCOPE_ITEMS } } })
  })

  // ─── 1. production host 传 project_id/year ──────────────────────────────────
  it('向 refresh-scopes 传递 projectId 和 year', async () => {
    const wrapper = mountDialog({ projectId: 'p-123', year: 2024 })
    await openDialog(wrapper)

    expect(mockGet).toHaveBeenCalledWith(
      '/api/workpapers/refresh-scopes',
      { params: { project_id: 'p-123', year: 2024 } },
    )
    wrapper.unmount()
  })

  it('props projectId/year 透传到 POST draft-refresh', async () => {
    mockPost.mockResolvedValue({
      data: {
        data: {
          status: 'success',
          run_id: 'run-001',
          transaction_mode: 'all_or_nothing',
          affected_count: 5,
          applied_count: 5,
          failed_count: 0,
          skipped_count: 0,
          scopes: ['report'],
          idempotent: false,
          rollback_available: true,
          warnings: [],
          failures: [],
          preset_application: { preset_count: 0, presetted_pages: [], pending_pages: [] },
        },
      },
    })

    const wrapper = mountDialog({ projectId: 'p-xyz', year: 2026 })
    await openDialog(wrapper)

    checkedKeysHolder.keys = ['report']
    wrapper.findComponent(ElTreeStub).vm.$emit('check')
    await nextTick()

    const confirmBtn = wrapper.findAll('button').find((b) => b.text().includes('确认刷新'))!
    await confirmBtn.trigger('click')
    await flushPromises()

    expect(mockPost).toHaveBeenCalledWith('/api/workpapers/draft-refresh', expect.objectContaining({
      project_id: 'p-xyz',
      year: 2026,
      scopes: ['report'],
    }))
    wrapper.unmount()
  })

  // ─── 2. contract 字段解析 ───────────────────────────────────────────────────
  it('parseDraftRefreshResponse 解析所有字段', () => {
    const raw = {
      status: 'partial_success',
      run_id: 'abc-123',
      transaction_mode: 'partial_success',
      affected_count: 10,
      applied_count: 7,
      failed_count: 3,
      skipped_count: 0,
      scopes: ['report', 'workpaper:D'],
      idempotent: false,
      rollback_available: true,
      warnings: ['low coverage'],
      failures: ['D2-1 审定表', 'D3-1 审定表', 'D4-5 检查表'],
      preset_application: {
        preset_count: 5,
        presetted_pages: ['report:BS', 'report:IS'],
        pending_pages: ['note:section1'],
      },
    }
    const result = parseDraftRefreshResponse(raw)

    expect(result.status).toBe('partial_success')
    expect(result.run_id).toBe('abc-123')
    expect(result.transaction_mode).toBe('partial_success')
    expect(result.applied_count).toBe(7)
    expect(result.failed_count).toBe(3)
    expect(result.failures).toEqual(['D2-1 审定表', 'D3-1 审定表', 'D4-5 检查表'])
    expect(result.preset_application.preset_count).toBe(5)
    expect(result.preset_application.presetted_pages).toHaveLength(2)
    expect(result.warnings).toEqual(['low coverage'])
    expect(result.rollback_available).toBe(true)
  })

  it('parseDraftRefreshResponse 对缺失字段补默认值', () => {
    const minimal = { status: 'success', run_id: 'r-1' }
    const result = parseDraftRefreshResponse(minimal)

    expect(result.applied_count).toBe(0)
    expect(result.failed_count).toBe(0)
    expect(result.failures).toEqual([])
    expect(result.warnings).toEqual([])
    expect(result.preset_application.preset_count).toBe(0)
    expect(result.rollback_available).toBe(true)
  })

  it('parseDraftRefreshResponse 拒绝非法 status', () => {
    expect(() => parseDraftRefreshResponse({ status: 'bogus', run_id: 'x' })).toThrow('invalid status')
  })

  it('parseDraftRefreshResponse 拒绝非对象输入', () => {
    expect(() => parseDraftRefreshResponse(null)).toThrow('must be a non-null object')
    expect(() => parseDraftRefreshResponse(42)).toThrow('must be a non-null object')
  })

  it('status helpers 分类正确', () => {
    const s = parseDraftRefreshResponse({ status: 'success', run_id: 'a' })
    const p = parseDraftRefreshResponse({ status: 'partial_success', run_id: 'b' })
    const f = parseDraftRefreshResponse({ status: 'failed', run_id: 'c' })
    const i = parseDraftRefreshResponse({ status: 'idempotent_hit', run_id: 'd' })

    expect(isSuccess(s)).toBe(true)
    expect(isPartialSuccess(p)).toBe(true)
    expect(isFailed(f)).toBe(true)
    expect(isIdempotentHit(i)).toBe(true)

    expect(isSuccess(f)).toBe(false)
    expect(isFailed(s)).toBe(false)
  })

  // ─── 3. failed 响应不弹 success toast ──────────────────────────────────────
  it('status=failed 不弹 success toast', async () => {
    mockPost.mockResolvedValue({
      data: {
        data: {
          status: 'failed',
          run_id: 'run-f',
          transaction_mode: 'all_or_nothing',
          affected_count: 0,
          applied_count: 0,
          failed_count: 3,
          skipped_count: 0,
          scopes: ['report'],
          idempotent: false,
          rollback_available: false,
          warnings: [],
          failures: ['target-A', 'target-B', 'target-C'],
          preset_application: { preset_count: 0, presetted_pages: [], pending_pages: [] },
        },
      },
    })

    const wrapper = mountDialog()
    await openDialog(wrapper)

    checkedKeysHolder.keys = ['report']
    wrapper.findComponent(ElTreeStub).vm.$emit('check')
    await nextTick()

    const confirmBtn = wrapper.findAll('button').find((b) => b.text().includes('确认刷新'))!
    await confirmBtn.trigger('click')
    await flushPromises()

    // 不弹 success
    expect(mockMsgSuccess).not.toHaveBeenCalled()
    // 不弹 warning（partial 才弹）
    expect(mockMsgWarning).not.toHaveBeenCalled()

    wrapper.unmount()
  })

  // ─── 4. partial_success 列出失败目标 ──────────────────────────────────────
  it('status=partial_success 显示失败目标列表', async () => {
    mockPost.mockResolvedValue({
      data: {
        data: {
          status: 'partial_success',
          run_id: 'run-p',
          transaction_mode: 'partial_success',
          affected_count: 5,
          applied_count: 3,
          failed_count: 2,
          skipped_count: 0,
          scopes: ['report'],
          idempotent: false,
          rollback_available: true,
          warnings: [],
          failures: ['D2-1 审定表写入失败', '附注 section3 格式错误'],
          preset_application: { preset_count: 0, presetted_pages: [], pending_pages: [] },
        },
      },
    })

    const wrapper = mountDialog()
    await openDialog(wrapper)

    checkedKeysHolder.keys = ['report']
    wrapper.findComponent(ElTreeStub).vm.$emit('check')
    await nextTick()

    const confirmBtn = wrapper.findAll('button').find((b) => b.text().includes('确认刷新'))!
    await confirmBtn.trigger('click')
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('D2-1 审定表写入失败')
    expect(text).toContain('附注 section3 格式错误')
    expect(text).toContain('失败')
    // partial 弹 warning toast
    expect(mockMsgWarning).toHaveBeenCalled()
    // 不弹 success toast
    expect(mockMsgSuccess).not.toHaveBeenCalled()

    wrapper.unmount()
  })

  // ─── 5. success 触发 refresh-complete emit ────────────────────────────────
  it('status=success emit refresh-complete 事件', async () => {
    mockPost.mockResolvedValue({
      data: {
        data: {
          status: 'success',
          run_id: 'run-s',
          transaction_mode: 'all_or_nothing',
          affected_count: 8,
          applied_count: 8,
          failed_count: 0,
          skipped_count: 0,
          scopes: ['report', 'note'],
          idempotent: false,
          rollback_available: true,
          warnings: [],
          failures: [],
          preset_application: { preset_count: 2, presetted_pages: ['report:BS'], pending_pages: [] },
        },
      },
    })

    const wrapper = mountDialog()
    await openDialog(wrapper)

    checkedKeysHolder.keys = ['report', 'note']
    wrapper.findComponent(ElTreeStub).vm.$emit('check')
    await nextTick()

    const confirmBtn = wrapper.findAll('button').find((b) => b.text().includes('确认刷新'))!
    await confirmBtn.trigger('click')
    await flushPromises()

    // emit refresh-complete
    const emitted = wrapper.emitted('refresh-complete')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toMatchObject({ status: 'success', applied_count: 8 })
    // 弹 success toast
    expect(mockMsgSuccess).toHaveBeenCalled()

    wrapper.unmount()
  })

  // ─── 6. 空勾选阻断（P23 回归） ────────────────────────────────────────────
  it('空勾选 → 确认按钮禁用 + 不发 POST', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)

    checkedKeysHolder.keys = []
    wrapper.findComponent(ElTreeStub).vm.$emit('check')
    await nextTick()

    expect((wrapper.vm as any).checkedScopes).toEqual([])

    const confirmBtn = wrapper.findAll('button').find((b) => b.text().includes('确认刷新'))!
    expect(confirmBtn.classes()).toContain('is-disabled')

    await confirmBtn.trigger('click')
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()

    wrapper.unmount()
  })
})
