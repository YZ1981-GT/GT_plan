/**
 * GtRefreshScopeDialog.spec.ts — 合伙人全局一键刷新勾选弹窗 示例测试 + P23
 *
 * spec formula-management-library Task 18.2（Req 19.1-19.6）
 *
 * 示例（不得假绿）：
 *  ① 弹窗含 报表 / 底稿 / 调整分录 / 附注 基础项（Req 19.3）
 *  ② 底稿按循环展开为各循环子项（Req 19.4）
 *  ③ 合伙人可见入口 / 非合伙人不可见入口（Req 19.1 / 19.2）
 *
 * Feature: formula-management-library, Property 23: 空勾选阻断刷新
 *   对任意"空勾选"等价集合（无勾选 / 仅合成父节点）→ 禁止提交（确认刷新禁用）、
 *   不触发刷新（不发 POST /draft-refresh）、无请求 / 无留痕。
 *   **Validates: Requirements 19.5**
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, ref, nextTick, type Ref } from 'vue'
import * as fc from 'fast-check'

// ─── ResizeObserver polyfill（Element Plus 部分组件在 jsdom 下需要） ────────────
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
  // 可变角色：控制合伙人 / 非合伙人两态
  roleHolder: { role: 'partner' as string },
  // el-tree.getCheckedKeys(true) 的受控返回（模拟勾选态）
  checkedKeysHolder: { keys: [] as string[] },
}))

// http（axios 封装，默认导出）：get 返回 refresh-scopes 桩，post 断言不被调用（空勾选）
vi.mock('@/utils/http', () => ({
  default: { get: mockGet, post: mockPost },
}))

// 前端门禁：mock usePermissionMatrix.currentRole（合伙人 vs 非合伙人）
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

const WORKPAPER_GROUP_KEY = '__workpaper_group__'

// ─── Stubs ────────────────────────────────────────────────────────────────────
// ElDialog：无条件渲染默认 + footer 插槽（不受 modelValue 限制，便于断言内容）
const ElDialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false }, title: { type: String, default: '' } },
  template: '<div class="el-dialog-stub"><slot /><slot name="footer" /></div>',
})

// ElTree：递归渲染 label（供文本断言）+ 暴露 getCheckedKeys（受控）+ 可 emit check
const ElTreeStub = defineComponent({
  name: 'ElTree',
  props: { data: { type: Array as () => any[], default: () => [] } },
  emits: ['check'],
  methods: {
    // 组件调用 treeRef.value.getCheckedKeys(true)
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

const STUBS = {
  ElDialog: ElDialogStub,
  ElTree: ElTreeStub,
} as const

// refresh-scopes 发现端点桩：覆盖 报表 / 底稿(按循环) / 调整分录 / 附注
const SCOPE_ITEMS = [
  { key: 'report', label: '报表', group: 'report' },
  { key: 'adjustment', label: '调整分录', group: 'adjustment' },
  { key: 'note', label: '附注', group: 'note' },
  { key: 'workpaper:D', label: 'D 类循环底稿', group: 'workpaper', cycle: 'D' },
  { key: 'workpaper:E', label: 'E 类循环底稿', group: 'workpaper', cycle: 'E' },
  { key: 'workpaper:F', label: 'F 类循环底稿', group: 'workpaper', cycle: 'F' },
]

function mountDialog(props: Record<string, unknown> = {}): VueWrapper {
  return mount(GtRefreshScopeDialog, {
    props: { projectId: 'proj-1', year: 2025, ...props },
    global: { plugins: [ElementPlus], stubs: STUBS },
  })
}

async function openDialog(wrapper: VueWrapper) {
  await (wrapper.vm as any).openDialog()
  await flushPromises()
  await nextTick()
}

// ══════════════════════════════════════════════════════════════════════════════
describe('GtRefreshScopeDialog — 示例（Req 19.1-19.6）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    roleHolder.role = 'partner'
    checkedKeysHolder.keys = []
    mockGet.mockResolvedValue({ data: { data: { items: SCOPE_ITEMS } } })
    mockPost.mockResolvedValue({ data: { data: { affected_count: 3, result_status: 'success' } } })
  })

  // ── ① 弹窗含 报表 / 底稿 / 调整分录 / 附注（Req 19.3） ────────────────────────
  it('弹窗渲染 报表 / 底稿 / 调整分录 / 附注 基础项', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)

    const text = wrapper.text()
    expect(text).toContain('报表')
    expect(text).toContain('调整分录')
    expect(text).toContain('附注')
    // 底稿域为合成父节点「底稿（按循环）」
    expect(text).toContain('底稿')
    expect(mockGet).toHaveBeenCalledWith(
      '/api/workpapers/refresh-scopes',
      { params: { project_id: 'proj-1', year: 2025 } },
    )
    wrapper.unmount()
  })

  // ── ② 底稿按循环展开为各循环子项（Req 19.4） ──────────────────────────────────
  it('底稿域展开为各循环子项（workpaper:{cycle}）', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)

    // 合成父节点存在
    const groupNode = wrapper.find(`[data-key="${WORKPAPER_GROUP_KEY}"]`)
    expect(groupNode.exists()).toBe(true)

    // 各循环子叶存在（可按循环单独勾选，而非只能整选全部底稿）
    expect(wrapper.find('[data-key="workpaper:D"]').exists()).toBe(true)
    expect(wrapper.find('[data-key="workpaper:E"]').exists()).toBe(true)
    expect(wrapper.find('[data-key="workpaper:F"]').exists()).toBe(true)

    const text = wrapper.text()
    expect(text).toContain('D 类循环底稿')
    expect(text).toContain('E 类循环底稿')
    wrapper.unmount()
  })

  // ── ③ 合伙人可见 / 非合伙人不可见入口（Req 19.1 / 19.2） ──────────────────────
  it('合伙人角色渲染「全局一键刷新」入口按钮', () => {
    roleHolder.role = 'partner'
    const wrapper = mountDialog()
    expect((wrapper.vm as any).isPartner).toBe(true)
    expect(wrapper.find('.gt-rsd-entry').exists()).toBe(true)
    wrapper.unmount()
  })

  it('signing_partner 角色同样渲染入口按钮', () => {
    roleHolder.role = 'signing_partner'
    const wrapper = mountDialog()
    expect((wrapper.vm as any).isPartner).toBe(true)
    expect(wrapper.find('.gt-rsd-entry').exists()).toBe(true)
    wrapper.unmount()
  })

  it('非合伙人角色（auditor / manager / admin）不渲染入口按钮', () => {
    for (const role of ['auditor', 'manager', 'admin']) {
      roleHolder.role = role
      const wrapper = mountDialog()
      expect((wrapper.vm as any).isPartner).toBe(false)
      expect(wrapper.find('.gt-rsd-entry').exists()).toBe(false)
      wrapper.unmount()
    }
  })

  // ── 正向对照：非空勾选 → 确认刷新发起 POST（证明 P23 非平凡绿） ────────────────
  it('勾选非空 → 确认刷新按钮启用并 POST /draft-refresh', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)

    // 模拟勾选 report 叶子
    checkedKeysHolder.keys = ['report']
    wrapper.findComponent(ElTreeStub).vm.$emit('check')
    await nextTick()
    expect((wrapper.vm as any).checkedScopes).toEqual(['report'])

    const confirmBtn = wrapper
      .findAll('button')
      .find((b) => b.text().includes('确认刷新'))!
    expect(confirmBtn.classes()).not.toContain('is-disabled')

    await confirmBtn.trigger('click')
    await flushPromises()

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/api/workpapers/draft-refresh', {
      project_id: 'proj-1',
      year: 2025,
      scopes: ['report'],
      confirm_overwrite: false,
    })
    wrapper.unmount()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Feature: formula-management-library, Property 23: 空勾选阻断刷新
//   对任意空勾选等价集合 → 禁止提交、不触发刷新（不发 POST /draft-refresh）、无请求/无留痕。
//   Validates: Requirements 19.5
describe('GtRefreshScopeDialog — Property 23：空勾选阻断刷新（Req 19.5）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    roleHolder.role = 'partner'
    checkedKeysHolder.keys = []
    mockGet.mockResolvedValue({ data: { data: { items: SCOPE_ITEMS } } })
    mockPost.mockResolvedValue({ data: { data: { affected_count: 0, result_status: 'success' } } })
  })

  it('任意"空勾选"等价集合（无勾选 / 仅合成父节点）→ 禁用确认 + 不发起任何请求', async () => {
    // 生成空勾选等价态：仅由合成父节点 key 组成（0..n 个），过滤后必为空
    const emptyEquivalentArb = fc.array(fc.constant(WORKPAPER_GROUP_KEY), {
      minLength: 0,
      maxLength: 4,
    })

    await fc.assert(
      fc.asyncProperty(emptyEquivalentArb, async (checked) => {
        const wrapper = mountDialog()
        await openDialog(wrapper)

        // clear 掉 openDialog 期间的 get 调用，聚焦断言"确认阶段无 POST"
        mockPost.mockClear()

        // 施加"空勾选"等价态
        checkedKeysHolder.keys = checked
        wrapper.findComponent(ElTreeStub).vm.$emit('check')
        await nextTick()

        // 过滤合成父节点后勾选集合必为空
        expect((wrapper.vm as any).checkedScopes).toEqual([])

        // 「确认刷新」按钮禁用（禁止提交）
        const confirmBtn = wrapper
          .findAll('button')
          .find((b) => b.text().includes('确认刷新'))!
        expect(confirmBtn.classes()).toContain('is-disabled')

        // 尝试点击 → 不触发刷新、不发 POST（无请求/无留痕）
        await confirmBtn.trigger('click')
        await flushPromises()
        expect(mockPost).not.toHaveBeenCalled()

        wrapper.unmount()
      }),
      { numRuns: 20 },
    )
  })
})
