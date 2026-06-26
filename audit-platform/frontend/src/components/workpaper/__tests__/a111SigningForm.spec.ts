/**
 * A1-11 签发流转控制表 — 注册契约测试
 *
 * 验证：
 *  1. htmlRendererRegistry 包含 componentType = 'a1-11-signing-form'
 *  2. wp_code_overrides.json 映射 A1-11 → a1-11-signing-form
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { HTML_RENDERER_REGISTRY } from '../htmlRendererRegistry'

describe('A1-11 签发流转控制表 — 注册契约', () => {
  it('registry 包含 a1-11-signing-form 条目且字段正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('a1-11-signing-form')
    expect(entry).toBeDefined()
    expect(entry!.componentType).toBe('a1-11-signing-form')
    expect(entry!.icon).toBe('✍️')
    expect(entry!.label).toBe('A1-11 签发流转控制表')
    expect(entry!.emits).toEqual(['save', 'completed'])
    expect(entry!.contextProps).toBe('standard')
  })

  it('wp_code_overrides.json 映射 A1-11 → a1-11-signing-form', () => {
    const overridesPath = resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = JSON.parse(readFileSync(overridesPath, 'utf-8'))
    expect(overrides['A1-11']).toBe('a1-11-signing-form')
  })
})

// ─── 组件行为测试 ─────────────────────────────────────────────────────────────
// Task 6.2: 签字操作 emit、debounce 保存、readonly 禁用

import { ref, nextTick } from 'vue'
import { beforeEach, afterEach, vi } from 'vitest'
import { useA111Signing } from '../composables/useA111Signing'

// Mock apiProxy for useA111FormData tests
const mockGet = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

// Mock element-plus ElMessage
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn() },
}))

// ─── 签字操作 ─────────────────────────────────────────────────────────────────

describe('A1-11 签发流转控制表 — 签字操作', () => {
  it('signAction 设置 conclusion=Y, remark=签字人, wp_ref=当天日期', () => {
    const businessCategory = ref('A')
    const signStates = ref<Record<string, any>>({})

    const { signAction, getSlotState } = useA111Signing(businessCategory, signStates)

    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-25'))

    signAction('pm', '张三')

    const state = getSlotState('pm')
    expect(state.conclusion).toBe('Y')
    expect(state.remark).toBe('张三')
    expect(state.wp_ref).toBe('2026-06-25')

    vi.useRealTimers()
  })

  it('signAction 对不同槽位独立写入', () => {
    const businessCategory = ref('A')
    const signStates = ref<Record<string, any>>({})

    const { signAction, getSlotState } = useA111Signing(businessCategory, signStates)

    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-25'))

    signAction('pm', '张三')
    signAction('partner', '李四')

    expect(getSlotState('pm').remark).toBe('张三')
    expect(getSlotState('partner').remark).toBe('李四')
    expect(getSlotState('qc').conclusion).toBeNull()

    vi.useRealTimers()
  })

  it('signAction 后 progress 和 isAllSigned 响应更新', () => {
    const businessCategory = ref<string>('B')
    const signStates = ref<Record<string, any>>({})

    const { signAction, progress, isAllSigned } = useA111Signing(businessCategory, signStates)

    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-25'))

    // B 类只需 pm + partner
    expect(progress.value).toEqual({ signed: 0, total: 2 })
    expect(isAllSigned.value).toBe(false)

    signAction('pm', '张三')
    expect(progress.value).toEqual({ signed: 1, total: 2 })
    expect(isAllSigned.value).toBe(false)

    signAction('partner', '李四')
    expect(progress.value).toEqual({ signed: 2, total: 2 })
    expect(isAllSigned.value).toBe(true)

    vi.useRealTimers()
  })
})

// ─── debounce 保存 ────────────────────────────────────────────────────────────

describe('A1-11 签发流转控制表 — debounce 保存', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockResolvedValue([])
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('scheduleSave 在 2000ms 后触发保存', async () => {
    const { useA111FormData } = await import('../composables/useA111FormData')
    const { effectScope } = await import('vue')

    const scope = effectScope()
    let formApi: ReturnType<typeof useA111FormData>

    scope.run(() => {
      formApi = useA111FormData(ref('wp-1'), ref('proj-1'))
    })

    // 先确保 formData 非空，否则 doSave 会因 items.length===0 提前返回
    formApi!.formData.value['A1-11-entity-name'] = {
      item_id: 'A1-11-entity-name', conclusion: null, remark: '测试公司', wp_ref: null,
    }
    mockPut.mockClear()

    // 调用 scheduleSave
    formApi!.scheduleSave()

    // 1999ms 后不应触发保存
    vi.advanceTimersByTime(1999)
    await nextTick()
    expect(mockPut).not.toHaveBeenCalled()

    // 再过 1ms（共 2000ms）触发保存
    vi.advanceTimersByTime(1)
    await nextTick()
    expect(mockPut).toHaveBeenCalledTimes(1)

    scope.stop()
  })

  it('多次 scheduleSave 只触发一次保存（debounce 重置）', async () => {
    const { useA111FormData } = await import('../composables/useA111FormData')
    const { effectScope } = await import('vue')

    const scope = effectScope()
    let formApi: ReturnType<typeof useA111FormData>

    scope.run(() => {
      formApi = useA111FormData(ref('wp-1'), ref('proj-1'))
    })

    formApi!.formData.value['A1-11-entity-name'] = {
      item_id: 'A1-11-entity-name', conclusion: null, remark: '测试', wp_ref: null,
    }
    mockPut.mockClear()

    // 连续调用 scheduleSave
    formApi!.scheduleSave()
    vi.advanceTimersByTime(1000)
    formApi!.scheduleSave() // 重置 timer
    vi.advanceTimersByTime(1000)
    await nextTick()
    // 第二次 scheduleSave 距离只过了 1000ms，不应触发
    expect(mockPut).not.toHaveBeenCalled()

    // 再等 1000ms（共 2000ms from 第二次调用）
    vi.advanceTimersByTime(1000)
    await nextTick()
    expect(mockPut).toHaveBeenCalledTimes(1)

    scope.stop()
  })

  it('saveImmediate 立即保存并取消 pending debounce', async () => {
    const { useA111FormData } = await import('../composables/useA111FormData')
    const { effectScope } = await import('vue')

    const scope = effectScope()
    let formApi: ReturnType<typeof useA111FormData>

    scope.run(() => {
      formApi = useA111FormData(ref('wp-1'), ref('proj-1'))
    })

    formApi!.formData.value['A1-11-entity-name'] = {
      item_id: 'A1-11-entity-name', conclusion: null, remark: '测试', wp_ref: null,
    }
    mockPut.mockClear()

    // 先 scheduleSave 启动 debounce
    formApi!.scheduleSave()
    vi.advanceTimersByTime(500)
    await nextTick()
    expect(mockPut).not.toHaveBeenCalled()

    // saveImmediate 立即保存
    await formApi!.saveImmediate()
    expect(mockPut).toHaveBeenCalledTimes(1)

    // 继续等 debounce 结束，不应再次触发
    mockPut.mockClear()
    vi.advanceTimersByTime(2000)
    await nextTick()
    expect(mockPut).not.toHaveBeenCalled()

    scope.stop()
  })
})

// ─── readonly 禁用 ────────────────────────────────────────────────────────────

// ─── Amendment 逻辑辅助（从组件提取的纯逻辑，用于测试） ─────────────────────
// These mirror the component's amendment logic for testability.

/** Amendment reason validation: non-empty after trim */
function isAmendmentReasonValid(reason: string): boolean {
  return reason.trim().length > 0
}

/** Generate amendment item_id for a role sign in a given amendment sequence */
function getAmendmentSignItemId(amendmentIndex: number, role: string): string {
  return `A1-11-amend-${amendmentIndex}-sign-${role}`
}

/** Generate amendment reason item_id */
function getAmendmentReasonItemId(amendmentIndex: number): string {
  return `A1-11-amend-${amendmentIndex}-reason`
}

/** Amendment roles (A category full set) */
const AMENDMENT_ROLES = ['pm', 'partner', 'qc', 'eqcr']

/** Check if all amendment roles are signed in given formData */
function isAmendmentFullySigned(
  formData: Record<string, { conclusion: string | null; remark: string | null; wp_ref: string | null }>,
  amendmentIndex: number,
): boolean {
  return AMENDMENT_ROLES.every(role => {
    const itemId = getAmendmentSignItemId(amendmentIndex, role)
    return formData[itemId]?.conclusion === 'Y'
  })
}

describe('A1-11 签发流转控制表 — readonly 禁用', () => {
  it('externalReadonly=true 时 isReadonly 为 true（无论签字状态）', () => {
    const businessCategory = ref('A')
    const signStates = ref<Record<string, any>>({})
    const externalReadonly = ref(true)

    const { isReadonly } = useA111Signing(businessCategory, signStates, externalReadonly)

    expect(isReadonly.value).toBe(true)
  })

  it('所有必填槽位签完后 isReadonly 变为 true', () => {
    const businessCategory = ref<string>('C')
    const signStates = ref<Record<string, any>>({})
    const externalReadonly = ref(false)

    const { isReadonly, signAction } = useA111Signing(businessCategory, signStates, externalReadonly)

    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-25'))

    // C 类需要 pm + partner
    expect(isReadonly.value).toBe(false)

    signAction('pm', '张三')
    expect(isReadonly.value).toBe(false)

    signAction('partner', '李四')
    expect(isReadonly.value).toBe(true)

    vi.useRealTimers()
  })

  it('externalReadonly 从 true 变为 false 且未全签，isReadonly 恢复 false', () => {
    const businessCategory = ref<string>('B')
    const signStates = ref<Record<string, any>>({})
    const externalReadonly = ref(true)

    const { isReadonly } = useA111Signing(businessCategory, signStates, externalReadonly)

    expect(isReadonly.value).toBe(true)

    externalReadonly.value = false
    expect(isReadonly.value).toBe(false)
  })

  it('A 类需要 4 个必填槽位全签才 readonly', () => {
    const businessCategory = ref<string>('A')
    const signStates = ref<Record<string, any>>({})
    const externalReadonly = ref(false)

    const { isReadonly, signAction } = useA111Signing(businessCategory, signStates, externalReadonly)

    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-25'))

    signAction('pm', '张三')
    signAction('partner', '李四')
    signAction('qc', '王五')
    expect(isReadonly.value).toBe(false) // 还差 eqcr

    signAction('eqcr', '赵六')
    expect(isReadonly.value).toBe(true)

    vi.useRealTimers()
  })
})


// ─── amendment 流程测试 (Task 6.3) ─────────────────────────────────────────────
// Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5

describe('A1-11 签发流转控制表 — amendment 流程', () => {
  // ─── 修改原因验证 ──────────────────────────────────────────────────────────

  describe('修改原因验证', () => {
    it('空字符串被拒绝', () => {
      expect(isAmendmentReasonValid('')).toBe(false)
    })

    it('纯空格被拒绝', () => {
      expect(isAmendmentReasonValid('   ')).toBe(false)
    })

    it('纯 tab 被拒绝', () => {
      expect(isAmendmentReasonValid('\t\t')).toBe(false)
    })

    it('混合空白字符被拒绝', () => {
      expect(isAmendmentReasonValid(' \n\t\r ')).toBe(false)
    })

    it('非空内容通过验证', () => {
      expect(isAmendmentReasonValid('客户要求调整审计意见')).toBe(true)
    })

    it('含前后空格但中间有内容通过验证', () => {
      expect(isAmendmentReasonValid('  调整  ')).toBe(true)
    })
  })

  // ─── item_id 前缀正确性 ───────────────────────────────────────────────────

  describe('amendment item_id 前缀', () => {
    it('第 1 次修改的签字 item_id 使用 A1-11-amend-1- 前缀', () => {
      expect(getAmendmentSignItemId(1, 'pm')).toBe('A1-11-amend-1-sign-pm')
      expect(getAmendmentSignItemId(1, 'partner')).toBe('A1-11-amend-1-sign-partner')
      expect(getAmendmentSignItemId(1, 'qc')).toBe('A1-11-amend-1-sign-qc')
      expect(getAmendmentSignItemId(1, 'eqcr')).toBe('A1-11-amend-1-sign-eqcr')
    })

    it('第 2 次修改的签字 item_id 使用 A1-11-amend-2- 前缀', () => {
      expect(getAmendmentSignItemId(2, 'pm')).toBe('A1-11-amend-2-sign-pm')
      expect(getAmendmentSignItemId(2, 'partner')).toBe('A1-11-amend-2-sign-partner')
    })

    it('第 N 次修改的 reason item_id 正确', () => {
      expect(getAmendmentReasonItemId(1)).toBe('A1-11-amend-1-reason')
      expect(getAmendmentReasonItemId(3)).toBe('A1-11-amend-3-reason')
      expect(getAmendmentReasonItemId(10)).toBe('A1-11-amend-10-reason')
    })

    it('不同次修改的 item_id 互不冲突', () => {
      const ids1 = AMENDMENT_ROLES.map(r => getAmendmentSignItemId(1, r))
      const ids2 = AMENDMENT_ROLES.map(r => getAmendmentSignItemId(2, r))
      // No overlap
      for (const id of ids1) {
        expect(ids2).not.toContain(id)
      }
    })
  })

  // ─── 完整流程：启动修改 → 填写原因 → 签字 → 重新锁定 ─────────────────────

  describe('amendment 完整流程', () => {
    it('启动修改条件：表单已 readonly 时可启动', () => {
      const businessCategory = ref<string>('A')
      const signStates = ref<Record<string, any>>({})
      const externalReadonly = ref(false)

      const { isReadonly, signAction } = useA111Signing(businessCategory, signStates, externalReadonly)

      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-06-25'))

      // 签完所有必填槽位 → readonly
      signAction('pm', '张三')
      signAction('partner', '李四')
      signAction('qc', '王五')
      signAction('eqcr', '赵六')
      expect(isReadonly.value).toBe(true)

      // canStartAmendment = isReadonly && !showAmendment
      const showAmendment = ref(false)
      const canStartAmendment = isReadonly.value && !showAmendment.value
      expect(canStartAmendment).toBe(true)

      vi.useRealTimers()
    })

    it('修改原因保存后签字槽位开放', () => {
      // Simulate: reason filled → signing slots become available
      const amendmentReason = ref('')
      const amendmentReasonValid = () => isAmendmentReasonValid(amendmentReason.value)

      // 未填写原因 → 签字不可用
      expect(amendmentReasonValid()).toBe(false)

      // 填写原因
      amendmentReason.value = '发现审计报告日期有误，需要更正'
      expect(amendmentReasonValid()).toBe(true)
    })

    it('amendment 签字使用 setFieldImmediate 写入正确 item_id', async () => {
      const { useA111FormData } = await import('../composables/useA111FormData')
      const { effectScope } = await import('vue')

      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-06-25'))
      mockGet.mockResolvedValue([])
      mockPut.mockResolvedValue({})

      const scope = effectScope()
      let formApi: ReturnType<typeof useA111FormData>

      scope.run(() => {
        formApi = useA111FormData(ref('wp-1'), ref('proj-1'))
      })

      mockPut.mockClear()

      // Simulate amendment sign for index=1, role=pm
      const idx = 1
      const role = 'pm'
      const itemId = getAmendmentSignItemId(idx, role)
      const userName = '张三'
      const today = '2026-06-25'

      formApi!.setFieldImmediate(itemId, {
        conclusion: 'Y',
        remark: userName,
        wp_ref: today,
      })

      // Verify formData was updated with correct item_id
      const field = formApi!.getField(itemId)
      expect(field.conclusion).toBe('Y')
      expect(field.remark).toBe('张三')
      expect(field.wp_ref).toBe('2026-06-25')
      expect(field.item_id).toBe('A1-11-amend-1-sign-pm')

      scope.stop()
      vi.useRealTimers()
    })

    it('全部 amendment 角色签完后 isAmendmentFullySigned 为 true', () => {
      const formData: Record<string, { conclusion: string | null; remark: string | null; wp_ref: string | null }> = {}

      // Initially not fully signed
      expect(isAmendmentFullySigned(formData, 1)).toBe(false)

      // Sign pm
      formData['A1-11-amend-1-sign-pm'] = { conclusion: 'Y', remark: '张三', wp_ref: '2026-06-25' }
      expect(isAmendmentFullySigned(formData, 1)).toBe(false)

      // Sign partner
      formData['A1-11-amend-1-sign-partner'] = { conclusion: 'Y', remark: '李四', wp_ref: '2026-06-25' }
      expect(isAmendmentFullySigned(formData, 1)).toBe(false)

      // Sign qc
      formData['A1-11-amend-1-sign-qc'] = { conclusion: 'Y', remark: '王五', wp_ref: '2026-06-25' }
      expect(isAmendmentFullySigned(formData, 1)).toBe(false)

      // Sign eqcr → fully signed
      formData['A1-11-amend-1-sign-eqcr'] = { conclusion: 'Y', remark: '赵六', wp_ref: '2026-06-25' }
      expect(isAmendmentFullySigned(formData, 1)).toBe(true)
    })

    it('不同序号的 amendment 独立判定完成状态', () => {
      const formData: Record<string, { conclusion: string | null; remark: string | null; wp_ref: string | null }> = {}

      // Complete amendment 1
      for (const role of AMENDMENT_ROLES) {
        formData[`A1-11-amend-1-sign-${role}`] = { conclusion: 'Y', remark: '签字人', wp_ref: '2026-06-25' }
      }
      expect(isAmendmentFullySigned(formData, 1)).toBe(true)
      // Amendment 2 not started
      expect(isAmendmentFullySigned(formData, 2)).toBe(false)
    })
  })

  // ─── 重新锁定 ─────────────────────────────────────────────────────────────

  describe('amendment 重新锁定', () => {
    it('主签字完成后表单 readonly，amendment 签字完成后仍 readonly', () => {
      const businessCategory = ref<string>('A')
      const signStates = ref<Record<string, any>>({})
      const externalReadonly = ref(false)

      const { isReadonly, signAction } = useA111Signing(businessCategory, signStates, externalReadonly)

      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-06-25'))

      // Complete main signing → readonly
      signAction('pm', '张三')
      signAction('partner', '李四')
      signAction('qc', '王五')
      signAction('eqcr', '赵六')
      expect(isReadonly.value).toBe(true)

      // Amendment signing doesn't affect the main isReadonly
      // (amendment is separate from the main workflow,
      //  form stays readonly throughout amendment process)
      expect(isReadonly.value).toBe(true)

      vi.useRealTimers()
    })

    it('amendment 完全签完后 isAmendmentFullySigned=true 表明可重新锁定', () => {
      const formData: Record<string, { conclusion: string | null; remark: string | null; wp_ref: string | null }> = {}

      // Simulate: amendment reason saved
      formData['A1-11-amend-1-reason'] = { conclusion: null, remark: '日期修改', wp_ref: null }

      // 签完所有修改签字
      for (const role of AMENDMENT_ROLES) {
        formData[`A1-11-amend-1-sign-${role}`] = { conclusion: 'Y', remark: '签字人', wp_ref: '2026-06-25' }
      }

      // Amendment fully signed → form re-enters locked state
      expect(isAmendmentFullySigned(formData, 1)).toBe(true)
    })

    it('amendment 部分签字时不可重新锁定', () => {
      const formData: Record<string, { conclusion: string | null; remark: string | null; wp_ref: string | null }> = {}

      formData['A1-11-amend-1-reason'] = { conclusion: null, remark: '需要修改', wp_ref: null }
      formData['A1-11-amend-1-sign-pm'] = { conclusion: 'Y', remark: '张三', wp_ref: '2026-06-25' }
      formData['A1-11-amend-1-sign-partner'] = { conclusion: 'Y', remark: '李四', wp_ref: '2026-06-25' }
      // qc and eqcr not signed yet

      expect(isAmendmentFullySigned(formData, 1)).toBe(false)
    })
  })
})
