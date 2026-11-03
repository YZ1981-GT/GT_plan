/**
 * 回收站操作列按行分支（spec advanced-query-linkage-closure 任务 25；R9.5，design §3.6 / §10.1）。
 *
 * - 按作者可见的类型（查询模板）带后端逐行能力 `can_restore` / `can_purge`：按它显示「恢复」「删除」，不经 v-permission
 *   ——模板作者多为系统 auditor，按系统角色的指令会把按钮藏掉（变异 #35）。
 * - 其余类型不带这两个键：原样保留两个 `v-permission` 按钮，判定只看前端 `ROLE_PERMISSIONS[role]`；经 `/api/users/me`
 *   取过资料的会话里 `user.permissions` 是后端权限码（`project:read` 等，没有 `recycle:*`），经理照样看得到（变异 #37：
 *   改成 `usePermission().can()` 兜底时按钮消失）。
 * 指令按 main.ts 的写法注册真实的 `vPermission`，不打桩。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, inject, provide } from 'vue'

const mocks = vi.hoisted(() => ({ stats: vi.fn(), list: vi.fn(), restore: vi.fn(), purge: vi.fn(), empty: vi.fn() }))
vi.mock('@/services/commonApi', () => ({
  getRecycleBinStats: mocks.stats,
  listRecycleBinItems: mocks.list,
  restoreRecycleBinItem: mocks.restore,
  permanentDeleteItem: mocks.purge,
  emptyRecycleBin: mocks.empty,
}))
vi.mock('@/utils/confirm', () => ({ confirmDangerous: vi.fn() }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn() } }))

import RecycleBin from '../RecycleBin.vue'
import { vPermission } from '@/directives/permission'
import { useAuthStore } from '@/stores/auth'

/** 后端 `permission_service.ROLE_PERMISSION_MATRIX["manager"]`：`/api/users/me` 下发给经理的 10 个权限码（没有 recycle:*） */
const MANAGER_BACKEND_PERMISSIONS = [
  'project:read', 'project:write', 'project:admin', 'workpaper:read', 'workpaper:write', 'workpaper:sign',
  'report:read', 'report:write', 'review:sign', 'sync:manage',
]

const ROWS = Symbol('rows')
const TableStub = defineComponent({
  props: { data: { type: Array, default: () => [] } },
  setup(props, { slots }) {
    provide(ROWS, () => props.data)
    return () => h('div', slots.default?.())
  },
})
const ColumnStub = defineComponent({
  props: { label: { type: String, default: '' } },
  setup(props, { slots }) {
    const rows = inject(ROWS) as () => any[]
    return () => h('div', { 'data-col': props.label },
      rows().map((row, i) => h('div', { class: 'cell', 'data-id': row.id }, slots.default?.({ row, $index: i }))))
  },
})
const stubs = {
  'el-table': TableStub,
  'el-table-column': ColumnStub,
  'el-button': { template: '<button class="op"><slot /></button>' },
  'el-tag': { template: '<span><slot /></span>' },
  'el-icon': { template: '<i><slot /></i>' },
  'el-alert': true,
  'el-progress': true,
  'el-pagination': true,
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio-button': { template: '<span><slot /></span>' },
}

const TEMPLATE_ROW = { id: 't1', type: 'custom_query_template', type_label: '查询模板', name: '【测试】我的模板',
  deleted_at: new Date().toISOString(), purgeable: true, can_restore: true, can_purge: true }
const PROJECT_ROW = { id: 'p1', type: 'project', type_label: '项目', name: '【测试】项目',
  deleted_at: new Date().toISOString(), purgeable: true }

/** 某行「操作」单元格里看得见的按钮文字（v-permission 不通过时是 display: none） */
async function visibleOps(user: Record<string, unknown>, items: Record<string, unknown>[]) {
  useAuthStore().user = user as any
  mocks.stats.mockResolvedValue({ total: items.length, limit: 500, is_over_limit: false, by_type: {} })
  mocks.list.mockResolvedValue({ total: items.length, items })
  const w = mount(RecycleBin, { global: { stubs, directives: { permission: vPermission, loading: {} } } })
  await flushPromises()
  const byRow: Record<string, string[]> = {}
  for (const cell of w.find('[data-col="操作"]').findAll('.cell')) {
    byRow[cell.attributes('data-id') as string] = cell.findAll('button.op')
      .filter(b => (b.element as HTMLElement).style.display !== 'none')
      .map(b => b.text())
  }
  return byRow
}

describe('回收站：操作列按行分支', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    mocks.stats.mockReset()
    mocks.list.mockReset()
  })

  it('模板行按后端逐行能力显示：系统 auditor 作者看得到「恢复」「删除」', async () => {
    const ops = await visibleOps({ id: 'u1', role: 'auditor' }, [TEMPLATE_ROW])
    expect(ops.t1).toEqual(['恢复', '删除'])
  })

  it('模板行能力为 false 时两个按钮都不渲染', async () => {
    const ops = await visibleOps({ id: 'u1', role: 'manager' },
      [{ ...TEMPLATE_ROW, can_restore: false, can_purge: false }])
    expect(ops.t1).toEqual([])
  })

  it('其余类型仍按系统角色：auditor 看不到项目行的「恢复」「删除」', async () => {
    const ops = await visibleOps({ id: 'u1', role: 'auditor' }, [PROJECT_ROW, TEMPLATE_ROW])
    expect(ops).toEqual({ p1: [], t1: ['恢复', '删除'] })
  })

  it('其余类型：经理取过 /api/users/me（后端权限码、没有 recycle:*）后照样看得到', async () => {
    const ops = await visibleOps({ id: 'u2', role: 'manager', permissions: MANAGER_BACKEND_PERMISSIONS }, [PROJECT_ROW])
    expect(ops.p1).toEqual(['恢复', '删除'])
  })
})
