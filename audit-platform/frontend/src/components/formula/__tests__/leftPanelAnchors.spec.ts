/**
 * leftPanelAnchors.spec.ts — Task 3.2 / ADR-FMC-05 左栏当前页 anchors 单测
 *
 * 验收判据（tasks.md Task 3.2）：
 *   - 左栏默认只返精确当前 sheet 的 addr_id（当前页 anchors，每行带同一 location identity）。
 *   - 缺 location identity 时返空集 + 告警（**非全局树**），fail-closed。
 *   - 「全局浏览」为独立态：decideLeftPanelMode 永不把缺身份兜底成 global-browse。
 *   - 变异反证：把缺 identity 回退改成全局树应打红；反向断言精确当前页时不误红。
 */
import { describe, it, expect, vi } from 'vitest'
import type { AcnrCellEntry } from '@/services/acnr/useAcnr'
import {
  hasCompleteLocationIdentity,
  decideLeftPanelMode,
  buildFailClosedWarning,
  buildCurrentSheetAnchorNodes,
  loadCurrentSheetLeftPanel,
  type LocationIdentity,
} from '../leftPanelAnchors'

const IDENTITY: LocationIdentity = {
  projectId: 'proj-1',
  wpId: 'wp-1',
  sheetUid: 'E1-1',
}

// 精确当前 sheet（E1-1）命名空间下的 anchors（GET /api/acnr/anchors?wp_code=E1&sheet=E1-1 返回形态）。
const E1_1_CELLS: AcnrCellEntry[] = [
  { addr_id: 'E1/E1-1/E6', parent_addr_id: 'E1/E1-1', domain: 'wp', cell_address: 'E6', semantic_label: '库存现金期末', formula_ref: "WP('E1','E1-1','E6')" },
  { addr_id: 'E1/E1-1/E7', parent_addr_id: 'E1/E1-1', domain: 'wp', cell_address: 'E7', semantic_label: '银行存款期末', formula_ref: "WP('E1','E1-1','E7')" },
]

describe('hasCompleteLocationIdentity — 三键齐备判定', () => {
  it('project_id + wp_id + sheet_uid 齐备 → true', () => {
    expect(hasCompleteLocationIdentity(IDENTITY)).toBe(true)
  })

  it('任一缺失/空白 → false', () => {
    expect(hasCompleteLocationIdentity(null)).toBe(false)
    expect(hasCompleteLocationIdentity(undefined)).toBe(false)
    expect(hasCompleteLocationIdentity({ projectId: '', wpId: 'wp-1', sheetUid: 'E1-1' })).toBe(false)
    expect(hasCompleteLocationIdentity({ projectId: 'p', wpId: '  ', sheetUid: 'E1-1' })).toBe(false)
    expect(hasCompleteLocationIdentity({ projectId: 'p', wpId: 'wp-1', sheetUid: '' })).toBe(false)
  })
})

describe('decideLeftPanelMode — 默认模式决策（全局浏览只能显式进入）', () => {
  it('identity 完整 → current-sheet（默认当前页 anchors）', () => {
    expect(decideLeftPanelMode(IDENTITY)).toBe('current-sheet')
  })

  it('identity 不完整 → fail-closed（不退全局树）', () => {
    expect(decideLeftPanelMode(null)).toBe('fail-closed')
    expect(decideLeftPanelMode({ projectId: 'p', wpId: '', sheetUid: 'E1-1' })).toBe('fail-closed')
  })

  // 🔴 变异反证的正向锚：缺身份绝不被静默兜底成 global-browse。
  it('缺身份时永不返回 global-browse（全局浏览须用户显式点按钮）', () => {
    expect(decideLeftPanelMode(null)).not.toBe('global-browse')
    expect(decideLeftPanelMode({})).not.toBe('global-browse')
  })
})

describe('buildFailClosedWarning — 缺身份显式告警', () => {
  it('列出缺失维度且明确「不回退全局」', () => {
    const w = buildFailClosedWarning({ projectId: 'p', wpId: '', sheetUid: '' })
    expect(w).toContain('底稿实例')
    expect(w).toContain('当前页')
    expect(w).toContain('不回退全局')
  })
})

describe('buildCurrentSheetAnchorNodes — 只构建精确当前 sheet 的 addr_id', () => {
  it('每个节点带 addr_id + 同一 location identity', () => {
    const nodes = buildCurrentSheetAnchorNodes(E1_1_CELLS, IDENTITY)
    expect(nodes).toHaveLength(2)
    expect(nodes.map((n) => n._addrId)).toEqual(['E1/E1-1/E6', 'E1/E1-1/E7'])
    // 左右栏对齐：每行挂同一 identity。
    for (const n of nodes) {
      expect(n._identity).toEqual(IDENTITY)
    }
    // addr_id 全属精确当前 sheet 命名空间（E1/E1-1/…）。
    for (const n of nodes) {
      expect(n._addrId.startsWith('E1/E1-1/')).toBe(true)
    }
  })

  it('过滤无 addr_id / deprecated / 重复条目', () => {
    const cells: AcnrCellEntry[] = [
      ...E1_1_CELLS,
      { addr_id: '', parent_addr_id: 'E1/E1-1', domain: 'wp', formula_ref: '' },
      { addr_id: 'E1/E1-1/E9', parent_addr_id: 'E1/E1-1', domain: 'wp', deprecated: true, formula_ref: '' },
      { addr_id: 'E1/E1-1/E6', parent_addr_id: 'E1/E1-1', domain: 'wp', formula_ref: '' }, // 重复
    ]
    const nodes = buildCurrentSheetAnchorNodes(cells, IDENTITY)
    expect(nodes.map((n) => n._addrId)).toEqual(['E1/E1-1/E6', 'E1/E1-1/E7'])
  })

  it('空/未定义 anchors → 空集', () => {
    expect(buildCurrentSheetAnchorNodes([], IDENTITY)).toEqual([])
    expect(buildCurrentSheetAnchorNodes(null, IDENTITY)).toEqual([])
    expect(buildCurrentSheetAnchorNodes(undefined, IDENTITY)).toEqual([])
  })
})

describe('loadCurrentSheetLeftPanel — 左栏默认加载唯一入口', () => {
  it('identity 完整 → current-sheet，只返精确当前 sheet 的 addr_id（反向断言：不误红）', async () => {
    const loader = vi.fn().mockResolvedValue(E1_1_CELLS)
    const res = await loadCurrentSheetLeftPanel(IDENTITY, loader)
    expect(res.mode).toBe('current-sheet')
    expect(res.warning).toBe('')
    expect(res.identity).toEqual(IDENTITY)
    expect(res.nodes.map((n) => n._addrId)).toEqual(['E1/E1-1/E6', 'E1/E1-1/E7'])
    // 每行 addr_id 全属精确当前 sheet（门禁断言④口径）。
    expect(res.nodes.every((n) => n._addrId.startsWith('E1/E1-1/'))).toBe(true)
    expect(loader).toHaveBeenCalledOnce()
  })

  it('缺 identity → fail-closed：空集 + 告警，且不发请求（不退全局树）', async () => {
    const loader = vi.fn().mockResolvedValue(E1_1_CELLS)
    const res = await loadCurrentSheetLeftPanel({ projectId: 'p', wpId: '', sheetUid: '' }, loader)
    expect(res.mode).toBe('fail-closed')
    expect(res.nodes).toEqual([])
    expect(res.warning).not.toBe('')
    expect(res.identity).toBeNull()
    // 🔴 fail-closed 不取当前页 anchors、更不取全局树。
    expect(loader).not.toHaveBeenCalled()
  })

  // ── 变异反证（tasks.md Task 3.2「把缺 identity 回退改成全局树应打红」）──
  // 模拟「缺身份回退全局树」的坏实现：若把 fail-closed 换成取全局集合（这里用一棵
  // 伪全局树代表 listSheets 五域树），下列断言会打红 —— 这正是本任务要防的回退。
  it('变异反证：缺 identity 若回退全局树（非空集），本断言打红', async () => {
    const GLOBAL_TREE_NODES = [
      { _addrId: 'TB/1001' },
      { _addrId: 'report/BS' },
      { _addrId: 'D2/D2-1/A1' }, // 别的 sheet 的地址，正是回退全局的病灶
    ]
    // 坏实现：缺身份时返回全局树而非空集。
    const badLoadWithGlobalFallback = (
      identity: Partial<LocationIdentity> | null,
    ): { mode: string; nodes: Array<{ _addrId: string }> } => {
      if (!hasCompleteLocationIdentity(identity)) {
        return { mode: 'global-browse', nodes: GLOBAL_TREE_NODES } // ← 被禁止的回退
      }
      return { mode: 'current-sheet', nodes: [] }
    }
    const bad = badLoadWithGlobalFallback(null)

    // 正确实现（loadCurrentSheetLeftPanel）对同一输入必须是 fail-closed + 空集：
    const good = await loadCurrentSheetLeftPanel(null, vi.fn().mockResolvedValue([]))
    expect(good.mode).toBe('fail-closed')
    expect(good.nodes).toEqual([])

    // 变异反证：坏实现与正确实现行为不同 —— 若把正确实现改成坏实现，这里会打红。
    expect(bad.mode).not.toBe(good.mode)
    expect(bad.nodes.length).toBeGreaterThan(0)
    expect(good.nodes.length).toBe(0)
    // 坏实现混入别 sheet 地址（D2/D2-1/…），正确实现绝不包含。
    expect(good.nodes.some((n) => n._addrId?.startsWith('D2/'))).toBe(false)
  })
})
