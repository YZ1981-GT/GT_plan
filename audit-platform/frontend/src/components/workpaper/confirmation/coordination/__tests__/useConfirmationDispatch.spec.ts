/**
 * useConfirmationDispatch.spec.ts — D0-1 枢纽分发逻辑单元测试
 *
 * 覆盖：
 * - 差异行→D0-4 路由
 * - 未回函→D0-5/D0-6 科目路由
 * - 电子回函→D0-7 路由
 * - 去重逻辑（已分发不重复）
 * - 双向等价（下游标记回标）
 * - 分发清单构建
 * - 执行分发
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  useConfirmationDispatch,
  routeAlternative,
  type DispatchTarget,
} from '../useConfirmationDispatch'
import type { ConfirmationRow } from '../../confirmationTypes'

// Mock dispatchApi
vi.mock('@/services/dispatchApi', () => ({
  dispatchApi: {
    batchCreate: vi.fn().mockResolvedValue({ dispatched: [], skipped: [] }),
    list: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    revoke: vi.fn().mockResolvedValue({ detail: 'ok', id: 'test' }),
  },
}))

describe('useConfirmationDispatch — D0-1 枢纽分发', () => {
  function createInstance(
    rows: ConfirmationRow[] = [],
    dispatched: Map<string, Set<DispatchTarget>> = new Map()
  ) {
    const rowsRef = ref<ConfirmationRow[]>(rows)
    const dispatchedRef = ref(dispatched)
    const projectIdRef = ref('test-project-id')
    return useConfirmationDispatch({ rows: rowsRef, dispatchedMap: dispatchedRef, projectId: projectIdRef })
  }

  // ─── 科目路由 ──────────────────────────────────────────────────────────────

  describe('routeAlternative()', () => {
    it('合同负债 → D0-5', () => {
      expect(routeAlternative('合同负债')).toBe('D0-5')
    })

    it('预收账款 → D0-5', () => {
      expect(routeAlternative('预收账款')).toBe('D0-5')
    })

    it('应收账款 → D0-6', () => {
      expect(routeAlternative('应收账款')).toBe('D0-6')
    })

    it('其他应收款 → D0-6', () => {
      expect(routeAlternative('其他应收款')).toBe('D0-6')
    })

    it('未知科目兜底 → D0-6', () => {
      expect(routeAlternative('银行存款')).toBe('D0-6')
      expect(routeAlternative('')).toBe('D0-6')
    })
  })

  // ─── 待分发行计算 ──────────────────────────────────────────────────────────

  describe('pendingDiffRows', () => {
    it('差异≠0 行被识别', () => {
      const { pendingDiffRows } = createInstance([
        { _row_id: '1', confirm_index: 'IDX-001', amount: 10000, reply_amount: 9000, match_status: '不符' },
        { _row_id: '2', confirm_index: 'IDX-002', amount: 5000, reply_amount: 5000, match_status: '相符' },
      ])
      expect(pendingDiffRows.value).toHaveLength(1)
      expect(pendingDiffRows.value[0].confirm_index).toBe('IDX-001')
    })

    it('相符行不分发（即使金额有误差）', () => {
      const { pendingDiffRows } = createInstance([
        { _row_id: '1', confirm_index: 'IDX-001', amount: 10000, reply_amount: 9000, match_status: '相符' },
      ])
      expect(pendingDiffRows.value).toHaveLength(0)
    })

    it('已分发到 D0-4 的不重复', () => {
      const dispatched = new Map<string, Set<DispatchTarget>>()
      dispatched.set('IDX-001', new Set(['D0-4']))

      const { pendingDiffRows } = createInstance(
        [{ _row_id: '1', confirm_index: 'IDX-001', amount: 10000, reply_amount: 9000, match_status: '不符' }],
        dispatched
      )
      expect(pendingDiffRows.value).toHaveLength(0)
    })

    it('无 confirm_index 行被排除', () => {
      const { pendingDiffRows } = createInstance([
        { _row_id: '1', amount: 10000, reply_amount: 9000, match_status: '不符' },
      ])
      expect(pendingDiffRows.value).toHaveLength(0)
    })
  })

  describe('pendingAltRows', () => {
    it('未回函积极式行被识别', () => {
      const { pendingAltRows } = createInstance([
        { _row_id: '1', confirm_index: 'IDX-001', is_replied: false, match_status: '未回函', confirmation_method: '积极式', account_type: '应收账款' },
      ])
      expect(pendingAltRows.value).toHaveLength(1)
    })

    it('消极式未回函不需要替代程序', () => {
      const { pendingAltRows } = createInstance([
        { _row_id: '1', confirm_index: 'IDX-001', is_replied: false, match_status: '未回函', confirmation_method: '消极式', account_type: '应收账款' },
      ])
      expect(pendingAltRows.value).toHaveLength(0)
    })

    it('已分发到 D0-6 的不重复', () => {
      const dispatched = new Map<string, Set<DispatchTarget>>()
      dispatched.set('IDX-001', new Set(['D0-6']))

      const { pendingAltRows } = createInstance(
        [{ _row_id: '1', confirm_index: 'IDX-001', is_replied: false, match_status: '未回函', confirmation_method: '积极式', account_type: '应收账款' }],
        dispatched
      )
      expect(pendingAltRows.value).toHaveLength(0)
    })
  })

  describe('pendingReliabilityRows', () => {
    it('电子邮件回函行被识别', () => {
      const { pendingReliabilityRows } = createInstance([
        { _row_id: '1', confirm_index: 'IDX-001', electronic_reply: true, reply_method: '电子邮件' },
      ])
      expect(pendingReliabilityRows.value).toHaveLength(1)
    })

    it('传真回函行被识别', () => {
      const { pendingReliabilityRows } = createInstance([
        { _row_id: '1', confirm_index: 'IDX-001', electronic_reply: true, reply_method: '传真' },
      ])
      expect(pendingReliabilityRows.value).toHaveLength(1)
    })

    it('原件寄回不需要可靠性验证', () => {
      const { pendingReliabilityRows } = createInstance([
        { _row_id: '1', confirm_index: 'IDX-001', electronic_reply: false, reply_method: '原件寄回' },
      ])
      expect(pendingReliabilityRows.value).toHaveLength(0)
    })

    it('已分发到 D0-7 的不重复', () => {
      const dispatched = new Map<string, Set<DispatchTarget>>()
      dispatched.set('IDX-001', new Set(['D0-7']))

      const { pendingReliabilityRows } = createInstance(
        [{ _row_id: '1', confirm_index: 'IDX-001', electronic_reply: true, reply_method: '电子邮件' }],
        dispatched
      )
      expect(pendingReliabilityRows.value).toHaveLength(0)
    })
  })

  // ─── 分发清单构建 ──────────────────────────────────────────────────────────

  describe('buildDispatchList()', () => {
    it('综合场景：多种分发目标', () => {
      const { buildDispatchList } = createInstance([
        { _row_id: '1', confirm_index: 'IDX-001', amount: 10000, reply_amount: 9000, match_status: '不符', account_type: '应收账款' },
        { _row_id: '2', confirm_index: 'IDX-002', is_replied: false, match_status: '未回函', confirmation_method: '积极式', account_type: '合同负债', amount: 5000 },
        { _row_id: '3', confirm_index: 'IDX-003', electronic_reply: true, reply_method: '电子邮件', account_type: '应收账款', amount: 8000 },
      ])

      const list = buildDispatchList()
      expect(list.length).toBeGreaterThanOrEqual(3)

      const targets = list.map(e => e.target)
      expect(targets).toContain('D0-4')
      expect(targets).toContain('D0-5')
      expect(targets).toContain('D0-7')
    })
  })

  // ─── 执行分发 + 去重 ──────────────────────────────────────────────────────

  describe('executeDispatch()', () => {
    it('首次分发调用 API', async () => {
      const { dispatchApi } = await import('@/services/dispatchApi')
      const mockBatchCreate = vi.mocked(dispatchApi.batchCreate)
      mockBatchCreate.mockResolvedValueOnce({
        dispatched: [{
          id: 'rec-1',
          project_id: 'test-project-id',
          confirm_index: 'IDX-001',
          target: 'D0-4',
          entity_name: '某公司',
          account_type: '应收账款',
          amount: 10000,
          reason: '差异金额 1000.00 元',
          dispatched_by: 'user-1',
          dispatched_at: '2026-06-22T10:00:00Z',
        }],
        skipped: [],
      })

      const { buildDispatchList, executeDispatch } = createInstance([
        { _row_id: '1', confirm_index: 'IDX-001', amount: 10000, reply_amount: 9000, match_status: '不符', account_type: '应收账款' },
      ])

      const list = buildDispatchList()
      const result = await executeDispatch(list)
      expect(result.dispatched).toHaveLength(1)
      expect(result.skipped).toHaveLength(0)
      expect(mockBatchCreate).toHaveBeenCalledOnce()
    })

    it('API 返回 skipped 也标记到 Map', async () => {
      const { dispatchApi } = await import('@/services/dispatchApi')
      const mockBatchCreate = vi.mocked(dispatchApi.batchCreate)
      mockBatchCreate.mockResolvedValueOnce({
        dispatched: [],
        skipped: [{ confirm_index: 'IDX-001', target: 'D0-4', reason: 'duplicate' }],
      })

      const dispatchedMap = ref(new Map<string, Set<DispatchTarget>>())
      const rowsRef = ref<ConfirmationRow[]>([
        { _row_id: '1', confirm_index: 'IDX-001', amount: 10000, reply_amount: 9000, match_status: '不符', account_type: '应收账款' },
      ])
      const projectIdRef = ref('test-project-id')
      const instance = useConfirmationDispatch({ rows: rowsRef, dispatchedMap, projectId: projectIdRef })

      const list = instance.buildDispatchList()
      await instance.executeDispatch(list)

      // skipped 条目也应被标记到 Map
      expect(dispatchedMap.value.get('IDX-001')?.has('D0-4')).toBe(true)
    })
  })

  // ─── 双向等价 ──────────────────────────────────────────────────────────────

  describe('markDispatched() — 下游回标', () => {
    it('下游标记后主动分发会跳过', () => {
      const { markDispatched, pendingDiffRows } = createInstance([
        { _row_id: '1', confirm_index: 'IDX-001', amount: 10000, reply_amount: 9000, match_status: '不符', account_type: '应收账款' },
      ])

      // 模拟下游 D0-4 已经"带入"了 IDX-001
      markDispatched('IDX-001', 'D0-4')

      // 主动分发时该行已不在待分发列表
      expect(pendingDiffRows.value).toHaveLength(0)
    })

    it('isAlreadyDispatched 查询正确', () => {
      const { markDispatched, isAlreadyDispatched } = createInstance([])

      expect(isAlreadyDispatched('IDX-001', 'D0-4')).toBe(false)
      markDispatched('IDX-001', 'D0-4')
      expect(isAlreadyDispatched('IDX-001', 'D0-4')).toBe(true)
      expect(isAlreadyDispatched('IDX-001', 'D0-7')).toBe(false)
    })
  })
})
