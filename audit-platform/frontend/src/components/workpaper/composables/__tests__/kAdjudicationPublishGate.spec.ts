/**
 * kAdjudicationPublishGate.spec.ts — K 循环审定表"发布到试算表"经显式确认门
 *
 * spec: .kiro/specs/tb-writeback-explicit-publish-gate/ (Task 7/8/9 / M6 K 循环 / Task 16 决策a / Req 1,2,5,6,8)
 *
 * 背景：此前 K 循环各审定表直调旧端点 `PUT /projects/{pid}/trial-balance/writeback`
 * （K5/K7 甚至是"假回写"只 emit 不写 TB），绕过显式确认门。改造后与 D2/D4-1/F 同范式：
 * 二次确认（中文）→ `POST /workpapers/{wpId}/audit-determination/publish-to-tb`（writeback_rows）。
 *
 * 覆盖两类活路径入口：
 *  - Group A（composable writebackTB，二次确认在宿主 Tab）：K1(双科目1221+坏账准备)、K3(2241)、
 *    K4(动态科目)、K5(动态科目2801，补真回写去假提示)、K10(6117 发生额)。
 *  - Group B（useKxAdjudication.writeback()，内置二次确认）：K8(6601)、K9(6602)、K11(6701) 发生额。
 *
 * 断言：确认→POST publish-to-tb（sheet_name 含 K{n}-1 / writeback_rows 科目 / amount_kind）；
 *       不再调 PUT trial-balance/writeback；发布后 emit substantive:adjudicated；
 *       Group B 额外验证取消二次确认→无 POST/无 emit + readonly→无 POST。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { useK1FormData } from '../useK1FormData'
import { useK3FormData } from '../useK3FormData'
import { useK4FormData } from '../useK4FormData'
import { useK5FormData } from '../useK5FormData'
import { useK10FormData } from '../useK10FormData'
import { useK8Adjudication } from '../useK8Adjudication'
import { useK9Adjudication } from '../useK9Adjudication'
import { useK11Adjudication } from '../useK11Adjudication'

// ─── mock apiProxy（隔离网络） ───
const { mockPost, mockPut, mockGet } = vi.hoisted(() => ({
  mockPost: vi.fn(async () => ({ message: '已发布到试算表', published: true })),
  mockPut: vi.fn(async () => ({})),
  mockGet: vi.fn(async () => ({ data: [] })),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { post: mockPost, put: mockPut, get: mockGet },
}))

// ─── mock element-plus（ElMessageBox.confirm / ElMessage） ───
const { confirmRef } = vi.hoisted(() => ({ confirmRef: { resolve: true } }))

vi.mock('element-plus', () => ({
  ElMessageBox: {
    confirm: vi.fn(async () => {
      if (!confirmRef.resolve) throw new Error('cancel')
      return 'confirm'
    }),
  },
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

beforeEach(() => {
  mockPost.mockClear()
  mockPut.mockClear()
  mockGet.mockClear()
  confirmRef.resolve = true
})

// ════════════════════════════════════════════════════════════════════════════
// Group A — composable writebackTB（二次确认在宿主 Tab，此处验证发布端点契约）
// ════════════════════════════════════════════════════════════════════════════

interface FormDataCase {
  cycle: string
  wpId: string
  sheetCodeRe: RegExp
  /** 期望 writeback_rows 至少包含的科目码 */
  expectAccountCodes: string[]
  amountKind: 'balance' | 'occurrence'
  wpCode: string
  /** 触发发布，返回 Promise */
  invoke: (wpId: Ref<string>) => Promise<void>
}

const FORM_DATA_CASES: FormDataCase[] = [
  {
    cycle: 'K1', wpId: 'wp-k1-001', sheetCodeRe: /K1-1/, expectAccountCodes: ['1221', '1231'],
    amountKind: 'balance', wpCode: 'K1',
    invoke: async (wpId) => {
      const fd = useK1FormData({ wpId, projectId: ref('proj-k1') })
      await fd.writebackTB(500000, 30000) // 双科目：其他应收款 + 坏账准备
    },
  },
  {
    cycle: 'K3', wpId: 'wp-k3-001', sheetCodeRe: /K3-1/, expectAccountCodes: ['2241'],
    amountKind: 'balance', wpCode: 'K3',
    invoke: async (wpId) => {
      const fd = useK3FormData({ wpId, projectId: ref('proj-k3'), sheetPrefix: 'K3-1' })
      await fd.writebackTB(800000)
    },
  },
  {
    cycle: 'K4', wpId: 'wp-k4-001', sheetCodeRe: /K4-1/, expectAccountCodes: ['2249'],
    amountKind: 'balance', wpCode: 'K4',
    invoke: async (wpId) => {
      const fd = useK4FormData({ wpId, projectId: ref('proj-k4'), sheetPrefix: 'K4-1' })
      // K4 宁缺勿造：科目由调用方(Tab k4Code)动态传入；此处传显式科目验证透传
      await fd.writebackTB(600000, '2249')
    },
  },
  {
    cycle: 'K5', wpId: 'wp-k5-001', sheetCodeRe: /K5-1/, expectAccountCodes: ['2801'],
    amountKind: 'balance', wpCode: 'K5',
    invoke: async (wpId) => {
      // K5 补真回写（Task16 决策a）：科目取 k5AccountCode（无 tb_source_codes 兜底 2801，非旧 2701）
      const fd = useK5FormData({ wpId, projectId: ref('proj-k5'), sheetPrefix: '1' })
      await fd.writebackTB(1200000)
    },
  },
  {
    cycle: 'K10', wpId: 'wp-k10-001', sheetCodeRe: /K10-1/, expectAccountCodes: ['6117'],
    amountKind: 'occurrence', wpCode: 'K10',
    invoke: async (wpId) => {
      const fd = useK10FormData({ wpId, projectId: ref('proj-k10') })
      await fd.writebackTB(450000) // 6117 其他收益发生额
    },
  },
]

describe.each(FORM_DATA_CASES)(
  '$cycle 审定表 writebackTB 走显式发布门（tb-writeback-explicit-publish-gate Task 7/8）',
  (c) => {
    it('调 POST publish-to-tb，body 含审定表 sheet_name + writeback_rows(科目/口径)', async () => {
      const scope = effectScope()
      try {
        await scope.run(() => c.invoke(ref(c.wpId)))
        expect(mockPost).toHaveBeenCalledTimes(1)
        const [url, body] = mockPost.mock.calls[0]!
        expect(url).toContain(`/api/workpapers/${c.wpId}/audit-determination/publish-to-tb`)
        expect(body.sheet_name).toMatch(c.sheetCodeRe)
        expect(Array.isArray(body.writeback_rows)).toBe(true)
        const codes = body.writeback_rows.map((r: any) => r.account_code)
        for (const code of c.expectAccountCodes) {
          expect(codes).toContain(code)
        }
        for (const row of body.writeback_rows) {
          expect(row.amount_kind).toBe(c.amountKind)
          expect(typeof row.audited_amount).toBe('number')
        }
      } finally {
        scope.stop()
      }
    })

    it('不再调旧端点 trial-balance/writeback（PUT 或 POST 变体）', async () => {
      const scope = effectScope()
      try {
        await scope.run(() => c.invoke(ref(c.wpId)))
        // 仅断言无任何 trial-balance/writeback 直调（K10 的 checklist-responses PUT 属正常持久化，不受限）
        for (const call of mockPut.mock.calls) {
          expect(call[0]).not.toContain('trial-balance/writeback')
        }
        for (const call of mockPost.mock.calls) {
          expect(call[0]).not.toContain('trial-balance/writeback')
        }
      } finally {
        scope.stop()
      }
    })

    it('发布后仍 emit substantive:adjudicated（下游附注刷新回归 / Req 8）', async () => {
      const emitSpy = vi.fn()
      eventBus.on('substantive:adjudicated', emitSpy)
      const scope = effectScope()
      try {
        await scope.run(() => c.invoke(ref(c.wpId)))
        expect(mockPost).toHaveBeenCalledTimes(1)
        expect(emitSpy).toHaveBeenCalled()
        const payload = emitSpy.mock.calls[0][0] as { wpCode: string }
        expect(payload.wpCode).toBe(c.wpCode)
      } finally {
        eventBus.off('substantive:adjudicated', emitSpy)
        scope.stop()
      }
    })
  },
)

describe('K1 双科目在单次 writeback_rows 原子发布（Task 8 / Req 5）', () => {
  it('1221 + 坏账准备 1231 同在一次 POST', async () => {
    const scope = effectScope()
    try {
      const fd = scope.run(() => useK1FormData({ wpId: ref('wp-k1-002'), projectId: ref('proj-k1') }))!
      await fd.writebackTB(500000, 30000)
      expect(mockPost).toHaveBeenCalledTimes(1)
      const body = mockPost.mock.calls[0]![1]
      expect(body.writeback_rows).toHaveLength(2)
      const byCode = Object.fromEntries(body.writeback_rows.map((r: any) => [r.account_code, r.audited_amount]))
      expect(byCode['1221']).toBe(500000)
      expect(byCode['1231']).toBe(30000)
    } finally {
      scope.stop()
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
// Group B — useKxAdjudication.writeback()（内置二次确认，损益发生额 occurrence）
// ════════════════════════════════════════════════════════════════════════════

interface AdjCase {
  cycle: string
  wpId: string
  sheetCodeRe: RegExp
  accountCode: string
  wpCode: string
  build: (readonly: boolean) => { writeback: () => Promise<void> }
}

const ADJ_CASES: AdjCase[] = [
  {
    cycle: 'K8', wpId: 'wp-k8-001', sheetCodeRe: /K8-1/, accountCode: '6601', wpCode: 'K8',
    build: (readonly) =>
      useK8Adjudication({
        allResponses: ref(new Map()),
        projectId: ref('proj-k8'),
        wpId: ref('wp-k8-001'),
        isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'K9', wpId: 'wp-k9-001', sheetCodeRe: /K9-1/, accountCode: '6602', wpCode: 'K9',
    build: (readonly) =>
      useK9Adjudication({
        allResponses: ref(new Map()),
        projectId: ref('proj-k9'),
        wpId: ref('wp-k9-001'),
        isReadonly: ref(readonly),
      }) as any,
  },
  {
    cycle: 'K11', wpId: 'wp-k11-001', sheetCodeRe: /K11-1/, accountCode: '6701', wpCode: 'K11',
    build: (readonly) =>
      useK11Adjudication({
        allResponses: ref(new Map()),
        projectId: ref('proj-k11'),
        wpId: ref('wp-k11-001'),
        isReadonly: ref(readonly),
      }) as any,
  },
]

function runAdj(c: AdjCase, readonly = false) {
  const scope = effectScope()
  const api = scope.run(() => c.build(readonly))!
  return { api, dispose: () => scope.stop() }
}

describe.each(ADJ_CASES)(
  '$cycle 审定发生额 writeback 走显式发布门（tb-writeback-explicit-publish-gate Task 7 / occurrence）',
  (c) => {
    it('确认后调 POST publish-to-tb（sheet_name 含 K{n}-1 / 科目 occurrence）', async () => {
      const { api, dispose } = runAdj(c)
      try {
        await api.writeback()
        expect(mockPost).toHaveBeenCalledTimes(1)
        const [url, body] = mockPost.mock.calls[0]!
        expect(url).toContain(`/api/workpapers/${c.wpId}/audit-determination/publish-to-tb`)
        expect(body.sheet_name).toMatch(c.sheetCodeRe)
        const row = body.writeback_rows[0]
        expect(row.account_code).toBe(c.accountCode)
        expect(row.amount_kind).toBe('occurrence')
      } finally {
        dispose()
      }
    })

    it('不再调旧端点 trial-balance/writeback（PUT）', async () => {
      const { api, dispose } = runAdj(c)
      try {
        await api.writeback()
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
      const { api, dispose } = runAdj(c)
      try {
        await api.writeback()
        expect(mockPost).not.toHaveBeenCalled()
        expect(emitSpy).not.toHaveBeenCalled()
      } finally {
        eventBus.off('substantive:adjudicated', emitSpy)
        dispose()
      }
    })

    it('readonly → 不发请求（早退）', async () => {
      const { api, dispose } = runAdj(c, true)
      try {
        await api.writeback()
        expect(mockPost).not.toHaveBeenCalled()
      } finally {
        dispose()
      }
    })

    it('发布后仍 emit substantive:adjudicated（Req 8）', async () => {
      const emitSpy = vi.fn()
      eventBus.on('substantive:adjudicated', emitSpy)
      const { api, dispose } = runAdj(c)
      try {
        await api.writeback()
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
