/**
 * eAdjudicationPublishGate.spec.ts — E 循环（E1 货币资金）审定表"发布到试算表"经显式确认门
 *
 * spec: .kiro/specs/tb-writeback-explicit-publish-gate/ (Task 14 / M9 E1 / Req 5,2,8)
 *
 * 背景：此前 E1-1 靠 `flushSave`（debounce 2s 保存）与 `watch(totalRow.endingAudited)`
 * （数据变化）**自动** `api.put('/projects/{pid}/trial-balance/writeback')` 三科目
 * （1001/1002/1012）直写 audited_amount，**绕过**显式确认门（无二次确认/无幂等/无
 * publish_confirmed），且违反 Req 1（普通保存/数据变化绝不写 TB）。
 * 改造后与 D2/D4-1/I 循环同范式：显式 publishToTb → 中文二次确认 →
 * `POST /workpapers/{wpId}/audit-determination/publish-to-tb`（多科目 writeback_rows 一次
 * 原子发布，amount_kind=balance 余额类）。
 *
 * 验证：
 * 1. 确认后调 POST publish-to-tb，body 含 sheet_name(E1-1) + writeback_rows（三科目单次）。
 * 2. 多科目（1001/1002/1012）在**同一次** writeback_rows，各科目 amount_kind=balance。
 * 3. 用户取消二次确认 → 不发请求、不 emit substantive:adjudicated。
 * 4. readonly → 不发请求。
 * 5. **不再**调旧端点 trial-balance/writeback（PUT）。
 * 6. 发布成功后仍 emit substantive:adjudicated（下游附注/E1-14 刷新回归 / Req 8）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope, type Ref } from 'vue'
import { useE1Adjudication, type ChecklistResponse, type UseE1BaseOptions } from '../useE1Adjudication'
import { eventBus } from '@/utils/eventBus'

// ─── mock apiProxy（隔离网络） ───
const { mockPost, mockPut, mockGet, confirmRef } = vi.hoisted(() => ({
  mockPost: vi.fn(async () => ({ message: '已发布货币资金审定数到试算表', published: true })),
  mockPut: vi.fn(async () => ({})),
  mockGet: vi.fn(),
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

/**
 * 构造 allResponses：喂三科目未审数（跨 sheet 键）使三行审定数非 0，
 * 从而 publish 出的 writeback_rows 覆盖 1001/1002/1012 各自审定数。
 * - 库存现金(1001)   ← E1-cash-detail-total-unaudited
 * - 银行存款本金(1002) ← E1-bank-detail-principal-total-unaudited
 * - 其他货币资金(1012) ← E1-bank-detail-other-total-unaudited（+ 数字货币 E1-digital-total-unaudited）
 */
function buildResponses(): Ref<Map<string, ChecklistResponse>> {
  const map = new Map<string, ChecklistResponse>()
  const set = (id: string, remark: string) =>
    map.set(id, { item_id: id, conclusion: null, remark })
  set('E1-cash-detail-total-unaudited', '100000')
  set('E1-bank-detail-principal-total-unaudited', '2000000')
  set('E1-bank-detail-other-total-unaudited', '30000')
  set('E1-digital-total-unaudited', '5000')
  return ref(map)
}

function runAdjudication(allResponses: Ref<Map<string, ChecklistResponse>>, readonly = false) {
  const scope = effectScope()
  const api = scope.run(() => {
    const options: UseE1BaseOptions = {
      wpId: ref('wp-e1-001'),
      projectId: ref('proj-e1-001'),
      allResponses,
      saveImmediate: vi.fn(async () => {}),
      debouncedSave: vi.fn(async () => {}),
      isReadonly: ref(readonly),
    }
    return useE1Adjudication(options)
  })!
  return { api, dispose: () => scope.stop() }
}

beforeEach(() => {
  mockPost.mockClear()
  mockPut.mockClear()
  confirmRef.resolve = true
})

describe('E1-1 货币资金审定表发布经显式确认门（tb-writeback-explicit-publish-gate Task 14）', () => {
  it('确认后调 POST publish-to-tb，body 含 sheet_name(E1-1) + writeback_rows', async () => {
    const { api, dispose } = runAdjudication(buildResponses())
    try {
      await api.publishToTb()
      expect(mockPost).toHaveBeenCalledTimes(1)
      const [url, body] = mockPost.mock.calls[0]!
      expect(url).toBe('/api/workpapers/wp-e1-001/audit-determination/publish-to-tb')
      // sheet_name 须含审定表子码 E1-1（后端 extract_determination_wp_code 据此解出）
      expect(body.sheet_name).toMatch(/E1-1/)
      expect(Array.isArray(body.writeback_rows)).toBe(true)
    } finally {
      dispose()
    }
  })

  it('多科目（1001/1002/1012）在同一次 writeback_rows，各科目 amount_kind=balance（Req 5）', async () => {
    const { api, dispose } = runAdjudication(buildResponses())
    try {
      await api.publishToTb()
      const body = mockPost.mock.calls[0]![1]
      const rows: Array<{ account_code: string; audited_amount: number; amount_kind: string }> =
        body.writeback_rows
      // 三科目一次原子发布
      const codes = rows.map((r) => r.account_code).sort()
      expect(codes).toEqual(['1001', '1002', '1012'])
      // 各科目余额类
      expect(rows.every((r) => r.amount_kind === 'balance')).toBe(true)
      // 审定数归集正确：1001=库存现金 100000；1002=银行存款本金 2000000；1012=其他货币资金+数字货币 35000
      const byCode = Object.fromEntries(rows.map((r) => [r.account_code, r.audited_amount]))
      expect(byCode['1001']).toBeCloseTo(100000, 2)
      expect(byCode['1002']).toBeCloseTo(2000000, 2)
      expect(byCode['1012']).toBeCloseTo(35000, 2)
    } finally {
      dispose()
    }
  })

  it('不再调旧端点 trial-balance/writeback（PUT）', async () => {
    const { api, dispose } = runAdjudication(buildResponses())
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

  it('用户取消二次确认 → 不发请求、不 emit substantive:adjudicated（Req 2.2）', async () => {
    confirmRef.resolve = false
    const emitSpy = vi.fn()
    eventBus.on('substantive:adjudicated', emitSpy)
    const { api, dispose } = runAdjudication(buildResponses())
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
    const { api, dispose } = runAdjudication(buildResponses(), true)
    try {
      await api.publishToTb()
      expect(mockPost).not.toHaveBeenCalled()
    } finally {
      dispose()
    }
  })

  it('发布成功后仍 emit substantive:adjudicated（下游附注/E1-14 刷新回归 / Req 8）', async () => {
    const emitSpy = vi.fn()
    eventBus.on('substantive:adjudicated', emitSpy)
    const { api, dispose } = runAdjudication(buildResponses())
    try {
      await api.publishToTb()
      expect(mockPost).toHaveBeenCalledTimes(1)
      expect(emitSpy).toHaveBeenCalled()
      const payload = emitSpy.mock.calls[0][0] as { wpCode: string; accountCode: string }
      expect(payload.wpCode).toBe('E1')
      expect(payload.accountCode).toBe('1001,1002,1012')
    } finally {
      eventBus.off('substantive:adjudicated', emitSpy)
      dispose()
    }
  })
})
