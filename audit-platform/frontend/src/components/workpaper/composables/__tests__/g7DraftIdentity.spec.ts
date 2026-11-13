import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest'
import { ref } from 'vue'

const getMock = vi.fn()
const putMock = vi.fn()
let consoleWarnSpy: { mockRestore(): void } | undefined

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: unknown[]) => getMock(...args),
    put: (...args: unknown[]) => putMock(...args),
    post: vi.fn(),
  },
}))
vi.mock('@/services/trialBalanceRows', () => ({
  fetchTrialBalanceRows: vi.fn(async () => ({ rows: [] })),
  tbSumUnder: vi.fn(() => 0),
}))
vi.mock('../workpaperAuditYear', () => ({ useWorkpaperAuditYear: () => ref(2025) }))
vi.mock('element-plus', () => ({ ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() } }))

const FORM_DATA = [
  ['G7 main', 'g7-main-draft', 'G7-main-draft', () => import('../useG7FormData').then(({ useG7FormData }) => useG7FormData({ wpId: ref('wp-1'), projectId: ref('project-1') }))],
  ['G7 子公司', 'g7-sub-draft', 'G7-sub-draft', () => import('../useG7SubFormData').then(({ useG7SubFormData }) => useG7SubFormData({ wpId: ref('wp-1'), projectId: ref('project-1') }))],
  ['G7 权益法', 'g7-equity-method-draft', 'G7-equity-draft', () => import('../useG7EquityMethodFormData').then(({ useG7EquityMethodFormData }) => useG7EquityMethodFormData({ wpId: ref('wp-1'), projectId: ref('project-1') }))],
] as const

describe('G7 草稿身份隔离', () => {
  beforeEach(() => {
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    localStorage.clear()
    sessionStorage.clear()
    getMock.mockReset()
    getMock.mockResolvedValue([])
    putMock.mockReset()
  })

  afterEach(() => {
    consoleWarnSpy?.mockRestore()
    consoleWarnSpy = undefined
  })

  it.each(FORM_DATA)('%s 不向另一登录用户恢复或自动写回草稿', async (_name, namespace, itemId, create) => {
    sessionStorage.setItem('user', JSON.stringify({ id: 'user-1' }))
    putMock.mockRejectedValueOnce(new Error('offline'))
    const first = await create()
    await first.saveImmediate(itemId, { remark: '用户一草稿' }, 1)
    expect(localStorage.getItem(`${namespace}:user-1:wp-1:${itemId}`)).toContain('用户一草稿')

    sessionStorage.setItem('user', JSON.stringify({ id: 'user-2' }))
    putMock.mockReset()
    const second = await create()
    await second.load()

    expect(second.data.value.has(itemId)).toBe(false)
    expect(putMock).not.toHaveBeenCalled()
  })
})