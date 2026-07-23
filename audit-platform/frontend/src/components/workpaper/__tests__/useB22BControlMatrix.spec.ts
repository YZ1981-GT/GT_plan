/**
 * useB22BControlMatrix — B22B 控制矩阵登记册 单元测试 (Task 11.1)
 *
 * 覆盖属性：
 *  P2  12 列 Control_Point 模型（列集合/顺序稳定 + 持久化 item_id 结构）
 *  P3  从 B22A 带入控制点（仅填空、按 controlName+description 去重、不覆盖已编辑行）
 *  P10 只读封锁（readonly 态下编辑控件短路、不触发 PUT）—— readonly 由组件 GtB22BControlMatrix 承载
 *
 * 说明：useB22BControlMatrix 本身不含 readonly（design：只读封锁在组件层），故 P10 通过
 * shallowMount GtB22BControlMatrix.vue 校验真实守卫行为，不臆造 composable API。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { shallowMount, flushPromises } from '@vue/test-utils'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), info: vi.fn(), success: vi.fn() },
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) },
}))

// 组件依赖的其它 workpaper composable（P10 mount 时用）—— 仅 mock 这些，保留被测 useB22BControlMatrix 真实
vi.mock('../composables/useWorkpaperEntryDualMode', async () => {
  const { ref } = await import('vue')
  return {
    useWorkpaperEntryDualMode: () => ({
      mode: ref('html'),
      switchMode: vi.fn(),
      ooAvailable: ref(false),
      checking: ref(false),
    }),
  }
})
vi.mock('../composables/useWorkpaperReviewThreads', () => ({
  useWorkpaperReviewThreads: () => ({ getThreadDot: vi.fn(), getRowDot: vi.fn() }),
}))
vi.mock('../composables/useWorkpaperVersionToolbar', async () => {
  const { ref } = await import('vue')
  return {
    useWorkpaperVersionToolbar: () => ({
      versionTrailRef: ref(null),
      openVersionHistory: vi.fn(),
      scheduleAutoSnapshot: vi.fn(),
    }),
  }
})

import {
  useB22BControlMatrix,
  CONTROL_POINT_FIELDS,
  type ControlPoint,
} from '../composables/useB22BControlMatrix'

// ═══════════════════════════════════════════════════════════════════════════════
// P2 — 12 列 Control_Point 模型
// ═══════════════════════════════════════════════════════════════════════════════

describe('useB22BControlMatrix — 12 列 Control_Point 模型 (P2)', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPut.mockReset()
    mockGet.mockResolvedValue([])
    mockPut.mockResolvedValue({})
  })

  it('CONTROL_POINT_FIELDS 恒为源模板 12 列，顺序稳定', () => {
    expect(CONTROL_POINT_FIELDS).toEqual([
      'element',
      'subCategory',
      'code',
      'controlName',
      'description',
      'antiFraud',
      'frequency',
      'performer',
      'competence',
      'relatedRisk',
      'nature',
      'itApp',
    ])
    expect(CONTROL_POINT_FIELDS).toHaveLength(12)
  })

  it('addRow 新增一行含全部 12 字段（初始为空）', () => {
    const scope = effectScope()
    scope.run(() => {
      const c = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      c.addRow()
      expect(c.rows.value).toHaveLength(1)
      const row = c.rows.value[0]
      for (const f of CONTROL_POINT_FIELDS) {
        expect(row).toHaveProperty(f)
        expect((row[f as keyof ControlPoint] as string)).toBe('')
      }
    })
    scope.stop()
  })

  it('持久化 item_id 结构 = B22B-row-count + B22B-row-{n}-{field}（12 字段/行，且不传 project_id）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const c = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      c.addRow()
      await flushPromises()

      expect(mockPut).toHaveBeenCalled()
      const [url, body] = mockPut.mock.calls[mockPut.mock.calls.length - 1]
      expect(url).toBe('/api/workpapers/wp-1/checklist-responses')
      // 绝不传 project_id（避免 422 project_mismatch）
      expect(body).not.toHaveProperty('project_id')

      const ids: string[] = body.items.map((it: any) => it.item_id)
      expect(ids).toContain('B22B-row-count')
      for (const f of CONTROL_POINT_FIELDS) {
        expect(ids).toContain(`B22B-row-0-${f}`)
      }
      // 每行恰好 12 个字段 item + 1 个 count
      expect(body.items.filter((it: any) => it.item_id.startsWith('B22B-row-0-'))).toHaveLength(12)
      const countItem = body.items.find((it: any) => it.item_id === 'B22B-row-count')
      expect(countItem.remark).toBe('1')
    })
    scope.stop()
  })

  it('updateField 写入枚举/文本字段并持久化对应值', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const c = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      c.addRow()
      await flushPromises()
      mockPut.mockClear()

      // 枚举字段（即时保存）
      c.updateField(0, 'element', '控制环境')
      expect(c.rows.value[0].element).toBe('控制环境')
      await flushPromises()
      expect(mockPut).toHaveBeenCalled()
      const body = mockPut.mock.calls[mockPut.mock.calls.length - 1][1]
      const elItem = body.items.find((it: any) => it.item_id === 'B22B-row-0-element')
      expect(elItem.remark).toBe('控制环境')
    })
    scope.stop()
  })

  it('loadAll 按 count 重建 12 列行', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      mockGet.mockResolvedValue([
        { item_id: 'B22B-row-count', conclusion: null, remark: '1', wp_ref: null },
        { item_id: 'B22B-row-0-element', conclusion: null, remark: '监督', wp_ref: null },
        { item_id: 'B22B-row-0-controlName', conclusion: null, remark: '内审复核', wp_ref: null },
        { item_id: 'B22B-row-0-antiFraud', conclusion: null, remark: '是', wp_ref: null },
      ])
      const c = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      await c.loadAll()
      expect(c.rows.value).toHaveLength(1)
      expect(c.rows.value[0].element).toBe('监督')
      expect(c.rows.value[0].controlName).toBe('内审复核')
      expect(c.rows.value[0].antiFraud).toBe('是')
      // 未提供的字段回退空
      expect(c.rows.value[0].itApp).toBe('')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P3 — 从 B22A 带入控制点（仅填空、去重）
// ═══════════════════════════════════════════════════════════════════════════════

describe('useB22BControlMatrix — 从 B22A 带入仅填空去重 (P3)', () => {
  const B22A_RESPONSES = [
    { item_id: 'B22A-T1-item-1-point', conclusion: null, remark: '控制环境控制A', wp_ref: null },
    { item_id: 'B22A-T1-item-1-desc', conclusion: null, remark: '描述A', wp_ref: null },
    { item_id: 'B22A-T2-item-1-point', conclusion: null, remark: '风险评估控制B', wp_ref: null },
    { item_id: 'B22A-T2-item-1-desc', conclusion: null, remark: '描述B', wp_ref: null },
  ]

  beforeEach(() => {
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
    // 路由：projects/{id}/workpapers?wp_code=B22A → 返回 B22A wp；B22A wp 的 checklist → 控制点
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/projects/') && url.includes('/workpapers')) {
        return Promise.resolve([{ id: 'b22a-wp' }])
      }
      if (url.includes('/workpapers/b22a-wp/checklist-responses')) {
        return Promise.resolve(B22A_RESPONSES)
      }
      // 被测 wp 自身 loadAll
      return Promise.resolve([])
    })
  })

  it('首次带入：解析 B22A 控制点为矩阵行', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const c = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      const added = await c.pullFromB22A()
      expect(added).toBe(2)
      expect(c.rows.value).toHaveLength(2)
      const names = c.rows.value.map((r) => r.controlName)
      expect(names).toContain('控制环境控制A')
      expect(names).toContain('风险评估控制B')
      // 要素映射（T1→控制环境、T2→风险评估过程）
      const a = c.rows.value.find((r) => r.controlName === '控制环境控制A')!
      expect(a.element).toBe('控制环境')
      expect(a.description).toBe('描述A')
    })
    scope.stop()
  })

  it('重复带入去重：第二次带入 added=0，不产生重复行', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const c = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      const first = await c.pullFromB22A()
      expect(first).toBe(2)
      const second = await c.pullFromB22A()
      expect(second).toBe(0)
      expect(c.rows.value).toHaveLength(2)
    })
    scope.stop()
  })

  it('仅填空不覆盖已编辑：同 controlName+description 的已存在行被去重跳过', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const c = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      // 预置一行与 B22A 控制A 同 key（controlName+description）且已编辑其它字段
      c.addRow({ controlName: '控制环境控制A', description: '描述A', frequency: '每月', performer: '财务经理' })
      await flushPromises()

      const added = await c.pullFromB22A()
      // 控制A 去重跳过，仅带入控制B
      expect(added).toBe(1)
      expect(c.rows.value).toHaveLength(2)
      // 已编辑行未被覆盖
      const a = c.rows.value.find((r) => r.controlName === '控制环境控制A')!
      expect(a.frequency).toBe('每月')
      expect(a.performer).toBe('财务经理')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P10 — 只读封锁（组件层守卫）
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtB22BControlMatrix — 只读封锁 (P10)', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPut.mockReset()
    mockGet.mockResolvedValue([]) // loadAll → 空
    mockPut.mockResolvedValue({})
  })

  async function mountComp(readonly: boolean) {
    const GtB22BControlMatrix = (await import('../GtB22BControlMatrix.vue')).default
    const wrapper = shallowMount(GtB22BControlMatrix, {
      props: { wpId: 'wp-1', projectId: 'proj-1', wpCode: 'B22B', year: 2025, readonly },
      global: {
        stubs: {
          'el-table': { template: '<div class="el-table-stub"><slot /></div>' },
          'el-table-column': { template: '<div class="el-table-column-stub" />' },
        },
      },
    })
    await flushPromises()
    return wrapper
  }

  it('readonly=true：isReadonly 为真，编辑控件短路不触发 PUT', async () => {
    const wrapper = await mountComp(true)
    const vm: any = wrapper.vm
    expect(vm.isReadonly).toBe(true)
    mockPut.mockClear()

    // 新增行守卫
    vm.handleAddRow()
    await flushPromises()
    expect(vm.rows.length).toBe(0)
    expect(mockPut).not.toHaveBeenCalled()

    // 字段编辑守卫（即使有行也不写入）—— 直接调用 handler 应短路
    vm.handleFieldChange(0, 'element', '控制环境')
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()

    // 从 B22A 带入守卫
    await vm.handlePullFromB22A()
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()
    expect(vm.rows.length).toBe(0)
  })

  it('readonly=false：编辑控件正常触发 PUT（正向对照）', async () => {
    const wrapper = await mountComp(false)
    const vm: any = wrapper.vm
    expect(vm.isReadonly).toBe(false)
    mockPut.mockClear()

    vm.handleAddRow()
    await flushPromises()
    expect(vm.rows.length).toBe(1)
    expect(mockPut).toHaveBeenCalled()
  })
})
