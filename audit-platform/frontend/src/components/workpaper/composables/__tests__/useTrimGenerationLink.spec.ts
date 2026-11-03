/**
 * useTrimGenerationLink（spec trim-generation-plan-linkage R3 / R5）：
 * 委派人先走初始化（补齐）、失败退回只读读取、只读成员不调初始化；`?cycle=` 只认已知循环；
 * 粗裁状态文字；业务分类建议只改执行中的行且仍需保存；保存后的下一步；没装 Pinia 时按「不能生成」。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  getProcedures: vi.fn(),
  confirmations: vi.fn(),
  confirm: vi.fn(),
}))
vi.mock('@/services/apiProxy', () => ({ api: { post: mocks.post, get: vi.fn() } }))
vi.mock('@/services/commonApi', () => ({ getProcedures: mocks.getProcedures }))
vi.mock('@/services/generationPlanApi', () => ({ getScopeConfirmations: mocks.confirmations }))
vi.mock('element-plus', () => ({ ElMessageBox: { confirm: mocks.confirm } }))

import { useTrimGenerationLink } from '../useTrimGenerationLink'
import { useRoleContextStore } from '@/stores/roleContext'

const CYCLES = ['B', 'C', 'D', 'A', 'S']

beforeEach(() => {
  for (const m of Object.values(mocks)) m.mockReset()
})

describe('useTrimGenerationLink', () => {
  it('委派人先走初始化接口（静默）；初始化失败退回只读读取；只读成员只读取', async () => {
    const link = useTrimGenerationLink(ref('p1'), CYCLES)
    mocks.post.mockResolvedValue({ count: 2, procedures: [{ id: 'a' }, { id: 'b' }] })
    expect(await link.loadCycleRows('B', true)).toEqual([{ id: 'a' }, { id: 'b' }])
    expect(mocks.post).toHaveBeenCalledWith('/api/projects/p1/procedures/B/init', {}, { _silent: true })
    expect(mocks.getProcedures).not.toHaveBeenCalled()

    mocks.post.mockRejectedValue({ response: { status: 403 } })
    mocks.getProcedures.mockResolvedValue([{ id: 'r' }])
    expect(await link.loadCycleRows('B', true)).toEqual([{ id: 'r' }])

    mocks.post.mockReset()
    mocks.getProcedures.mockResolvedValue([])
    expect(await link.loadCycleRows('C', false)).toEqual([])
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it('同一循环并发加载共享一个初始化请求，完成后下一次会重新读取', async () => {
    const link = useTrimGenerationLink(ref('p1'), CYCLES)
    let resolve!: (value: any) => void
    mocks.post.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const first = link.loadCycleRows('B', true)
    const second = link.loadCycleRows('B', true)
    expect(mocks.post).toHaveBeenCalledTimes(1)
    resolve({ procedures: [{ id: 'shared' }] })
    expect(await first).toEqual([{ id: 'shared' }])
    expect(await second).toEqual([{ id: 'shared' }])

    mocks.post.mockResolvedValueOnce({ procedures: [{ id: 'fresh' }] })
    expect(await link.loadCycleRows('B', true)).toEqual([{ id: 'fresh' }])
    expect(mocks.post).toHaveBeenCalledTimes(2)
  })

  it('?cycle= 只认已知循环（大小写不敏感），其余忽略', () => {
    const link = useTrimGenerationLink(ref('p1'), CYCLES)
    expect(link.initialCycleFromRoute({ cycle: 'd' })).toBe('D')
    expect(link.initialCycleFromRoute({ cycle: ['A', 'B'] })).toBe('A')
    expect(link.initialCycleFromRoute({ cycle: 'Z' })).toBeNull()
    expect(link.initialCycleFromRoute({})).toBeNull()
  })

  it('粗裁状态：读到后按循环显示；读不到显示「状态未知」', async () => {
    const link = useTrimGenerationLink(ref('p1'), CYCLES)
    mocks.confirmations.mockResolvedValue([
      { cycle: 'D', trim_state: 'confirmed', program_count: 17, confirmed_at: null, confirmed_by: '王经理' },
      { cycle: 'A', trim_state: 'unconfirmed', program_count: 3, confirmed_at: null, confirmed_by: null },
    ])
    await link.loadConfirmations()
    expect(link.confirmationText('D')).toBe('已保存（王经理）')
    expect(link.isConfirmed('D')).toBe(true)
    expect(link.confirmationText('A')).toBe('未保存')
    expect(link.confirmationText('B')).toBe('状态未知')
    mocks.confirmations.mockRejectedValue(new Error('x'))
    await link.loadConfirmations()
    expect(link.confirmationText('D')).toBe('已保存（王经理）')
    expect(link.confirmationLoadFailed.value).toBe(true)
  })

  it('粗裁状态只接纳最新请求，旧响应晚到不能覆盖保存后的新状态', async () => {
    const link = useTrimGenerationLink(ref('p1'), CYCLES)
    let resolveOld!: (value: any[]) => void
    let resolveNew!: (value: any[]) => void
    mocks.confirmations
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNew = resolve }))
    const oldRequest = link.loadConfirmations()
    const newRequest = link.loadConfirmations()
    resolveNew([{ cycle: 'A', trim_state: 'confirmed', program_count: 5, confirmed_at: null, confirmed_by: '新状态' }])
    await newRequest
    resolveOld([{ cycle: 'A', trim_state: 'unconfirmed', program_count: 5, confirmed_at: null, confirmed_by: null }])
    await oldRequest
    expect(link.confirmationText('A')).toBe('已保存（新状态）')
    expect(link.confirmationLoadFailed.value).toBe(false)
  })

  it('业务分类建议：只处理执行中且有建议的行，理由取后端说明', () => {
    const link = useTrimGenerationLink(ref('p1'), CYCLES)
    const hint = { reason: '按项目业务分类 C 类，本行 9 个底稿均不适用：仅 A 类适用', codes: ['A17'] }
    const rows = [
      { _applicable: true, status: 'execute', skip_reason: '', category_hint: hint },
      { _applicable: false, status: 'not_applicable', skip_reason: '已裁', category_hint: hint },
      { _applicable: true, status: 'execute', skip_reason: '', category_hint: null },
    ]
    expect(link.categoryHintRows(rows)).toEqual([rows[0]])
    expect(link.adoptAllCategoryHints(rows)).toBe(1)
    expect(rows[0]).toMatchObject({ _applicable: false, status: 'not_applicable', skip_reason: hint.reason })
    expect(rows[1].skip_reason).toBe('已裁')
    expect(rows[2]).toMatchObject({ _applicable: true, status: 'execute' })
  })

  it('保存后的下一步：能生成时三选一；不能生成时只问是否去委派', async () => {
    const link = useTrimGenerationLink(ref('p1'), CYCLES)
    // 没装 Pinia：按「不能生成」
    expect(link.canGenerate.value).toBe(false)
    mocks.confirm.mockResolvedValue(true)
    expect(await link.promptAfterSave()).toBe('delegate')
    mocks.confirm.mockRejectedValue('cancel')
    expect(await link.promptAfterSave()).toBe('stay')

    setActivePinia(createPinia())
    const role = useRoleContextStore()
    role.currentProjectRole = { permission_level: 'edit' } as any
    const editable = useTrimGenerationLink(ref('p1'), CYCLES)
    expect(editable.canGenerate.value).toBe(true)
    mocks.confirm.mockResolvedValue(true)
    expect(await editable.promptAfterSave()).toBe('generate')
    mocks.confirm.mockRejectedValue('cancel')
    expect(await editable.promptAfterSave()).toBe('delegate')
    mocks.confirm.mockRejectedValue('close')
    expect(await editable.promptAfterSave()).toBe('stay')
  })
})
