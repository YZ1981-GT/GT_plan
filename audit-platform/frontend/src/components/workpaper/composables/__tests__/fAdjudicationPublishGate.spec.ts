/**
 * fAdjudicationPublishGate.spec.ts — F1~F5 审定表"发布到试算表"经显式确认门
 *
 * spec: .kiro/specs/tb-writeback-explicit-publish-gate/ (Task 3 / M2 F 循环 / Req 1,2,5,6,8)
 *
 * 背景：此前 F1~F5（form B）靠 useFxAdjudication.publishAdjudicated 自动 dispatch
 * `fx:writeback-trial-balance` → GtFx 监听 → 旧端点
 * `PUT /projects/{pid}/trial-balance/writeback` 直写 audited_amount，**绕过**显式确认门。
 * 改造后与 D2/D4-1 同范式：显式 publishToTb → 二次确认（中文）→
 * `POST /workpapers/{wpId}/audit-determination/publish-to-tb`（writeback_rows 预算行）。
 *
 * 参数化验证 F1~F5：
 * 1. 确认后调 POST publish-to-tb，body 含审定表 sheet_name([D-N]{n}-1 可解) + writeback_rows。
 * 2. 用户取消二次确认 → 不发请求、不 emit substantive:adjudicated。
 * 3. readonly → 不发请求。
 * 4. **不再**调旧端点 trial-balance/writeback(PUT)；**不再** dispatch/监听 fx:writeback-trial-balance。
 * 5. 发布成功后仍 emit substantive:adjudicated（下游附注/F5-7 校验区刷新回归）。
 * 6. amount_kind：F1~F4=balance，F5=occurrence（损益发生额）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { useF1Adjudication } from '../useF1Adjudication'
import { useF2Adjudication } from '../useF2Adjudication'
import { useF3Adjudication } from '../useF3Adjudication'
import { useF4Adjudication } from '../useF4Adjudication'
import { useF5Adjudication } from '../useF5Adjudication'

// ─── mock apiProxy（隔离网络） ───
const { mockPost, mockPut, confirmRef } = vi.hoisted(() => ({
  mockPost: vi.fn(async () => ({ message: '已发布审定数到试算表', published: true })),
  mockPut: vi.fn(async () => ({})),
  confirmRef: { resolve: true },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { post: mockPost, put: mockPut, get: vi.fn() },
}))

// ─── mock element-plus（ElMessageBox.confirm / ElMessage） ───
vi.mock('element-plus', () => ({
  ElMessageBox: {
    confirm: vi.fn(async () => {
      if (!confirmRef.resolve) throw new Error('cancel')
      return 'confirm'
    }),
  },
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

// F1 依赖 crossSheet：最小 stub（本 gate 测试只关心 publishToTb 是否发 POST，不关心审定数值）
function makeF1CrossSheetStub() {
  return {
    natureAggregation: ref({}),
    agingAggregation: ref({}),
    detailRowCount: ref(0),
    adjustmentTotals: ref({ ajeTotal: 0, rjeTotal: 0 }),
  } as any
}

interface CycleCase {
  cycle: string
  wpId: string
  /** 期望 sheet_name 能解出的子码正则 */
  sheetCodeRe: RegExp
  /** 期望 writeback_rows 至少包含的科目码 */
  expectAccountCodes: string[]
  amountKind: 'balance' | 'occurrence'
  /** substantive:adjudicated 的 wpCode */
  wpCode: string
  /** 构造 adjudication，返回带 publishToTb/publishing 的 api */
  build: (allResponses: Ref<Map<string, any>>, readonly: boolean) => {
    publishToTb: () => Promise<void>
    publishing: Ref<boolean>
  }
}

const CASES: CycleCase[] = [
  {
    cycle: 'F1', wpId: 'wp-f1-001', sheetCodeRe: /F1-1/, expectAccountCodes: ['1123'],
    amountKind: 'balance', wpCode: 'F1',
    build: (allResponses, readonly) =>
      useF1Adjudication({
        allResponses,
        wpId: ref('wp-f1-001'),
        projectId: ref('proj-f1'),
        saveImmediate: vi.fn(async () => {}),
        debouncedSave: vi.fn(),
        crossSheet: makeF1CrossSheetStub(),
        isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'F2', wpId: 'wp-f2-001', sheetCodeRe: /F2-1/, expectAccountCodes: ['1401'],
    amountKind: 'balance', wpCode: 'F2',
    build: (allResponses, readonly) =>
      useF2Adjudication({
        wpId: ref('wp-f2-001'),
        projectId: ref('proj-f2'),
        allResponses,
        debouncedSave: vi.fn(),
        isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'F3', wpId: 'wp-f3-001', sheetCodeRe: /F3-1/, expectAccountCodes: ['2201'],
    amountKind: 'balance', wpCode: 'F3',
    build: (allResponses, readonly) =>
      useF3Adjudication({
        wpId: ref('wp-f3-001'),
        projectId: ref('proj-f3'),
        allResponses,
        isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'F4', wpId: 'wp-f4-001', sheetCodeRe: /F4-1/, expectAccountCodes: ['2202'],
    amountKind: 'balance', wpCode: 'F4',
    build: (allResponses, readonly) =>
      useF4Adjudication({
        wpId: ref('wp-f4-001'),
        projectId: ref('proj-f4'),
        allResponses,
        isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'F5', wpId: 'wp-f5-001', sheetCodeRe: /F5-1/, expectAccountCodes: ['6401'],
    amountKind: 'occurrence', wpCode: 'F5',
    build: (allResponses, readonly) =>
      useF5Adjudication({
        wpId: ref('wp-f5-001'),
        projectId: ref('proj-f5'),
        allResponses,
        isReadonly: ref(readonly),
      }) as any,
  },
]

function run(c: CycleCase, readonly = false) {
  const scope = effectScope()
  const allResponses = ref(new Map<string, any>())
  const api = scope.run(() => c.build(allResponses, readonly))!
  return { api, dispose: () => scope.stop() }
}

beforeEach(() => {
  mockPost.mockClear()
  mockPut.mockClear()
  confirmRef.resolve = true
})

describe.each(CASES)(
  '$cycle 审定表发布经显式确认门（tb-writeback-explicit-publish-gate Task 3）',
  (c) => {
    it('确认后调 POST publish-to-tb，body 含审定表 sheet_name + writeback_rows(科目/口径)', async () => {
      const { api, dispose } = run(c)
      try {
        await api.publishToTb()
        expect(mockPost).toHaveBeenCalledTimes(1)
        const [url, body] = mockPost.mock.calls[0]!
        expect(url).toContain(`/api/workpapers/${c.wpId}/audit-determination/publish-to-tb`)
        // sheet_name 须含审定表子码（后端 extract_determination_wp_code 据此解出）
        expect(body.sheet_name).toMatch(c.sheetCodeRe)
        expect(Array.isArray(body.writeback_rows)).toBe(true)
        expect(body.writeback_rows.length).toBeGreaterThan(0)
        const codes = body.writeback_rows.map((r: any) => r.account_code)
        for (const code of c.expectAccountCodes) {
          expect(codes).toContain(code)
        }
        // amount_kind：F5 发生额 occurrence，其余余额 balance
        for (const row of body.writeback_rows) {
          expect(row.amount_kind).toBe(c.amountKind)
          expect(typeof row.audited_amount).toBe('number')
        }
      } finally {
        dispose()
      }
    })

    it('不再调旧端点 trial-balance/writeback（PUT）', async () => {
      const { api, dispose } = run(c)
      try {
        await api.publishToTb()
        expect(mockPut).not.toHaveBeenCalled()
        for (const call of mockPost.mock.calls) {
          expect(call[0]).not.toContain('trial-balance/writeback')
        }
      } finally {
        dispose()
      }
    })

    it('用户取消二次确认 → 不发请求、不 emit substantive:adjudicated', async () => {
      confirmRef.resolve = false
      const emitSpy = vi.fn()
      eventBus.on('substantive:adjudicated', emitSpy)
      const { api, dispose } = run(c)
      try {
        await api.publishToTb()
        expect(mockPost).not.toHaveBeenCalled()
        expect(emitSpy).not.toHaveBeenCalled()
      } finally {
        eventBus.off('substantive:adjudicated', emitSpy)
        dispose()
      }
    })

    it('readonly → 不发请求（处理函数早退）', async () => {
      const { api, dispose } = run(c, true)
      try {
        await api.publishToTb()
        expect(mockPost).not.toHaveBeenCalled()
      } finally {
        dispose()
      }
    })

    it(`不再 dispatch 绕过门的 ${c.cycle.toLowerCase()}:writeback-trial-balance 事件`, async () => {
      const spy = vi.fn()
      const evt = `${c.cycle.toLowerCase()}:writeback-trial-balance`
      window.addEventListener(evt, spy)
      const { api, dispose } = run(c)
      try {
        await api.publishToTb()
        expect(spy).not.toHaveBeenCalled()
      } finally {
        window.removeEventListener(evt, spy)
        dispose()
      }
    })

    it('发布成功后仍 emit substantive:adjudicated（下游附注/F5-7 校验区刷新回归 / Req 8）', async () => {
      const emitSpy = vi.fn()
      eventBus.on('substantive:adjudicated', emitSpy)
      const { api, dispose } = run(c)
      try {
        await api.publishToTb()
        expect(mockPost).toHaveBeenCalledTimes(1)
        expect(emitSpy).toHaveBeenCalled()
        const payload = emitSpy.mock.calls[0][0] as { wpCode: string }
        expect(payload.wpCode).toBe(c.wpCode)
      } finally {
        eventBus.off('substantive:adjudicated', emitSpy)
        dispose()
      }
    })
  },
)
