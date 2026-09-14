/**
 * d4AdjudicationPublishGate.spec.ts — D4-1 审定表"确认审定（回写TB）"经显式确认门（P0-项3 / AC-3.4）
 *
 * spec: .kiro/specs/d4-dual-mode-formula-governance/  (P0-3b / AC-3.4)
 *
 * 背景（情形B缺口）：D4-1 用 d4-operating-revenue 组件渲染（非 GtAuditSheet）。此前
 * publishAdjudicated 只 dispatch `d4:writeback-trial-balance` → 经 `PUT /trial-balance/writeback`
 * 直写 audited_amount，**绕过** P0-项3 的 publish_confirmed 显式确认门。修复后与 GtAuditSheet 同范式：
 * 二次确认（中文）→ `POST /workpapers/{wpId}/audit-determination/publish-to-tb`。
 *
 * 验证：
 * 1. 确认后调 POST publish-to-tb，body 含 sheet_name（含 D4-1 子码）+ html_data.audit_rows（6001/6051）。
 * 2. 用户取消二次确认 → 不发请求。
 * 3. readonly → 不发请求。
 * 4. **不再** dispatch 绕过门的 `d4:writeback-trial-balance` 事件。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope, type Ref } from 'vue'
import { useD4Adjudication } from '../useD4Adjudication'
import type { ChecklistResponse } from '../useD4FormData'

// ─── mock apiProxy（隔离网络） ───
const { mockPost, confirmRef } = vi.hoisted(() => ({
  mockPost: vi.fn(async () => ({ message: '已发布 2 个科目的审定数到试算表', published: true })),
  confirmRef: { resolve: true },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { post: mockPost, get: vi.fn() },
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

function buildResponses(): Ref<Map<string, ChecklistResponse>> {
  const map = new Map<string, ChecklistResponse>()
  // 一条主营手工行 + 金额，使主营小计非 0（审定数可发布）
  map.set('D4-1-rows', {
    item_id: 'D4-1-rows', conclusion: null,
    remark: JSON.stringify([{ rowId: 'm1', label: '主营A', source: 'manual', accountCode: '6001' }]),
  })
  map.set('D4-1-m1-currentUnadjusted', { item_id: 'D4-1-m1-currentUnadjusted', conclusion: null, remark: '1000000' })
  return ref(map)
}

function runAdjudication(allResponses: Ref<Map<string, ChecklistResponse>>, readonly = false) {
  const scope = effectScope()
  const api = scope.run(() =>
    useD4Adjudication({
      wpId: ref('wp-d4-001'),
      projectId: ref('proj-d4-001'),
      allResponses,
      isReadonly: ref(readonly),
    }),
  )!
  return { api, dispose: () => scope.stop() }
}

beforeEach(() => {
  mockPost.mockClear()
  confirmRef.resolve = true
})

describe('D4-1 审定表发布经显式确认门（P0-3b / AC-3.4）', () => {
  it('确认后调 POST publish-to-tb，body 含 sheet_name(D4-1) + audit_rows(6001/6051)', async () => {
    const { api, dispose } = runAdjudication(buildResponses())
    try {
      await api.publishAdjudicated()
      expect(mockPost).toHaveBeenCalledTimes(1)
      const [url, body] = mockPost.mock.calls[0]!
      expect(url).toContain('/api/workpapers/wp-d4-001/audit-determination/publish-to-tb')
      // sheet_name 须含审定表子码 D4-1（后端 extract_determination_wp_code 据此解出）
      expect(body.sheet_name).toMatch(/D4-1/)
      const codes = body.html_data.audit_rows.map((r: any) => r.account_code).sort()
      expect(codes).toEqual(['6001', '6051'])
      // 主营行 current_unadjusted 汇总到 6001
      const row6001 = body.html_data.audit_rows.find((r: any) => r.account_code === '6001')
      expect(row6001.current_unadjusted).toBeCloseTo(1000000, 2)
    } finally {
      dispose()
    }
  })

  it('用户取消二次确认 → 不发请求', async () => {
    confirmRef.resolve = false
    const { api, dispose } = runAdjudication(buildResponses())
    try {
      await api.publishAdjudicated()
      expect(mockPost).not.toHaveBeenCalled()
    } finally {
      dispose()
    }
  })

  it('readonly → 不发请求（处理函数早退）', async () => {
    const { api, dispose } = runAdjudication(buildResponses(), true)
    try {
      await api.publishAdjudicated()
      expect(mockPost).not.toHaveBeenCalled()
    } finally {
      dispose()
    }
  })

  it('不再 dispatch 绕过门的 d4:writeback-trial-balance 事件', async () => {
    const spy = vi.fn()
    window.addEventListener('d4:writeback-trial-balance', spy)
    const { api, dispose } = runAdjudication(buildResponses())
    try {
      await api.publishAdjudicated()
      expect(spy).not.toHaveBeenCalled()
    } finally {
      window.removeEventListener('d4:writeback-trial-balance', spy)
      dispose()
    }
  })
})
