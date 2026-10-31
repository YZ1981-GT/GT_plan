/**
 * cellTrace.spec.ts — 单元格溯源测试（任务 11.3 + 12.3）
 *
 * Spec:   .kiro/specs/global-refinement-v5-closure/ Tasks 11.3, 12.3
 *
 * Property 1: 溯源请求载荷完整性（fast-check）
 * 单测: 空来源提示 / 有来源展示 / GET 失败处理 / 点来源节点打开底稿编辑器（调用生产 useReportTrace）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { computed, ref } from 'vue'
import * as fc from 'fast-check'

const { pushMock, resolveMock } = vi.hoisted(() => ({ pushMock: vi.fn(), resolveMock: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: pushMock }) }))
vi.mock('@/services/resolveWorkpaperByCode', () => ({ resolveWorkpaperByCode: resolveMock }))
const WP_E1 = '8c8cd491-2d21-48ce-9622-e2d9bca0d499'

// ─── Mock apiProxy ───────────────────────────────────────────────────────────
const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))

// ─── Mock eventBus ───────────────────────────────────────────────────────────
const mockEmit = vi.fn()
vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: (...args: any[]) => mockEmit(...args), on: vi.fn(), off: vi.fn() },
}))

// ─── Mock errorHandler ───────────────────────────────────────────────────────
const mockHandleApiError = vi.fn()
vi.mock('@/utils/errorHandler', () => ({
  handleApiError: (...args: any[]) => mockHandleApiError(...args),
}))

// ─── Mock ElMessage ──────────────────────────────────────────────────────────
const mockInfo = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { info: (...args: any[]) => mockInfo(...args), warning: vi.fn(), success: vi.fn(), error: vi.fn() },
  ElDialog: { name: 'ElDialog', template: '<div><slot/></div>' },
  ElButton: { name: 'ElButton', template: '<button><slot/></button>' },
  ElEmpty: { name: 'ElEmpty', template: '<div class="el-empty"/>' },
}))

import { useReportTrace } from '../composables/useReportTrace'

// ── Helper: 构造 lineage 请求参数（模拟组件内部逻辑）──
function buildLineageParams(ctx: { objectType: string; objectId: string; cellRef?: string }) {
  const params: Record<string, string> = {
    object_type: ctx.objectType,
    object_id: ctx.objectId,
    direction: 'both',
  }
  if (ctx.cellRef) {
    params.cell_ref = ctx.cellRef
  }
  return params
}

// ── Helper: 模拟 openTrace 调用逻辑 ──
async function openTrace(projectId: string, ctx: { objectType: string; objectId: string; cellRef?: string }) {
  const params = buildLineageParams(ctx)
  const qs = new URLSearchParams(params).toString()
  try {
    const data = await mockGet(`/api/projects/${projectId}/lineage?${qs}`)
    if (!data.upstream?.length && !data.downstream?.length) {
      mockInfo('该数字暂无溯源信息')
      return { empty: true, data }
    }
    return { empty: false, data }
  } catch (e) {
    mockHandleApiError(e, '数字溯源')
    return { error: true }
  }
}

// Feature: global-refinement-v5-closure, Property 1
describe('Property 1: 溯源请求载荷完整性', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('随机 object_type + object_id + 可选 cellRef → 请求 params 完整', () => {
    const objectTypes = fc.constantFrom('tb_row', 'report_row', 'note_cell', 'wp_cell', 'adjustment')
    const objectIds = fc.string({ minLength: 1, maxLength: 20 })
    const optionalCellRef = fc.option(fc.string({ minLength: 1, maxLength: 10 }), { nil: undefined })

    fc.assert(
      fc.property(objectTypes, objectIds, optionalCellRef, (objectType, objectId, cellRef) => {
        const params = buildLineageParams({ objectType, objectId, cellRef })

        // 必须包含 object_type + object_id + direction='both'
        expect(params.object_type).toBe(objectType)
        expect(params.object_id).toBe(objectId)
        expect(params.direction).toBe('both')

        // cellRef 存在时也传
        if (cellRef) {
          expect(params.cell_ref).toBe(cellRef)
        } else {
          expect(params.cell_ref).toBeUndefined()
        }
      }),
      { numRuns: 5 },
    )
  })
})

// Task 12.3: 溯源接线单测
describe('溯源接线单测 — Task 12.3', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('空来源 → ElMessage.info("该数字暂无溯源信息")', async () => {
    mockGet.mockResolvedValue({ upstream: [], downstream: [] })

    const result = await openTrace('proj-001', { objectType: 'tb_row', objectId: '1001' })

    expect(result.empty).toBe(true)
    expect(mockInfo).toHaveBeenCalledWith('该数字暂无溯源信息')
  })

  it('有来源 → 返回 upstream/downstream 数据', async () => {
    mockGet.mockResolvedValue({
      upstream: [{ id: 'u1', type: 'tb_row', label: '应收账款' }],
      downstream: [{ id: 'd1', type: 'ledger', label: '凭证#001' }],
    })

    const result = await openTrace('proj-001', { objectType: 'report_row', objectId: 'BS-001' })

    expect(result.empty).toBe(false)
    expect(result.data.upstream.length).toBe(1)
    expect(result.data.downstream.length).toBe(1)
  })

  it('GET 失败 → handleApiError 被调用', async () => {
    const err = new Error('Network Error')
    mockGet.mockRejectedValue(err)

    const result = await openTrace('proj-001', { objectType: 'wp_cell', objectId: 'D1!B5' })

    expect(result.error).toBe(true)
    expect(mockHandleApiError).toHaveBeenCalledWith(err, '数字溯源')
  })

  // 原用例在测试里自己发事件再断言发了（不经生产代码），且记的是错误行为：溯源弹窗所在页面没有渲染器，
  // `workpaper:locate-cell` 事件无人接收、还把编码当 wpId。改为调用生产的 useReportTrace（spec wp-deeplink-locate-coverage-closure 需求 3）。
  it('点击来源节点 → 关闭弹窗，按编码打开该底稿编辑器并带 ?sheet=&cell=，不再发定位事件', async () => {
    resolveMock.mockResolvedValueOnce({ wpId: WP_E1 })
    const trace = useReportTrace({
      projectId: computed(() => 'proj-001'),
      year: computed(() => 2025),
      activeTab: ref('balance_sheet'),
      activeTabLabel: computed(() => '资产负债表'),
      consistencyResult: ref(null),
      fetchReport: vi.fn(),
      rvCtx: { closeContextMenu: vi.fn(), contextMenu: { rowData: null } } as any,
    })
    trace.rvTraceDialogVisible.value = true

    await trace.onRvTraceLocate({ wp_code: 'E1', sheet_name: '分析程序E1-14', cell_ref: 'C34' })

    expect(trace.rvTraceDialogVisible.value).toBe(false)
    expect(resolveMock).toHaveBeenCalledWith('proj-001', 'E1', true)
    expect(pushMock).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: 'proj-001', wpId: WP_E1 },
      query: { sheet: '分析程序E1-14', cell: 'C34' },
    })
    expect(mockEmit).not.toHaveBeenCalledWith('workpaper:locate-cell', expect.anything())
  })
})
