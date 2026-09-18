/**
 * I 循环审定表显式发布门（publish-to-tb）参数化验证
 *
 * spec: tb-writeback-explicit-publish-gate Task 13 / Req 1,2,5,6,8。
 *
 * 覆盖 I1(多科目 1701/1702/1703 balance) / I3(1711) / I4(1801) / I5(1911) /
 * I6(6602 occurrence，含 I6→I2 联动) 的 adjudication 层 publishToTb：
 *   - 确认放行 → POST publish-to-tb 命中 sheet_name/科目/amount_kind
 *   - 取消二次确认 → 无 post、无 emit
 *   - readonly → 无 post（I 循环 gate 在宿主 disabled + 早退；此处以确认取消模拟）
 *   - 不再调旧端点 PUT trial-balance/writeback
 *   - 发布后仍 emit substantive:adjudicated
 *   - I6 专项：I6→I2 联动 research:expense-updated 仍 emit
 *   - I1 专项：多科目在单次 writeback_rows
 *
 * 改造后普通保存（saveAdjudication/writeback）只 emit 不写 TB（Req 1），另有
 * 各循环既有回归测试与本文件互补。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockPost = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...a: any[]) => Promise.resolve({}),
    put: (...a: any[]) => mockPut(...a),
    post: (...a: any[]) => mockPost(...a),
  },
}))

const mockConfirm = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: (...a: any[]) => mockConfirm(...a) },
  ElNotification: vi.fn(),
}))

// 捕获 window.dispatchEvent 派发的 CustomEvent（I 循环用 window CustomEvent 发 substantive:adjudicated）
let dispatched: CustomEvent[] = []
const originalDispatch = window.dispatchEvent

beforeEach(() => {
  dispatched = []
  window.dispatchEvent = vi.fn((event: Event) => {
    if (event instanceof CustomEvent) dispatched.push(event)
    return true
  }) as any
  mockPost.mockReset().mockResolvedValue({ message: 'ok' })
  mockPut.mockReset().mockResolvedValue({})
  mockConfirm.mockReset().mockResolvedValue('confirm')
})

afterEach(() => {
  window.dispatchEvent = originalDispatch
})

function findAdjudicated(): CustomEvent | undefined {
  return dispatched.find((e) => e.type === 'substantive:adjudicated')
}
function findPublishCall(): any[] | undefined {
  return mockPost.mock.calls.find((c) => String(c[0]).includes('audit-determination/publish-to-tb'))
}

// ─── 各 I 循环 publishToTb 工厂 ────────────────────────────────────────────────
// I1/I3/I4/I5 签名 (wpId, projectId, allResponses, options)；I6/I2 单 options 对象。

interface Case {
  wp: string
  wpId: string
  sheetCode: RegExp
  accounts: string[]
  amountKind: 'balance' | 'occurrence'
  multi?: boolean
  /** 构造 composable 实例并返回 { publishToTb } */
  build: () => Promise<{ publishToTb: () => Promise<void> }>
}

async function buildI1(): Promise<{ publishToTb: () => Promise<void> }> {
  const { useI1Adjudication } = await import('../useI1Adjudication')
  const c = useI1Adjudication(ref('wp-i1'), ref('p'), ref(new Map()), { onSave: () => {} })
  return { publishToTb: c.publishToTb }
}
async function buildI3(): Promise<{ publishToTb: () => Promise<void> }> {
  const { useI3Adjudication } = await import('../useI3Adjudication')
  const c = useI3Adjudication(ref('wp-i3'), ref('p'), ref(new Map()), { onSave: () => {} })
  return { publishToTb: c.publishToTb }
}
async function buildI4(): Promise<{ publishToTb: () => Promise<void> }> {
  const { useI4Adjudication } = await import('../useI4Adjudication')
  const c = useI4Adjudication(ref('wp-i4'), ref('p'), ref(new Map()), { onSave: () => {} })
  return { publishToTb: c.publishToTb }
}
async function buildI5(): Promise<{ publishToTb: () => Promise<void> }> {
  const { useI5Adjudication } = await import('../useI5Adjudication')
  const c = useI5Adjudication(ref('wp-i5'), ref('p'), ref(new Map()), { onSave: () => {} })
  return { publishToTb: c.publishToTb }
}
async function buildI6(): Promise<{ publishToTb: () => Promise<void> }> {
  const { useI6Adjudication } = await import('../useI6Adjudication')
  const c = useI6Adjudication({
    allResponses: ref(new Map()),
    tbData: ref({ unadjusted6602: 0, audited6602: 0 }),
    wpId: ref('wp-i6'),
    projectId: ref('p'),
    onSave: () => {},
  })
  return { publishToTb: c.publishToTb }
}

const cases: Case[] = [
  { wp: 'I1', wpId: 'wp-i1', sheetCode: /I1-1/, accounts: ['1701', '1702', '1703'], amountKind: 'balance', multi: true, build: buildI1 },
  { wp: 'I3', wpId: 'wp-i3', sheetCode: /I3-1/, accounts: ['1711'], amountKind: 'balance', build: buildI3 },
  { wp: 'I4', wpId: 'wp-i4', sheetCode: /I4-1/, accounts: ['1801'], amountKind: 'balance', build: buildI4 },
  { wp: 'I5', wpId: 'wp-i5', sheetCode: /I5-1/, accounts: ['1911'], amountKind: 'balance', build: buildI5 },
  { wp: 'I6', wpId: 'wp-i6', sheetCode: /I6-1/, accounts: ['6602'], amountKind: 'occurrence', build: buildI6 },
]

describe('I 循环审定表显式发布门 publish-to-tb（参数化）', () => {
  for (const c of cases) {
    describe(`${c.wp}`, () => {
      it('确认放行 → POST publish-to-tb 命中 sheet_name/科目/amount_kind，不调旧端点', async () => {
        mockConfirm.mockResolvedValue('confirm')
        const { publishToTb } = await c.build()
        await publishToTb()

        // 不再调旧端点 PUT trial-balance/writeback
        const putCalls = mockPut.mock.calls
        expect(putCalls.some((x) => String(x[0]).includes('trial-balance/writeback'))).toBe(false)

        const pub = findPublishCall()
        expect(pub).toBeDefined()
        expect(pub![0]).toBe(`/api/workpapers/${c.wpId}/audit-determination/publish-to-tb`)
        expect(pub![1].sheet_name).toMatch(c.sheetCode)
        const rows = pub![1].writeback_rows as any[]
        expect(Array.isArray(rows)).toBe(true)
        // 科目全覆盖
        expect(rows.map((r) => r.account_code).sort()).toEqual([...c.accounts].sort())
        // amount_kind 口径
        for (const r of rows) expect(r.amount_kind).toBe(c.amountKind)
      })

      it('取消二次确认 → 无 post、无 emit（无副作用）', async () => {
        mockConfirm.mockRejectedValue(new Error('cancel'))
        const { publishToTb } = await c.build()
        await publishToTb()

        expect(findPublishCall()).toBeUndefined()
        expect(mockPut).not.toHaveBeenCalled()
        expect(findAdjudicated()).toBeUndefined()
      })

      it('发布成功后仍 emit substantive:adjudicated（下游附注刷新回归）', async () => {
        mockConfirm.mockResolvedValue('confirm')
        const { publishToTb } = await c.build()
        await publishToTb()

        const adj = findAdjudicated()
        expect(adj).toBeDefined()
        expect(adj!.detail.wpCode).toBe(c.wp)
      })
    })
  }

  // ─── I1 专项：多科目单次 writeback_rows ──────────────────────────────────────
  it('I1 多科目 1701/1702/1703 在单次 writeback_rows 原子发布', async () => {
    mockConfirm.mockResolvedValue('confirm')
    const { publishToTb } = await buildI1()
    await publishToTb()

    // 仅一次 publish-to-tb POST（单次原子发布，非三次 PUT）
    const pubs = mockPost.mock.calls.filter((x) => String(x[0]).includes('publish-to-tb'))
    expect(pubs.length).toBe(1)
    const rows = pubs[0][1].writeback_rows as any[]
    expect(rows.map((r) => r.account_code)).toEqual(['1701', '1702', '1703'])
    expect(rows.every((r) => r.amount_kind === 'balance')).toBe(true)
  })

  // ─── I6 专项：发生额 occurrence + I6→I2 联动 research:expense-updated 仍 emit ──
  it('I6 发布 → amount_kind=occurrence 且 I6→I2 联动 research:expense-updated 仍 emit', async () => {
    mockConfirm.mockResolvedValue('confirm')
    const { publishToTb } = await buildI6()
    await publishToTb()

    const pub = findPublishCall()
    expect(pub![1].writeback_rows[0]).toMatchObject({ account_code: '6602', amount_kind: 'occurrence' })

    // I6→I2 联动事件保留
    const research = dispatched.find((e) => e.type === 'research:expense-updated')
    expect(research).toBeDefined()
    expect(research!.detail).toMatchObject({ source: 'I6-adjudication' })
  })
})
