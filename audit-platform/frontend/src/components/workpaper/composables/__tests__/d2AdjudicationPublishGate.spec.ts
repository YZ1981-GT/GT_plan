/**
 * d2AdjudicationPublishGate.spec.ts — D2-1 审定表"发布到试算表"经显式确认门
 *
 * spec: .kiro/specs/tb-writeback-explicit-publish-gate/ (Task 2 / M1 D 循环 / Req 1,2,8)
 *
 * 背景：此前 D2-1 靠 totalRow.currentAudited watcher 自动 dispatch
 * `d2:writeback-trial-balance` → 经旧端点 `PUT /projects/{pid}/trial-balance/writeback`
 * 直写 audited_amount，**绕过**显式确认门（无二次确认/无幂等/无 publish_confirmed）。
 * 改造后与 D4-1 同范式：显式 publishToTb → 二次确认（中文）→
 * `POST /workpapers/{wpId}/audit-determination/publish-to-tb`（writeback_rows 预算行）。
 *
 * 验证：
 * 1. 确认后调 POST publish-to-tb，body 含 sheet_name(D2-1) + writeback_rows(科目1122)。
 * 2. 用户取消二次确认 → 不发请求、不 emit substantive:adjudicated。
 * 3. readonly → 不发请求。
 * 4. **不再**调旧端点 trial-balance/writeback；**不再** dispatch d2:writeback-trial-balance。
 * 5. 发布成功后仍 emit substantive:adjudicated（下游附注刷新回归）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope, type Ref } from 'vue'
import { useD2Adjudication } from '../useD2Adjudication'
import type { ChecklistResponse } from '../useD2FormData'
import { eventBus } from '@/utils/eventBus'

// ─── mock apiProxy（隔离网络） ───
const { mockPost, mockPut, confirmRef } = vi.hoisted(() => ({
  mockPost: vi.fn(async () => ({ message: '已发布应收账款审定数到试算表', published: true })),
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
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

function buildResponses(currentUnadjusted = '500000'): Ref<Map<string, ChecklistResponse>> {
  const map = new Map<string, ChecklistResponse>()
  // D2-detail-rows 为空 → agg=null → getSumifOrManual 回退手工键；
  // 设单项计提期末未审 → 合计行 currentAudited 非 0（审定数可发布）。
  map.set('D2-adj-individual-current-unadjusted', {
    item_id: 'D2-adj-individual-current-unadjusted', conclusion: null, remark: currentUnadjusted,
  })
  return ref(map)
}

function runAdjudication(allResponses: Ref<Map<string, ChecklistResponse>>, readonly = false) {
  const scope = effectScope()
  const api = scope.run(() =>
    useD2Adjudication({
      wpId: ref('wp-d2-001'),
      projectId: ref('proj-d2-001'),
      allResponses,
      isReadonly: ref(readonly),
    }),
  )!
  return { api, dispose: () => scope.stop() }
}

beforeEach(() => {
  mockPost.mockClear()
  mockPut.mockClear()
  confirmRef.resolve = true
})

describe('D2-1 审定表发布经显式确认门（tb-writeback-explicit-publish-gate Task 2）', () => {
  it('确认后调 POST publish-to-tb，body 含 sheet_name(D2-1) + writeback_rows(1122)', async () => {
    const { api, dispose } = runAdjudication(buildResponses('500000'))
    try {
      await api.publishToTb()
      expect(mockPost).toHaveBeenCalledTimes(1)
      const [url, body] = mockPost.mock.calls[0]!
      expect(url).toContain('/api/workpapers/wp-d2-001/audit-determination/publish-to-tb')
      // sheet_name 须含审定表子码 D2-1（后端 extract_determination_wp_code 据此解出）
      expect(body.sheet_name).toMatch(/D2-1/)
      // writeback_rows 预算行：科目 1122，audited 为合计行 currentAudited
      expect(Array.isArray(body.writeback_rows)).toBe(true)
      expect(body.writeback_rows).toHaveLength(1)
      expect(body.writeback_rows[0].account_code).toBe('1122')
      expect(body.writeback_rows[0].audited_amount).toBeCloseTo(500000, 2)
      expect(body.writeback_rows[0].amount_kind).toBe('balance')
    } finally {
      dispose()
    }
  })

  it('不再调旧端点 trial-balance/writeback（PUT）', async () => {
    const { api, dispose } = runAdjudication(buildResponses('500000'))
    try {
      await api.publishToTb()
      expect(mockPut).not.toHaveBeenCalled()
      // 也不应命中旧端点字面量
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
    const { api, dispose } = runAdjudication(buildResponses('500000'))
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
    const { api, dispose } = runAdjudication(buildResponses('500000'), true)
    try {
      await api.publishToTb()
      expect(mockPost).not.toHaveBeenCalled()
    } finally {
      dispose()
    }
  })

  it('不再 dispatch 绕过门的 d2:writeback-trial-balance 事件', async () => {
    const spy = vi.fn()
    window.addEventListener('d2:writeback-trial-balance', spy)
    const { api, dispose } = runAdjudication(buildResponses('500000'))
    try {
      await api.publishToTb()
      expect(spy).not.toHaveBeenCalled()
    } finally {
      window.removeEventListener('d2:writeback-trial-balance', spy)
      dispose()
    }
  })

  it('发布成功后仍 emit substantive:adjudicated（下游附注刷新回归 / Req 8）', async () => {
    const emitSpy = vi.fn()
    eventBus.on('substantive:adjudicated', emitSpy)
    const { api, dispose } = runAdjudication(buildResponses('500000'))
    try {
      await api.publishToTb()
      expect(mockPost).toHaveBeenCalledTimes(1)
      // publishAdjudicated 经 eventBus.emit 发布 substantive:adjudicated（payload 含 D2/1122）
      expect(emitSpy).toHaveBeenCalled()
      const payload = emitSpy.mock.calls[0][0] as { wpCode: string; accountCode: string }
      expect(payload.wpCode).toBe('D2')
      expect(payload.accountCode).toBe('1122')
    } finally {
      eventBus.off('substantive:adjudicated', emitSpy)
      dispose()
    }
  })
})
