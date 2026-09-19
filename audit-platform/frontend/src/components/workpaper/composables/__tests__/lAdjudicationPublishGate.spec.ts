/**
 * lAdjudicationPublishGate.spec.ts — L1~L8 审定表"发布到试算表"经显式确认门
 *
 * spec: .kiro/specs/tb-writeback-explicit-publish-gate/ (Task 4 / L 循环 / Req 1,2,8)
 *
 * 背景：此前 L{n}-1 审定表靠 useL{n}Adjudication 的 watcher / tab watch / 保存按钮
 * **自动或无确认**调 useL{n}FormData.writebackTB → 经旧端点
 * `PUT /projects/{pid}/trial-balance/writeback` 直写 audited_amount，**绕过**显式确认门
 * （无二次确认/无幂等/无 publish_confirmed），且数据变化即写 TB（违反 Req 1）。
 * 改造后与 M/D 同范式：
 *   - 数据变化 / 普通保存仅 emit substantive:adjudicated（附注刷新），不写 TB；
 *   - 用户显式点「发布到试算表」→ publishToTb 二次确认（中文）→
 *     `POST /workpapers/{wpId}/audit-determination/publish-to-tb`（writeback_rows 预算行）。
 *
 * 每个 L{n} 参数化验证：
 * 1. writebackTB 走 POST publish-to-tb，body 含 sheet_name(L{n}-1) + writeback_rows(对应科目, amount_kind)。
 * 2. writebackTB 不再调旧端点 trial-balance/writeback(PUT)。
 * 3. writebackTB 成功后仍 emit substantive:adjudicated（下游附注刷新回归 / Req 8）。
 * 4. publishToTb 用户取消二次确认 → 不发请求、不 emit substantive:adjudicated。
 * 5. publishToTb 确认后 → 经 writebackTB 调 POST publish-to-tb。
 *
 * 口径差异：L8=6603 财务费用发生额口径（amount_kind='occurrence'）；其余余额类（'balance'）。
 * 结构差异：L1 FormData 用 positional args (wpId, projectId, isReadonly)；
 *           L5 writebackTB(payload) 双科目（2701+2702，单次 POST 两 writeback_rows）；
 *           L1/L3 Adjudication 在 @/composables，其余在 components/workpaper/composables。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, reactive, effectScope } from 'vue'
import { eventBus } from '@/utils/eventBus'

import { useL1FormData } from '@/composables/useL1FormData'
import { useL1Adjudication } from '@/composables/useL1Adjudication'
import { useL2FormData } from '../useL2FormData'
import { useL2Adjudication } from '../useL2Adjudication'
import { useL3FormData } from '../useL3FormData'
import { useL3Adjudication } from '@/composables/useL3Adjudication'
import { useL4FormData } from '../useL4FormData'
import { useL4Adjudication } from '../useL4Adjudication'
import { useL5FormData } from '../useL5FormData'
import { useL5Adjudication } from '../useL5Adjudication'
import { useL6FormData } from '../useL6FormData'
import { useL6Adjudication } from '../useL6Adjudication'
import { useL7FormData } from '../useL7FormData'
import { useL7Adjudication } from '../useL7Adjudication'
import { useL8FormData } from '../useL8FormData'
import { useL8Adjudication } from '../useL8Adjudication'

// ─── mock apiProxy（隔离网络） ───
const { mockPost, mockPut, mockGet, confirmRef } = vi.hoisted(() => ({
  mockPost: vi.fn(async () => ({ message: '已发布审定数到试算表', published: true })),
  mockPut: vi.fn(async () => ({})),
  mockGet: vi.fn(async () => []),
  confirmRef: { resolve: true },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { post: mockPost, put: mockPut, get: mockGet },
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

// ─── 各 L 循环元数据（科目 + 审定表子码 + composable 引用 + 结构差异适配） ───
interface LCase {
  cycle: string
  account: string
  sheetCode: string
  amountKind: 'balance' | 'occurrence'
  /** 构造 formData（吸收 L1 positional args vs 其余 options 差异） */
  makeFormData: (wpId: string, projectId: string) => any
  /** writebackTB 调用（吸收 L5 payload vs 其余 number 差异）→ 传入 amount */
  callWriteback: (formData: any, amount: number) => Promise<void>
  /** 构造 adjudication（吸收各构造签名差异） */
  makeAdjudication: (formData: any) => any
}

const L_CASES: LCase[] = [
  {
    cycle: 'L1', account: '2001', sheetCode: 'L1-1', amountKind: 'balance',
    makeFormData: (w, p) => useL1FormData(ref(w), ref(p), ref(false)),
    callWriteback: (fd, amt) => fd.writebackTB(amt),
    makeAdjudication: (fd) => useL1Adjudication(fd),
  },
  {
    cycle: 'L2', account: '2231', sheetCode: 'L2-1', amountKind: 'balance',
    makeFormData: (w, p) => useL2FormData({ wpId: ref(w), projectId: ref(p) }),
    callWriteback: (fd, amt) => fd.writebackTB(amt),
    makeAdjudication: (fd) => useL2Adjudication({
      allResponses: fd.allResponses,
      saveField: fd.saveField,
      debouncedSave: fd.debouncedSave,
      writebackTB: fd.writebackTB,
    }),
  },
  {
    cycle: 'L3', account: '2501', sheetCode: 'L3-1', amountKind: 'balance',
    makeFormData: (w, p) => useL3FormData({ wpId: ref(w), projectId: ref(p) }),
    callWriteback: (fd, amt) => fd.writebackTB(amt),
    makeAdjudication: (fd) => useL3Adjudication(fd),
  },
  {
    cycle: 'L4', account: '2502', sheetCode: 'L4-1', amountKind: 'balance',
    makeFormData: (w, p) => useL4FormData({ wpId: ref(w), projectId: ref(p) }),
    callWriteback: (fd, amt) => fd.writebackTB(amt),
    makeAdjudication: (fd) => useL4Adjudication(fd),
  },
  {
    cycle: 'L5', account: '2701', sheetCode: 'L5-1', amountKind: 'balance',
    makeFormData: (w, p) => useL5FormData({ wpId: ref(w), projectId: ref(p) }),
    // L5 双科目 payload：payableAmount(2701) + unrecognizedAmount(2702)
    callWriteback: (fd, amt) => fd.writebackTB({ payableAmount: amt, unrecognizedAmount: 0 }),
    // L5AdjudicationData = { grossRows: L5AdjRow[], unrecognizedRows: L5AdjRow[] }（reactive 对象）
    makeAdjudication: (fd) => useL5Adjudication(fd, reactive({ grossRows: [], unrecognizedRows: [] }) as any),
  },
  {
    cycle: 'L6', account: '2711', sheetCode: 'L6-1', amountKind: 'balance',
    makeFormData: (w, p) => useL6FormData({ wpId: ref(w), projectId: ref(p) }),
    callWriteback: (fd, amt) => fd.writebackTB(amt),
    makeAdjudication: (fd) => useL6Adjudication(fd, ref([])),
  },
  {
    cycle: 'L7', account: 'BS-071', sheetCode: 'L7-1', amountKind: 'balance',
    makeFormData: (w, p) => useL7FormData({ wpId: ref(w), projectId: ref(p) }),
    callWriteback: (fd, amt) => fd.writebackTB(amt),
    makeAdjudication: (fd) => useL7Adjudication(fd, ref([])),
  },
  {
    cycle: 'L8', account: '6603', sheetCode: 'L8-1', amountKind: 'occurrence',
    makeFormData: (w, p) => useL8FormData({ wpId: ref(w), projectId: ref(p) }),
    callWriteback: (fd, amt) => fd.writebackTB(amt),
    makeAdjudication: (fd) => useL8Adjudication(fd, ref([])),
  },
]

beforeEach(() => {
  mockPost.mockClear()
  mockPut.mockClear()
  mockGet.mockClear()
  confirmRef.resolve = true
})

describe.each(L_CASES)(
  '$cycle-1 审定表发布经显式确认门（tb-writeback-explicit-publish-gate Task 4）',
  ({ cycle, account, sheetCode, amountKind, makeFormData, callWriteback, makeAdjudication }) => {
    const codeRe = new RegExp(sheetCode.replace('-', '\\-'))

    it(`writebackTB 走 POST publish-to-tb，body 含 sheet_name(${sheetCode}) + writeback_rows(${account}, ${amountKind})`, async () => {
      const scope = effectScope()
      await scope.run(async () => {
        const formData = makeFormData('wp-001', 'proj-001')
        await callWriteback(formData, 500000)

        expect(mockPost).toHaveBeenCalledTimes(1)
        const [url, body] = mockPost.mock.calls[0]!
        expect(url).toContain('/api/workpapers/wp-001/audit-determination/publish-to-tb')
        expect(body.sheet_name).toMatch(codeRe)
        expect(Array.isArray(body.writeback_rows)).toBe(true)
        // 找到目标科目行（L5 双科目 rows 含 2701+2702，取 account 那行）
        const row = body.writeback_rows.find((r: any) => r.account_code === account)
        expect(row).toBeDefined()
        expect(row.audited_amount).toBeCloseTo(500000, 2)
        expect(row.amount_kind).toBe(amountKind)
      })
      scope.stop()
    })

    it('writebackTB 不再调旧端点 trial-balance/writeback（PUT）', async () => {
      const scope = effectScope()
      await scope.run(async () => {
        const formData = makeFormData('wp-001', 'proj-001')
        await callWriteback(formData, 500000)
        expect(mockPut).not.toHaveBeenCalled()
        for (const call of mockPost.mock.calls) {
          expect(call[0]).not.toContain('trial-balance/writeback')
        }
      })
      scope.stop()
    })

    it('writebackTB 成功后仍 emit substantive:adjudicated（下游附注刷新回归 / Req 8）', async () => {
      const emitSpy = vi.fn()
      eventBus.on('substantive:adjudicated', emitSpy)
      const scope = effectScope()
      await scope.run(async () => {
        const formData = makeFormData('wp-001', 'proj-001')
        await callWriteback(formData, 500000)
        expect(mockPost).toHaveBeenCalledTimes(1)
        expect(emitSpy).toHaveBeenCalled()
        // 至少有一次 emit 的 wpCode 是本循环
        const payloads = emitSpy.mock.calls.map((c) => c[0] as { wpCode: string; accountCode: string })
        expect(payloads.some((p) => p.wpCode === cycle && p.accountCode === account)).toBe(true)
      })
      eventBus.off('substantive:adjudicated', emitSpy)
      scope.stop()
    })

    it('publishToTb 用户取消二次确认 → 不发请求、不 emit substantive:adjudicated', async () => {
      confirmRef.resolve = false
      const emitSpy = vi.fn()
      eventBus.on('substantive:adjudicated', emitSpy)
      const scope = effectScope()
      await scope.run(async () => {
        const formData = makeFormData('wp-001', 'proj-001')
        const adj = makeAdjudication(formData)
        await adj.publishToTb()
        expect(mockPost).not.toHaveBeenCalled()
        expect(emitSpy).not.toHaveBeenCalled()
      })
      eventBus.off('substantive:adjudicated', emitSpy)
      scope.stop()
    })

    it('publishToTb 确认后 → 调 POST publish-to-tb（经 writebackTB）', async () => {
      const scope = effectScope()
      await scope.run(async () => {
        const formData = makeFormData('wp-002', 'proj-002')
        const adj = makeAdjudication(formData)
        await adj.publishToTb()
        const publishCall = mockPost.mock.calls.find((c) =>
          String(c[0]).includes('/audit-determination/publish-to-tb'),
        )
        expect(publishCall).toBeDefined()
        expect(publishCall![1].sheet_name).toMatch(codeRe)
        const row = publishCall![1].writeback_rows.find((r: any) => r.account_code === account)
        expect(row).toBeDefined()
      })
      scope.stop()
    })
  },
)
