/**
 * 行内识别附件挂到本行（spec attachment-inline-preview ADR-AIP-03）
 *
 * - appendRowEvidence：识别表单带表页 / 单元格（表页级只带表页）；
 * - shiftIndexedRowEvidence：按序号挂附件的表删行后，被删行的附件转表页级、其后各行附件前移一位；
 * - 各识别 composable 的表单：K1（地址带底稿 id + 位置 + 读 ocr_text）、I2 runWorkpaperOcr、J1、F2 监盘；
 * - F1 逐笔凭证附件位置：表格 / 弹窗识别 / 弹窗 ⑤ 同一位置（散列槽位钉值，防口径漂移）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockDelete = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: (...a: any[]) => mockGet(...a),
    post: (...a: any[]) => mockPost(...a),
    delete: (...a: any[]) => mockDelete(...a),
  },
  downloadFile: vi.fn(),
}))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { projectId: 'p-route' } }) }))
vi.mock('element-plus', () => ({
  ElMessage: Object.assign(vi.fn(), { info: vi.fn(), success: vi.fn(), warning: vi.fn(), error: vi.fn() }),
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

import { appendRowEvidence, rowEvidenceCell, shiftIndexedRowEvidence } from '../rowEvidence'
import { resetWpEvidenceLinksForTest } from '@/composables/useWpEvidenceLinks'
import { useK1VoucherOcr, voucherEvidenceCell } from '@/components/workpaper/composables/useK1VoucherOcr'
import { runWorkpaperOcr } from '@/components/workpaper/composables/i2EnhancementHelpers'
import { useJ1VoucherOcr } from '@/composables/workpaper/j1/useJ1VoucherOcr'
import { useF2StocktakeOcr } from '@/components/workpaper/composables/useF2StocktakeOcr'
import { f1VoucherAttSlot, f1VoucherEvidence } from '@/components/workpaper/f1/f1VoucherEvidence'

function link(id: string, sheet: string, cell: string | null) {
  return {
    id, wp_id: 'w1', sheet_name: sheet, cell_ref: cell, attachment_id: `att-${id}`, page_ref: null,
    evidence_type: 'contract', check_conclusion: null, created_by: 'u1', created_at: null,
    attachment: { id: `att-${id}`, file_name: `${id}.pdf`, file_size: 1, file_type: 'pdf', attachment_type: null, ocr_status: null, created_at: null },
  }
}

const formOf = (call: any[]) => call[1] as FormData

describe('appendRowEvidence', () => {
  it('带表页与单元格；只给表页 = 表页级；表页为空不写', () => {
    const a = new FormData()
    appendRowEvidence(a, 'K3-6', rowEvidenceCell('rp-1'))
    expect([a.get('evidence_sheet'), a.get('evidence_cell')]).toEqual(['K3-6', 'row:rp-1'])
    const b = new FormData()
    appendRowEvidence(b, 'E1-10')
    expect([b.get('evidence_sheet'), b.has('evidence_cell')]).toEqual(['E1-10', false])
    const c = new FormData()
    appendRowEvidence(c, '', 'row:1')
    expect([...c.keys()]).toEqual([])
  })
})

describe('shiftIndexedRowEvidence（按序号挂附件的表删行）', () => {
  beforeEach(() => {
    resetWpEvidenceLinksForTest()
    mockGet.mockReset()
    mockPost.mockReset().mockResolvedValue({ data: {} })
    mockDelete.mockReset().mockResolvedValue({ data: {} })
  })

  it('删第 2 行：第 2 行附件转表页级，第 3、4 行前移；别的表页与非序号位置不动', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        items: [
          link('a', 'L1-6', 'row:1'), link('b', 'L1-6', 'row:2'), link('c', 'L1-6', 'row:3'),
          link('d', 'L1-6', 'row:4'), link('e', 'L3-6', 'row:3'), link('f', 'L1-6', 'row:x-1'), link('g', 'L1-6', null),
        ],
      },
    })
    const failed = await shiftIndexedRowEvidence('p1', 'w1', 'L1-6', 2)
    expect(failed).toBe(0)
    const created = mockPost.mock.calls.map((c) => [c[1].attachment_id, c[1].cell_ref])
    expect(created).toEqual([['att-b', null], ['att-c', 'row:2'], ['att-d', 'row:3']])
    expect(mockPost.mock.calls.every((c) => c[0] === '/api/projects/p1/workpapers/w1/evidence/link' && c[1].sheet_name === 'L1-6')).toBe(true)
    expect(mockDelete.mock.calls.map((c) => String(c[0]).split('/').pop())).toEqual(['b', 'c', 'd'])
  })

  it('单条失败不影响其余，返回失败条数；缺参数直接返回 0', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [link('b', 'L1-6', 'row:2'), link('c', 'L1-6', 'row:3')] } })
    mockPost.mockRejectedValueOnce(new Error('409'))
    expect(await shiftIndexedRowEvidence('p1', 'w1', 'L1-6', 2)).toBe(1)
    expect(mockDelete.mock.calls.map((c) => String(c[0]).split('/').pop())).toEqual(['c'])
    expect(await shiftIndexedRowEvidence('', 'w1', 'L1-6', 2)).toBe(0)
    expect(await shiftIndexedRowEvidence('p1', 'w1', 'L1-6', 0)).toBe(0)
  })
})

describe('识别 composable 的表单', () => {
  beforeEach(() => {
    resetWpEvidenceLinksForTest()
    mockPost.mockReset()
  })

  it('K1：地址带底稿 id，附件挂到本行，正文读 ocr_text', async () => {
    mockPost.mockResolvedValueOnce({ data: { data: { ocr_text: '回单原文', extracted_fields: {} } } })
    const { runOcr } = useK1VoucherOcr(() => 'w1', () => 'p1')
    const onConfirm = vi.fn()
    await runOcr(new File(['x'], 'a.pdf'), onConfirm, { sheet: 'K1-12', cell: voucherEvidenceCell('post', 'r9') })
    expect(mockPost.mock.calls[0][0]).toBe('/api/workpapers/w1/d4/contract-ocr')
    const fd = formOf(mockPost.mock.calls[0])
    expect([fd.get('evidence_sheet'), fd.get('evidence_cell')]).toEqual(['K1-12', 'row:post-r9'])
    expect(onConfirm).toHaveBeenCalledWith('回单原文', 'a.pdf')
  })

  it('I2 runWorkpaperOcr：透传表页 / 行槽位', async () => {
    mockPost.mockResolvedValueOnce({ data: { extracted_fields: { name: '张三' } } })
    const fields = await runWorkpaperOcr('w1', new File(['x'], 'b.png'), { projectId: 'p1', evidenceSheet: 'I2-10', evidenceCell: 'row:i210-1' })
    expect(fields).toEqual({ name: '张三' })
    const fd = formOf(mockPost.mock.calls[0])
    expect([fd.get('evidence_sheet'), fd.get('evidence_cell')]).toEqual(['I2-10', 'row:i210-1'])
  })

  it('J1：带位置时写进表单', async () => {
    mockPost.mockResolvedValueOnce({ data: { extracted_fields: {}, confidence: 0.9 } })
    const { uploadAndMerge } = useJ1VoucherOcr(ref('w1'), ref('p1'))
    await uploadAndMerge('r1', new File(['x'], 'c.pdf'), 'debit', vi.fn(), { sheet: 'J1-9', cell: 'row:r1' })
    const fd = formOf(mockPost.mock.calls[0])
    expect([fd.get('evidence_sheet'), fd.get('evidence_cell')]).toEqual(['J1-9', 'row:r1'])
  })

  it('F2 监盘：表页 = 调用方给的监盘表，单元格 = 本行', async () => {
    mockPost.mockResolvedValueOnce({ data: { extracted_fields: {}, confidence: 0.9 } })
    const { uploadAndMerge } = useF2StocktakeOcr(ref('w1'), ref('p1'))
    await uploadAndMerge('F2-25', 'st-1', new File(['x'], 'd.pdf'), vi.fn())
    const fd = formOf(mockPost.mock.calls[0])
    expect([fd.get('evidence_sheet'), fd.get('evidence_cell')]).toEqual(['F2-25', 'row:st-1'])
  })
})

describe('F1 逐笔凭证附件位置', () => {
  it('散列槽位钉值（与弹窗 ⑤ 本笔附件既有口径一致）且只随行 id 变', () => {
    expect(f1VoucherAttSlot('r1')).toBe(3683)
    expect(f1VoucherAttSlot('f1-debit-abc123')).toBe(1607)
    expect(f1VoucherAttSlot('')).toBe(f1VoucherAttSlot('0'))
    expect(f1VoucherEvidence('credit', 'r1')).toEqual({ sheet: 'F1-7-credit', cell: 'item:3683' })
  })
})
