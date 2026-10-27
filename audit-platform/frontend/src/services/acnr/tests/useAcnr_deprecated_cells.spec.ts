/**
 * useAcnr 地址树不列停用 cell（spec acnr-foundation-defect-closure T10，design §3.3）
 *
 * /api/acnr/anchors 照常返回停用 cell（带 deprecated 标记，供已有引用定位）；
 * 地址树的 cell 子节点（loadCellNodes，公式选址 / 高级查询选字段共用）默认不列它们。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...args: unknown[]) => mockGet(...args) },
}))
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return { ...actual, onUnmounted: vi.fn() }
})

const SHEET = { addr_id: 'I6/I6-7', parent_wp_code: 'I6', sheet_code: 'I6-7' }
const CELLS = [
  { addr_id: 'I6/I6-7/B5', parent_addr_id: 'I6/I6-7', cell_address: 'B5', semantic_label: '有效格', formula_ref: "WP('I6','I6-7','B5')" },
  { addr_id: 'I6/I6-7/C9', parent_addr_id: 'I6/I6-7', cell_address: 'C9', semantic_label: '停用格', formula_ref: "WP('I6','I6-7','C9')", deprecated: true },
]

describe('useAcnr — 停用 cell 不进地址树', () => {
  beforeEach(() => {
    mockGet.mockReset()
    vi.resetModules()
  })

  it('loadCellNodes 只返回非停用 cell；listCells（anchors）仍含停用 cell', async () => {
    const { useAcnr } = await import('../useAcnr')
    mockGet.mockResolvedValue({ data: CELLS })
    const acnr = useAcnr()
    const nodes = await acnr.loadCellNodes(SHEET as never)
    expect(nodes.map((n) => n.addrId)).toEqual(['I6/I6-7/B5'])
    const cells = await acnr.listCells('I6', 'I6-7')
    expect(cells.map((c) => c.addr_id)).toEqual(['I6/I6-7/B5', 'I6/I6-7/C9'])
  })
})
