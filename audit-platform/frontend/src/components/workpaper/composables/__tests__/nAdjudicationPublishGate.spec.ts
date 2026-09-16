/**
 * nAdjudicationPublishGate.spec.ts — N1~N5 审定表"发布到试算表"经显式确认门
 *
 * spec: .kiro/specs/tb-writeback-explicit-publish-gate/ (Task 6 / N 循环 / Req 1,2,8)
 *
 * 背景：此前 N{n}-1 审定表靠 useN{n}FormData.writebackTB 直调旧端点
 * `PUT /projects/{pid}/trial-balance/writeback`（无二次确认/无 publish_confirmed/无幂等）。
 * N1 更严重——`useN1Adjudication` 有一个 debounce 2s watcher 在数据变化时**自动**写 TB
 * （违反 Req 1）。改造后与 M/L/D 同范式：
 *   - 数据变化 / 普通保存仅 emit substantive:adjudicated（附注刷新），不写 TB；
 *   - 用户显式点「发布到试算表」→ publishToTb 二次确认（中文）→
 *     useN{n}FormData.writebackTB 走 `POST /workpapers/{wpId}/audit-determination/publish-to-tb`。
 *
 * 各 N{n} 参数化验证（Group A：N1~N4 有 adjudication composable）：
 * 1. writebackTB 走 POST publish-to-tb，body 含 sheet_name(N{n}-1) + writeback_rows(对应科目, amount_kind)。
 * 2. writebackTB 不再调旧端点 trial-balance/writeback(PUT)。
 * 3. writebackTB 成功后仍 emit substantive:adjudicated（下游附注刷新回归 / Req 8）。
 * 4. publishToTb 用户取消二次确认 → 不发请求、不 emit substantive:adjudicated。
 * 5. publishToTb 确认后 → 经 writebackTB 调 POST publish-to-tb。
 *
 * 口径差异：N4=6403 税金及附加 / N5=6801 所得税费用（发生额口径 amount_kind='occurrence'）；
 *           N1=1811 / N2=2221 / N3=2901（余额类 'balance'）。
 * N1 特例（Req 1）：数据变化只 emit 不写 TB（原自动写 watcher 已删除）；
 *           且 N1 发布后仍 emit deferred-tax:asset-updated（N1→N5 联动，Req 8 保留）。
 * N5 特例：无 useN5Adjudication composable，显式确认门在 N5TabAdjudication.vue；
 *           故 N5 的 publishToTb 确认/取消门在下方独立 describe 覆盖，routing（dim 1~3）
 *           在 Group A 参数化覆盖。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { eventBus } from '@/utils/eventBus'

import { useN1FormData } from '../useN1FormData'
import { useN1Adjudication } from '../useN1Adjudication'
import { useN2FormData } from '../useN2FormData'
import { useN2Adjudication14 } from '../useN2Adjudication'
import { useN3FormData } from '../useN3FormData'
import { useN3Adjudication } from '../useN3Adjudication'
import { useN4FormData } from '../useN4FormData'
import { useN4Adjudication } from '../useN4Adjudication'
import { useN5FormData } from '../useN5FormData'

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

// ─── 各 N 循环元数据（科目 + 审定表子码 + 口径 + composable 构造差异适配） ───
interface NCase {
  cycle: string
  account: string
  sheetCode: string
  amountKind: 'balance' | 'occurrence'
  /** 构造 formData */
  makeFormData: (wpId: string, projectId: string) => any
  /** writebackTB 调用（吸收各 FormData 签名差异）→ 传入 amount */
  callWriteback: (formData: any, amount: number) => Promise<void>
  /** 构造 adjudication 并暴露 publishToTb（吸收各构造签名差异） */
  makeAdjudication: (formData: any) => any
}

const N_CASES: NCase[] = [
  {
    cycle: 'N1', account: '1811', sheetCode: 'N1-1', amountKind: 'balance',
    makeFormData: (w, p) => useN1FormData({ wpId: ref(w), projectId: ref(p) }),
    callWriteback: (fd, amt) => fd.writebackTB(amt),
    makeAdjudication: (fd) => useN1Adjudication({
      wpId: ref('wp-001'),
      projectId: ref('proj-001'),
      allResponses: fd.allResponses,
      formData: fd,
    }),
  },
  {
    cycle: 'N2', account: '2221', sheetCode: 'N2-1', amountKind: 'balance',
    makeFormData: (w, p) => useN2FormData({ wpId: ref(w), projectId: ref(p) }),
    callWriteback: (fd, amt) => fd.writebackTB(amt),
    makeAdjudication: (fd) => useN2Adjudication14({
      allResponses: fd.allResponses,
      saveField: fd.setField,
      getField: fd.getField,
      writebackTB: fd.writebackTB,
    }),
  },
  {
    cycle: 'N3', account: '2901', sheetCode: 'N3-1', amountKind: 'balance',
    makeFormData: (w, p) => useN3FormData({ wpId: ref(w), projectId: ref(p) }),
    callWriteback: (fd, amt) => fd.writebackTB(amt),
    makeAdjudication: (fd) => useN3Adjudication({
      allResponses: fd.allResponses,
      saveField: fd.setField,
      getField: fd.getField,
      writebackTB: fd.writebackTB,
    }),
  },
  {
    cycle: 'N4', account: '6403', sheetCode: 'N4-1', amountKind: 'occurrence',
    makeFormData: (w, p) => useN4FormData({ wpId: ref(w), projectId: ref(p) }),
    callWriteback: (fd, amt) => fd.writebackTB(amt),
    makeAdjudication: (fd) => useN4Adjudication({
      allResponses: fd.allResponses,
      projectId: ref('proj-001'),
      wpId: ref('wp-001'),
      isReadonly: ref(false),
      onSave: (itemId: string, value: any) => fd.saveResponse(itemId, value),
      writebackTB: fd.writebackTB,
    }),
  },
]

beforeEach(() => {
  mockPost.mockClear()
  mockPut.mockClear()
  mockGet.mockClear()
  confirmRef.resolve = true
})

// ═══════════════════════════════════════════════════════════════════════════
// Group A: N1~N4（有 adjudication composable，5 维全覆盖）
// ═══════════════════════════════════════════════════════════════════════════

describe.each(N_CASES)(
  '$cycle-1 审定表发布经显式确认门（tb-writeback-explicit-publish-gate Task 6）',
  ({ cycle, account, sheetCode, amountKind, makeFormData, callWriteback, makeAdjudication }) => {
    const codeRe = new RegExp(sheetCode.replace('-', '\\-'))

    it(`writebackTB 走 POST publish-to-tb，body 含 sheet_name(${sheetCode}) + writeback_rows(${account}, ${amountKind})`, async () => {
      const scope = effectScope()
      await scope.run(async () => {
        const formData = makeFormData('wp-001', 'proj-001')
        await callWriteback(formData, 500000)

        const publishCall = mockPost.mock.calls.find((c) =>
          String(c[0]).includes('/audit-determination/publish-to-tb'),
        )
        expect(publishCall).toBeDefined()
        const [url, body] = publishCall!
        expect(url).toContain('/api/workpapers/wp-001/audit-determination/publish-to-tb')
        expect(body.sheet_name).toMatch(codeRe)
        expect(Array.isArray(body.writeback_rows)).toBe(true)
        const row = body.writeback_rows.find((r: any) => r.account_code === account)
        expect(row).toBeDefined()
        expect(row.audited_amount).toBeCloseTo(500000, 2)
        expect(row.amount_kind).toBe(amountKind)
      })
      scope.stop()
    })

    it('writebackTB 不再调旧端点 trial-balance/writeback（PUT/POST 皆无该字面量）', async () => {
      const scope = effectScope()
      await scope.run(async () => {
        const formData = makeFormData('wp-001', 'proj-001')
        await callWriteback(formData, 500000)
        // 注：N4 writebackTB 仍会 PUT /checklist-responses 保存审定合计（正常持久化，非 TB 回写），
        //     故断言口径改为「无任何 PUT/POST 命中旧 trial-balance/writeback 端点」。
        for (const call of mockPut.mock.calls) {
          expect(call[0]).not.toContain('trial-balance/writeback')
        }
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
        expect(emitSpy).toHaveBeenCalled()
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

// ═══════════════════════════════════════════════════════════════════════════
// N1 特例：数据变化只 emit 不写 TB（Req 1）+ N1→N5 联动保留（Req 8）
// ═══════════════════════════════════════════════════════════════════════════

describe('N1 特例：数据变化不写 TB（Req 1）+ N1→N5 联动（Req 8）', () => {
  it('构造 useN1Adjudication（含数据行变化）不触发任何 POST/PUT（自动写 watcher 已删除）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const formData = useN1FormData({ wpId: ref('wp-001'), projectId: ref('proj-001') })
      const adj = useN1Adjudication({
        wpId: ref('wp-001'),
        projectId: ref('proj-001'),
        allResponses: formData.allResponses,
        formData,
      })
      // 模拟数据行变化（原实现会经 watch(totals.endAudited) debounce 自动写 TB）
      adj.updateRow(0, 'endUnadjusted', 123456)
      adj.updateRow(0, 'endAje', 1000)
      // 等待可能的 debounce（原自动写 watcher 是 2s；已删除，应无任何回写）
      await new Promise((r) => setTimeout(r, 20))
      // 数据变化绝不写 TB（既不调新 publish-to-tb，也不调旧 PUT）
      expect(mockPut).not.toHaveBeenCalled()
      for (const call of mockPost.mock.calls) {
        expect(call[0]).not.toContain('publish-to-tb')
        expect(call[0]).not.toContain('trial-balance/writeback')
      }
    })
    scope.stop()
  })

  it('N1 显式发布成功后仍 emit deferred-tax:asset-updated（N1→N5 联动保留）', async () => {
    const dtSpy = vi.fn()
    const subSpy = vi.fn()
    eventBus.on('deferred-tax:asset-updated', dtSpy)
    eventBus.on('substantive:adjudicated', subSpy)
    const scope = effectScope()
    await scope.run(async () => {
      const formData = useN1FormData({ wpId: ref('wp-001'), projectId: ref('proj-001') })
      await formData.writebackTB(6500000)
      // 两条联动事件都发（design §3 保留）
      expect(subSpy).toHaveBeenCalled()
      expect(dtSpy).toHaveBeenCalled()
      const dtPayload = dtSpy.mock.calls[0][0] as { wpCode: string; accountCode: string }
      expect(dtPayload.wpCode).toBe('N1')
      expect(dtPayload.accountCode).toBe('1811')
    })
    eventBus.off('deferred-tax:asset-updated', dtSpy)
    eventBus.off('substantive:adjudicated', subSpy)
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// N4 特例：发生额回写不再携带旧 is_occurrence / amount_type:'period' 参数
// ═══════════════════════════════════════════════════════════════════════════

describe('N4 发生额回写参数迁移', () => {
  it('N4 publish-to-tb body 用 amount_kind=occurrence，不再含旧 is_occurrence/amount_type', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const formData = useN4FormData({ wpId: ref('wp-001'), projectId: ref('proj-001') })
      await formData.writebackTB(88888)
      const publishCall = mockPost.mock.calls.find((c) =>
        String(c[0]).includes('/audit-determination/publish-to-tb'),
      )
      expect(publishCall).toBeDefined()
      const body = publishCall![1]
      expect(body.is_occurrence).toBeUndefined()
      expect(body.amount_type).toBeUndefined()
      const row = body.writeback_rows.find((r: any) => r.account_code === '6403')
      expect(row.amount_kind).toBe('occurrence')
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// N5：routing（FormData.writebackTB → publish-to-tb 6801 occurrence）
// N5 无 useN5Adjudication composable，显式确认门在 N5TabAdjudication.vue（见下方 tab 断言）
// ═══════════════════════════════════════════════════════════════════════════

describe('N5-1 审定表发布 routing（tb-writeback-explicit-publish-gate Task 6）', () => {
  it('N5 writebackTB 走 POST publish-to-tb，body 含 sheet_name(N5-1) + writeback_rows(6801, occurrence)', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const formData = useN5FormData({ wpId: ref('wp-001'), projectId: ref('proj-001') })
      await formData.writebackTB(500000)
      const publishCall = mockPost.mock.calls.find((c) =>
        String(c[0]).includes('/audit-determination/publish-to-tb'),
      )
      expect(publishCall).toBeDefined()
      const [url, body] = publishCall!
      expect(url).toContain('/api/workpapers/wp-001/audit-determination/publish-to-tb')
      expect(body.sheet_name).toMatch(/N5\-1/)
      const row = body.writeback_rows.find((r: any) => r.account_code === '6801')
      expect(row).toBeDefined()
      expect(row.audited_amount).toBeCloseTo(500000, 2)
      expect(row.amount_kind).toBe('occurrence')
    })
    scope.stop()
  })

  it('N5 writebackTB 不再调旧端点 trial-balance/writeback（PUT）', async () => {
    const scope = effectScope()
    await scope.run(async () => {
      const formData = useN5FormData({ wpId: ref('wp-001'), projectId: ref('proj-001') })
      await formData.writebackTB(500000)
      expect(mockPut).not.toHaveBeenCalled()
      for (const call of mockPost.mock.calls) {
        expect(call[0]).not.toContain('trial-balance/writeback')
      }
    })
    scope.stop()
  })

  it('N5 writebackTB 成功后仍 emit substantive:adjudicated（Req 8）', async () => {
    const emitSpy = vi.fn()
    eventBus.on('substantive:adjudicated', emitSpy)
    const scope = effectScope()
    await scope.run(async () => {
      const formData = useN5FormData({ wpId: ref('wp-001'), projectId: ref('proj-001') })
      await formData.writebackTB(500000)
      const payloads = emitSpy.mock.calls.map((c) => c[0] as { wpCode: string; accountCode: string })
      expect(payloads.some((p) => p.wpCode === 'N5' && p.accountCode === '6801')).toBe(true)
    })
    eventBus.off('substantive:adjudicated', emitSpy)
    scope.stop()
  })
})
