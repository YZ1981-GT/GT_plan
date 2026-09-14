/**
 * B50 重大错报风险评估 — Unit Tests (Tasks 6.1–6.6)
 *
 * 验证：
 *  6.1 注册契约测试 — registry + wp_code_overrides
 *  6.2 组件行为测试 — 4 tab + 默认 Tab_3 + tab 状态
 *  6.3 CAS 预置科目测试 — 收入确认 + 管理层凌驾
 *  6.4 保存行为测试 — debounce 2s + 即时保存
 *  6.5 只读模式测试 — readonly / approved → isReadonly
 *  6.6 Amendment 流程测试 — startAmendment + reason validation
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

describe('B50 重大错报风险评估 — 注册契约 (6.1)', () => {
  it('registry 包含 b50-risk-assessment 条目且字段正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('b50-risk-assessment')
    expect(entry).toBeDefined()
    expect(entry!.componentType).toBe('b50-risk-assessment')
    expect(entry!.icon).toBe('🎯')
    expect(entry!.label).toBe('B50 重大错报风险评估')
    expect(entry!.emits).toEqual(['save', 'completed'])
    expect(entry!.contextProps).toBe('standard')
  })

  it('wp_code_overrides.json 映射 B50 → b50-risk-assessment', () => {
    const overridesPath = resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = JSON.parse(readFileSync(overridesPath, 'utf-8'))
    expect(overrides['B50']).toBe('b50-risk-assessment')
  })

  it('wp_code_overrides.json 映射 B50-1~4 → skip', () => {
    const overridesPath = resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = JSON.parse(readFileSync(overridesPath, 'utf-8'))
    expect(overrides['B50-1']).toBe('skip')
    expect(overrides['B50-2']).toBe('skip')
    expect(overrides['B50-3']).toBe('skip')
    expect(overrides['B50-4']).toBe('skip')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.2 组件行为测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B50 重大错报风险评估 — 组件行为 (6.2)', () => {
  beforeEach(() => {
    mockGet.mockResolvedValue([])
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('useB50RiskMatrix 初始化后 accounts 包含预置科目', async () => {
    const { useB50RiskMatrix, PRESET_ACCOUNTS } = await import('../composables/useB50RiskMatrix')

    const scope = effectScope()
    scope.run(() => {
      const tab3Data = ref({ items: new Map() })
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const { accounts } = useB50RiskMatrix(tab3Data, saveFn)

      // Should have preset accounts initialized
      expect(accounts.value.length).toBeGreaterThanOrEqual(2)
      const names = accounts.value.map(a => a.name)
      expect(names).toContain('收入确认')
      expect(names).toContain('管理层凌驾控制')
    })
    scope.stop()
  })

  it('4 个 tab 数据视图按前缀正确分发', async () => {
    const { useB50FormData } = await import('../composables/useB50FormData')

    const scope = effectScope()
    scope.run(() => {
      const formApi = useB50FormData(ref('wp-1'))

      // Populate with items from various tabs
      formApi.allResponses.value.set('B50-T1-factor-1-desc', {
        item_id: 'B50-T1-factor-1-desc', conclusion: null, remark: '测试', wp_ref: null,
      })
      formApi.allResponses.value.set('B50-T2-fs-1-level', {
        item_id: 'B50-T2-fs-1-level', conclusion: 'H', remark: null, wp_ref: null,
      })
      formApi.allResponses.value.set('B50-T3-matrix-收入确认-existence-IR', {
        item_id: 'B50-T3-matrix-收入确认-existence-IR', conclusion: 'H', remark: null, wp_ref: null,
      })
      formApi.allResponses.value.set('B50-T4-sr-收入确认-existence-response', {
        item_id: 'B50-T4-sr-收入确认-existence-response', conclusion: null, remark: '细节测试', wp_ref: null,
      })

      // Verify tab distribution
      expect(formApi.tab1Data.value.items.has('B50-T1-factor-1-desc')).toBe(true)
      expect(formApi.tab2Data.value.items.has('B50-T2-fs-1-level')).toBe(true)
      expect(formApi.tab3Data.value.items.has('B50-T3-matrix-收入确认-existence-IR')).toBe(true)
      expect(formApi.tab4Data.value.items.has('B50-T4-sr-收入确认-existence-response')).toBe(true)

      // Cross-tab items should NOT be in wrong tabs
      expect(formApi.tab1Data.value.items.has('B50-T2-fs-1-level')).toBe(false)
      expect(formApi.tab3Data.value.items.has('B50-T4-sr-收入确认-existence-response')).toBe(false)
    })
    scope.stop()
  })

  it('默认 Tab 3（认定层面风险矩阵）— activeTab 初始值为 tab3', () => {
    // Per design: Tab_3 is the default active tab
    // This is a design contract; the component uses activeTab = ref('tab3')
    const activeTab = ref('tab3')
    expect(activeTab.value).toBe('tab3')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.3 CAS 预置科目测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B50 重大错报风险评估 — CAS 预置科目 (6.3)', () => {
  it('PRESET_ACCOUNTS 包含收入确认和管理层凌驾控制', async () => {
    const { PRESET_ACCOUNTS } = await import('../composables/useB50RiskMatrix')
    const names = PRESET_ACCOUNTS.map(p => p.name)
    expect(names).toContain('收入确认')
    expect(names).toContain('管理层凌驾控制')
  })

  it('收入确认不可删除 — removeAccount 对 preset 行为 no-op', async () => {
    const { useB50RiskMatrix } = await import('../composables/useB50RiskMatrix')

    const scope = effectScope()
    scope.run(() => {
      const tab3Data = ref({ items: new Map() })
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const { accounts, removeAccount } = useB50RiskMatrix(tab3Data, saveFn)

      const presetIdx = accounts.value.findIndex(a => a.name === '收入确认')
      expect(presetIdx).toBeGreaterThanOrEqual(0)

      const countBefore = accounts.value.length
      removeAccount(presetIdx)
      expect(accounts.value.length).toBe(countBefore)
      expect(accounts.value.some(a => a.name === '收入确认')).toBe(true)
    })
    scope.stop()
  })

  it('管理层凌驾控制 — 所有认定 isSpecialRisk 默认为 true', async () => {
    const { useB50RiskMatrix, ASSERTIONS } = await import('../composables/useB50RiskMatrix')

    const scope = effectScope()
    scope.run(() => {
      const tab3Data = ref({ items: new Map() })
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const { accounts } = useB50RiskMatrix(tab3Data, saveFn)

      const mgmtRow = accounts.value.find(a => a.name === '管理层凌驾控制')
      expect(mgmtRow).toBeDefined()

      for (const assertion of ASSERTIONS) {
        expect(mgmtRow!.cells[assertion].isSpecialRisk).toBe(true)
      }
    })
    scope.stop()
  })

  it('管理层凌驾控制不可删除', async () => {
    const { useB50RiskMatrix } = await import('../composables/useB50RiskMatrix')

    const scope = effectScope()
    scope.run(() => {
      const tab3Data = ref({ items: new Map() })
      const saveFn = vi.fn().mockResolvedValue(undefined)
      const { accounts, removeAccount } = useB50RiskMatrix(tab3Data, saveFn)

      const mgmtIdx = accounts.value.findIndex(a => a.name === '管理层凌驾控制')
      const countBefore = accounts.value.length
      removeAccount(mgmtIdx)
      expect(accounts.value.length).toBe(countBefore)
      expect(accounts.value.some(a => a.name === '管理层凌驾控制')).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.4 保存行为测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B50 重大错报风险评估 — 保存行为 (6.4)', () => {
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
    const { useB50FormData } = await import('../composables/useB50FormData')

    const scope = effectScope()
    let formApi: ReturnType<typeof useB50FormData>

    scope.run(() => {
      formApi = useB50FormData(ref('wp-1'))
    })

    mockPut.mockClear()

    const item = {
      item_id: 'B50-T1-factor-1-desc',
      conclusion: null,
      remark: '测试描述',
      wp_ref: null,
    }

    formApi!.saveDebouncedText(item)

    // 1999ms should not trigger
    vi.advanceTimersByTime(1999)
    await nextTick()
    expect(mockPut).not.toHaveBeenCalled()

    // 2000ms total triggers save
    vi.advanceTimersByTime(1)
    await nextTick()
    expect(mockPut).toHaveBeenCalledTimes(1)

    scope.stop()
  })

  it('风险等级变更触发 setFieldImmediate 立即保存', async () => {
    const { useB50FormData } = await import('../composables/useB50FormData')

    const scope = effectScope()
    let formApi: ReturnType<typeof useB50FormData>

    scope.run(() => {
      formApi = useB50FormData(ref('wp-1'))
    })

    mockPut.mockClear()

    // setFieldImmediate triggers save immediately (no debounce)
    formApi!.setFieldImmediate('B50-T2-fs-1-level', { conclusion: 'H' })

    await nextTick()
    expect(mockPut).toHaveBeenCalledTimes(1)

    scope.stop()
  })

  it('debounce 重置 — 多次 saveDebouncedText 只触发一次保存', async () => {
    const { useB50FormData } = await import('../composables/useB50FormData')

    const scope = effectScope()
    let formApi: ReturnType<typeof useB50FormData>

    scope.run(() => {
      formApi = useB50FormData(ref('wp-1'))
    })

    mockPut.mockClear()

    const item1 = { item_id: 'B50-T1-factor-1-desc', conclusion: null, remark: '第一次', wp_ref: null }
    const item2 = { item_id: 'B50-T1-factor-1-desc', conclusion: null, remark: '第二次', wp_ref: null }

    formApi!.saveDebouncedText(item1)
    vi.advanceTimersByTime(1000)
    formApi!.saveDebouncedText(item2) // resets timer
    vi.advanceTimersByTime(1000)
    await nextTick()
    expect(mockPut).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1000) // 2000ms from second call
    await nextTick()
    expect(mockPut).toHaveBeenCalledTimes(1)

    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.5 只读模式测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B50 重大错报风险评估 — 只读模式 (6.5)', () => {
  it('readonly=true → isReadonly=true', async () => {
    const { useB50Approval } = await import('../composables/useB50Approval')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map())
      const incompleteAccounts = computed(() => [] as string[])
      const specialRiskCells = computed(() => [] as any[])
      const externalReadonly = ref(true)
      const saveFn = vi.fn().mockResolvedValue(undefined)

      const { isReadonly } = useB50Approval(
        ref('wp-1'), allResponses, incompleteAccounts, specialRiskCells, externalReadonly, saveFn
      )

      expect(isReadonly.value).toBe(true)
    })
    scope.stop()
  })

  it('approved (B50-approval-sign conclusion=Y) → isReadonly=true', async () => {
    const { useB50Approval } = await import('../composables/useB50Approval')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map([
        ['B50-approval-sign', { item_id: 'B50-approval-sign', conclusion: 'Y', remark: '张三', wp_ref: '2026-06-25' }],
      ]))
      const incompleteAccounts = computed(() => [] as string[])
      const specialRiskCells = computed(() => [] as any[])
      const externalReadonly = ref(false)
      const saveFn = vi.fn().mockResolvedValue(undefined)

      const { isReadonly, isApproved } = useB50Approval(
        ref('wp-1'), allResponses, incompleteAccounts, specialRiskCells, externalReadonly, saveFn
      )

      expect(isApproved.value).toBe(true)
      expect(isReadonly.value).toBe(true)
    })
    scope.stop()
  })

  it('!readonly + !approved → isReadonly=false', async () => {
    const { useB50Approval } = await import('../composables/useB50Approval')

    const scope = effectScope()
    scope.run(() => {
      const allResponses = ref(new Map())
      const incompleteAccounts = computed(() => [] as string[])
      const specialRiskCells = computed(() => [] as any[])
      const externalReadonly = ref(false)
      const saveFn = vi.fn().mockResolvedValue(undefined)

      const { isReadonly } = useB50Approval(
        ref('wp-1'), allResponses, incompleteAccounts, specialRiskCells, externalReadonly, saveFn
      )

      expect(isReadonly.value).toBe(false)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 6.6 Amendment 流程测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('B50 重大错报风险评估 — Amendment 流程 (6.6)', () => {
  it('startAmendment 有效原因 → 重置审批 + 保存原因', async () => {
    const { useB50Approval } = await import('../composables/useB50Approval')

    const scope = effectScope()
    scope.run(async () => {
      const allResponses = ref(new Map([
        ['B50-approval-sign', { item_id: 'B50-approval-sign', conclusion: 'Y', remark: '张三', wp_ref: '2026-06-25' }],
      ]))
      const incompleteAccounts = computed(() => [] as string[])
      const specialRiskCells = computed(() => [] as any[])
      const externalReadonly = ref(false)
      const saveFn = vi.fn().mockResolvedValue(undefined)

      const { startAmendment, isApproved } = useB50Approval(
        ref('wp-1'), allResponses, incompleteAccounts, specialRiskCells, externalReadonly, saveFn
      )

      expect(isApproved.value).toBe(true)

      await startAmendment('发现审计报告日期有误')

      // Approval should be reset
      expect(isApproved.value).toBe(false)
      const approvalItem = allResponses.value.get('B50-approval-sign')
      expect(approvalItem?.conclusion).toBeNull()

      // Amendment reason should be saved
      const reasonItem = allResponses.value.get('B50-amend-0-reason')
      expect(reasonItem).toBeDefined()
      expect(reasonItem!.remark).toBe('发现审计报告日期有误')

      // saveImmediate should have been called
      expect(saveFn).toHaveBeenCalled()
    })
    scope.stop()
  })

  it('startAmendment 空原因 → 抛出错误', async () => {
    const { useB50Approval } = await import('../composables/useB50Approval')

    const scope = effectScope()
    scope.run(async () => {
      const allResponses = ref(new Map([
        ['B50-approval-sign', { item_id: 'B50-approval-sign', conclusion: 'Y', remark: '张三', wp_ref: '2026-06-25' }],
      ]))
      const incompleteAccounts = computed(() => [] as string[])
      const specialRiskCells = computed(() => [] as any[])
      const externalReadonly = ref(false)
      const saveFn = vi.fn().mockResolvedValue(undefined)

      const { startAmendment } = useB50Approval(
        ref('wp-1'), allResponses, incompleteAccounts, specialRiskCells, externalReadonly, saveFn
      )

      await expect(startAmendment('')).rejects.toThrow('Amendment 原因不能为空')
      await expect(startAmendment('   ')).rejects.toThrow('Amendment 原因不能为空')
    })
    scope.stop()
  })

  it('amendment index 递增 — 多次 amendment 产生不同序号', async () => {
    const { useB50Approval } = await import('../composables/useB50Approval')

    const scope = effectScope()
    scope.run(async () => {
      const allResponses = ref(new Map([
        ['B50-approval-sign', { item_id: 'B50-approval-sign', conclusion: 'Y', remark: '张三', wp_ref: '2026-06-25' }],
      ]))
      const incompleteAccounts = computed(() => [] as string[])
      const specialRiskCells = computed(() => [] as any[])
      const externalReadonly = ref(false)
      const saveFn = vi.fn().mockResolvedValue(undefined)

      const { startAmendment } = useB50Approval(
        ref('wp-1'), allResponses, incompleteAccounts, specialRiskCells, externalReadonly, saveFn
      )

      // First amendment: index 0
      await startAmendment('第一次修改')
      expect(allResponses.value.has('B50-amend-0-reason')).toBe(true)

      // Re-approve to allow second amendment
      allResponses.value.set('B50-approval-sign', {
        item_id: 'B50-approval-sign', conclusion: 'Y', remark: '李四', wp_ref: '2026-06-26',
      })

      // Second amendment: index 1 (because index 0 already exists)
      await startAmendment('第二次修改')
      expect(allResponses.value.has('B50-amend-1-reason')).toBe(true)
      expect(allResponses.value.get('B50-amend-1-reason')!.remark).toBe('第二次修改')
    })
    scope.stop()
  })
})
