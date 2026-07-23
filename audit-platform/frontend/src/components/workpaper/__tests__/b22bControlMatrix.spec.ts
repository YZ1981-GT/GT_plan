/**
 * B22B 企业层面控制矩阵登记册 — Unit Tests (Task 11.1, Wave 4)
 *
 * 方案 A：B22B 恢复为控制矩阵登记册（12 列），取代原缺陷评价表。
 *
 * 覆盖正确性属性：
 *  P2  12 列完整   —— CONTROL_POINT_FIELDS 恰含 12 列且顺序稳定；新增行 + 持久化列集合 = 12 列
 *  P3  带入仅填空 —— 从 B22A 带入控制点，已编辑行不覆盖、同名同描述不重复
 *  P10 只读封锁   —— readonly 语义在组件层（GtB22BControlMatrix.vue）拦截：控件禁用 + setter 短路不调 PUT
 *
 * 说明：useB22BControlMatrix composable 本身无 readonly 概念（readonly 在组件 handler 层拦截），
 * 故 P10 在组件 mount 层测（readonly=true → 控件禁用 + 触发 handler 不调用 PUT）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

// ─── Mock apiProxy ─────────────────────────────────────────────────────────
const mockGet = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

// ─── Mock element-plus ─────────────────────────────────────────────────────
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) },
}))

// ─── Mock 重量级子组件（P10 mount 用）─────────────────────────────────────────
vi.mock('../GtOnlyOfficeSheet.vue', () => ({ default: { name: 'GtOnlyOfficeSheet', render: () => null } }))
vi.mock('../GtReviewTrigger.vue', () => ({ default: { name: 'GtReviewTrigger', render: () => null } }))
vi.mock('../version-trail/GtWpVersionTrail.vue', () => ({ default: { name: 'GtWpVersionTrail', render: () => null } }))

// ─── Mock 复用范式 composable（避免 mount 时真实 IO / 定时器噪音）──────────────
vi.mock('../composables/useWorkpaperEntryDualMode', async () => {
  const { ref } = await import('vue')
  return {
    useWorkpaperEntryDualMode: () => ({
      mode: ref('html'),
      ooAvailable: ref(false),
      checking: ref(false),
      switchMode: vi.fn(),
      checkOOHealth: vi.fn(),
      resolveOoSheetName: () => 'B22B',
    }),
  }
})
vi.mock('../composables/useWorkpaperReviewThreads', () => ({
  useWorkpaperReviewThreads: () => ({ getThreadDot: () => null, getRowDot: () => null }),
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
  ELEMENT_OPTIONS,
  ANTI_FRAUD_OPTIONS,
  type ControlPoint,
} from '../composables/useB22BControlMatrix'

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
  mockGet.mockResolvedValue([])
  mockPut.mockResolvedValue({})
})

// ═══════════════════════════════════════════════════════════════════════════
// P2 — 12 列完整
// ═══════════════════════════════════════════════════════════════════════════

describe('B22B 控制矩阵 — P2 12 列完整', () => {
  const EXPECTED_FIELDS: (keyof ControlPoint)[] = [
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
  ]

  it('CONTROL_POINT_FIELDS 恰含 12 列且顺序严格对齐源模板', () => {
    expect(CONTROL_POINT_FIELDS).toHaveLength(12)
    expect(CONTROL_POINT_FIELDS).toEqual(EXPECTED_FIELDS)
  })

  it('枚举常量：要素 5 类 + 反舞弊 是/否', () => {
    expect(ELEMENT_OPTIONS).toHaveLength(5)
    expect(ELEMENT_OPTIONS).toContain('控制环境')
    expect(ELEMENT_OPTIONS).toContain('IT一般控制')
    expect([...ANTI_FRAUD_OPTIONS]).toEqual(['是', '否'])
  })

  it('新增行含全部 12 字段（无缺列、无多列）', () => {
    const scope = effectScope()
    scope.run(() => {
      const m = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      m.addRow()
      const row = m.rows.value[0]
      expect(Object.keys(row).sort()).toEqual([...EXPECTED_FIELDS].sort())
      for (const f of EXPECTED_FIELDS) {
        expect(f in row).toBe(true)
      }
    })
    scope.stop()
  })

  it('持久化列集合恒等于 12 列 + 行数（PUT payload = count + 12 字段/行）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const m = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      m.addRow()
      await flushPromises()

      expect(mockPut).toHaveBeenCalled()
      const payload = mockPut.mock.calls[mockPut.mock.calls.length - 1][1]
      const ids: string[] = payload.items.map((i: any) => i.item_id)

      // 行数标记
      expect(ids).toContain('B22B-row-count')
      // 恰好 12 个字段（第 0 行）
      for (const f of EXPECTED_FIELDS) {
        expect(ids).toContain(`B22B-row-0-${f}`)
      }
      const rowFieldIds = ids.filter((id) => id.startsWith('B22B-row-0-'))
      expect(rowFieldIds).toHaveLength(12)
      // 1 行 → 1 count + 12 字段 = 13 条
      expect(payload.items).toHaveLength(13)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// P3 — 从 B22A 带入仅填空（不覆盖已编辑行、同名同描述不重复）
// ═══════════════════════════════════════════════════════════════════════════

describe('B22B 控制矩阵 — P3 带入仅填空', () => {
  const b22aResponses = [
    { item_id: 'B22A-T1-item-1-point', conclusion: null, remark: '控制环境控制A', wp_ref: null },
    { item_id: 'B22A-T1-item-1-desc', conclusion: null, remark: '描述A', wp_ref: null },
    {
      item_id: 'B22A-T1-item-1-attrs',
      conclusion: null,
      remark: JSON.stringify({ antiFraud: '是', frequency: '每日' }),
      wp_ref: null,
    },
    { item_id: 'B22A-T2-item-1-point', conclusion: null, remark: '风险评估控制B', wp_ref: null },
  ]

  function stubB22AGets() {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/projects/') && url.includes('/workpapers')) {
        return Promise.resolve([{ id: 'b22a-wp-id' }])
      }
      if (url.includes('/api/workpapers/b22a-wp-id/checklist-responses')) {
        return Promise.resolve(b22aResponses)
      }
      return Promise.resolve([])
    })
  }

  it('带入生成对应行，读取控制名/描述/属性', async () => {
    stubB22AGets()
    const scope = effectScope()
    await scope.run(async () => {
      const m = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      const added = await m.pullFromB22A()
      expect(added).toBe(2)
      expect(m.rows.value).toHaveLength(2)

      const envRow = m.rows.value.find((r) => r.controlName === '控制环境控制A')!
      expect(envRow).toBeDefined()
      expect(envRow.element).toBe('控制环境')
      expect(envRow.description).toBe('描述A')
      expect(envRow.antiFraud).toBe('是')
      expect(envRow.frequency).toBe('每日')

      const riskRow = m.rows.value.find((r) => r.controlName === '风险评估控制B')!
      expect(riskRow.element).toBe('风险评估过程')
    })
    scope.stop()
  })

  it('重复带入不产生重复行（同名同描述去重）', async () => {
    stubB22AGets()
    const scope = effectScope()
    await scope.run(async () => {
      const m = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      const added1 = await m.pullFromB22A()
      expect(added1).toBe(2)
      const added2 = await m.pullFromB22A()
      expect(added2).toBe(0)
      expect(m.rows.value).toHaveLength(2)
    })
    scope.stop()
  })

  it('已编辑行不被覆盖：手工行与 B22A 同名同描述时保留手工编辑', async () => {
    stubB22AGets()
    const scope = effectScope()
    await scope.run(async () => {
      const m = useB22BControlMatrix(ref('wp-1'), ref('proj-1'))
      // 手工新增一行，与 B22A 的「控制环境控制A / 描述A」同名同描述，但 performer 是手工编辑值
      m.addRow({
        element: '控制环境',
        controlName: '控制环境控制A',
        description: '描述A',
        performer: '手工编辑人',
      })
      await flushPromises()

      const added = await m.pullFromB22A()
      // 只带入「风险评估控制B」（1 项），「控制环境控制A」已存在 → 跳过
      expect(added).toBe(1)
      expect(m.rows.value).toHaveLength(2)

      // 手工编辑行未被覆盖
      const manual = m.rows.value.find((r) => r.controlName === '控制环境控制A')!
      expect(manual.performer).toBe('手工编辑人')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// P10 — 只读封锁（组件层拦截：控件禁用 + setter 短路不调 PUT）
// ═══════════════════════════════════════════════════════════════════════════

// el-button 显式 stub：渲染 slot + 透传 disabled + 转发 click（用于验证组件层 handler 守卫）
const ElButtonStub = {
  name: 'ElButton',
  props: ['disabled', 'type', 'plain', 'size', 'text', 'link'],
  emits: ['click'],
  template: `<button class="ep-button" :disabled="disabled || undefined" @click="$emit('click', $event)"><slot/></button>`,
}

const MOUNT_STUBS = {
  'el-button': ElButtonStub,
  'el-table': true,
  'el-table-column': true,
  'el-select': true,
  'el-input': true,
  'el-option': true,
  'el-tag': true,
  'el-alert': true,
  'el-segmented': true,
}

async function mountMatrix(readonly: boolean) {
  const GtB22BControlMatrix = (await import('../GtB22BControlMatrix.vue')).default
  const wrapper = mount(GtB22BControlMatrix, {
    props: { wpId: 'wp-1', projectId: 'proj-1', wpCode: 'B22B', year: 2025, readonly },
    global: {
      stubs: MOUNT_STUBS,
      directives: { loading: {} },
    },
  })
  await flushPromises()
  return wrapper
}

function findAddButton(wrapper: any) {
  return wrapper
    .findAll('button.ep-button')
    .find((b: any) => b.text().includes('新增控制'))
}

describe('B22B 控制矩阵 — P10 只读封锁（组件层）', () => {
  it('readonly=true → 编辑控件禁用', async () => {
    const wrapper = await mountMatrix(true)
    const addBtn = findAddButton(wrapper)
    expect(addBtn).toBeTruthy()
    // 禁用态：native button disabled 属性存在
    expect(addBtn.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('readonly=false → 编辑控件可用', async () => {
    const wrapper = await mountMatrix(false)
    const addBtn = findAddButton(wrapper)
    expect(addBtn).toBeTruthy()
    expect(addBtn.attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('readonly=true → 触发新增 handler 短路，不调用 PUT（setter 不落库）', async () => {
    const wrapper = await mountMatrix(true)
    mockPut.mockClear()
    const addBtn = findAddButton(wrapper)
    await addBtn.trigger('click')
    await flushPromises()
    // handler 守卫 isReadonly → addRow 不执行 → 无 PUT
    expect(mockPut).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('readonly=false → 触发新增 handler 正常保存（对照组：调用 PUT）', async () => {
    const wrapper = await mountMatrix(false)
    mockPut.mockClear()
    const addBtn = findAddButton(wrapper)
    await addBtn.trigger('click')
    await flushPromises()
    expect(mockPut).toHaveBeenCalled()
    wrapper.unmount()
  })
})
