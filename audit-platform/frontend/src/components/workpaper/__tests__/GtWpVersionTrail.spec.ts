/**
 * GtWpVersionTrail.vue — 单元测试
 *
 * Spec: .kiro/specs/workpaper-version-trail/
 * Task: 15.2
 *
 * 测试范围：
 * - 时间线渲染正确数量的节点
 * - snapshot_type 颜色标签正确
 * - 回滚按钮仅对有权限用户显示
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import { ref, nextTick } from 'vue'

// ─── Mock http ───────────────────────────────────────────────────────────────
const mockGet = vi.fn()
const mockPost = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

// ─── Mock element-plus ───────────────────────────────────────────────────────
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockRejectedValue('cancel') },
}))

// ─── Mock stores ─────────────────────────────────────────────────────────────
let mockEffectiveRole: string | null = 'manager'
let mockAuthRole = 'manager'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { role: mockAuthRole },
  }),
}))

vi.mock('@/stores/roleContext', () => ({
  useRoleContextStore: () => ({
    effectiveRole: mockEffectiveRole,
  }),
}))

// ─── Mock formatters ─────────────────────────────────────────────────────────
vi.mock('@/utils/formatters', () => ({
  fmtDateTime: (val: string) => val || '--',
}))

import GtWpVersionTrail from '../version-trail/GtWpVersionTrail.vue'

// ─── Helpers ─────────────────────────────────────────────────────────────────

const MOCK_VERSIONS = [
  {
    id: 'v-001',
    snapshot_type: 'manual',
    description: '手动保存',
    change_summary: '新增2项',
    item_count: 10,
    data_size_bytes: 2048,
    user_id: 'u-001',
    user_name: '张三',
    created_at: '2025-06-01T10:00:00Z',
  },
  {
    id: 'v-002',
    snapshot_type: 'auto_sampling',
    description: null,
    change_summary: '抽凭快照',
    item_count: 8,
    data_size_bytes: 1500,
    user_id: 'u-002',
    user_name: '李四',
    created_at: '2025-06-01T09:00:00Z',
  },
  {
    id: 'v-003',
    snapshot_type: 'rollback',
    description: '回滚到上一版本',
    change_summary: null,
    item_count: 5,
    data_size_bytes: 800,
    user_id: 'u-001',
    user_name: '张三',
    created_at: '2025-06-01T08:00:00Z',
  },
]

function mountComponent(options?: { effectiveRole?: string | null }) {
  if (options?.effectiveRole !== undefined) {
    mockEffectiveRole = options.effectiveRole
  }

  return shallowMount(GtWpVersionTrail, {
    props: {
      workpaperId: 'wp-001',
      projectId: 'proj-001',
    },
    global: {
      stubs: {
        'el-drawer': {
          template: '<div class="el-drawer-stub"><slot /></div>',
          props: ['modelValue'],
        },
        'el-timeline': {
          template: '<div class="el-timeline-stub"><slot /></div>',
        },
        'el-timeline-item': {
          template: '<div class="el-timeline-item-stub" :data-color="color"><slot /></div>',
          props: ['timestamp', 'placement', 'color'],
        },
        'el-tag': {
          template: '<span class="el-tag-stub" :data-color="color"><slot /></span>',
          props: ['size', 'color', 'effect'],
        },
        'el-button': {
          template: '<button class="el-button-stub" :class="type" @click="$emit(\'click\')"><slot /></button>',
          props: ['type', 'loading', 'link', 'size', 'disabled'],
          emits: ['click'],
        },
        'el-input': {
          template: '<input class="el-input-stub" />',
          props: ['modelValue', 'placeholder', 'maxlength', 'clearable'],
        },
        'el-radio-group': {
          template: '<div class="el-radio-group-stub"><slot /></div>',
          props: ['modelValue', 'size'],
        },
        'el-radio': {
          template: '<label class="el-radio-stub"><slot /></label>',
          props: ['value'],
        },
        'el-empty': {
          template: '<div class="el-empty-stub">{{ description }}</div>',
          props: ['description'],
        },
        'VersionDiffPanel': true,
      },
      directives: {
        loading: () => {},
      },
    },
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// 时间线渲染正确数量的节点
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtWpVersionTrail - 时间线渲染', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAuthRole = 'manager'
    mockEffectiveRole = 'manager'
  })

  it('渲染与 versions 数量相同的 timeline-item 节点', async () => {
    mockGet.mockResolvedValue({
      data: { items: MOCK_VERSIONS, total: 3 },
    })

    const wrapper = mountComponent()

    // 通过 expose 的 openDrawer 触发加载
    const vm = wrapper.vm as any
    vm.openDrawer()
    await flushPromises()

    const items = wrapper.findAll('.el-timeline-item-stub')
    expect(items).toHaveLength(3)
  })

  it('空列表时显示空状态', async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0 },
    })

    const wrapper = mountComponent()
    const vm = wrapper.vm as any
    vm.openDrawer()
    await flushPromises()

    const empty = wrapper.find('.el-empty-stub')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('暂无版本记录')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// snapshot_type 颜色标签正确
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtWpVersionTrail - snapshot_type 颜色标签', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAuthRole = 'manager'
    mockEffectiveRole = 'manager'
  })

  it('manual 类型标签为蓝色 #409eff', async () => {
    mockGet.mockResolvedValue({
      data: { items: [MOCK_VERSIONS[0]], total: 1 },
    })

    const wrapper = mountComponent()
    const vm = wrapper.vm as any
    vm.openDrawer()
    await flushPromises()

    const tag = wrapper.find('.el-tag-stub')
    expect(tag.exists()).toBe(true)
    expect(tag.attributes('data-color')).toBe('#409eff')
    expect(tag.text()).toBe('手动保存')
  })

  it('auto_sampling 类型标签为橙色 #e6a23c', async () => {
    mockGet.mockResolvedValue({
      data: { items: [MOCK_VERSIONS[1]], total: 1 },
    })

    const wrapper = mountComponent()
    const vm = wrapper.vm as any
    vm.openDrawer()
    await flushPromises()

    const tag = wrapper.find('.el-tag-stub')
    expect(tag.exists()).toBe(true)
    expect(tag.attributes('data-color')).toBe('#e6a23c')
    expect(tag.text()).toBe('抽凭快照')
  })

  it('rollback 类型标签为红色 #f56c6c', async () => {
    mockGet.mockResolvedValue({
      data: { items: [MOCK_VERSIONS[2]], total: 1 },
    })

    const wrapper = mountComponent()
    const vm = wrapper.vm as any
    vm.openDrawer()
    await flushPromises()

    const tag = wrapper.find('.el-tag-stub')
    expect(tag.exists()).toBe(true)
    expect(tag.attributes('data-color')).toBe('#f56c6c')
    expect(tag.text()).toBe('回滚')
  })

  it('timeline-item 节点 color 属性正确', async () => {
    mockGet.mockResolvedValue({
      data: { items: MOCK_VERSIONS, total: 3 },
    })

    const wrapper = mountComponent()
    const vm = wrapper.vm as any
    vm.openDrawer()
    await flushPromises()

    const items = wrapper.findAll('.el-timeline-item-stub')
    expect(items[0].attributes('data-color')).toBe('#409eff')  // manual
    expect(items[1].attributes('data-color')).toBe('#e6a23c')  // auto_sampling
    expect(items[2].attributes('data-color')).toBe('#f56c6c')  // rollback
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 回滚按钮仅对有权限用户显示
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtWpVersionTrail - 回滚按钮权限', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('manager 角色可看到回滚按钮', async () => {
    mockEffectiveRole = 'manager'
    mockAuthRole = 'manager'
    mockGet.mockResolvedValue({
      data: { items: [MOCK_VERSIONS[0]], total: 1 },
    })

    const wrapper = mountComponent({ effectiveRole: 'manager' })
    const vm = wrapper.vm as any
    vm.openDrawer()
    await flushPromises()

    const buttons = wrapper.findAll('.el-button-stub')
    const rollbackBtn = buttons.find(b => b.text() === '回滚')
    expect(rollbackBtn).toBeDefined()
  })

  it('assistant 角色看不到回滚按钮', async () => {
    mockEffectiveRole = 'assistant'
    mockAuthRole = 'assistant'
    mockGet.mockResolvedValue({
      data: { items: [MOCK_VERSIONS[0]], total: 1 },
    })

    const wrapper = mountComponent({ effectiveRole: 'assistant' })
    const vm = wrapper.vm as any
    vm.openDrawer()
    await flushPromises()

    const buttons = wrapper.findAll('.el-button-stub')
    const rollbackBtn = buttons.find(b => b.text() === '回滚')
    expect(rollbackBtn).toBeUndefined()
  })

  it('admin 角色可看到回滚按钮', async () => {
    mockEffectiveRole = 'admin'
    mockAuthRole = 'admin'
    mockGet.mockResolvedValue({
      data: { items: [MOCK_VERSIONS[0]], total: 1 },
    })

    const wrapper = mountComponent({ effectiveRole: 'admin' })
    const vm = wrapper.vm as any
    vm.openDrawer()
    await flushPromises()

    const buttons = wrapper.findAll('.el-button-stub')
    const rollbackBtn = buttons.find(b => b.text() === '回滚')
    expect(rollbackBtn).toBeDefined()
  })
})
