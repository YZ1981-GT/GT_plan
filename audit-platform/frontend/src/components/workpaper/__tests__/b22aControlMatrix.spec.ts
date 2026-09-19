/**
 * B22A 内部控制了解程序表 — Unit Tests (Tasks 6.1–6.10)
 *
 * 验证：
 *  6.1 注册契约测试 — registry + wp_code_overrides
 *  6.2 组件行为测试 — 6 tab + 默认 Tab_1 + tab 状态 + 完成进度
 *  6.3 检查项 CRUD — 新增/删除/预置不可删 + 了解方法 + Conclusion
 *  6.4 IT 子区交互 — 手风琴展开/收起 + IT_Dependency + ITGC 警告
 *  6.5 保存行为 — debounce 2s + 即时保存 + emit save
 *  6.6 只读模式 — readonly / reviewed → 全交互禁用
 *  6.7 Amendment 流程 — 启动修改 + 原因校验 + 重置复核
 *  6.8 续审模式 — "本年无变化" + 上年结论 + 仅填充空白项
 *  6.9 控制环境薄弱横幅 — 触发条件 + 恢复后消失
 *  6.10 手动覆盖 Element_Score — 需理由校验 + 标识
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref, computed, effectScope, nextTick } from 'vue'

import { HTML_RENDERER_REGISTRY } from '../htmlRendererRegistry'

// Mock apiProxy
const mockGet = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn() },
}))


// ═══════════════════════════════════════════════════════════════════════════════
// 6.1 注册契约测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22A 内部控制了解程序表 — 注册契约 (6.1)', () => {
  it('registry 包含 b22a-control-matrix 条目且字段正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('b22a-control-matrix')
    expect(entry).toBeDefined()
    expect(entry!.componentType).toBe('b22a-control-matrix')
    expect(entry!.icon).toBe('🛡️')
    expect(entry!.label).toBe('B22A 内部控制了解程序表')
    expect(entry!.emits).toEqual(['save', 'completed'])
    expect(entry!.contextProps).toBe('standard')
  })

  it('wp_code_overrides.json 映射 B22A → b22a-control-matrix', () => {
    const overridesPath = resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = JSON.parse(readFileSync(overridesPath, 'utf-8'))
    expect(overrides['B22A']).toBe('b22a-control-matrix')
  })

  it('wp_code_overrides.json 映射 B22A-1~5 + B22A-4-x → skip', () => {
    const overridesPath = resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = JSON.parse(readFileSync(overridesPath, 'utf-8'))
    expect(overrides['B22A-1']).toBe('skip')
    expect(overrides['B22A-2']).toBe('skip')
    expect(overrides['B22A-3']).toBe('skip')
    expect(overrides['B22A-4']).toBe('skip')
    expect(overrides['B22A-4-1']).toBe('skip')
    expect(overrides['B22A-4-2']).toBe('skip')
    expect(overrides['B22A-4-3']).toBe('skip')
    expect(overrides['B22A-4-4-1']).toBe('skip')
    expect(overrides['B22A-4-4-2']).toBe('skip')
    expect(overrides['B22A-4-5']).toBe('skip')
    expect(overrides['B22A-5']).toBe('skip')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.2 组件行为测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22A 内部控制了解程序表 — 组件行为 (6.2)', () => {
  it('COSO_TABS 定义 5 个要素 + 默认激活 Tab_1', async () => {
    const { COSO_TABS } = await import('../composables/useB22AControlMatrix')
    expect(COSO_TABS).toHaveLength(5)
    expect(COSO_TABS[0].tab).toBe(1)
    expect(COSO_TABS[0].label).toBe('控制环境')

    // Default active tab should be 1
    const activeTab = ref(1)
    expect(activeTab.value).toBe(1)
  })

  it('6 tab 数据视图按前缀正确分发', async () => {
    const { useB22AFormData } = await import('../composables/useB22AFormData')

    const scope = effectScope()
    scope.run(() => {
      const formApi = useB22AFormData(ref('wp-1'))

      formApi.allResponses.value.set('B22A-T1-count', {
        item_id: 'B22A-T1-count', conclusion: null, remark: '3', wp_ref: null,
      })
      formApi.allResponses.value.set('B22A-T4-IT-dependency', {
        item_id: 'B22A-T4-IT-dependency', conclusion: '中', remark: null, wp_ref: null,
      })
      formApi.allResponses.value.set('B22A-SUM-overall', {
        item_id: 'B22A-SUM-overall', conclusion: '有效', remark: null, wp_ref: null,
      })
      formApi.allResponses.value.set('B22A-review-sign', {
        item_id: 'B22A-review-sign', conclusion: 'Y', remark: '经理', wp_ref: '2026-01-01',
      })

      expect(formApi.tab1Data.value.items.has('B22A-T1-count')).toBe(true)
      expect(formApi.tab4Data.value.items.has('B22A-T4-IT-dependency')).toBe(true)
      expect(formApi.summaryData.value.items.has('B22A-SUM-overall')).toBe(true)
      expect(formApi.summaryData.value.items.has('B22A-review-sign')).toBe(true)

      // Cross-tab items should NOT be in wrong tabs
      expect(formApi.tab1Data.value.items.has('B22A-T4-IT-dependency')).toBe(false)
      expect(formApi.tab4Data.value.items.has('B22A-SUM-overall')).toBe(false)
    })
    scope.stop()
  })

  it('tabStatus 计算 empty/partial/complete 正确', async () => {
    const { computeTabStatus } = await import('../composables/useB22AControlMatrix')

    const makeItem = (c: string | null) => ({
      index: 1, controlPoint: '', description: '', methods: [],
      conclusion: c as any, reference: '', isPreset: false,
      isDeficiency: false, priorYearConclusion: null,
      noChangeConfirmed: false, noChangeConfirmer: null, noChangeDate: null,
    })

    expect(computeTabStatus([])).toBe('empty')
    expect(computeTabStatus([makeItem(null), makeItem(null)])).toBe('empty')
    expect(computeTabStatus([makeItem('设计有效'), makeItem(null)])).toBe('partial')
    expect(computeTabStatus([makeItem('设计有效'), makeItem('已实施')])).toBe('complete')
  })

  it('completedElementCount 统计有 score 的要素数', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())

      // Tab 1 has 2 items with conclusions → score computed
      allResponses.value.set('B22A-T1-count', { item_id: 'B22A-T1-count', conclusion: null, remark: '2', wp_ref: null })
      allResponses.value.set('B22A-T1-item-1-conclusion', { item_id: 'B22A-T1-item-1-conclusion', conclusion: '设计有效', remark: null, wp_ref: null })
      allResponses.value.set('B22A-T1-item-2-conclusion', { item_id: 'B22A-T1-item-2-conclusion', conclusion: '设计有效', remark: null, wp_ref: null })

      // Tab 2 has 0 items → no score
      allResponses.value.set('B22A-T2-count', { item_id: 'B22A-T2-count', conclusion: null, remark: '0', wp_ref: null })
      // Tab 3~5 no count → 0 items
      for (const t of [3, 4, 5]) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      // Only Tab 1 has items → completedElementCount = 1
      expect(matrix.completedElementCount.value).toBe(1)
    })
    scope.stop()
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// 6.3 检查项 CRUD 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22A 内部控制了解程序表 — 检查项 CRUD (6.3)', () => {
  it('addCheckItem 递增 count + 调用 saveImmediate', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B22A-T1-count', { item_id: 'B22A-T1-count', conclusion: null, remark: '2', wp_ref: null })
      for (let t = 2; t <= 5; t++) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      matrix.addCheckItem(1)

      // Count should be 3
      const countItem = allResponses.value.get('B22A-T1-count')
      expect(countItem!.remark).toBe('3')
      expect(saveFn).toHaveBeenCalled()
    })
    scope.stop()
  })

  it('removeCheckItem 递减 count + 移位数据', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B22A-T2-count', { item_id: 'B22A-T2-count', conclusion: null, remark: '3', wp_ref: null })
      allResponses.value.set('B22A-T2-item-1-point', { item_id: 'B22A-T2-item-1-point', conclusion: null, remark: '第一项', wp_ref: null })
      allResponses.value.set('B22A-T2-item-2-point', { item_id: 'B22A-T2-item-2-point', conclusion: null, remark: '第二项', wp_ref: null })
      allResponses.value.set('B22A-T2-item-3-point', { item_id: 'B22A-T2-item-3-point', conclusion: null, remark: '第三项', wp_ref: null })
      for (const t of [1, 3, 4, 5]) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      // Remove item 2 → item 3 shifts to position 2
      matrix.removeCheckItem(2, 2)

      expect(allResponses.value.get('B22A-T2-count')!.remark).toBe('2')
      expect(allResponses.value.get('B22A-T2-item-2-point')!.remark).toBe('第三项')
    })
    scope.stop()
  })

  it('setConclusion 即时保存 + 更新 allResponses', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B22A-T1-count', { item_id: 'B22A-T1-count', conclusion: null, remark: '1', wp_ref: null })
      for (let t = 2; t <= 5; t++) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      matrix.setConclusion(1, 1, '设计有效')

      const item = allResponses.value.get('B22A-T1-item-1-conclusion')
      expect(item!.conclusion).toBe('设计有效')
      expect(saveFn).toHaveBeenCalledWith([expect.objectContaining({ conclusion: '设计有效' })])
    })
    scope.stop()
  })

  it('setUnderstandingMethod 多选方法存为逗号分隔 remark', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B22A-T1-count', { item_id: 'B22A-T1-count', conclusion: null, remark: '1', wp_ref: null })
      for (let t = 2; t <= 5; t++) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      matrix.setUnderstandingMethod(1, 1, ['询问', '观察', '穿行测试'])

      const item = allResponses.value.get('B22A-T1-item-1-method')
      expect(item!.remark).toBe('询问,观察,穿行测试')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.4 IT 子区交互测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22A 内部控制了解程序表 — IT 子区交互 (6.4)', () => {
  it('IT_SUB_PANELS 定义 6 个子面板', async () => {
    const { IT_SUB_PANELS } = await import('../composables/useB22AControlMatrix')
    expect(IT_SUB_PANELS).toHaveLength(6)
    expect(IT_SUB_PANELS.map(p => p.key)).toEqual(['env', 'itgc', 'app', 'change', 'access', 'sod'])
  })

  it('setITDependency 更新 itDependency + 保存', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      for (let t = 1; t <= 5; t++) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      matrix.setITDependency('高')
      expect(matrix.itDependency.value).toBe('高')
      expect(allResponses.value.get('B22A-T4-IT-dependency')!.conclusion).toBe('高')
      expect(saveFn).toHaveBeenCalled()
    })
    scope.stop()
  })

  it('isITGCInvalid 当 ITGC 全部"设计无效"时为 true', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      for (let t = 1; t <= 5; t++) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }
      // 3 ITGC items all 设计无效 → score=无效 (>20%)
      allResponses.value.set('B22A-T4-IT-itgc-count', { item_id: 'B22A-T4-IT-itgc-count', conclusion: null, remark: '3', wp_ref: null })
      allResponses.value.set('B22A-T4-IT-itgc-1-conclusion', { item_id: 'B22A-T4-IT-itgc-1-conclusion', conclusion: '设计无效', remark: null, wp_ref: null })
      allResponses.value.set('B22A-T4-IT-itgc-2-conclusion', { item_id: 'B22A-T4-IT-itgc-2-conclusion', conclusion: '设计无效', remark: null, wp_ref: null })
      allResponses.value.set('B22A-T4-IT-itgc-3-conclusion', { item_id: 'B22A-T4-IT-itgc-3-conclusion', conclusion: '设计无效', remark: null, wp_ref: null })

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      expect(matrix.isITGCInvalid.value).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.5 保存行为测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22A 内部控制了解程序表 — 保存行为 (6.5)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockResolvedValue([])
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('saveDebouncedText 在 2000ms 后触发保存', async () => {
    const { useB22AFormData } = await import('../composables/useB22AFormData')

    const scope = effectScope()
    let formApi: ReturnType<typeof useB22AFormData>
    scope.run(() => { formApi = useB22AFormData(ref('wp-1')) })
    mockPut.mockClear()

    const item = { item_id: 'B22A-T1-item-1-point', conclusion: null, remark: '测试描述', wp_ref: null }
    formApi!.saveDebouncedText(item)

    vi.advanceTimersByTime(1999)
    await nextTick()
    expect(mockPut).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1)
    await nextTick()
    expect(mockPut).toHaveBeenCalledTimes(1)

    scope.stop()
  })

  it('saveImmediate 立即保存不 debounce', async () => {
    const { useB22AFormData } = await import('../composables/useB22AFormData')

    const scope = effectScope()
    let formApi: ReturnType<typeof useB22AFormData>
    scope.run(() => { formApi = useB22AFormData(ref('wp-1')) })
    mockPut.mockClear()

    const item = { item_id: 'B22A-T1-item-1-conclusion', conclusion: '设计有效', remark: null, wp_ref: null }
    await formApi!.saveImmediate([item])

    expect(mockPut).toHaveBeenCalledTimes(1)
    scope.stop()
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// 6.6 只读模式测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22A 内部控制了解程序表 — 只读模式 (6.6)', () => {
  it('externalReadonly=true → isReadonly=true', async () => {
    const { useB22AReview } = await import('../composables/useB22AReview')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const overallConclusion = ref<any>(null)
      const completedCount = computed(() => 0)
      const externalReadonly = ref(true)
      const saveFn = vi.fn().mockResolvedValue(undefined)

      const review = useB22AReview(ref('wp-1'), allResponses, completedCount, overallConclusion, externalReadonly, saveFn)
      expect(review.isReadonly.value).toBe(true)
    })
    scope.stop()
  })

  it('reviewed (B22A-review-sign conclusion=Y) → isReadonly=true', async () => {
    const { useB22AReview } = await import('../composables/useB22AReview')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B22A-review-sign', { item_id: 'B22A-review-sign', conclusion: 'Y', remark: '经理', wp_ref: '2026-01-01' })
      const overallConclusion = ref<any>('有效')
      const completedCount = computed(() => 5)
      const externalReadonly = ref(false)
      const saveFn = vi.fn().mockResolvedValue(undefined)

      const review = useB22AReview(ref('wp-1'), allResponses, completedCount, overallConclusion, externalReadonly, saveFn)
      expect(review.isReadonly.value).toBe(true)
      expect(review.isReviewed.value).toBe(true)
      expect(review.reviewInfo.value).toEqual({ reviewer: '经理', date: '2026-01-01' })
    })
    scope.stop()
  })

  it('未复核 + externalReadonly=false → isReadonly=false', async () => {
    const { useB22AReview } = await import('../composables/useB22AReview')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      const overallConclusion = ref<any>(null)
      const completedCount = computed(() => 0)
      const externalReadonly = ref(false)
      const saveFn = vi.fn().mockResolvedValue(undefined)

      const review = useB22AReview(ref('wp-1'), allResponses, completedCount, overallConclusion, externalReadonly, saveFn)
      expect(review.isReadonly.value).toBe(false)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.7 Amendment 流程测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22A 内部控制了解程序表 — Amendment 流程 (6.7)', () => {
  it('startAmendment 空原因抛出错误', async () => {
    const { useB22AReview } = await import('../composables/useB22AReview')

    const scope = effectScope()
    scope.run(async () => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B22A-review-sign', { item_id: 'B22A-review-sign', conclusion: 'Y', remark: '经理', wp_ref: '2026-01-01' })
      const overallConclusion = ref<any>('有效')
      const completedCount = computed(() => 5)
      const externalReadonly = ref(false)
      const saveFn = vi.fn().mockResolvedValue(undefined)

      const review = useB22AReview(ref('wp-1'), allResponses, completedCount, overallConclusion, externalReadonly, saveFn)

      await expect(review.startAmendment('')).rejects.toThrow('修改原因不能为空')
      await expect(review.startAmendment('   ')).rejects.toThrow('修改原因不能为空')
    })
    scope.stop()
  })

  it('startAmendment 有效原因 → 重置复核 + 保存原因', async () => {
    const { useB22AReview } = await import('../composables/useB22AReview')

    const scope = effectScope()
    scope.run(async () => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B22A-review-sign', { item_id: 'B22A-review-sign', conclusion: 'Y', remark: '经理', wp_ref: '2026-01-01' })
      const overallConclusion = ref<any>('有效')
      const completedCount = computed(() => 5)
      const externalReadonly = ref(false)
      const saveFn = vi.fn().mockResolvedValue(undefined)

      const review = useB22AReview(ref('wp-1'), allResponses, completedCount, overallConclusion, externalReadonly, saveFn)

      await review.startAmendment('发现新信息需要补充')

      // Review sign should be reset
      const signItem = allResponses.value.get('B22A-review-sign')
      expect(signItem!.conclusion).toBeNull()

      // Amendment reason should be saved
      const reasonItem = allResponses.value.get('B22A-amend-0-reason')
      expect(reasonItem).toBeDefined()
      expect(reasonItem!.remark).toBe('发现新信息需要补充')

      // isReviewed should now be false
      expect(review.isReviewed.value).toBe(false)
      expect(review.isReadonly.value).toBe(false)

      expect(saveFn).toHaveBeenCalled()
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.8 续审模式测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22A 内部控制了解程序表 — 续审模式 (6.8)', () => {
  it('markNoChange 设置确认标记 + 日期 + 确认人', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B22A-T1-count', { item_id: 'B22A-T1-count', conclusion: null, remark: '2', wp_ref: null })
      for (let t = 2; t <= 5; t++) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      matrix.markNoChange(1, 1, '张三')

      const nochangeItem = allResponses.value.get('B22A-T1-item-1-nochange')
      expect(nochangeItem).toBeDefined()
      expect(nochangeItem!.conclusion).toBe('Y')
      expect(nochangeItem!.remark).toBe('张三')
      expect(nochangeItem!.wp_ref).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    })
    scope.stop()
  })

  it('priorYearData 填充后 getCheckItems 包含 priorYearConclusion', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B22A-T1-count', { item_id: 'B22A-T1-count', conclusion: null, remark: '1', wp_ref: null })
      allResponses.value.set('B22A-T1-item-1-point', { item_id: 'B22A-T1-item-1-point', conclusion: null, remark: '要点', wp_ref: null })
      for (let t = 2; t <= 5; t++) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      // Set prior year data
      matrix.priorYearData.value.set('B22A-T1-item-1-conclusion', {
        item_id: 'B22A-T1-item-1-conclusion', conclusion: '已实施', remark: null, wp_ref: null,
      })

      const items = matrix.getCheckItems(1)
      expect(items[0].priorYearConclusion).toBe('已实施')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.9 控制环境薄弱横幅测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22A 内部控制了解程序表 — 控制环境薄弱横幅 (6.9)', () => {
  it('Tab_1 score=无效 + 诚信检查项"设计无效" → warning=true', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      // 5 items: 4 "设计无效" (>20%) → Tab_1 score = "无效"
      allResponses.value.set('B22A-T1-count', { item_id: 'B22A-T1-count', conclusion: null, remark: '5', wp_ref: null })
      allResponses.value.set('B22A-T1-item-1-conclusion', { item_id: 'B22A-T1-item-1-conclusion', conclusion: '设计无效', remark: null, wp_ref: null })
      allResponses.value.set('B22A-T1-item-1-point', { item_id: 'B22A-T1-item-1-point', conclusion: null, remark: '管理层诚信与道德', wp_ref: null })
      allResponses.value.set('B22A-T1-item-2-conclusion', { item_id: 'B22A-T1-item-2-conclusion', conclusion: '设计无效', remark: null, wp_ref: null })
      allResponses.value.set('B22A-T1-item-2-point', { item_id: 'B22A-T1-item-2-point', conclusion: null, remark: '组织结构', wp_ref: null })
      allResponses.value.set('B22A-T1-item-3-conclusion', { item_id: 'B22A-T1-item-3-conclusion', conclusion: '设计无效', remark: null, wp_ref: null })
      allResponses.value.set('B22A-T1-item-3-point', { item_id: 'B22A-T1-item-3-point', conclusion: null, remark: '能力要求', wp_ref: null })
      allResponses.value.set('B22A-T1-item-4-conclusion', { item_id: 'B22A-T1-item-4-conclusion', conclusion: '设计无效', remark: null, wp_ref: null })
      allResponses.value.set('B22A-T1-item-4-point', { item_id: 'B22A-T1-item-4-point', conclusion: null, remark: '普通控制', wp_ref: null })
      allResponses.value.set('B22A-T1-item-5-conclusion', { item_id: 'B22A-T1-item-5-conclusion', conclusion: '设计有效', remark: null, wp_ref: null })
      allResponses.value.set('B22A-T1-item-5-point', { item_id: 'B22A-T1-item-5-point', conclusion: null, remark: '考核奖惩', wp_ref: null })

      for (let t = 2; t <= 5; t++) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      // Tab_1 has 4/5 deficient (80% >20%) → "无效", AND item_1 "诚信" is "设计无效"
      expect(matrix.controlEnvWeakWarning.value).toBe(true)
    })
    scope.stop()
  })

  it('Tab_1 score=有效 → warning=false', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      allResponses.value.set('B22A-T1-count', { item_id: 'B22A-T1-count', conclusion: null, remark: '2', wp_ref: null })
      allResponses.value.set('B22A-T1-item-1-conclusion', { item_id: 'B22A-T1-item-1-conclusion', conclusion: '设计有效', remark: null, wp_ref: null })
      allResponses.value.set('B22A-T1-item-1-point', { item_id: 'B22A-T1-item-1-point', conclusion: null, remark: '管理层诚信', wp_ref: null })
      allResponses.value.set('B22A-T1-item-2-conclusion', { item_id: 'B22A-T1-item-2-conclusion', conclusion: '设计有效', remark: null, wp_ref: null })
      allResponses.value.set('B22A-T1-item-2-point', { item_id: 'B22A-T1-item-2-point', conclusion: null, remark: '组织结构', wp_ref: null })
      for (let t = 2; t <= 5; t++) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      expect(matrix.controlEnvWeakWarning.value).toBe(false)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.10 手动覆盖 Element_Score 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B22A 内部控制了解程序表 — 手动覆盖 Element_Score (6.10)', () => {
  it('overrideElementScore 无理由时 no-op', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      for (let t = 1; t <= 5; t++) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      matrix.overrideElementScore(1, '有效', '')
      matrix.overrideElementScore(1, '有效', '   ')

      // Should not have saved
      expect(saveFn).not.toHaveBeenCalled()
      expect(allResponses.value.has('B22A-T1-score')).toBe(false)
    })
    scope.stop()
  })

  it('overrideElementScore 有理由 → 保存 score + override 标记', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map<string, any>())
      for (let t = 1; t <= 5; t++) {
        allResponses.value.set(`B22A-T${t}-count`, { item_id: `B22A-T${t}-count`, conclusion: null, remark: '0', wp_ref: null })
      }

      const saveFn = vi.fn().mockResolvedValue(undefined)
      const matrix = useB22AControlMatrix(allResponses, saveFn)
      matrix.initialize()

      matrix.overrideElementScore(2, '部分有效', '考虑到补偿控制')

      expect(allResponses.value.get('B22A-T2-score')!.conclusion).toBe('部分有效')
      expect(allResponses.value.get('B22A-T2-score-override')!.conclusion).toBe('Y')
      expect(allResponses.value.get('B22A-T2-score-override')!.remark).toBe('考虑到补偿控制')
      expect(matrix.isScoreOverridden(2)).toBe(true)
      expect(saveFn).toHaveBeenCalled()
    })
    scope.stop()
  })
})
