/**
 * GtRowNameAlignmentDialog.spec.ts — Task 9 / 12 守卫
 *
 * 覆盖：
 *  - eventBus 打开弹窗，两栏渲染，状态标签
 *  - 多对一检测（同一候选被多行选中 → multiToOneRows 非空）
 *  - 确认调 /row-name-mapping/confirm 端点，携带 base_mapping_version（版本冲突基础）
 *  - 取消零写入（关闭不发 http.post）
 *  - DEC-4 隔离：全局刷新弹窗源码不引用本行级弹窗 / open-row-name-alignment
 *
 * spec: formula-row-name-alignment-confirmation
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount, flushPromises } from '@vue/test-utils'

if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

const { mockPost, mockMsgSuccess, mockMsgError, mockConfirm } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockMsgSuccess: vi.fn(),
  mockMsgError: vi.fn(),
  mockConfirm: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: { post: mockPost } }))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: { success: mockMsgSuccess, error: mockMsgError, warning: vi.fn(), info: vi.fn() },
    ElMessageBox: { confirm: mockConfirm },
  }
})

import ElementPlus from 'element-plus'
import GtRowNameAlignmentDialog from '../GtRowNameAlignmentDialog.vue'
import { eventBus } from '@/utils/eventBus'

function target(name: string, code = '1221', auxType = '客户', ds = 'ds-active') {
  const dim = `${code}|${auxType}|${name}`
  return {
    source_kind: 'aux_name',
    account_code: code,
    aux_type: auxType,
    aux_name: name,
    dimension_key: dim,
    dataset_id: ds,
  }
}

function candidate(name: string, sim = 0.9, amount = '100.00', code = '1221') {
  return {
    target_identity: target(name, code),
    display_name: name,
    amount,
    similarity: sim,
    source_kind: 'aux_name',
  }
}

function openPayload(rows: any[]) {
  return {
    wpId: 'wp-1',
    projectId: 'p-1',
    year: 2025,
    wpCode: 'K1-1',
    sheetCode: 'K1-1',
    datasetId: 'ds-active',
    rows,
  }
}

beforeEach(() => {
  mockPost.mockReset()
  mockMsgSuccess.mockReset()
  mockMsgError.mockReset()
  mockConfirm.mockReset()
})

function mountDialog() {
  return mount(GtRowNameAlignmentDialog, {
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
}

describe('GtRowNameAlignmentDialog', () => {
  it('eventBus 打开弹窗并渲染待确认行', async () => {
    const w = mountDialog()
    eventBus.emit('open-row-name-alignment', openPayload([
      {
        row_key: 'r1', row_label: '预收销售款', match_state: 'unmatched',
        candidates: [candidate('预收甲客户')], target_identity: [],
        amount: null, similarity: null, source_kind: null,
        confirmed_by: null, confirmed_at: null, mapping_version: null, stale_reason: null,
      },
    ]))
    await flushPromises()
    expect((w.vm as any).visible).toBe(true)
    expect((w.vm as any).rows.length).toBe(1)
    w.unmount()
  })

  it('多对一：同一候选被两行选中 → multiToOneRows 非空', async () => {
    const w = mountDialog()
    const shared = candidate('共享单位')
    eventBus.emit('open-row-name-alignment', openPayload([
      {
        row_key: 'r1', row_label: '行一', match_state: 'unmatched',
        candidates: [shared], target_identity: [], amount: null, similarity: null,
        source_kind: null, confirmed_by: null, confirmed_at: null,
        mapping_version: null, stale_reason: null,
      },
      {
        row_key: 'r2', row_label: '行二', match_state: 'unmatched',
        candidates: [shared], target_identity: [], amount: null, similarity: null,
        source_kind: null, confirmed_by: null, confirmed_at: null,
        mapping_version: null, stale_reason: null,
      },
    ]))
    await flushPromises()
    const vm = w.vm as any
    // 两行各选同一 dimension_key
    vm.toggleSelection('r1', shared, true)
    vm.toggleSelection('r2', shared, true)
    await flushPromises()
    expect(vm.multiToOneRows.length).toBe(2)
    w.unmount()
  })

  it('确认：调 confirm 端点，rows 带 base_mapping_version', async () => {
    mockPost.mockResolvedValue({ data: { data: {} } })
    const w = mountDialog()
    const cand = candidate('预收甲客户')
    eventBus.emit('open-row-name-alignment', openPayload([
      {
        row_key: 'r1', row_label: '预收销售款', match_state: 'unmatched',
        candidates: [cand], target_identity: [], amount: null, similarity: null,
        source_kind: null, confirmed_by: null, confirmed_at: null,
        mapping_version: 2, stale_reason: null,
      },
    ]))
    await flushPromises()
    const vm = w.vm as any
    vm.toggleSelection('r1', cand, true)
    await flushPromises()
    await vm.onConfirm()
    await flushPromises()
    expect(mockPost).toHaveBeenCalled()
    const [url, body] = mockPost.mock.calls[0]
    expect(url).toBe('/api/workpapers/wp-1/row-name-mapping/confirm')
    expect(body.rows[0].base_mapping_version).toBe(2)
    expect(body.rows[0].targets[0].dimension_key).toBe(cand.target_identity.dimension_key)
    w.unmount()
  })

  it('取消零写入：关闭弹窗不发 confirm 请求', async () => {
    const w = mountDialog()
    eventBus.emit('open-row-name-alignment', openPayload([
      {
        row_key: 'r1', row_label: '预收销售款', match_state: 'unmatched',
        candidates: [candidate('预收甲客户')], target_identity: [], amount: null,
        similarity: null, source_kind: null, confirmed_by: null, confirmed_at: null,
        mapping_version: null, stale_reason: null,
      },
    ]))
    await flushPromises()
    const vm = w.vm as any
    vm.visible = false
    await flushPromises()
    expect(mockPost).not.toHaveBeenCalled()
    w.unmount()
  })
})

describe('复盘 #1：eventBus 监听器生命周期', () => {
  it('unmount 后事件不再打开已卸载实例（无泄漏）', async () => {
    const w = mountDialog()
    w.unmount()
    // 卸载后再触发事件：不应抛错，也不应让已卸载实例复活
    eventBus.emit('open-row-name-alignment', openPayload([
      {
        row_key: 'r1', row_label: '行', match_state: 'unmatched',
        candidates: [], target_identity: [], amount: null, similarity: null,
        source_kind: null, confirmed_by: null, confirmed_at: null,
        mapping_version: null, stale_reason: null,
      },
    ]))
    await flushPromises()
    // 挂新实例，事件只驱动它一个
    const w2 = mountDialog()
    eventBus.emit('open-row-name-alignment', openPayload([
      {
        row_key: 'r2', row_label: '行2', match_state: 'unmatched',
        candidates: [], target_identity: [], amount: null, similarity: null,
        source_kind: null, confirmed_by: null, confirmed_at: null,
        mapping_version: null, stale_reason: null,
      },
    ]))
    await flushPromises()
    expect((w2.vm as any).rows.map((r: any) => r.row_key)).toEqual(['r2'])
    w2.unmount()
  })
})

describe('复盘 #4：D3 样板底稿真实接线 getRowNameAlignmentRows', () => {
  const detailSrc = readFileSync(
    resolve(__dirname, '../../workpaper/d3/D3TabDetail.vue'),
    'utf-8',
  )
  const bundleSrc = readFileSync(
    resolve(__dirname, '../../workpaper/GtD3PrepaidAccounts.vue'),
    'utf-8',
  )

  it('D3TabDetail 暴露 getRowNameAlignmentRows 且 expose', () => {
    expect(detailSrc).toContain('function getRowNameAlignmentRows()')
    expect(detailSrc).toMatch(/defineExpose\(\{[^}]*getRowNameAlignmentRows/s)
    // 行名用客户名、account_prefixes 留空由后端解析（不在前端写死科目码）
    expect(detailSrc).toContain('row_label: String(r.customerName)')
    expect(detailSrc).toContain('account_prefixes: [] as string[]')
  })

  it('顶层 bundle 持 detailRef 并转发（activeComponentRef 才拿得到）', () => {
    expect(bundleSrc).toContain("ref=\"detailRef\"")
    expect(bundleSrc).toContain('function getRowNameAlignmentRows()')
    expect(bundleSrc).toContain('detailRef.value.getRowNameAlignmentRows()')
    expect(bundleSrc).toMatch(/defineExpose\(\{[^}]*getRowNameAlignmentRows/s)
  })
})

describe('DEC-4 隔离：全局刷新弹窗不承载行级对齐弹窗', () => {
  const globalDialogSrc = readFileSync(
    resolve(__dirname, '../GtRefreshScopeDialog.vue'),
    'utf-8',
  )

  it('GtRefreshScopeDialog 源码不引用 GtRowNameAlignmentDialog', () => {
    expect(globalDialogSrc).not.toContain('GtRowNameAlignmentDialog')
  })

  it('GtRefreshScopeDialog 不 emit open-row-name-alignment（不误挂第二触发点）', () => {
    expect(globalDialogSrc).not.toContain("emit('open-row-name-alignment'")
    expect(globalDialogSrc).not.toContain('open-row-name-alignment')
  })
})
