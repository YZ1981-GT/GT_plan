/**
 * mAdjudicationPublishGate.spec.ts — M1~M10 审定表"发布到试算表"经显式确认门
 *
 * spec: .kiro/specs/tb-writeback-explicit-publish-gate/ (Task 5 / M 循环 / Req 1,2,8)
 *
 * 背景：此前 M{n}-1 审定表靠 useM{n}Adjudication 的 totalRow watcher **自动** 调
 * useM{n}FormData.writebackTB → 经旧端点 `PUT /projects/{pid}/trial-balance/writeback`
 * 直写 audited_amount，**绕过**显式确认门（无二次确认/无幂等/无 publish_confirmed），
 * 且数据变化即写 TB（违反 Req 1）。改造后与 D2/D4-1 同范式：
 *   - 数据变化仅 emit substantive:adjudicated（附注刷新），不写 TB；
 *   - 用户显式点「发布到试算表」→ publishToTb 二次确认（中文）→
 *     `POST /workpapers/{wpId}/audit-determination/publish-to-tb`（writeback_rows 预算行）。
 *
 * 每个 M{n} 参数化验证：
 * 1. writebackTB 走 POST publish-to-tb，body 含 sheet_name(M{n}-1) + writeback_rows(对应科目, amount_kind=balance)。
 * 2. writebackTB 不再调旧端点 trial-balance/writeback(PUT)。
 * 3. writebackTB 成功后仍 emit substantive:adjudicated（下游附注刷新回归 / Req 8）。
 * 4. publishToTb 用户取消二次确认 → 不发请求、不 emit substantive:adjudicated。
 * 5. publishToTb 确认后 → 经 writebackTB 调 POST publish-to-tb。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { eventBus } from '@/utils/eventBus'

import { useM1FormData } from '../useM1FormData'
import { useM1Adjudication } from '../useM1Adjudication'
import { useM2FormData } from '../useM2FormData'
import { useM2Adjudication } from '../useM2Adjudication'
import { useM3FormData } from '../useM3FormData'
import { useM3Adjudication } from '../useM3Adjudication'
import { useM4FormData } from '../useM4FormData'
import { useM4Adjudication } from '../useM4Adjudication'
import { useM5FormData } from '../useM5FormData'
import { useM5Adjudication } from '../useM5Adjudication'
import { useM6FormData } from '../useM6FormData'
import { useM6Adjudication } from '../useM6Adjudication'
import { useM7FormData } from '../useM7FormData'
import { useM7Adjudication } from '../useM7Adjudication'
import { useM8FormData } from '../useM8FormData'
import { useM8Adjudication } from '../useM8Adjudication'
import { useM9FormData } from '../useM9FormData'
import { useM9Adjudication } from '../useM9Adjudication'
import { useM10FormData } from '../useM10FormData'
import { useM10Adjudication } from '../useM10Adjudication'

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
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

// ─── 各 M 循环元数据（科目 + 审定表子码 + composable 引用） ───
interface MCase {
  cycle: string
  account: string
  sheetCode: string
  useFormData: (opts: any) => any
  useAdjudication: (formData: any, rows: any) => any
}

const M_CASES: MCase[] = [
  { cycle: 'M1', account: '2232', sheetCode: 'M1-1', useFormData: useM1FormData, useAdjudication: useM1Adjudication },
  { cycle: 'M2', account: '4001', sheetCode: 'M2-1', useFormData: useM2FormData, useAdjudication: useM2Adjudication },
  { cycle: 'M3', account: '4002', sheetCode: 'M3-1', useFormData: useM3FormData, useAdjudication: useM3Adjudication },
  { cycle: 'M4', account: '4002', sheetCode: 'M4-1', useFormData: useM4FormData, useAdjudication: useM4Adjudication },
  { cycle: 'M5', account: '4101', sheetCode: 'M5-1', useFormData: useM5FormData, useAdjudication: useM5Adjudication },
  { cycle: 'M6', account: '4104', sheetCode: 'M6-1', useFormData: useM6FormData, useAdjudication: useM6Adjudication },
  { cycle: 'M7', account: '4201', sheetCode: 'M7-1', useFormData: useM7FormData, useAdjudication: useM7Adjudication },
  { cycle: 'M8', account: '4104', sheetCode: 'M8-1', useFormData: useM8FormData, useAdjudication: useM8Adjudication },
  { cycle: 'M9', account: '4103', sheetCode: 'M9-1', useFormData: useM9FormData, useAdjudication: useM9Adjudication },
  { cycle: 'M10', account: '4003', sheetCode: 'M10-1', useFormData: useM10FormData, useAdjudication: useM10Adjudication },
]

beforeEach(() => {
  mockPost.mockClear()
  mockPut.mockClear()
  mockGet.mockClear()
  confirmRef.resolve = true
})

describe.each(M_CASES)(
  '$cycle-1 审定表发布经显式确认门（tb-writeback-explicit-publish-gate Task 5）',
  ({ cycle, account, sheetCode, useFormData, useAdjudication }) => {
    const codeRe = new RegExp(sheetCode.replace('-', '\\-'))

    it(`writebackTB 走 POST publish-to-tb，body 含 sheet_name(${sheetCode}) + writeback_rows(${account}, balance)`, async () => {
      const scope = effectScope()
      await scope.run(async () => {
        const formData = useFormData({ wpId: ref('wp-001'), projectId: ref('proj-001') })
        await formData.writebackTB(500000)

        expect(mockPost).toHaveBeenCalledTimes(1)
        const [url, body] = mockPost.mock.calls[0]!
        expect(url).toContain('/api/workpapers/wp-001/audit-determination/publish-to-tb')
        expect(body.sheet_name).toMatch(codeRe)
        expect(Array.isArray(body.writeback_rows)).toBe(true)
        expect(body.writeback_rows).toHaveLength(1)
        expect(body.writeback_rows[0].account_code).toBe(account)
        expect(body.writeback_rows[0].audited_amount).toBeCloseTo(500000, 2)
        expect(body.writeback_rows[0].amount_kind).toBe('balance')
      })
      scope.stop()
    })

    it('writebackTB 不再调旧端点 trial-balance/writeback（PUT）', async () => {
      const scope = effectScope()
      await scope.run(async () => {
        const formData = useFormData({ wpId: ref('wp-001'), projectId: ref('proj-001') })
        await formData.writebackTB(500000)
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
        const formData = useFormData({ wpId: ref('wp-001'), projectId: ref('proj-001') })
        await formData.writebackTB(500000)
        expect(mockPost).toHaveBeenCalledTimes(1)
        expect(emitSpy).toHaveBeenCalled()
        const payload = emitSpy.mock.calls[0][0] as { wpCode: string; accountCode: string; auditedAmount: number }
        expect(payload.wpCode).toBe(cycle)
        expect(payload.accountCode).toBe(account)
        expect(payload.auditedAmount).toBeCloseTo(500000, 2)
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
        const formData = useFormData({ wpId: ref('wp-001'), projectId: ref('proj-001') })
        const adj = useAdjudication(formData, ref([]))
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
        const formData = useFormData({ wpId: ref('wp-002'), projectId: ref('proj-002') })
        const adj = useAdjudication(formData, ref([]))
        await adj.publishToTb()
        const publishCall = mockPost.mock.calls.find((c) =>
          String(c[0]).includes('/audit-determination/publish-to-tb'),
        )
        expect(publishCall).toBeDefined()
        expect(publishCall![1].sheet_name).toMatch(codeRe)
        expect(publishCall![1].writeback_rows[0].account_code).toBe(account)
      })
      scope.stop()
    })
  },
)
